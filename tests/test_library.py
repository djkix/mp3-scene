import pytest
from fastapi import HTTPException

from app.security import safe_path

A = "A-Trak--Ibanez-(SP983)-WEB-2015-WUS"


def test_list_sorted_and_paginated(user_client, library):
    r = user_client.get("/api/releases?limit=2").json()
    assert len(r["items"]) == 2 and r["has_more"] is True
    assert user_client.get("/api/releases?limit=5000").status_code == 200   # plafonné, pas d'erreur
    assert {"id", "name", "path", "category", "added_at", "size", "track_count", "has_nfo", "artist", "title",
            "source", "year", "grp", "genre", "duration", "favorite"} <= r["items"][0].keys()
    keys = [(x["added_at"], x["id"]) for x in user_client.get("/api/releases").json()["items"]]
    assert keys == sorted(keys, reverse=True)
    assert user_client.get("/api/releases?offset=2&limit=2").json()["has_more"] is False


@pytest.mark.parametrize("qs", ["offset=-1", "limit=0", "limit=-3", "limit=abc", "offset=x", "year=abc"])
def test_bad_paging_is_422(user_client, library, qs):
    assert user_client.get(f"/api/releases?{qs}").status_code == 422


def test_filters(user_client, library):
    f = user_client.get("/api/filters").json()
    assert f["categories"] == ["Singles", "Albums"] and "House" in f["genres"] and f["years"] == [2017, 2015, 2003]
    assert [x["name"] for x in user_client.get("/api/releases?genre=House&year=2015").json()["items"]] == [A]
    assert [x["name"] for x in user_client.get("/api/releases?category=Albums").json()["items"]] == ["VA-Big_Mix-2CD-2003-GRP"]


def test_groups(user_client, library):
    g = user_client.get("/api/groups").json()
    assert sorted(x["name"] for x in g) == ["GRP", "PWT", "WUS"] and all(x["releases"] == 1 and x["size"] > 0 for x in g)
    assert [x["name"] for x in user_client.get("/api/groups?genre=House&year=2015").json()] == ["WUS"]
    assert user_client.get("/api/groups?name=WUS&year=2017").json() == []
    assert [x["name"] for x in user_client.get("/api/releases?grp=WUS").json()["items"]] == [A]
    assert {"A-Trak", "Bicep"} <= {x["name"] for x in user_client.get("/api/groups?by=artist").json()}
    assert {x["name"] for x in user_client.get("/api/groups?by=genre").json()} == {"House", "Techno"}
    assert [x["name"] for x in user_client.get("/api/releases?artist=A-Trak").json()["items"]] == [A]
    assert user_client.get("/api/groups?by=password_hash").status_code == 422


def test_search_tracks(user_client, library):
    find = lambda q: [t["title"] for t in user_client.get("/api/tracks", params={"q": q}).json()["items"]]
    assert find("ibanez") == ["Ibanez", "Ibanez Dub"] and find("trak dub") == ["Ibanez Dub"] and find("glu") == ["Glue"]
    assert find("") == [] and find("%") == [] and find("_") == [] and find("zzz") == []


def test_playlists(user_client, admin_client, library):
    ids = [t["id"] for t in user_client.get("/api/tracks", params={"q": "ibanez"}).json()["items"]]
    rid = user_client.get("/api/releases?grp=PWT").json()["items"][0]["id"]
    pid = user_client.post("/api/playlists", json={"name": " Soir "}).json()["id"]
    assert user_client.post("/api/playlists", json={"name": "  "}).status_code == 422
    add = lambda body: user_client.post(f"/api/playlists/{pid}/tracks", json=body).status_code
    assert add({"track_ids": [ids[1], 99999]}) == 204 and add({"track_ids": ids}) == 204 and add({"release_id": rid}) == 204
    p = user_client.get(f"/api/playlists/{pid}").json()
    assert p["name"] == "Soir" and [t["title"] for t in p["items"]] == ["Ibanez Dub", "Ibanez", "Glue"]
    assert user_client.get("/api/playlists").json()[0]["tracks"] == 3
    # privées : un autre utilisateur ne les voit pas et ne peut rien y faire
    assert admin_client.get("/api/playlists").json() == [] and admin_client.get(f"/api/playlists/{pid}").status_code == 404
    assert admin_client.post(f"/api/playlists/{pid}/tracks", json={"track_ids": ids}).status_code == 404
    assert admin_client.delete(f"/api/playlists/{pid}").status_code == 204 and len(user_client.get("/api/playlists").json()) == 1
    assert user_client.delete(f"/api/playlists/{pid}/tracks/{ids[0]}").status_code == 204
    assert user_client.put(f"/api/playlists/{pid}", json={"name": "Nuit"}).status_code == 204
    assert [t["title"] for t in user_client.get(f"/api/playlists/{pid}").json()["items"]] == ["Ibanez Dub", "Glue"]
    assert user_client.get("/api/playlists").json()[0]["name"] == "Nuit"
    assert user_client.delete(f"/api/playlists/{pid}").status_code == 204 and user_client.get("/api/playlists").json() == []


def test_player_state(user_client, admin_client, library):
    assert user_client.get("/api/player-state").json() == {"state": None, "updated_at": 0}
    at = user_client.put("/api/player-state", json={"queue": {"tracks": [{"id": 1}], "index": 0}, "position": 12}).json()["updated_at"]
    got = user_client.get("/api/player-state").json()
    assert got["updated_at"] == at > 0 and got["state"]["position"] == 12
    assert user_client.put("/api/player-state", json={"position": 3}).json()["updated_at"] >= at
    assert user_client.get("/api/player-state").json()["state"] == {"position": 3}
    assert admin_client.get("/api/player-state").json()["state"] is None   # un état par utilisateur
    assert user_client.put("/api/player-state", json={"x": "a" * 600_000}).status_code == 413
    assert user_client.put("/api/player-state", json=[1]).status_code == 422


def test_mix_and_new_count(user_client, library):
    ids = lambda qs="": sorted(t["title"] for t in user_client.get("/api/mix" + qs).json()["items"])
    assert ids() == ["Glue", "Ibanez", "Ibanez Dub", "One", "Two"]
    assert ids("?grp=WUS") == ["Ibanez", "Ibanez Dub"] and ids("?genre=Techno&limit=5") == ["Glue"] and ids("?year=1990") == []
    assert user_client.get("/api/new-count?since=0").json() == {"count": 3}
    assert user_client.get("/api/new-count?since=99999999999").json() == {"count": 0}
    assert user_client.get("/api/new-count").status_code == 422


