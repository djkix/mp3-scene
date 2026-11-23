import time

from app import db, security
from app.main import create_app
from fastapi.testclient import TestClient


def _with_token(app, token):
    return TestClient(app, base_url="https://testserver", cookies={"session": token})


def _login(client, username, password, **kw):
    return client.post("/api/login", json={"username": username, "password": password}, **kw)


def test_login_sets_secure_cookie_and_me(client):
    r = _login(client, "admin", "adminpass")
    assert r.status_code == 200 and r.json() == {"username": "admin", "role": "admin"}
    c = r.headers["set-cookie"].lower()
    assert "httponly" in c and "secure" in c and "samesite=lax" in c and "path=/" in c
    assert f"max-age={30 * 86400}" in c
    assert client.get("/api/me").json() == {"username": "admin", "role": "admin"}


def test_everything_requires_session(client):                               # critère 8
    for url in ["/api/me", "/api/releases", "/api/filters", "/api/folders", "/api/releases/1", "/api/releases/1/nfo",
                "/api/tracks/1/stream", "/api/releases/1/zip", "/api/favorites/tracks", "/api/admin/users",
                "/api/admin/scan", "/api/nimporte/quoi"]:
        assert client.get(url).status_code == 401, url
    assert client.post("/api/logout").status_code == 401
    assert client.get("/api/health").status_code == 200
    for url in ["/docs", "/redoc", "/openapi.json"]:
        assert client.get(url).status_code == 404, url


def test_invalid_or_expired_cookie_rejected(app, settings):
    assert _with_token(app, "faux").get("/api/me").status_code == 401
    conn = db.connect(settings.data_dir)
    uid = conn.execute("SELECT id FROM users WHERE username='admin'").fetchone()[0]
    token = security.create_session(conn, uid, time.time() - 31 * 86400)
    conn.close()
    assert _with_token(app, token).get("/api/me").status_code == 401


def test_version_admin_only(admin_client, user_client, monkeypatch):
    assert admin_client.get("/api/admin/version").json() == {"version": "dev"}
    monkeypatch.setenv("APP_VERSION", "1.2.3")
    assert admin_client.get("/api/admin/version").json() == {"version": "1.2.3"}
    assert user_client.get("/api/admin/version").status_code == 403


def test_csrf_header_required(admin_client):
    assert admin_client.post("/api/logout", headers={"X-CSRF": ""}).status_code == 403
    assert admin_client.get("/api/me").status_code == 200


def test_login_requires_csrf(client):
    assert _login(client, "admin", "adminpass", headers={"X-CSRF": ""}).status_code == 403


def test_logout_drops_session(admin_client):
    r = admin_client.post("/api/logout")
    assert r.status_code == 204 and "session=" in r.headers["set-cookie"]
    assert admin_client.get("/api/me").status_code == 401


def test_login_issues_fresh_token(app, client):
    t1 = _login(client, "admin", "adminpass").cookies["session"]
    t2 = _login(client, "admin", "adminpass").cookies["session"]
    assert t1 != t2
    assert _with_token(app, t1).get("/api/me").status_code == 401   # l'ancienne session est supprimée
    assert _with_token(app, t2).get("/api/me").status_code == 200


def test_login_does_not_reveal_username(client):
    a = _login(client, "admin", "mauvais")
    b = _login(client, "inconnu", "mauvais")
    assert a.status_code == b.status_code == 401 and a.json() == b.json()


def test_bruteforce_lockout(client):
    for _ in range(5):
        assert _login(client, "admin", "bad").status_code == 401
    assert _login(client, "admin", "adminpass").status_code == 429


def test_bruteforce_ip_is_last_xff_entry(client):
    # le proxy de confiance ajoute l'adresse réelle en dernier ; la première entrée est choisie par le client
    for i in range(5):
        h = {"X-Forwarded-For": f"10.9.9.{i}, 203.0.113.7", "X-CSRF": "1"}
        assert _login(client, f"inconnu{i}", "bad", headers=h).status_code == 401
    h = {"X-Forwarded-For": "10.9.9.99, 203.0.113.7", "X-CSRF": "1"}
    assert _login(client, "admin", "adminpass", headers=h).status_code == 429
    assert _login(client, "admin", "adminpass").status_code == 200   # autre IP, compte non bloqué


