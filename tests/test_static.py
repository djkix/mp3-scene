def test_static_shell(client):
    r = client.get("/")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]
    assert r.headers["cache-control"] == "no-cache"
    assert client.get("/js/app.js").status_code == 200
    assert client.get("/app.css").status_code == 200


def test_api_still_protected_and_unknown_404(client):
    assert client.get("/api/me").status_code == 401
    assert client.get("/nimportequoi").status_code == 404


def test_manifest_and_sw_headers(client):
    r = client.get("/manifest.webmanifest")
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/manifest+json")
    r = client.get("/sw.js")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-cache"
    assert "javascript" in r.headers["content-type"]


def test_sw_precache_matches_static_js():
    import re
    from pathlib import Path
    static = Path(__file__).resolve().parent.parent / "static"
    listed = set(re.findall(r"'(/[^']*)'", re.search(r"PRECACHE = \[(.*?)\]", (static / "sw.js").read_text(), re.S).group(1)))
    for path in listed:
        assert path == "/" or (static / path.lstrip("/")).is_file(), path
    on_disk = {"/" + p.relative_to(static).as_posix() for p in (static / "js").rglob("*.js") if not p.name.endswith(".test.js")}
    assert on_disk <= listed, on_disk - listed


def test_public_url_warning(settings, caplog):
    from fastapi.testclient import TestClient
    from app.main import create_app
    settings.public_url = ""
    with caplog.at_level("WARNING", logger="uvicorn.error"), TestClient(create_app(settings)):
        pass
    assert "PUBLIC_URL" in caplog.text
    caplog.clear()
    settings.public_url = "httpfoo"
    with caplog.at_level("WARNING", logger="uvicorn.error"), TestClient(create_app(settings)):
        pass
    assert "PUBLIC_URL" in caplog.text
    caplog.clear()
    settings.public_url = "https://mp3.test"
    with caplog.at_level("WARNING", logger="uvicorn.error"), TestClient(create_app(settings)):
        pass
    assert "PUBLIC_URL" not in caplog.text


def test_no_admin_warning_when_no_user_and_no_credentials(settings, caplog):
    from fastapi.testclient import TestClient
    from app.main import create_app
    with caplog.at_level("WARNING", logger="uvicorn.error"), TestClient(create_app(settings)):
        pass
    assert "ADMIN_PASSWORD" in caplog.text


def test_favicon_ico(client):
    r = client.get("/favicon.ico")
    assert r.status_code == 200 and r.content[:4] == b"\x00\x00\x01\x00"


def test_nosniff_on_every_response(client):
    for url in ["/api/health", "/api/me", "/", "/app.css", "/js/app.js", "/cast/1?exp=1&sig=00"]:
        assert client.get(url).headers.get("x-content-type-options") == "nosniff", url


def test_app_logger_configured_once(settings):
    import logging
    from app.main import create_app
    create_app(settings)
    create_app(settings)
    lg = logging.getLogger("app")
    assert lg.level == logging.INFO and len(lg.handlers) == 1
    assert lg.handlers[0].formatter._fmt == "%(asctime)s %(levelname)s %(name)s: %(message)s"