def test_playlist_move(user_client, library):
    rid = user_client.get("/api/releases?grp=GRP").json()["items"][0]["id"]
    pid = user_client.post("/api/playlists", json={"name": "Ordre"}).json()["id"]
    user_client.post(f"/api/playlists/{pid}/tracks", json={"release_id": rid})
    titles = lambda: [t["title"] for t in user_client.get(f"/api/playlists/{pid}").json()["items"]]
    ids = [t["id"] for t in user_client.get(f"/api/playlists/{pid}").json()["items"]]
    assert titles() == ["One", "Two"]
    move = lambda tid, d: user_client.post(f"/api/playlists/{pid}/tracks/{tid}/move?dir={d}").status_code
    assert move(ids[0], "down") == 204 and titles() == ["Two", "One"]
    assert move(ids[0], "down") == 204 and titles() == ["Two", "One"]   # déjà en bas
    assert move(ids[0], "up") == 204 and titles() == ["One", "Two"]
    assert move(99999, "up") == 404 and move(ids[0], "left") == 422


def test_share(client, user_client, admin_client, library, settings):
    rid = user_client.get("/api/releases?grp=WUS").json()["items"][0]["id"]
    other = user_client.get("/api/tracks", params={"q": "glue"}).json()["items"][0]["id"]
    url = user_client.post("/api/share", json={"kind": "release", "id": rid}).json()["url"]
    token = url.rsplit("/", 1)[-1]
    assert client.get(f"/s/{token}").status_code == 200   # sans session
    info = client.get(f"/s/{token}/info").json()
    assert info["name"] == A and [t["title"] for t in info["tracks"]] == ["Ibanez", "Ibanez Dub"]
    tid = info["tracks"][0]["id"]
    assert client.get(f"/s/{token}/track/{tid}").status_code == 200
    assert client.get(f"/s/{token}/track/{other}").status_code == 404   # piste hors du partage
    bad = token[:-1] + ("0" if token[-1] != "0" else "1")
    assert client.get(f"/s/{bad}").status_code == 404 and client.get(f"/s/{bad}/info").status_code == 404
    assert client.get(f"/s/{bad}/track/{tid}").status_code == 404 and client.get("/s/nimporte").status_code == 404
    # anciens liens signés (1.15.0) : valides jusqu'à leur échéance, refusés ensuite
    import time
    from app.security import sign_share
    assert client.get(f"/s/{sign_share(settings.secret_key, 'r', rid, int(time.time()) + 3600)}/info").status_code == 200
    assert client.get(f"/s/{sign_share(settings.secret_key, 'r', rid, 1000)}/info").status_code == 404
    # playlist : seul son propriétaire peut la partager
    pid = user_client.post("/api/playlists", json={"name": "Amis"}).json()["id"]
    user_client.post(f"/api/playlists/{pid}/tracks", json={"track_ids": [other]})
    assert admin_client.post("/api/share", json={"kind": "playlist", "id": pid}).status_code == 404
    ptoken = user_client.post("/api/share", json={"kind": "playlist", "id": pid}).json()["url"].rsplit("/", 1)[-1]
    assert [t["title"] for t in client.get(f"/s/{ptoken}/info").json()["tracks"]] == ["Glue"]
    assert client.get(f"/s/{ptoken}/track/{tid}").status_code == 404
    assert user_client.post("/api/share", json={"kind": "release", "id": 99999}).status_code == 404
    # liste, compteur d'ouvertures, révocation
    mine = user_client.get("/api/shares").json()
    assert [(s["kind"], s["name"], s["opens"]) for s in mine] == [("playlist", "Amis", 1), ("release", A, 1)]
    assert mine[1]["url"] == url and admin_client.get("/api/shares").json() == []
    assert admin_client.delete(f"/api/shares/{mine[1]['id']}").status_code == 204   # pas le sien : sans effet
    assert client.get(f"/s/{token}/info").status_code == 200
    assert user_client.delete(f"/api/shares/{mine[1]['id']}").status_code == 204
    assert client.get(f"/s/{token}").status_code == 404 and client.get(f"/s/{token}/track/{tid}").status_code == 404
    assert len(user_client.get("/api/shares").json()) == 1


def test_admin_library_and_quality(user_client, admin_client, library):
    assert user_client.get("/api/admin/library").status_code == 403 and user_client.get("/api/admin/quality").status_code == 403
    s = admin_client.get("/api/admin/library").json()
    assert s["releases"] == 3 and s["tracks"] == 5 and s["size"] > 0
    assert [y["name"] for y in s["years"]] == [2017, 2015, 2003] and {g["name"] for g in s["genres"]} == {"House", "Techno"}
    assert sum(b["n"] for b in s["bitrates"]) == 5 and len(s["months"]) >= 1 and {c["name"] for c in s["categories"]} == {"Albums", "Singles"}
    q = admin_client.get("/api/admin/quality").json()
    assert q["no_nfo"] == 2 and q["no_tracks"] == 0 and q["no_year"] == 0
    names = [r["name"] for r in admin_client.get("/api/admin/quality?kind=no_nfo").json()["items"]]
    assert names == ["Bicep-Glue-(NT123)-WEB-2017-PWT", "VA-Big_Mix-2CD-2003-GRP"]
    assert admin_client.get("/api/admin/quality?kind=drop").status_code == 422
    assert q["no_cover"] == 3                                                  # aucune image, aucun tag APIC


def test_cover_check_and_similar(user_client, admin_client, library, settings):
    from app import db
    from app.scanner import scan_tags
    (settings.music_root / "Singles/A" / A / "Cover.JPG").write_bytes(b"x")
    c = db.connect(settings.data_dir)
    c.execute("UPDATE releases SET has_cover=NULL"); c.commit()                # comme une base antérieure à la colonne
    scan_tags(c, settings.music_root)
    c.execute("UPDATE releases SET genre='House', year=2015 WHERE name LIKE 'Bicep%'"); c.commit(); c.close()
    assert admin_client.get("/api/admin/quality").json()["no_cover"] == 2
    rid = user_client.get("/api/release-by-name", params={"name": A}).json()["id"]
    assert [r["name"] for r in user_client.get(f"/api/releases/{rid}/similar").json()] == ["Bicep-Glue-(NT123)-WEB-2017-PWT"]
    assert user_client.get("/api/releases/999999/similar").status_code == 404
    assert [t["title"] for t in user_client.get(f"/api/releases/{rid}/radio").json()["items"]] == ["Glue"]   # 2017 : à deux ans près
    assert user_client.get("/api/releases/999999/radio").status_code == 404