def test_forged_xff_cannot_lock_out_another_ip(client):
    for i in range(5):
        h = {"X-Forwarded-For": f"198.51.100.1, 203.0.113.{i}", "X-CSRF": "1"}
        assert _login(client, f"inconnu{i}", "bad", headers=h).status_code == 401
    h = {"X-Forwarded-For": "198.51.100.1", "X-CSRF": "1"}
    assert _login(client, "admin", "adminpass", headers=h).status_code == 200


def test_login_limiter():
    lim = security.LoginLimiter()
    assert [lim.attempt(("k",), 1000.0 + i) for i in range(7)] == [True] * 5 + [False] * 2
    assert lim.blocked("k", 1004.0 + 899)
    assert not lim.blocked("k", 1004.0 + 901)            # un essai bloqué ne prolonge pas le blocage
    assert lim.attempt(("k",), 1004.0 + 901)
    # des essais espacés de plus de 15 min ne s'additionnent pas
    assert all(lim.attempt(("lent",), 5000.0 + i * 1000) for i in range(10))
    # une clé bloquée refuse l'essai sans le compter pour l'autre clé
    for _ in range(5):
        lim.attempt(("ip",), 0.0)
    assert not lim.attempt(("u", "ip"), 1.0)
    assert "u" not in lim._tries
    lim.reset("ip")
    assert lim.attempt(("u", "ip"), 2.0)
    # les entrées périmées sont purgées
    lim.attempt(("autre",), 1_000_000.0)
    assert set(lim._tries) | set(lim._until) == {"autre"}