def test_stats(user_client, admin_client, library):
    ids = [t["id"] for t in user_client.get("/api/tracks", params={"q": "ibanez"}).json()["items"]]
    for tid in (ids[0], ids[0], ids[1]):
        assert user_client.post(f"/api/history/{tid}").status_code == 204
    s = user_client.get("/api/stats?days=7").json()
    assert s["plays"] == 3 and s["duration"] > 0 and [(t["id"], t["plays"]) for t in s["tracks"]] == [(ids[0], 2), (ids[1], 1)]
    assert s["artists"] == [{"name": "A-Trak", "plays": 3}] and s["genres"] == [{"name": "House", "plays": 3}]
    assert s["groups"] == [{"name": "WUS", "plays": 3}]
    assert admin_client.get("/api/stats").json()["plays"] == 0


def test_search_words_and_prefix(user_client, library):
    names = lambda q: [x["name"] for x in user_client.get("/api/releases", params={"q": q}).json()["items"]]
    assert names("ibanez trak") == [A]
    assert names("big mi") == ["VA-Big_Mix-2CD-2003-GRP"]                    # _ séparateur + préfixe
    assert names("sp983") == [A]
    assert names("ibanez bicep") == []


@pytest.mark.parametrize("q", ['"', "*", "(", "a-", "AND", "NEAR(", "foo OR", "'; DROP", "  "])
def test_search_special_chars_never_500(user_client, library, q):
    assert user_client.get("/api/releases", params={"q": q}).status_code == 200


def test_blank_query_is_no_filter(user_client, library):
    assert len(user_client.get("/api/releases", params={"q": " - "}).json()["items"]) == 3


def test_folders(user_client, library):
    root = user_client.get("/api/folders").json()
    assert [f["name"] for f in root["folders"]] == ["Albums", "Singles"] and root["releases"]["items"] == []
    a = user_client.get("/api/folders", params={"path": "Singles/A"}).json()
    assert a["folders"] == [] and len(a["releases"]["items"]) == 1
    assert user_client.get("/api/folders", params={"path": "../etc"}).status_code == 404
    s = user_client.get("/api/folders", params={"path": "Singles"}).json()
    assert s["path"] == "Singles" and s["folders"] == [{"path": "Singles/A", "name": "A"},
                                                       {"path": "Singles/B", "name": "B"}]
    assert user_client.get("/api/folders", params={"path": "Singles", "offset": 1}).json()["folders"] == []


def test_history_per_user(user_client, admin_client, library):
    rel = user_client.get("/api/releases", params={"q": "ibanez"}).json()["items"][0]
    a, b = [t["id"] for t in user_client.get(f"/api/releases/{rel['id']}").json()["tracks"]]
    for tid in (a, b, a):
        assert user_client.post(f"/api/history/{tid}").status_code == 204
    items = user_client.get("/api/history").json()["items"]
    assert [t["id"] for t in items] == [a, b, a] and items[0]["played_at"] > 0 and items[0]["release_name"] == rel["name"]
    assert admin_client.get("/api/history").json()["items"] == []
    assert user_client.post("/api/history/99999").status_code == 404
    assert user_client.delete("/api/history").status_code == 204
    assert user_client.get("/api/history").json()["items"] == []


def test_sort(user_client, library):
    get = lambda **p: user_client.get("/api/releases", params=p).json()["items"]
    sizes = [r["size"] for r in get(sort="size", dir="desc")]
    assert sizes == sorted(sizes, reverse=True) and len(sizes) > 1
    names = [r["name"].lower() for r in get(sort="name")]
    assert names == sorted(names)
    assert get() == get(sort="date", dir="desc")  # l'ordre par défaut est inchangé
    rates = [r["bitrate"] or 0 for r in get(sort="bitrate", dir="desc")]
    assert rates == sorted(rates, reverse=True) and "bitrate" in get()[0]
    assert user_client.get("/api/releases", params={"sort": "id; DROP"}).status_code == 422
    f = user_client.get("/api/folders", params={"path": "Singles/A", "sort": "name", "dir": "desc"}).json()["releases"]["items"]
    assert [r["name"].lower() for r in f] == sorted((r["name"].lower() for r in f), reverse=True)


def test_detail_tracks_and_tag_artist(user_client, library):
    rid = user_client.get("/api/releases", params={"q": "ibanez"}).json()["items"][0]["id"]
    d = user_client.get(f"/api/releases/{rid}").json()
    assert d["artist"] == "A-Trak" and d["has_nfo"] in (1, True) and d["track_count"] == 2
    assert [t["filename"] for t in d["tracks"]] == ["01-a-trak--ibanez.mp3", "02-a-trak--ibanez_(dub).mp3"]
    assert {"id", "release_id", "release_name", "filename", "disc", "size", "title", "artist", "duration",
            "bitrate", "favorite"} <= d["tracks"][0].keys() and d["tracks"][0]["release_name"] == A
    assert d["tracks"][0]["genre"] == "House"
    assert user_client.get("/api/release-by-name", params={"name": A}).json() == d
    assert user_client.get("/api/release-by-name", params={"name": "inconnue"}).status_code == 404
    vid = user_client.get("/api/releases", params={"q": "big"}).json()["items"][0]["id"]
    v = user_client.get(f"/api/releases/{vid}").json()
    assert [t["disc"] for t in v["tracks"]] == [1, 2]
    assert user_client.get("/api/releases/99999").status_code == 404


def test_nfo_cp437(user_client, library):
    rid = user_client.get("/api/releases", params={"q": "ibanez"}).json()["items"][0]["id"]
    r = user_client.get(f"/api/releases/{rid}/nfo")
    assert r.headers["content-type"] == "text/plain; charset=utf-8" and "██" in r.text
    bid = user_client.get("/api/releases", params={"q": "bicep"}).json()["items"][0]["id"]
    assert user_client.get(f"/api/releases/{bid}/nfo").status_code == 404
    assert user_client.get("/api/releases/99999/nfo").status_code == 404


def test_nfo_folder_missing_is_404(user_client, library, settings):
    import shutil
    rid = user_client.get("/api/releases", params={"q": "ibanez"}).json()["items"][0]["id"]
    shutil.rmtree(settings.music_root / "Singles/A")
    assert user_client.get(f"/api/releases/{rid}/nfo").status_code == 404


def test_favorites_are_per_user(user_client, admin_client, library):
    rel = user_client.get("/api/releases", params={"q": "ibanez"}).json()["items"][0]
    tid = user_client.get(f"/api/releases/{rel['id']}").json()["tracks"][0]["id"]
    assert user_client.put(f"/api/favorites/release/{rel['id']}").status_code == 204
    assert user_client.put(f"/api/favorites/release/{rel['id']}").status_code == 204   # idempotent
    assert user_client.put(f"/api/favorites/track/{tid}").status_code == 204
    fav = lambda c: [x["id"] for x in c.get("/api/releases?favorites=1").json()["items"]]
    assert fav(user_client) == [rel["id"]] and fav(admin_client) == []
    assert user_client.get(f"/api/releases/{rel['id']}").json()["favorite"] is True
    assert admin_client.get(f"/api/releases/{rel['id']}").json()["favorite"] is False
    assert user_client.get(f"/api/releases/{rel['id']}").json()["tracks"][0]["favorite"] is True
    ft = user_client.get("/api/favorites/tracks").json()
    assert [t["id"] for t in ft["items"]] == [tid] and ft["has_more"] is False and ft["items"][0]["favorite"] is True
    assert admin_client.get("/api/favorites/tracks").json()["items"] == []
    assert user_client.delete(f"/api/favorites/release/{rel['id']}").status_code == 204
    assert user_client.delete(f"/api/favorites/release/{rel['id']}").status_code == 204   # déjà retiré
    assert fav(user_client) == []
    assert user_client.delete(f"/api/favorites/track/{tid}").status_code == 204
    assert user_client.get("/api/favorites/tracks").json()["items"] == []


def test_favorites_invalid(user_client, library):
    assert user_client.put("/api/favorites/album/1").status_code == 404
    assert user_client.put("/api/favorites/release/99999").status_code == 404
    assert user_client.put("/api/favorites/track/99999").status_code == 404
    assert user_client.delete("/api/favorites/album/1").status_code == 404


def test_library_requires_session(client, library):
    assert client.get("/api/releases").status_code == 401


def _code(fn):
    with pytest.raises(HTTPException) as e:
        fn()
    return e.value.status_code


def test_safe_path(tmp_path):
    root = tmp_path / "root"
    (root / "d").mkdir(parents=True)
    (root / "d/f.txt").write_text("x")
    (tmp_path / "out").mkdir()
    (tmp_path / "out/s.txt").write_text("s")
    (root / "link").symlink_to(tmp_path / "out")
    assert safe_path(root, "d", "f.txt") == (root / "d/f.txt").resolve()
    assert _code(lambda: safe_path(root, "..", "out", "s.txt")) == 404
    assert _code(lambda: safe_path(root, "/etc/passwd")) == 404
    assert _code(lambda: safe_path(root, "link", "s.txt")) == 404
    assert _code(lambda: safe_path(root, "d", "absent")) == 404


@pytest.mark.parametrize("n", [2**63, 2**64, 0])
@pytest.mark.parametrize("method,url,code", [
    ("get", "/api/releases?year={n}", None), ("get", "/api/releases?offset={n}", None),
    ("get", "/api/releases?limit={n}", None), ("get", "/api/folders?offset={n}", None),
    ("get", "/api/favorites/tracks?offset={n}", None),
    ("get", "/api/releases/{n}", 422), ("get", "/api/releases/{n}/nfo", 422), ("get", "/api/releases/{n}/zip", 422),
    ("get", "/api/tracks/{n}/stream", 422), ("put", "/api/favorites/release/{n}", 422),
    ("delete", "/api/favorites/track/{n}", 422), ("post", "/api/cast/urls", 422),
    ("patch", "/api/admin/users/{n}", 422), ("delete", "/api/admin/users/{n}", 422),
    ("get", "/cast/{n}?exp={exp}&sig=00", 403), ("get", "/cast/{n}?exp={exp}&sig={sig}", 404)])
def test_out_of_range_integers_never_500(admin_client, library, method, url, code, n):
    import time
    from app.security import sign_track
    if code is None:   # entier de requête : 0 est valide, seuls les grands sont refusés
        if n == 0:
            return
        code = 422
    exp = int(time.time()) + 60
    url = url.format(n=n, exp=exp, sig=sign_track("test", n, exp))
    kw = {"json": {"track_ids": [n]}} if method == "post" else {"json": {"role": "user"}} if method == "patch" else {}
    assert admin_client.request(method.upper(), url, **kw).status_code == code, url


def test_source_decade_appears_versions(user_client, admin_client, library, settings):
    from app import db
    names = lambda qs: sorted(x["name"] for x in user_client.get(f"/api/releases?{qs}").json()["items"])
    B, V = "Bicep-Glue-(NT123)-WEB-2017-PWT", "VA-Big_Mix-2CD-2003-GRP"
    assert user_client.get("/api/filters").json()["sources"] == ["WEB"]
    assert names("source=WEB") == [A, B] and names("decade=2010") == [A, B] and names("decade=2000") == [V]
    assert [x["name"] for x in user_client.get("/api/groups?decade=2000").json()] == ["GRP"]
    # apparitions : piste signée dans la release d'un autre ; ses propres releases n'en sont pas
    assert names("appears=X") == [V] and names("appears=A-Trak") == []
    assert all(t["artist"] == "X" for t in user_client.get("/api/mix?appears=X&source=WEB").json()["items"])
    rid = {x["name"]: x["id"] for x in user_client.get("/api/releases").json()["items"]}
    assert user_client.get(f"/api/releases/{rid[A]}/versions").json() == []
    assert admin_client.get("/api/admin/quality").json()["dupes"] == 0
    c = db.connect(settings.data_dir)
    c.execute("UPDATE releases SET artist='a-trak', title='IBANEZ', category='Albums' WHERE name=?", (B,))
    c.commit()
    c.close()
    assert [x["name"] for x in user_client.get(f"/api/releases/{rid[A]}/versions").json()] == [B]
    assert admin_client.get("/api/admin/quality").json()["dupes"] == 2
    # un dossier ne montre que les releases de sa catégorie
    assert user_client.get("/api/folders?path=Singles/B").json()["releases"]["items"] == []
    assert len(user_client.get("/api/folders?path=Singles/A").json()["releases"]["items"]) == 1


def test_date_from_nfo(user_client, library, settings):
    from app import db
    from app.scanner import scan_tags
    rel = lambda: {x["name"]: x for x in user_client.get("/api/releases").json()["items"]}
    assert all(x["date"] == x["added_at"] for x in rel().values())               # NFO sans date, ou pas de NFO
    (settings.music_root / "Singles/A" / A / "a-trak--ibanez.nfo").write_bytes(b"Rip Date: Mar-04-2015")
    c = db.connect(settings.data_dir)
    c.execute("UPDATE releases SET released_at=NULL"); c.commit()                  # comme une base antérieure à la colonne
    scan_tags(c, settings.music_root)
    c.close()
    r = rel()
    assert r[A]["date"] == 1425470400 != r[A]["added_at"]
    assert user_client.get("/api/releases?sort=date&dir=asc").json()["items"][0]["name"] == A  # 2015 avant les ajouts du jour
    assert user_client.get("/api/releases?sort=added&dir=desc").status_code == 200