def test_login_limiter_concurrent():
    import threading
    lim, barrier, results = security.LoginLimiter(), threading.Barrier(20), []

    def go():
        barrier.wait()
        results.append(lim.attempt(("u:x", "ip:y"), 1000.0))
    threads = [threading.Thread(target=go) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results.count(True) == 5


def test_success_resets_username_not_ip(client):
    xff = {"X-Forwarded-For": "198.51.100.9", "X-CSRF": "1"}
    for _ in range(4):
        assert _login(client, "admin", "bad", headers=xff).status_code == 401
    assert _login(client, "admin", "adminpass", headers=xff).status_code == 200   # non compté pour l'IP
    assert _login(client, "admin", "bad", headers=xff).status_code == 401         # 5e échec de l'IP
    assert _login(client, "admin", "adminpass", headers=xff).status_code == 429
    assert _login(client, "admin", "adminpass").status_code == 200                # clé identifiant remise à zéro


def test_successful_logins_do_not_consume_ip_budget(client):
    for _ in range(10):
        assert _login(client, "admin", "adminpass").status_code == 200


def test_limiter_forgive():
    lim = security.LoginLimiter()
    for i in range(4):
        assert lim.attempt(("ip",), float(i))
    assert lim.attempt(("ip",), 4.0) and lim.blocked("ip", 4.0)
    lim.forgive("ip")                                   # le 5e essai a réussi : blocage levé, 4 échecs restent
    assert not lim.blocked("ip", 4.0)
    assert lim.attempt(("ip",), 5.0) and not lim.attempt(("ip",), 6.0)


def test_password_hashing_works():
    h = security.hash_password("motdepasse")
    assert security.verify_password(h, "motdepasse") and not security.verify_password(h, "autre")
    assert not security.verify_password("pas-un-hash", "motdepasse")


def test_bootstrap_rejects_invalid_admin(settings):
    settings.music_root.mkdir()
    settings.admin_user, settings.admin_password = "admin", "court"
    import pytest
    with pytest.raises(RuntimeError) as e:
        with TestClient(create_app(settings)):
            pass
    assert "ADMIN_PASSWORD" in str(e.value) and "court" not in str(e.value)
    settings.admin_user, settings.admin_password = " ", "assezlong"
    with pytest.raises(RuntimeError, match="ADMIN_USER"):
        with TestClient(create_app(settings)):
            pass


def test_cookie_refreshed_only_when_extended(app, admin_client, settings):
    r = admin_client.get("/api/me")
    assert r.status_code == 200 and "set-cookie" not in r.headers
    conn = db.connect(settings.data_dir)
    conn.execute("UPDATE sessions SET expires_at = ?", (time.time() + 10 * 86400,))
    conn.commit()
    r = admin_client.get("/api/me")
    assert "max-age=2592000" in r.headers["set-cookie"].lower()
    # session prolongée puis invalidée par le traitement : le jeton mort n'est pas renvoyé
    uid = _uid(admin_client, "admin")
    conn.execute("UPDATE sessions SET expires_at = ?", (time.time() + 10 * 86400,))
    conn.commit()
    conn.close()
    r = admin_client.patch(f"/api/admin/users/{uid}", json={"password": "nouveaumdp"})
    assert r.status_code == 204 and "set-cookie" not in r.headers


def test_session_sliding_expiry(conn):
    conn.execute("INSERT INTO users(username,password_hash,role) VALUES('u','x','user')")
    token = security.create_session(conn, 1, 0.0)
    h = conn.execute("SELECT token_hash, expires_at FROM sessions").fetchone()
    assert h["token_hash"] != token and h["expires_at"] == 30 * 86400
    u = security.session_user(conn, token, 3600.0)
    assert u["username"] == "u" and not u["renewed"]
    assert conn.execute("SELECT expires_at FROM sessions").fetchone()[0] == 30 * 86400   # moins d'un jour : inchangé
    assert security.session_user(conn, token, 2 * 86400.0)["renewed"]
    assert conn.execute("SELECT expires_at FROM sessions").fetchone()[0] == 32 * 86400
    assert security.session_user(conn, token, 63 * 86400.0) is None
    assert security.session_user(conn, "inconnu", 0.0) is None


def test_admin_bootstrap_only_when_empty(app, settings):
    settings.admin_password = "autremotdepasse"
    with TestClient(create_app(settings), base_url="https://testserver", headers={"X-CSRF": "1"}) as c:
        assert _login(c, "admin", "adminpass").status_code == 200
        assert _login(c, "admin", "autremotdepasse").status_code == 401
    conn = db.connect(settings.data_dir)
    assert conn.execute("SELECT count(*) FROM users").fetchone()[0] == 1
    conn.close()


def test_no_bootstrap_without_credentials(settings):
    settings.music_root.mkdir()
    settings.admin_user = "admin"
    with TestClient(create_app(settings)):
        pass
    conn = db.connect(settings.data_dir)
    assert conn.execute("SELECT count(*) FROM users").fetchone()[0] == 0
    conn.close()


def test_user_cannot_reach_admin(user_client):
    assert user_client.get("/api/me").json() == {"username": "user", "role": "user"}
    assert user_client.get("/api/admin/users").status_code == 403
    assert user_client.get("/api/admin/scan").status_code == 403
    assert user_client.post("/api/admin/scan").status_code == 403
    assert user_client.post("/api/admin/users", json={"username": "x", "password": "12345678", "role": "admin"}).status_code == 403
    assert user_client.patch("/api/admin/users/2", json={"role": "admin"}).status_code == 403
    assert user_client.delete("/api/admin/users/1").status_code == 403


def _uid(admin_client, username):
    return next(u["id"] for u in admin_client.get("/api/admin/users").json() if u["username"] == username)


def test_last_admin_protected(admin_client):
    uid = _uid(admin_client, "admin")
    assert admin_client.delete(f"/api/admin/users/{uid}").status_code == 409
    assert admin_client.patch(f"/api/admin/users/{uid}", json={"role": "user"}).status_code == 409
    assert admin_client.get("/api/me").json() == {"username": "admin", "role": "admin"}


def test_admin_can_demote_self_when_other_admin(admin_client):
    assert admin_client.post("/api/admin/users", json={"username": "admin2", "password": "12345678", "role": "admin"}).status_code == 201
    uid = _uid(admin_client, "admin")
    assert admin_client.patch(f"/api/admin/users/{uid}", json={"role": "user"}).status_code == 204
    assert admin_client.get("/api/admin/users").status_code == 403


def test_password_reset_drops_sessions(admin_client, user_client):
    uid = _uid(admin_client, "user")
    assert admin_client.patch(f"/api/admin/users/{uid}", json={"password": "court"}).status_code == 400
    assert user_client.get("/api/me").status_code == 200
    assert admin_client.patch(f"/api/admin/users/{uid}", json={"password": "nouveaumdp"}).status_code == 204
    assert user_client.get("/api/me").status_code == 401
    assert _login(user_client, "user", "nouveaumdp").status_code == 200


def test_change_own_password(app, user_client):
    other = TestClient(app, base_url="https://testserver", headers={"X-CSRF": "1"})
    assert _login(other, "user", "userpass1").status_code == 200
    assert user_client.post("/api/me/password", json={"current": "faux", "new": "nouveaumdp"}).status_code == 400
    assert user_client.post("/api/me/password", json={"current": "userpass1", "new": "court"}).status_code == 400
    assert user_client.post("/api/me/password", json={"current": "userpass1", "new": "nouveaumdp"}).status_code == 204
    assert user_client.get("/api/me").status_code == 200          # la session courante reste valide
    assert other.get("/api/me").status_code == 401                # les autres sont invalidées
    assert _login(other, "user", "nouveaumdp").status_code == 200


def test_user_crud(admin_client, settings):
    r = admin_client.post("/api/admin/users", json={"username": "  bob ", "password": "12345678", "role": "user"})
    assert r.status_code == 201 and r.json()["username"] == "bob"
    assert admin_client.post("/api/admin/users", json={"username": "bob", "password": "12345678", "role": "user"}).status_code == 409
    assert admin_client.post("/api/admin/users", json={"username": "Bob", "password": "12345678", "role": "user"}).status_code == 201
    assert admin_client.post("/api/admin/users", json={"username": "carl", "password": "1234567", "role": "user"}).status_code == 400
    assert admin_client.post("/api/admin/users", json={"username": "   ", "password": "12345678", "role": "user"}).status_code == 400
    assert admin_client.post("/api/admin/users", json={"username": "x" * 65, "password": "12345678", "role": "user"}).status_code == 400
    assert admin_client.post("/api/admin/users", json={"username": "z", "password": "12345678", "role": "root"}).status_code == 422
    users = admin_client.get("/api/admin/users").json()
    assert {u["username"] for u in users} == {"admin", "bob", "Bob"} and all(set(u) == {"id", "username", "role"} for u in users)

    uid = _uid(admin_client, "bob")
    bob = TestClient(admin_client.app, base_url="https://testserver", headers={"X-CSRF": "1"})
    assert _login(bob, "bob", "12345678").status_code == 200
    conn = db.connect(settings.data_dir)
    conn.execute("INSERT INTO favorites(user_id,kind,item_id,created_at) VALUES(?,'release',1,0)", (uid,))
    conn.commit()
    assert admin_client.delete(f"/api/admin/users/{uid}").status_code == 204
    assert admin_client.delete(f"/api/admin/users/{uid}").status_code == 404
    assert admin_client.patch(f"/api/admin/users/{uid}", json={"role": "admin"}).status_code == 404
    assert conn.execute("SELECT count(*) FROM sessions WHERE user_id=?", (uid,)).fetchone()[0] == 0
    assert conn.execute("SELECT count(*) FROM favorites WHERE user_id=?", (uid,)).fetchone()[0] == 0
    conn.close()
    assert bob.get("/api/me").status_code == 401


def test_scan_endpoints(app, admin_client):
    r = admin_client.post("/api/admin/scan")
    assert r.status_code == 202 and r.json() == {"started": True}
    app.state.runner.stop()
    s = admin_client.get("/api/admin/scan").json()
    assert {"status", "releases_found", "tracks_pending"} <= set(s)
    app.state.runner.start = lambda: False
    r = admin_client.post("/api/admin/scan")
    assert r.status_code == 409 and r.json()["detail"]


def test_bruteforce_ip_xff_on_two_header_lines(client):
    # le proxy ajoute une seconde ligne X-Forwarded-For : seule sa valeur (la dernière) compte
    for i in range(5):
        h = [("X-Forwarded-For", f"10.9.9.{i}"), ("X-Forwarded-For", "203.0.113.7"), ("X-CSRF", "1")]
        assert _login(client, f"inconnu{i}", "bad", headers=h).status_code == 401
    h = [("X-Forwarded-For", "10.9.9.99"), ("X-Forwarded-For", "203.0.113.7"), ("X-CSRF", "1")]
    assert _login(client, "admin", "adminpass", headers=h).status_code == 429
    assert _login(client, "admin", "adminpass").status_code == 200


def test_password_hashed_outside_write_transaction(admin_client, settings, monkeypatch):
    import sqlite3
    other = sqlite3.connect(settings.data_dir / "mp3scene.db", timeout=0, check_same_thread=False)
    real, errors = security.hash_password, []

    def hashing(pw):
        try:
            other.execute("UPDATE scan_state SET error='x' WHERE id=1"); other.commit()
        except sqlite3.OperationalError as e:
            errors.append(e)
        return real(pw)
    monkeypatch.setattr(security, "hash_password", hashing)
    assert admin_client.post("/api/admin/users", json={"username": "bob", "password": "12345678", "role": "admin"}).status_code == 201
    assert admin_client.patch(f"/api/admin/users/{_uid(admin_client, 'bob')}",
                              json={"role": "user", "password": "87654321"}).status_code == 204
    assert admin_client.post("/api/me/password", json={"current": "adminpass", "new": "nouveaumdp"}).status_code == 204
    other.close()
    assert errors == []


def test_failures_from_one_address_do_not_lock_the_account_elsewhere(client):
    h = {"X-Forwarded-For": "198.51.100.20", "X-CSRF": "1"}
    for _ in range(5):
        assert _login(client, "admin", "bad", headers=h).status_code == 401
    assert _login(client, "admin", "adminpass", headers=h).status_code == 429          # cette adresse est bloquée
    other = {"X-Forwarded-For": "198.51.100.21", "X-CSRF": "1"}
    assert _login(client, "admin", "adminpass", headers=other).status_code == 200      # le compte ne l'est pas


def test_forwarded_for_is_ignored_from_an_internet_peer():
    from starlette.requests import Request
    from app.routes_auth import client_ip
    req = lambda peer: Request({"type": "http", "headers": [(b"x-forwarded-for", b"10.0.0.9")], "client": (peer, 1)})
    assert client_ip(req("172.18.0.2")) == "10.0.0.9"      # le proxy, dans le réseau Docker
    assert client_ip(req("203.0.114.5")) == "203.0.114.5"  # connexion directe depuis Internet : l'en-tête est ignoré


def test_security_headers(client):
    r = client.get("/api/health")
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"] and r.headers["x-frame-options"] == "DENY"
    assert r.headers["referrer-policy"] == "same-origin"


def test_huge_image_is_refused():
    import io
    from PIL import Image
    from app.routes_media import IMAGE_ERRORS
    buf = io.BytesIO()
    Image.new("1", (9000, 9000)).save(buf, "PNG")  # 81 Mpx, quelques Ko
    try:
        with Image.open(io.BytesIO(buf.getvalue())) as img:
            img.convert("RGB")
        refused = False
    except IMAGE_ERRORS:
        refused = True
    assert refused