def test_corrections_collab_and_nfo_year(user_client, admin_client, library, settings):
    from app import artists, db
    from app.scanner import scan_structure, scan_tags
    B = "Bicep-Glue-(NT123)-WEB-2017-PWT"
    rel = lambda: {x["name"]: x for x in user_client.get("/api/releases").json()["items"]}
    rid = rel()[A]["id"]
    fix = lambda body, c=admin_client: c.patch(f"/api/admin/releases/{rid}", json=body).status_code
    assert fix({"artist": "A-Trak & Friends", "genre": "techno", "category": "Albums"}) == 204
    assert fix({"artist": "X"}, user_client) == 403 and fix({"category": "Nope"}) == 400
    assert admin_client.patch("/api/admin/releases/99999", json={"genre": "x"}).status_code == 404
    want = ("A-Trak & Friends", "Techno", "Albums")
    assert (rel()[A]["artist"], rel()[A]["genre"], rel()[A]["category"]) == want
    c = db.connect(settings.data_dir)
    scan_structure(c, settings.music_root, now=2000.0); scan_tags(c, settings.music_root)   # la correction survit au scan
    db.init(settings.data_dir)                                                               # et au redémarrage
    assert (rel()[A]["artist"], rel()[A]["genre"], rel()[A]["category"]) == want
    assert fix({"artist": "", "genre": " ", "category": None}) == 204                        # retour à l'automatique
    assert (rel()[A]["artist"], rel()[A]["genre"], rel()[A]["category"]) == ("A-Trak", "House", "Singles")
    assert c.execute("SELECT COUNT(*) FROM overrides").fetchone()[0] == 0
    # « Avec » : le nom associe l'artiste à un autre
    assert artists.collab("Zedd_Feat_Bright_Lights-Title-WEB-2012-GRP", "Bright Lights")
    assert artists.collab("Daft_Punk_Vs_Madonna-Title-2005-GRP", "daft punk") and artists.collab("X_and_Bicep-T-2017-G", "Bicep")
    assert not artists.collab(A, "A-Trak") and not artists.collab("Bicepology_and_X-T-2017-G", "Bicep") and not artists.collab(A, " ")
    c.execute("UPDATE releases SET name='Bicep_Feat_A-Trak-Glue-WEB-2017-PWT' WHERE name=?", (B,))
    # année : sans année dans le nom, celle du NFO
    c.execute("UPDATE releases SET year=NULL, released_at=1425470400 WHERE id=?", (rid,)); c.commit()
    db.year_from_nfo(c); c.commit(); c.close()
    assert [x["name"] for x in user_client.get("/api/releases?collab=A-Trak").json()["items"]] == ["Bicep_Feat_A-Trak-Glue-WEB-2017-PWT"]
    assert rel()[A]["year"] == 2015


def test_admin_overview_classify_schedule(admin_client, user_client, library, app, settings):
    from app import db
    assert user_client.get("/api/admin/overview").status_code == 403
    o = admin_client.get("/api/admin/overview").json()
    assert o["artists"] >= 2 and o["groups"] == 3 and o["users"] == 2 and o["db_size"] > 0 and o["thumbs_size"] == 0
    assert o["overrides"] == {"total": 0, "artist": 0, "category": 0, "genre": 0, "year": 0, "hidden": 0} and o["shares"] == 0
    rid = admin_client.get("/api/releases?grp=WUS").json()["items"][0]["id"]
    admin_client.patch(f"/api/admin/releases/{rid}", json={"genre": "Techno"})
    assert admin_client.get("/api/admin/overrides").json() == [{"id": rid, "name": A, "artist": None, "category": None, "genre": "Techno", "year": None, "hidden": None}]
    assert admin_client.get("/api/admin/overview").json()["overrides"]["genre"] == 1
    # reclassement à la demande : une graphie isolée rejoint la majorité, la correction manuelle tient
    c = db.connect(settings.data_dir)
    c.execute("UPDATE releases SET grp='wus_INT', artist=NULL, tag_artist=NULL WHERE id=?", (rid,)); c.commit()
    assert admin_client.get("/api/admin/quality").json()["no_artist"] == 1
    assert admin_client.post("/api/admin/classify").status_code == 204
    r = admin_client.get(f"/api/releases/{rid}").json()
    assert r["grp"] == "wus" and r["genre"] == "Techno"
    # scan quotidien : heure du serveur, pas deux fois de suite
    runner = app.state.runner
    assert admin_client.put("/api/admin/scan/schedule", json={"hour": 24}).status_code == 422
    assert admin_client.put("/api/admin/scan/schedule", json={"hour": 3}).status_code == 204
    s = admin_client.get("/api/admin/scan").json()
    assert s["daily_at"] == 3 and len(s["server_time"]) == 5
    import time
    at = lambda h: time.mktime((2026, 11, 20, h, 30, 0, 0, 0, -1))
    c.execute("UPDATE scan_state SET started_at=?", (at(3) - 86400,)); c.commit()
    assert runner.due(c, at(3)) and not runner.due(c, at(4))
    c.execute("UPDATE scan_state SET started_at=?", (at(3) - 600,)); c.commit()
    assert not runner.due(c, at(3))
    assert admin_client.put("/api/admin/scan/schedule", json={"hour": None}).status_code == 204
    assert not runner.due(c, at(3) + 86400)
    c.close()


def test_bulk_correction_and_artist_alias(admin_client, user_client, library):
    rel = lambda: {x["name"]: x for x in admin_client.get("/api/releases").json()["items"]}
    B = "Bicep-Glue-(NT123)-WEB-2017-PWT"
    ids = [rel()[A]["id"], rel()[B]["id"]]
    bulk = lambda body, c=admin_client: c.patch("/api/admin/releases", json=body).status_code
    assert bulk({"ids": ids, "genre": "trance", "artist": " "}) == 204                 # champ vide : inchangé
    assert bulk({"ids": ids, "genre": "x"}, user_client) == 403 and bulk({"ids": ids}) == 400
    assert bulk({"ids": [], "genre": "x"}) == 422 and bulk({"ids": [ids[0], 99999], "genre": "x"}) == 404
    assert [rel()[n]["genre"] for n in (A, B)] == ["Trance", "Trance"] and rel()[A]["artist"] == "A-Trak"
    assert len(admin_client.get("/api/admin/overrides").json()) == 2
    # rattachement manuel : Bicep rejoint A-Trak, et y reste après un reclassement
    put = lambda body: admin_client.put("/api/admin/artists/aliases", json=body).status_code
    assert put({"alias": "bicep", "target": "A-Trak"}) == 204 and put({"alias": "A-Trak", "target": "a-trak"}) == 400
    assert rel()[B]["artist"] == "A-Trak"
    assert admin_client.post("/api/admin/classify").status_code == 204 and rel()[B]["artist"] == "A-Trak"
    assert admin_client.get("/api/admin/artists/aliases").json() == [{"alias": "bicep", "target": "A-Trak"}]
    assert admin_client.delete("/api/admin/artists/aliases", params={"alias": "Bicep"}).status_code == 204
    assert rel()[B]["artist"] == "Bicep" and rel()[A]["artist"] == "A-Trak"
    assert admin_client.delete("/api/admin/artists/aliases", params={"alias": "Bicep"}).status_code == 404


def test_year_correction_select_all_and_played_releases(admin_client, user_client, library, settings):
    from app import db
    rel = lambda: {x["name"]: x for x in admin_client.get("/api/releases").json()["items"]}
    B = "Bicep-Glue-(NT123)-WEB-2017-PWT"
    rid, auto = rel()[B]["id"], rel()[B]["year"]
    fix = lambda body: admin_client.patch(f"/api/admin/releases/{rid}", json=body).status_code
    assert fix({"year": 1999}) == 204 and fix({"year": 12}) == 422 and rel()[B]["year"] == 1999
    db.init(settings.data_dir)                                             # la correction survit au redémarrage
    assert rel()[B]["year"] == 1999 and admin_client.get("/api/admin/overview").json()["overrides"]["year"] == 1
    assert fix({"year": None}) == 204 and rel()[B]["year"] == auto == 2017  # retour à l'année du nom
    assert admin_client.get("/api/admin/overrides").json() == []
    ids = [x["id"] for x in rel().values()]
    assert admin_client.patch("/api/admin/releases", json={"ids": ids, "year": 2001}).status_code == 204
    assert {x["year"] for x in rel().values()} == {2001}
    # tout cocher : tous les identifiants d'un contrôle, réservés à l'administrateur
    c = db.connect(settings.data_dir)
    c.execute("UPDATE releases SET has_cover=0"); c.commit(); c.close()
    assert sorted(admin_client.get("/api/admin/quality?kind=no_cover&ids=1").json()["ids"]) == sorted(ids)
    assert user_client.get("/api/admin/quality?kind=no_cover&ids=1").status_code == 403
    # releases écoutées : la dernière écoutée d'abord, une fois chacune, par utilisateur
    track = lambda r: user_client.get(f"/api/releases/{r}").json()["tracks"][0]["id"]
    a, b = rel()[A]["id"], rid
    for r in (a, b, a):
        assert user_client.post(f"/api/history/{track(r)}").status_code == 204
    assert [x["id"] for x in user_client.get("/api/history/releases").json()["items"]] == [a, b]
    assert [x["name"] for x in user_client.get("/api/history/releases?sort=name&dir=desc").json()["items"]] == [B, A]
    assert admin_client.get("/api/history/releases").json()["items"] == []


def test_keep_version_separate_artist_label_smart_playlist(admin_client, user_client, library, settings):
    import sqlite3
    from app import artists, db, nfo
    from app.scanner import scan_structure, scan_tags
    rel = lambda c=admin_client, qs="": {x["name"]: x for x in c.get("/api/releases" + qs).json()["items"]}
    B = "Bicep-Glue-(NT123)-WEB-2017-PWT"
    a, b = rel()[A]["id"], rel()[B]["id"]
    # doublons : même artiste et même titre dans le nom ; garder une version masque l'autre des listes
    c = db.connect(settings.data_dir)
    c.execute("UPDATE releases SET artist='A-Trak', title='Ibanez' WHERE id=?", (b,)); c.commit()
    assert admin_client.get("/api/admin/quality").json()["dupes"] == 2
    assert user_client.put(f"/api/admin/releases/{a}/keep").status_code == 403
    assert admin_client.put(f"/api/admin/releases/{a}/keep").status_code == 204
    assert B not in rel() and A in rel() and admin_client.get("/api/admin/quality").json()["dupes"] == 0
    assert [(v["name"], v["hidden"]) for v in admin_client.get(f"/api/releases/{a}/versions").json()] == [(B, True)]
    db.init(settings.data_dir)                                              # masquée après un redémarrage aussi
    assert B not in rel() and admin_client.get(f"/api/releases/{b}").json()["hidden"] is True
    assert admin_client.put(f"/api/admin/releases/{b}/keep").status_code == 204 and A not in rel() and B in rel()
    assert admin_client.delete(f"/api/admin/releases/{b}/keep").status_code == 204 and {A, B} <= set(rel())
    assert admin_client.get("/api/admin/overrides").json() == []
    c.execute("UPDATE releases SET artist='Bicep', title='Glue' WHERE id=?", (b,)); c.commit()
    # artistes à ne jamais fusionner : « Florida » ne rejoint plus « Flo Rida »
    pairs = {1: ("Flo Rida", None), 2: ("Flo_Rida", None), 3: ("Florida", None)}
    assert {v[0] for v in artists._step(pairs, {}).values()} == {"Flo Rida"}
    assert [v[0] for v in artists._step(pairs, {}, frozenset({"florida"})).values()] == ["Flo Rida", "Flo Rida", "Florida"]
    c.execute("UPDATE releases SET name='A_Trak-Ibanez-WEB-2009-WUS' WHERE id=?", (a,)); c.commit()
    sep = lambda m, **kw: getattr(admin_client, m)("/api/admin/artists/separate", **kw).status_code
    assert sep("put", json={"name": "A_Trak"}) == 204 and admin_client.get("/api/admin/artists/separate").json() == ["A Trak"]
    assert user_client.get("/api/admin/artists/separate").status_code == 403
    assert sep("delete", params={"name": "a trak"}) == 204 and sep("delete", params={"name": "a trak"}) == 404
    c.execute("UPDATE releases SET name=? WHERE id=?", (A, a)); c.commit()
    # label et catalogue : lus dans le NFO, sinon le numéro entre parenthèses du nom
    assert nfo.label("\u2551 Label.....: Ministry of Sound      \u2551\n\u2551 Cat.Nr....: MOS123CD \u2551\n Category: x\n") == ("Ministry of Sound", "MOS123CD")
    assert nfo.label("LABEL: n/a\nCatalogue: -\n") == (None, None) and nfo.label("Label : http://x.com") == (None, None)
    folder = settings.music_root / c.execute("SELECT path FROM releases WHERE id=?", (b,)).fetchone()[0]
    (folder / "00-bicep.nfo").write_bytes(b"Label....: Ninja Tune\nR.Date...: 2017-09-01\n")
    scan_structure(c, settings.music_root, now=3000.0); scan_tags(c, settings.music_root); c.commit()
    r = admin_client.get(f"/api/releases/{b}").json()
    assert (r["label"], r["catalog"]) == ("Ninja Tune", "NT123")
    assert admin_client.get("/api/groups?by=label").json()[0]["name"] == "Ninja Tune"
    assert list(rel(qs="?label=Ninja%20Tune")) == [B]
    # labels : restes de mise en forme retirés, graphies proches réunies sous la plus répandue
    cl = nfo.clean_label
    assert [cl(x) for x in ("..... Defected", "] Deep State", "\u2588 PIAS", "(Warner)", "(P) 2014 Protocol Recordings", "!K7", "?", ".....", "X")] \
        == ["Defected", "Deep State", "PIAS", "Warner", "Protocol Recordings", "!K7", "", "", ""]
    assert cl("((JOLLY ROGER) SOUND OF PIRATES))") == "JOLLY ROGER SOUND OF PIRATES"
    assert len({nfo.label_key(cl(x)) for x in ("Spinnin Records", "Spinnin' Records", "SpinninRecords", "spinnin", "..... Spinnin`Records")}) == 1
    assert nfo.label_key("Records") == "records" and nfo.label_key("Armada") == nfo.label_key("Armada Music")
    c.execute("UPDATE releases SET label='..... ninja-tune records' WHERE id=?", (a,))
    c.execute("UPDATE releases SET label='?' WHERE name LIKE 'VA-%'"); c.commit()
    db.merge_labels(c); c.commit()
    assert [r[0] for r in c.execute("SELECT DISTINCT label FROM releases WHERE label!='' ORDER BY 1")] in (["Ninja Tune"], ["ninja-tune records"])
    assert c.execute("SELECT label FROM releases WHERE name LIKE 'VA-%'").fetchone()[0] == ""
    c.execute("UPDATE releases SET label='' WHERE id=?", (a,)); c.commit()
    # numéro de catalogue pris pour un label, parenthèse redondante, « Music » final, puis rattachement manuel
    assert {nfo.label_key(cl(x)) for x in ("ZYX", "ZYX (ZYX-9168-8)", "ZYX 55786-2", "ZYX82273-2", "ZYX Music", "Zyx Music (ZYX)",
                                           "ZYX Music / Noise Traxx", "ZYX Music \u00fb ZYX 20590-2")} == {"zyx"}
    assert cl("Studio 2000") == "Studio 2000" and cl("Area 51") == "Area 51" and cl("Kontor Records (Edel)") == "Kontor Records (Edel)"
    c.execute("UPDATE releases SET label='ZYX Germany' WHERE id=?", (a,)); c.commit()
    lab = lambda m, **kw: getattr(admin_client, m)("/api/admin/labels/aliases", **kw).status_code
    assert lab("put", json={"alias": "ZYX Germany", "target": "Ninja Tune"}) == 204
    assert lab("put", json={"alias": "Ninja Tune", "target": "ninja-tune"}) == 400 and user_client.get("/api/admin/labels/aliases").status_code == 403
    assert admin_client.get(f"/api/releases/{a}").json()["label"] == "Ninja Tune"
    assert admin_client.get("/api/admin/labels/aliases").json() == [{"alias": "ZYX Germany", "target": "Ninja Tune"}]
    assert lab("delete", params={"alias": "zyx germany"}) == 204 and lab("delete", params={"alias": "zyx germany"}) == 404
    scan_structure(c, settings.music_root, now=3500.0); scan_tags(c, settings.music_root); c.commit()   # relus dans les NFO
    assert admin_client.get(f"/api/releases/{a}").json()["label"] is None and admin_client.get(f"/api/releases/{b}").json()["label"] == "Ninja Tune"
    # playlist intelligente : les pistes des releases qui passent les filtres, sans modification manuelle
    mk = lambda body: user_client.post("/api/playlists", json=body)
    assert mk({"name": "Vide", "rules": {}}).status_code == 400
    pid = mk({"name": "Ninja", "rules": {"label": "Ninja Tune"}}).json()["id"]
    p = user_client.get(f"/api/playlists/{pid}").json()
    assert p["smart"] and p["rules"] == {"label": "Ninja Tune"} and {t["release_id"] for t in p["items"]} == {b}
    row = next(x for x in user_client.get("/api/playlists").json() if x["id"] == pid)
    assert row["smart"] and row["tracks"] == len(p["items"]) > 0
    assert user_client.post(f"/api/playlists/{pid}/tracks", json={"release_id": a}).status_code == 400
    assert admin_client.get(f"/api/playlists/{pid}").status_code == 404
    c.close()


def test_other_formats_are_indexed_and_transcoded(admin_client, library, settings, monkeypatch):
    import shutil, subprocess
    from app import db, routes_media
    from app.scanner import scan_structure, scan_tags
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg absent")
    folder = settings.music_root / "Singles" / "Tone-Sine-WEB-FLAC-2020-GRP"
    folder.mkdir(parents=True)
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=1", "-metadata", "title=Sine",
                    str(folder / "01-tone-sine.flac")], check=True)
    c = db.connect(settings.data_dir)
    scan_structure(c, settings.music_root, now=4000.0); scan_tags(c, settings.music_root); c.commit(); c.close()
    rel = admin_client.get("/api/release-by-name", params={"name": folder.name}).json()
    t = rel["tracks"][0]
    assert t["title"] == "Sine" and t["filename"].endswith(".flac") and 0.9 < t["duration"] < 1.1
    assert (rel["artist"], rel["title"], rel["source"], rel["year"]) == ("Tone", "Sine", "WEB", 2020)   # « FLAC » hors du titre
    r = admin_client.get(f"/api/tracks/{t['id']}/stream")
    assert r.status_code == 200 and r.headers["content-type"] == "audio/mpeg" and r.content[:3] in (b"ID3", b"\xff\xfb\xe0"[:3])
    assert len(list((settings.data_dir / "transcode").glob("*.mp3"))) == 1
    part = admin_client.get(f"/api/tracks/{t['id']}/stream", headers={"Range": "bytes=0-9"})
    assert part.status_code == 206 and len(part.content) == 10                      # déplacement dans la piste
    assert admin_client.get(f"/api/tracks/{t['id']}/stream?download=1").content[:4] == b"fLaC"   # l'original
    assert admin_client.get(f"/api/tracks/{t['id']}/waveform").status_code == 200
    # sans ffmpeg : erreur claire, pas de fichier servi à moitié
    for f in (settings.data_dir / "transcode").glob("*"):
        f.unlink()
    monkeypatch.setattr(routes_media.shutil, "which", lambda name: None)
    assert admin_client.get(f"/api/tracks/{t['id']}/stream").status_code == 503
    assert not list(settings.music_root.rglob("*.mp3.part")) and not list(settings.music_root.rglob("*.part"))


def test_filters_accept_several_values(user_client, library):
    names = lambda qs: sorted(x["name"] for x in user_client.get("/api/releases?" + qs).json()["items"])
    B = "Bicep-Glue-(NT123)-WEB-2017-PWT"
    assert names("genre=House&genre=Techno") == [A, B] and names("genre=House") == [A]
    assert names("year=2015&year=2017") == [A, B] and names("year=2015&decade=2000") == [A, "VA-Big_Mix-2CD-2003-GRP"]
    assert names("genre=House&genre=Techno&year=2017") == [B] and names("decade=1980") == []
    assert user_client.get("/api/mix?genre=House&genre=Techno").status_code == 200
    assert [g["name"] for g in user_client.get("/api/groups?by=category").json()] == ["Singles", "Albums"]
    grp = lambda qs: sorted(g["name"] for g in user_client.get("/api/groups?by=artist&" + qs).json())
    assert grp("genre=House&genre=Techno") == ["A-Trak", "Bicep"] and grp("year=2015&decade=2000") == ["A-Trak", "VA"]
    pid = user_client.post("/api/playlists", json={"name": "Deux genres", "rules": {"genre": ["House", "Techno"], "year": [2015, 2017]}}).json()["id"]
    assert len(user_client.get(f"/api/playlists/{pid}").json()["items"]) == 3


def test_truncated_id3v1_title_is_completed_from_filename():
    from app.naming import complete_title as ct
    cut = "Dajae\u00b0-\u00b0Everyday My Life (Cevi"
    assert len(cut) == 30
    assert ct(cut, "01-dajae-everyday_my_life_(cevin_fisher_mix).mp3") == cut + "n fisher mix)"
    assert ct(cut, "track01.mp3") == cut and ct("Short title", "01-short_title_extended.mp3") == "Short title"
    assert ct("Only If I (Alex Megane Radio E", "02-foo-only_if_i_(alex_megane_radio_edit)-etlmp3.mp3") == "Only If I (Alex Megane Radio Edit)"
    assert ct("The Black Lodge (Original Mix)", "01-x-the_black_lodge_(original_mix)-eithel.mp3") == "The Black Lodge (Original Mix)"
    assert ct("Hotel St Tropez La Suite (Cd1)", "01-hotel_st_tropez_la_suite_(cd1)_jimmys_bar.mp3") == "Hotel St Tropez La Suite (Cd1)"
    assert ct(None, "x.mp3") is None and ct("A" * 30, "01-" + "a" * 30 + ".mp3") == "A" * 30


def test_track_search_filters_and_title_order(user_client, library):
    titles = lambda qs: [t["title"] for t in user_client.get("/api/tracks?" + qs).json()["items"]]
    assert titles("q=e") == ["Glue", "Ibanez", "Ibanez Dub", "One"]                       # par titre
    assert titles("q=e&genre=House") == ["Ibanez", "Ibanez Dub"] and titles("q=e&year=2017&year=2003") == ["Glue", "One"]
    assert titles("q=e&category=Albums&genre=House") == [] and titles("q=e&decade=2010") == ["Glue", "Ibanez", "Ibanez Dub"]


def test_backup_daily_copy_rotation_and_admin(admin_client, user_client, library, settings, tmp_path):
    import sqlite3, time
    from app import backup, db
    assert admin_client.get("/api/admin/backup").json() == {"configured": False, "hour": 3, "last": None, "last_ok_at": None, "late": False}
    assert admin_client.post("/api/admin/backup").status_code == 400 and user_client.get("/api/admin/backup").status_code == 403
    settings.backup_dir, settings.stack_dir = tmp_path / "nas", tmp_path / "pile"
    settings.backup_dir.mkdir(); settings.stack_dir.mkdir()
    (settings.stack_dir / "compose.yaml").write_text("services: {}"); (settings.stack_dir / ".env").write_text("X=1")
    at = lambda day, hour: time.mktime((2026, 11, day, hour, 30, 0, 0, 0, -1))
    c = db.connect(settings.data_dir)
    assert not backup.due(c, settings, at(10, 2)) and backup.due(c, settings, at(10, 3))      # à partir de 3 h
    for day in range(1, 10):                                                                    # neuf jours : sept gardés
        assert backup.run(settings, at(day, 3))["ok"]
    days = sorted(p.name for p in settings.backup_dir.iterdir())
    assert days == [f"2026-11-0{d}" for d in range(3, 10)]
    last = settings.backup_dir / "2026-11-09"
    copy = sqlite3.connect(last / "mp3scene.db")
    assert copy.execute("SELECT COUNT(*) FROM releases").fetchone()[0] == 3 and sorted(p.name for p in (last / "config").iterdir()) == [".env", "compose.yaml"]
    copy.close()
    assert not backup.due(c, settings, at(9, 5)) and backup.due(c, settings, at(10, 9))        # faite ; puis nuit manquée rattrapée
    # un dossier illisible : l'échec est inscrit, rien n'est supprimé, pas de nouvelle tentative avant une heure
    good, settings.backup_dir = settings.backup_dir, tmp_path / "absent" / "x"
    (tmp_path / "absent").write_text("fichier, pas dossier")
    bad = backup.run(settings, at(10, 9))
    assert not bad["ok"] and bad["message"] and len(list(good.iterdir())) == 7
    assert not backup.due(c, settings, at(10, 9) + 600) and backup.due(c, settings, at(10, 11))
    st = backup.status(c, settings, at(12, 9))
    assert st["late"] and st["last"]["ok"] is False and st["last_ok_at"] == at(9, 3)
    c.close()
    settings.backup_dir = good
    r = admin_client.post("/api/admin/backup")
    assert r.status_code == 200 and r.json()["size"] > 0 and admin_client.get("/api/admin/backup").json()["last"]["ok"] is True


def test_categories_keep_a_fixed_order():
    from app.routes_library import _category_rank
    names = ["Albums", "03.Live & Radio", "02.Various Artists - Compilations", "Zzz", "01.Singles", "Autres"]
    assert sorted(names, key=_category_rank) == ["01.Singles", "Albums", "02.Various Artists - Compilations", "03.Live & Radio", "Autres", "Zzz"]
