import pytest
from app import db
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
    assert [(f["name"], f["n"]) for f in s["formats"]] == [("mp3", 5)] and s["formats"][0]["size"] > 0
    assert sum(g["n"] for g in s["groups"]) == 3 and all(g["size"] > 0 for g in s["groups"])   # releases par groupe
    cats = user_client.get("/api/groups?by=category&artist=A-Trak").json()   # page d'un artiste : ses releases par catégorie
    assert len(cats) == 1 and cats[0]["releases"] == 1 and cats[0]["size"] > 0
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


def test_admin_usage_counts_all_accounts(admin_client, user_client, library):
    assert user_client.get("/api/admin/usage").status_code == 403
    empty = admin_client.get("/api/admin/usage").json()
    assert empty["plays"] == 0 and empty["days"] == [] and empty["accounts"] == 2
    tid = lambda c, name: c.get("/api/release-by-name", params={"name": name}).json()["tracks"][0]["id"]
    for c, name in ((user_client, A), (user_client, A), (admin_client, "Bicep-Glue-(NT123)-WEB-2017-PWT")):
        assert c.post(f"/api/history/{tid(c, name)}").status_code == 204
    u = admin_client.get("/api/admin/usage?days=7").json()
    assert (u["plays"], u["distinct_tracks"], u["active"]) == (3, 2, 2) and u["duration"] > 0 and len(u["days"]) == 1 and u["days"][0]["n"] == 3
    assert [(x["name"], x["n"]) for x in u["users"]] == [("user", 2), ("admin", 1)] and len(u["tracks"]) == 2
    assert [(x["name"], x["n"]) for x in u["artists"]] == [("A-Trak", 2), ("Bicep", 1)] and u["releases"][0] == {"name": A, "n": 2, "duration": u["releases"][0]["duration"]}
    assert [x["name"] for x in u["genres"]] == ["House", "Techno"]


def test_truncated_artist_search_original_stream_and_custom_cover(admin_client, user_client, library, settings, make_mp3):
    import io, shutil, subprocess
    from PIL import Image
    from app import db
    from app.naming import complete_title as ct
    from app.scanner import scan_structure, scan_tags
    # artiste coupé à 30 caractères : complété jusqu'au tiret qui le sépare du titre
    cut = "Bob Sinclar Feat Gary Nesta Pi"
    assert len(cut) == 30 and ct(cut, "01-bob_sinclar_feat_gary_nesta_pine-love_generation-grp.mp3", artist=True) == cut + "ne"
    assert ct("Short", "01-short_name-title.mp3", artist=True) == "Short"
    # recherche : un mot de la partie coupée d'un titre de 30 caractères est trouvé par le nom du fichier
    folder = settings.music_root / "Singles" / "Dajae-Everyday_My_Life-WEB-2001-GRP"
    folder.mkdir(parents=True)
    make_mp3(folder / "01-dajae-everyday_my_life_(cevin_fisher_mix).mp3", title="Dajae - Everyday My Life (Cevi", artist="Dajae")
    c = db.connect(settings.data_dir)
    scan_structure(c, settings.music_root, now=5000.0); scan_tags(c, settings.music_root); c.commit()
    hit = user_client.get("/api/tracks?q=fisher").json()["items"]
    assert [x["title"] for x in hit] == ["Dajae - Everyday My Life (Cevin fisher mix)"] and len("Dajae - Everyday My Life (Cevi") == 30 and user_client.get("/api/tracks?q=zzz").json()["items"] == []
    # pochette déposée à la main : réservée à l'administrateur, validée, servie avant celle du dossier, retirable
    rid = hit[0]["release_id"]
    png = io.BytesIO(); Image.new("RGB", (2400, 1200), (200, 30, 30)).save(png, "PNG")
    put = lambda cl, data: cl.put(f"/api/admin/releases/{rid}/cover", content=data, headers={"Content-Type": "image/png"}).status_code
    assert put(user_client, png.getvalue()) == 403 and put(admin_client, b"pas une image") == 400 and put(admin_client, b"") == 400
    assert user_client.get(f"/api/releases/{rid}/cover").status_code == 404
    assert put(admin_client, png.getvalue()) == 204
    got = user_client.get(f"/api/releases/{rid}/cover")
    assert got.status_code == 200 and got.headers["content-type"] == "image/jpeg" and Image.open(io.BytesIO(got.content)).size == (1600, 800)
    assert user_client.get(f"/api/releases/{rid}/thumb").status_code == 200 and user_client.get(f"/api/releases/{rid}").json()["custom_cover"] is True
    c.execute("UPDATE releases SET has_cover=0 WHERE id=?", (rid,)); c.commit()
    assert rid not in admin_client.get("/api/admin/quality?kind=no_cover&ids=1").json()["ids"]
    assert not list(settings.music_root.rglob("*.jpg"))                       # rien n'est écrit dans la musique
    assert admin_client.delete(f"/api/admin/releases/{rid}/cover").status_code == 204
    assert user_client.get(f"/api/releases/{rid}/cover").status_code == 404 and admin_client.get("/api/admin/overrides").json() == []
    c.close()
    # qualité d'origine : un FLAC est servi tel quel sur demande, un MP3 ne change pas
    mp3 = user_client.get(f"/api/tracks/{hit[0]['id']}/stream?original=1")
    assert mp3.status_code == 200 and mp3.headers["content-type"] == "audio/mpeg"
    if shutil.which("ffmpeg"):
        f = settings.music_root / "Singles" / "Tone-Sine-WEB-FLAC-2020-GRP"
        f.mkdir()
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=1", str(f / "01-tone-sine.flac")], check=True)
        c = db.connect(settings.data_dir)
        scan_structure(c, settings.music_root, now=6000.0); scan_tags(c, settings.music_root); c.commit(); c.close()
        tid = user_client.get("/api/release-by-name", params={"name": f.name}).json()["tracks"][0]["id"]
        raw = user_client.get(f"/api/tracks/{tid}/stream?original=1", headers={"Range": "bytes=0-3"})
        assert raw.status_code == 206 and raw.content == b"fLaC" and raw.headers["content-type"] == "audio/flac"
        assert user_client.get(f"/api/tracks/{tid}/stream").headers["content-type"] == "audio/mpeg"


def test_chapters_tech_artist_years_and_activity(admin_client, user_client, library, settings):
    from app import cue
    text = 'PERFORMER "2ManyDJs"\nTITLE "Mix"\nFILE "01-a-trak--ibanez.mp3" MP3\n  TRACK 01 AUDIO\n    TITLE "Intro"\n    PERFORMER "2ManyDJs"\n' \
           '    INDEX 01 00:00:00\n  TRACK 02 AUDIO\n    TITLE "Mediate"\n    PERFORMER "INXS"\n    INDEX 00 01:50:00\n    INDEX 01 01:55:05\n' \
           '  TRACK 03 AUDIO\n    TITLE "Sans index"\n'
    parts = cue.parse(text)["01-a-trak--ibanez.mp3"]
    assert [(p["artist"], p["title"], round(p["start"], 2)) for p in parts] == [("2ManyDJs", "Intro", 0.0), ("INXS", "Mediate", 115.07)]
    assert cue.parse("n'importe quoi\n") == {}
    rel = user_client.get("/api/release-by-name", params={"name": A}).json()
    assert user_client.get(f"/api/releases/{rel['id']}/chapters").json() == {}          # pas de .cue : rien
    (settings.music_root / rel["path"] / "mix.cue").write_text(text)
    from app import db
    from app.scanner import _scan_cues
    c = db.connect(settings.data_dir)
    c.execute("UPDATE releases SET cue_done=NULL WHERE id=?", (rel["id"],)); c.commit()   # comme après un changement du dossier
    ch = user_client.get(f"/api/releases/{rel['id']}/chapters").json()                    # pas encore en base : lu dans le fichier
    assert [x["title"] for x in ch[str(rel["tracks"][0]["id"])]] == ["Intro", "Mediate"]
    _scan_cues(c, settings.music_root, lambda: False)                                     # le scan les met en base
    assert c.execute("SELECT COUNT(*) FROM chapters").fetchone()[0] == 2 and c.execute("SELECT cue_done FROM releases WHERE id=?", (rel["id"],)).fetchone()[0] == 1
    c.close()
    tid = rel["tracks"][0]["id"]
    assert [x["title"] for x in user_client.get(f"/api/tracks/{tid}/chapters").json()] == ["Intro", "Mediate"]
    assert user_client.get(f"/api/tracks/{rel['tracks'][1]['id']}/chapters").json() == []
    # recherche : un morceau joué dans un mix est trouvé par son chapitre, avec l'endroit où il commence
    hit = user_client.get("/api/tracks?q=inxs mediate").json()["items"]
    assert [x["id"] for x in hit] == [tid] and round(hit[0]["chapter"]["start"]) == 115 and hit[0]["chapter"]["artist"] == "INXS"
    assert "chapter" not in user_client.get("/api/tracks?q=ibanez").json()["items"][0]
    # position gardée dans une longue piste, par utilisateur
    assert user_client.get(f"/api/positions/{tid}").json() == {"pos": 0}
    assert user_client.put(f"/api/positions/{tid}", json={"pos": 2592.5}).status_code == 204
    assert user_client.get(f"/api/positions/{tid}").json() == {"pos": 2592.5} and admin_client.get(f"/api/positions/{tid}").json() == {"pos": 0}
    assert user_client.put(f"/api/positions/{tid}", json={"pos": 0}).status_code == 204 and user_client.get(f"/api/positions/{tid}").json() == {"pos": 0}
    assert user_client.put("/api/positions/99999", json={"pos": 5}).status_code == 204 and user_client.get("/api/positions/99999").json() == {"pos": 0}
    ch = user_client.get(f"/api/releases/{rel['id']}/chapters").json()
    assert list(ch) == [str(rel["tracks"][0]["id"])] and [c["title"] for c in ch[str(rel["tracks"][0]["id"])]] == ["Intro", "Mediate"]
    assert user_client.get("/api/releases/99999/chapters").status_code == 404
    # page d'un artiste : les mixes où un chapitre est de lui, à la casse près, avec l'endroit où il commence
    hit = user_client.get("/api/tracks?mixes=inxs").json()["items"]
    assert [x["id"] for x in hit] == [tid] and hit[0]["chapter"]["title"] == "Mediate"
    assert user_client.get("/api/tracks?mixes=Personne").json()["items"] == []
    # détails techniques lus dans le fichier
    tech = user_client.get(f"/api/tracks/{rel['tracks'][0]['id']}/tech").json()
    assert tech["format"] == "MP3" and tech["sample_rate"] == 44100 and tech["bitrate"] == 128000 and tech["size"] > 0
    assert user_client.get("/api/tracks/99999/tech").status_code == 404
    # chronologie d'un artiste : ses releases par année
    assert user_client.get("/api/groups?by=year&artist=A-Trak").json() == [{"name": 2015, "releases": 1, "size": rel["size"]}]
    # journal : connexion, action d'administration réussie (pas l'échec), écoutes à la demande
    assert user_client.get("/api/admin/activity").status_code == 403
    assert admin_client.patch(f"/api/admin/releases/{rel['id']}", json={"genre": "Techno"}).status_code == 204
    assert admin_client.patch("/api/admin/releases/99999", json={"genre": "x"}).status_code == 404
    assert user_client.post(f"/api/history/{rel['tracks'][0]['id']}").status_code == 204
    log = admin_client.get("/api/admin/activity").json()["items"]
    assert [(x["user"], x["action"]) for x in log[:2]] == [("user", "Écoute"), ("admin", "Correction")] and log[1]["detail"] == A
    assert {x["action"] for x in log} >= {"Connexion", "Correction", "Écoute"} and [x["action"] for x in log].count("Correction") == 1
    assert "Écoute" not in {x["action"] for x in admin_client.get("/api/admin/activity?plays=0").json()["items"]}


def test_similar_follows_series_and_label_for_compilations(user_client, library, settings):
    from app import db
    from app.routes_library import _series
    assert _series("Global Underground 47 Joseph Capriati Montreal") == "Global Underground"
    assert _series("Kontor Top Of The Clubs Vol. 63") == "Kontor Top Of The Clubs" and _series("Hits Vol 3") == "Hits Vol"
    assert _series("Ibanez") is None and _series("Big Mix") is None and _series("Hed Kandi 2005") == "Hed Kandi" and _series(None) is None
    names = lambda rid: [x["name"] for x in user_client.get(f"/api/releases/{rid}/similar").json()]
    rel = {x["name"]: x for x in user_client.get("/api/releases").json()["items"]}
    va, b = rel["VA-Big_Mix-2CD-2003-GRP"]["id"], rel["Bicep-Glue-(NT123)-WEB-2017-PWT"]["id"]
    assert names(va) == []                                              # compilation sans série, label ni genre commun
    c = db.connect(settings.data_dir)
    c.execute("UPDATE releases SET title='Global Underground 47 Montreal' WHERE id=?", (va,))
    c.execute("UPDATE releases SET title='Global Underground 12 Ibiza' WHERE id=?", (b,)); c.commit()
    assert names(va) == ["Bicep-Glue-(NT123)-WEB-2017-PWT"]              # même série
    # page de la série : volumes dans l'ordre, numéros absents à partir de trois volumes, autre série écartée
    assert user_client.get(f"/api/releases/{va}").json()["series"] == "Global Underground"
    got = user_client.get("/api/series?name=global underground").json()
    assert [(x["id"], x["volume"]) for x in got["items"]] == [(b, 12), (va, 47)] and got["missing"] == []
    a = rel[A]["id"]
    c.execute("UPDATE releases SET title='Global Underground 010 Athens' WHERE id=?", (a,)); c.commit()
    got = user_client.get("/api/series?name=Global Underground").json()
    assert [x["volume"] for x in got["items"]] == [10, 12, 47] and got["missing"] == [11, *range(13, 47)]
    c.execute("UPDATE releases SET title='Global Underground Nubreed 8' WHERE id=?", (a,)); c.commit()
    assert [x["volume"] for x in user_client.get("/api/series?name=Global Underground").json()["items"]] == [12, 47]
    assert user_client.get("/api/series?name=Ibanez").json()["items"] == []
    c.execute("UPDATE releases SET title='Ibanez' WHERE id=?", (a,)); c.commit()
    c.execute("UPDATE releases SET title='Glue', label='Ninja Tune' WHERE id=?", (b,))
    c.execute("UPDATE releases SET label='Ninja Tune' WHERE id=?", (va,)); c.commit(); c.close()
    assert names(va) == ["Bicep-Glue-(NT123)-WEB-2017-PWT"]              # même label


def test_cover_search_proposes_signed_images_and_saves_the_chosen_one(admin_client, user_client, library, settings, monkeypatch):
    import io
    from PIL import Image
    from app import coversearch
    rid = user_client.get("/api/release-by-name", params={"name": A}).json()["id"]
    asked = []
    def fake(url, headers=None):
        asked.append(url)
        if "deezer" in url:
            return {"data": [{"cover_xl": "https://cdn.example/xl.jpg", "cover_medium": "https://cdn.example/m.jpg", "title": "Ibanez", "artist": {"name": "A-Trak"}}]}
        if "itunes" in url:
            raise OSError("panne")                                        # une source en panne ne bloque pas les autres
        assert headers == {"Authorization": "Discogs token=jeton"}
        if "release_title=Ibanez" not in url:   # titre avec suffixe, titre raccourci : rien ; la référence de catalogue trouve
            return {"results": [{"cover_image": "https://i.example/c.jpg", "thumb": "https://i.example/t"}] if "catno=BL-16188+X" in url else []}
        return {"results": [{"cover_image": "https://i.example/spacer.gif", "thumb": "https://i.example/s"},      # sans image
                            {"cover_image": "http://sans-https.example/a.jpg", "thumb": "https://i.example/t"},
                            {"cover_image": "https://i.example/a.jpg", "thumb": "https://i.example/t", "title": "A-Trak - Ibanez"}]}
    monkeypatch.setattr(coversearch, "_json", fake)
    assert [x["url"] for x in coversearch.candidates("A-Trak", "Ibanez", "jeton")] == ["https://cdn.example/xl.jpg", "https://i.example/a.jpg"]
    assert [x["url"] for x in coversearch.candidates("A-Trak", "Autre EP", "jeton", "A-Trak-Autre_EP-(BL-16188_X)-WEB-2008-GRP")][-1] == "https://i.example/c.jpg"
    assert [x for x in asked if "discogs" in x and "Autre" in x][-1].count("EP") == 0   # second essai sans « EP »
    assert not [x for x in coversearch.candidates("X", "Live", "jeton", "X-Live_(18-11-1995)-TAPE") if x["source"] == "Discogs"]  # une date n'est pas une référence
    asked.clear()
    assert user_client.get(f"/api/admin/releases/{rid}/cover/search").status_code == 403
    got = admin_client.get(f"/api/admin/releases/{rid}/cover/search").json()
    assert got["web"] is False and [x["source"] for x in got["items"]] == ["Deezer"] and len(asked) == 2 and "A-Trak" in asked[0]
    pick = {"url": got["items"][0]["url"], "sig": got["items"][0]["sig"]}
    buf = io.BytesIO(); Image.new("RGB", (40, 40), "red").save(buf, "PNG")
    monkeypatch.setattr(coversearch, "fetch", lambda url: buf.getvalue())
    post = lambda body: admin_client.post(f"/api/admin/releases/{rid}/cover/fetch", json=body).status_code
    assert post({"url": "https://ailleurs.example/x.jpg", "sig": pick["sig"]}) == 400     # adresse jamais proposée
    assert post(pick) == 204 and user_client.get(f"/api/releases/{rid}").json()["custom_cover"] is True
    monkeypatch.undo()
    # téléchargement : https, hôte public, jamais le serveur ni le réseau local
    assert not coversearch.public_host("127.0.0.1") and not coversearch.public_host("192.168.1.10") and not coversearch.public_host("localhost")
    for bad in ("http://example.com/a.jpg", "https://127.0.0.1/a.jpg", "file:///etc/passwd"):
        try:
            coversearch.fetch(bad); raise AssertionError(bad)
        except ValueError:
            pass
    assert admin_client.post(f"/api/admin/releases/{rid}/cover/fetch",
                             json={"url": "https://127.0.0.1/a.jpg", "sig": coversearch.sign(settings.secret_key, "https://127.0.0.1/a.jpg")}).status_code == 502


def test_similar_falls_back_to_the_set_performer_then_the_genre(user_client, library, settings):
    from app import db
    names = lambda rid: [x["name"] for x in user_client.get(f"/api/releases/{rid}/similar").json()]
    rel = {x["name"]: x for x in user_client.get("/api/releases").json()["items"]}
    va, a = rel["VA-Big_Mix-2CD-2003-GRP"]["id"], rel[A]["id"]
    c = db.connect(settings.data_dir)
    # set d'un festival : l'artiste connu est le festival, celui qui joue est dans le nom avant « _Live »
    c.execute("UPDATE releases SET name='Fest_2025-Bicep_Live-STREAM-08-16-2025-GRP', artist='Fest 2025', tag_artist=NULL,"
              " title='STREAM-08-16', genre='Hardcore', year=2025, label=NULL WHERE id=?", (va,)); c.commit()
    assert names(va) == ["Bicep-Glue-(NT123)-WEB-2017-PWT"]              # les releases de celui qui joue
    c.execute("UPDATE releases SET genre='Hardcore', year=1999 WHERE id=?", (a,)); c.commit()
    assert names(va) == ["Bicep-Glue-(NT123)-WEB-2017-PWT", A]           # puis le même genre, quelle que soit l'année


def test_a_meaningless_tag_artist_gives_way_to_the_release_name(user_client, library, settings):
    from app import db
    c = db.connect(settings.data_dir)
    c.execute("UPDATE releases SET tag_artist='[Notag]' WHERE name=?", (A,)); c.commit()
    db.categorize(c); c.commit()
    assert user_client.get("/api/release-by-name", params={"name": A}).json()["artist"] == "A-Trak"   # celui du nom
    assert not [g for g in user_client.get("/api/groups?by=artist").json() if g["name"] == "[Notag]"]


def test_dated_compilations_of_a_known_series_are_filed_like_the_series(user_client, library, settings):
    from app import db
    c = db.connect(settings.data_dir)
    one = lambda rid: user_client.get(f"/api/releases/{rid}").json()
    rel = {x["name"]: x for x in user_client.get("/api/releases").json()["items"]}
    a, b = rel[A]["id"], rel["Bicep-Glue-(NT123)-WEB-2017-PWT"]["id"]
    c.execute("UPDATE releases SET name='1999_-_Hed_kandi_-_Nu_Cool_Vol._2_[2CD]', artist='VA', tag_artist='Artist', title='Hed kandi', year=NULL, label=NULL WHERE id=?", (a,))
    c.execute("UPDATE releases SET name='2019 - Some Artist - An Album [2CD]', tag_artist=NULL WHERE id=?", (b,)); c.commit()
    before = dict(c.execute("SELECT artist, title, year FROM releases WHERE id=?", (b,)).fetchone())
    db.categorize(c); c.commit()
    got = one(a)
    assert (got["artist"], got["title"], got["year"], got["label"]) == ("VA", "Hed Kandi Nu Cool Vol. 2", 1999, "Hed Kandi Records")
    assert got["name"] == "VA-Hed_Kandi_Nu_Cool_Vol._2-2CD-1999"          # nom affiché : comme le reste de la série
    names = lambda letter: [x["name"] for x in user_client.get("/api/releases", params={"letter": letter}).json()["items"]]
    assert names("H") == [got["name"]] and got["name"] not in names("V")   # initiale sans le « VA- »
    assert names("#") == ["2019 - Some Artist - An Album [2CD]"] and user_client.get("/api/releases?letter=ab").status_code == 422
    assert dict(c.execute("SELECT artist, title, year FROM releases WHERE id=?", (b,)).fetchone()) == before   # série inconnue : intacte


def test_a_last_segment_starting_with_an_underscore_is_not_a_group():
    from app.naming import group
    assert group("_Ballroom_Tunes_6") == ("P2P", None)        # fin d'un titre
    assert group("_XDS") == ("XDS", None) and group("AOV_INT") == ("AOV", None)


def test_a_tag_artist_wrapped_in_a_decorative_symbol_is_unwrapped(user_client, library, settings):
    from app import db
    from app.naming import unwrap
    assert unwrap("✖ Tristan Garner ✖") == "Tristan Garner" and unwrap("★★ X ★★") == "X"
    assert [unwrap(x) for x in ("A+", "200°", "Life+", "✖", "✖✖", None)] == ["A+", "200°", "Life+", "✖", "✖✖", None]
    c = db.connect(settings.data_dir)
    rid = user_client.get("/api/release-by-name", params={"name": A}).json()["id"]
    c.execute("UPDATE tracks SET artist='✖ A-Trak ✖' WHERE release_id=?", (rid,))
    c.execute("UPDATE releases SET tag_artist='✖ A-Trak ✖' WHERE id=?", (rid,)); c.commit()
    db.classify(c); c.commit()
    got = user_client.get(f"/api/releases/{rid}").json()
    assert got["artist"] == "A-Trak" and {t["artist"] for t in got["tracks"]} == {"A-Trak"}


def test_search_summary_counts_releases_by_category(user_client, library):
    rows = user_client.get("/api/release-summary").json()
    assert sum(r["releases"] for r in rows) == 3 and all(r["size"] > 0 for r in rows) and {r["name"] for r in rows} == {"Albums", "Singles"}
    one = user_client.get("/api/release-summary", params={"q": "Ibanez"}).json()
    assert len(one) == 1 and one[0]["releases"] == 1
    assert user_client.get("/api/release-summary", params={"q": "Ibanez", "category": "Introuvable"}).json() == []


def test_track_search_summary_counts_tracks_by_category(user_client, library):
    rows = user_client.get("/api/tracks", params={"q": "a", "summary": 1}).json()
    listed = user_client.get("/api/tracks", params={"q": "a", "limit": 500}).json()["items"]
    assert rows and sum(r["tracks"] for r in rows) == len(listed) and all(r["size"] > 0 for r in rows)
    assert user_client.get("/api/tracks", params={"summary": 1}).json() == []


def test_classify_rereads_titles_left_by_the_old_parser(tmp_path):
    import sqlite3
    from app import db
    from app.naming import parse_release_name
    name = "VA-La_Rocca_-_Ballroom_Tunes_6"
    assert parse_release_name(name, legacy=True)["title"] == "La Rocca"
    db.init(tmp_path)
    conn = db.connect(tmp_path)
    for path, title in (("a", "La Rocca"), ("b", "Corrigé à la main")):
        conn.execute("INSERT INTO releases(path, name, parent, category, mtime, added_at, size, track_count, has_nfo, artist, title)"
                     " VALUES (?,?,'','Compilations',0,0,1,0,0,'VA',?)", (path, name, title))
    db.classify(conn)
    assert [r[0] for r in conn.execute("SELECT title FROM releases ORDER BY path")] == ["La Rocca - Ballroom Tunes 6", "Corrigé à la main"]


def test_series_are_listed_from_three_volumes(user_client, settings):
    conn = db.connect(settings.data_dir)
    for i, t in enumerate(["Kontor Top Of The Clubs Vol 1", "Kontor Top Of The Clubs 2", "Kontor Top Of The Clubs Vol. 4",
                           "Other Series 1", "Other Series 2", "Seul"]):
        conn.execute("INSERT INTO releases(path, name, parent, category, mtime, added_at, size, track_count, has_nfo, artist, title)"
                     " VALUES (?,?,'','Compilations',0,0,10,0,0,'VA',?)", (f"s{i}", f"VA-{i}", t))
    conn.commit()
    assert user_client.get("/api/groups", params={"by": "series"}).json() == [{"name": "Kontor Top Of The Clubs", "releases": 3, "size": 30, "series": 1}]


def test_track_versions_share_artist_and_song(user_client, library, settings):
    conn = db.connect(settings.data_dir)
    one = conn.execute("SELECT id FROM tracks WHERE title='Ibanez'").fetchone()[0]
    rel = conn.execute("SELECT release_id FROM tracks WHERE title='Glue'").fetchone()[0]
    for title, artist in (("Ibanez (Club Mix)", "A-Trak feat. Someone"), ("Ibanez (Cover)", "Bicep"), ("Ibanezzz", "A-Trak")):
        conn.execute("INSERT INTO tracks(release_id, relpath, size, title, artist) VALUES (?,?,1,?,?)", (rel, title + ".mp3", title, artist))
    conn.commit()
    assert [t["title"] for t in user_client.get(f"/api/tracks/{one}/versions").json()["items"]] == ["Ibanez (Club Mix)"]
    assert user_client.get("/api/tracks/999999/versions").status_code == 404


def test_artist_info_gives_years_labels_partners_and_top(user_client, library, settings):
    conn = db.connect(settings.data_dir)
    rid, tid = conn.execute("SELECT release_id, id FROM tracks WHERE title='Ibanez'").fetchone()
    conn.execute("UPDATE releases SET label='Fool''s Gold' WHERE id=?", (rid,))
    conn.execute("INSERT INTO tracks(release_id, relpath, size, title, artist) VALUES (?,'x.mp3',1,'X','A-Trak feat. Andrew Wyatt')", (rid,))
    conn.execute("INSERT INTO plays(user_id, track_id, played_at) SELECT id, ?, 1 FROM users WHERE username='user'", (tid,))
    conn.commit()
    info = user_client.get("/api/artist-info", params={"name": "A-Trak"}).json()
    assert info["lists"]["releases"]["n"] == 1 and info["lists"]["releases"]["size"] > 0 and info["lists"]["mixes"] == {"n": 0, "size": 0}
    assert set(info["lists"]) == {"releases", "with", "appears", "mixes", "remixes"} and info["labels"] == [{"name": "Fool's Gold", "releases": 1}]
    assert info["with"] == [{"name": "Andrew Wyatt", "tracks": 1}] and [(x["id"], x["plays"]) for x in info["top"]] == [(rid, 1)]


def test_tag_that_adds_a_mention_to_the_name_artist_is_dropped():
    from app import artists
    pairs = {1: ("Daft Punk", "Daft Punk - Live"), 2: ("Daft Punk", "Daft Punk [BMi D0MiNAti0N]"), 3: ("Daft Punk", "Daft Punk"),
             4: ("VA", "Bob Sinclar - Live")}  # un autre artiste que celui du nom : gardé
    assert artists._step(pairs, {}) == {1: ("Daft Punk", None), 2: ("Daft Punk", None), 3: ("Daft Punk", "Daft Punk"),
                                         4: ("VA", "Bob Sinclar - Live")}


def test_series_missing_suggest_and_bpm_filter(user_client, library, settings):
    conn = db.connect(settings.data_dir)
    for i, t in enumerate(["Serious Beats 1", "Serious Beats 2", "Serious Beats 5"]):
        conn.execute("INSERT INTO releases(path, name, parent, category, mtime, added_at, size, track_count, has_nfo, artist, title, label)"
                     " VALUES (?,?,'','Compilations',0,0,10,0,0,'VA',?,'Serious Label')", (f"m{i}", f"VA-m{i}", t))
    conn.execute("UPDATE tracks SET bpm=128 WHERE title='Ibanez'")
    conn.commit()
    assert user_client.get("/api/series-missing").json() == [{"name": "Serious Beats", "releases": 3, "missing": [3, 4]}]
    s = user_client.get("/api/suggest", params={"q": "serious"}).json()
    assert s["series"] == [{"name": "Serious Beats", "releases": 3}] and s["labels"] == [{"name": "Serious Label", "releases": 3}]
    assert user_client.get("/api/suggest", params={"q": "trak"}).json()["artists"][0]["name"] == "A-Trak"
    got = user_client.get("/api/tracks", params={"q": "ibanez", "bpm_min": 120, "bpm_max": 130}).json()["items"]
    assert [(t["title"], t["bpm"]) for t in got] == [("Ibanez", 128.0)]


def test_admin_suggests_merges_and_clears_transcode_cache(admin_client, settings):
    conn = db.connect(settings.data_dir)
    for i, (artist, label) in enumerate([("Prodigy", "Yellow Productions"), ("Prodigy", "Yellow Productions"), ("The Prodigy", "Yellow"),
                                         ("Autre", "Bits & Pieces"), ("Autre", "Bits And Pieces"), ("Autre", "Bits & Pieces")]):
        conn.execute("INSERT INTO releases(path, name, parent, category, mtime, added_at, size, track_count, has_nfo, artist, label)"
                     " VALUES (?,?,'','Singles',0,0,1,0,0,?,?)", (f"g{i}", f"g{i}", artist, label))
    conn.commit()
    s = admin_client.get("/api/admin/suggestions").json()
    assert s["artists"] == [{"alias": "The Prodigy", "releases": 1, "target": "Prodigy", "target_releases": 2}]
    assert {(x["alias"], x["target"]) for x in s["labels"]} == {("Yellow", "Yellow Productions"), ("Bits And Pieces", "Bits & Pieces")}
    cache = settings.data_dir / "transcode"
    cache.mkdir()
    (cache / "1-1.mp3").write_bytes(b"x" * 10)
    assert admin_client.get("/api/admin/overview").json()["transcode_size"] == 10
    assert admin_client.delete("/api/admin/transcode", headers={"X-CSRF": "1"}).status_code == 204 and not list(cache.iterdir())


def test_remixes_of_an_artist_and_exact_cover_match(user_client, library, settings):
    from app import artists, coversearch
    assert artists.remixed("Crazy (Axwell Remix)", "Axwell") and artists.remixed("Crazy [Axwell & Ingrosso Dub]", "Axwell")
    assert not artists.remixed("Axwell Mix", "Axwell") and not artists.remixed("Crazy (Maxwell Remix)", "Axwell")
    conn = db.connect(settings.data_dir)
    rel = conn.execute("SELECT release_id FROM tracks WHERE title='Glue'").fetchone()[0]
    conn.execute("INSERT INTO tracks(release_id, relpath, size, title, artist) VALUES (?, 'r.mp3', 7, 'Glue (A-Trak Remix)', 'Bicep')", (rel,))
    conn.commit()
    assert [t["title"] for t in user_client.get("/api/tracks", params={"remixes": "A-Trak"}).json()["items"]] == ["Glue (A-Trak Remix)"]
    assert user_client.get("/api/artist-info", params={"name": "A-Trak"}).json()["lists"]["remixes"] == {"n": 1, "size": 7}
    assert coversearch.exact("Bob Sinclar", "Love Generation", "Bob Sinclar (2) - Love Génération!")
    assert coversearch.exact("VA", "Big Mix", "Various - Big Mix") and not coversearch.exact("VA", "Big Mix", "Someone - Big Mix")
    assert not coversearch.exact("Bob Sinclar", "Love Generation", "Bob Sinclar - Love Generation (Remixes)")


def test_genre_guess_group_info_and_track_artist_case(admin_client, settings):
    conn = db.connect(settings.data_dir)
    rows = [("Bob", "House", "Yellow", "GRP"), ("Bob", "House", "Yellow", "GRP"), ("Bob", "Techno", "Yellow", "XYZ"), ("Bob", None, None, "GRP"),
            ("VA", "Pop", None, "GRP"), ("VA", "Pop", None, "GRP"), ("VA", None, None, "GRP"), ("Seul", None, "Yellow", "GRP")]
    for i, (artist, genre, label, grp) in enumerate(rows):
        conn.execute("INSERT INTO releases(path, name, parent, category, mtime, added_at, size, track_count, has_nfo, artist, genre, label, grp, year)"
                     " VALUES (?,?,'','Singles',0,0,5,1,0,?,?,?,?,?)", (f"q{i}", f"q{i}", artist, genre, label, grp, 2000 + i))
        conn.execute("INSERT INTO tracks(release_id, relpath, size, artist) SELECT id, 'a.mp3', 1, ? FROM releases WHERE path=?",
                     ("AXWELL" if i else "Axwell", f"q{i}"))
    conn.commit()
    assert admin_client.get("/api/admin/quality").json()["no_genre"] == 3
    g = admin_client.get("/api/admin/genres/guess").json()  # Bob : House domine ; Seul : le label Yellow ; VA : rien
    assert g["count"] == 2 and {x["genre"] for x in g["sample"]} == {"House"}
    assert admin_client.post("/api/admin/genres/guess", headers={"X-CSRF": "1"}).status_code == 204
    assert admin_client.get("/api/admin/quality").json()["no_genre"] == 1
    info = admin_client.get("/api/group-info", params={"by": "label", "name": "Yellow"}).json()
    assert (info["n"], info["first"], info["last"]) == (4, 2000, 2007) and info["artists"][0] == {"name": "Bob", "releases": 3}
    assert info["others"] == [{"name": "GRP", "releases": 3}, {"name": "XYZ", "releases": 1}]
    db.merge_track_artists(conn)
    assert [r[0] for r in conn.execute("SELECT DISTINCT artist FROM tracks WHERE artist LIKE 'axwell'")] == ["Axwell"]  # la mixte l'emporte


def test_series_sharing_their_first_words_form_a_family(user_client, settings):
    conn = db.connect(settings.data_dir)
    titles = [f"Hed Kandi Beach House {i}" for i in (1, 2, 4)] + [f"Hed Kandi Nu Cool {i}" for i in (1, 2, 3)] + [f"Serious Beats {i}" for i in (1, 2, 3)]
    for i, t in enumerate(titles):
        conn.execute("INSERT INTO releases(path, name, parent, category, mtime, added_at, size, track_count, has_nfo, artist, title)"
                     " VALUES (?,?,'','Compilations',0,0,10,0,0,'VA',?)", (f"f{i}", f"VA-f{i}", t))
    conn.commit()
    rows = {g["name"]: g for g in user_client.get("/api/groups", params={"by": "series"}).json()}
    assert rows == {"Hed Kandi": {"name": "Hed Kandi", "releases": 6, "size": 60, "series": 2},
                    "Serious Beats": {"name": "Serious Beats", "releases": 3, "size": 30, "series": 1}}
    fam = user_client.get("/api/series", params={"name": "Hed Kandi"}).json()
    assert [(x["series"], x["volume"]) for x in fam["items"]] == [("Hed Kandi Beach House", 1), ("Hed Kandi Beach House", 2),
        ("Hed Kandi Beach House", 4), ("Hed Kandi Nu Cool", 1), ("Hed Kandi Nu Cool", 2), ("Hed Kandi Nu Cool", 3)]
    assert fam["subs"] == [{"name": "Hed Kandi Beach House", "releases": 3, "missing": [3]}, {"name": "Hed Kandi Nu Cool", "releases": 3, "missing": []}]
    one = user_client.get("/api/series", params={"name": "Hed Kandi Beach House"}).json()
    assert len(one["items"]) == 3 and one["missing"] == [3] and one["subs"] == []


def test_series_rules_genre_families_plays_and_nfo_search(admin_client, library, settings):
    from app import scanner
    conn = db.connect(settings.data_dir)
    titles = [f"Hed Kandi Beach House {i}" for i in (1, 2, 3)] + [f"Hed Kandi Nu Cool {i}" for i in (1, 2, 3)] + [f"Serious Beats {i}" for i in (1, 2, 3)]
    for i, t in enumerate(titles):
        conn.execute("INSERT INTO releases(path, name, parent, category, mtime, added_at, size, track_count, has_nfo, artist, title, genre)"
                     " VALUES (?,?,'','Compilations',0,0,10,0,0,'VA',?,?)", (f"r{i}", f"VA-r{i}", t, "Deep House" if i % 2 else "House"))
    conn.commit()
    series = lambda: {g["name"]: g["series"] for g in admin_client.get("/api/groups", params={"by": "series"}).json()}
    put = lambda name, family: admin_client.put("/api/admin/series/rules", json={"name": name, "family": family}, headers={"X-CSRF": "1"}).status_code
    assert series() == {"Hed Kandi": 2, "Serious Beats": 1}
    assert put("Serious Beats", "Hed Kandi") == 204 and series() == {"Hed Kandi": 3}          # rattachée
    assert put("Hed Kandi Nu Cool", "") == 204 and series() == {"Hed Kandi": 2, "Hed Kandi Nu Cool": 1}  # gardée à part
    assert put("Hed Kandi", "") == 204 and len(series()) == 3 and put(" ", "x") == 400         # famille défaite
    # tout ce qui commence par Hed, sauf les séries qui ont leur propre règle (à part, ou rattachée ailleurs)
    assert put("Hed", "Hed") == 204 and series() == {"Hed": 1, "Hed Kandi": 1, "Hed Kandi Nu Cool": 1}
    assert admin_client.delete("/api/admin/series/rules", params={"name": "Hed"}, headers={"X-CSRF": "1"}).status_code == 204
    assert admin_client.delete("/api/admin/series/rules", params={"name": "Hed Kandi"}, headers={"X-CSRF": "1"}).status_code == 204
    # genres : « Deep House » rejoint « House », la page du genre donne les deux
    genres = {g["name"]: g for g in admin_client.get("/api/groups", params={"by": "genre"}).json()}
    assert genres["House"]["genres"] == 2 and "Deep House" not in genres
    info = admin_client.get("/api/group-info", params={"by": "genre", "name": "House"}).json()
    assert [m["name"] for m in info["members"]] == ["House", "Deep House"] and info["n"] == sum(m["releases"] for m in info["members"])
    assert admin_client.get("/api/group-info", params={"by": "genre", "name": "House", "sub": "Deep House"}).json()["n"] == 4
    # écoutes : compteur de la fiche, tri par écoutes, tri d'un artiste par catégorie
    rid, tid = conn.execute("SELECT release_id, id FROM tracks WHERE title='Glue'").fetchone()
    conn.execute("INSERT INTO plays(user_id, track_id, played_at) SELECT id, ?, 50 FROM users", (tid,))
    conn.commit()
    d = admin_client.get(f"/api/releases/{rid}").json()
    assert (d["plays"], d["last_played"]) == (1, 50)
    assert admin_client.get("/api/releases", params={"sort": "plays", "dir": "desc"}).json()["items"][0]["id"] == rid
    kinds = [x["category"] for x in admin_client.get("/api/releases", params={"sort": "kind", "limit": 100}).json()["items"]]
    assert kinds == sorted(kinds, key=lambda c: ("album" not in c.lower(), "single" not in c.lower(), "compil" not in c.lower()))
    # NFO : le texte est indexé au scan, la recherche nfo=1 le trouve, la recherche par nom non
    nfo_rid = conn.execute("SELECT id FROM releases WHERE has_nfo=1").fetchone()[0]
    scanner._scan_nfo_text(conn, settings.music_root, lambda: False)
    assert [x["id"] for x in admin_client.get("/api/releases", params={"q": "ascii", "nfo": 1}).json()["items"]] == [nfo_rid]
    assert admin_client.get("/api/releases", params={"q": "ascii"}).json()["items"] == []
    assert admin_client.get("/api/release-summary", params={"q": "ascii", "nfo": 1}).json()[0]["releases"] == 1


def test_appearances_list_names_the_artist_tracks(user_client, library, settings):
    conn = db.connect(settings.data_dir)
    rid = conn.execute("SELECT release_id FROM tracks WHERE title='Glue'").fetchone()[0]
    conn.execute("INSERT INTO tracks(release_id, relpath, size, title, artist) VALUES (?, 'g.mp3', 1, 'Guest Track', 'A-Trak')", (rid,))
    conn.commit()
    items = user_client.get("/api/releases", params={"appears": "A-Trak"}).json()["items"]
    assert [(x["id"], x["by_artist"], x["by"]) for x in items] == [(rid, "A-Trak", ["Guest Track"])]
    assert "by" not in user_client.get("/api/releases").json()["items"][0]


def test_search_title_drops_disc_count_and_nfo_tracklist_gives_chapters(app, settings):
    from app import coversearch, nfo, scanner
    assert [coversearch.clean_title(t) for t in ("Mystery Land 2010-2CD", "Best Of (3CD)", "Album CD1", "CD", "Plain")] == \
        ["Mystery Land 2010", "Best Of", "Album", "CD", "Plain"]
    assert coversearch.exact("VA", "Mystery Land 2010-2CD", "Various - Mystery Land 2010")
    text = """[ Tracklist ]
CD 1/2
1.  An21 & MaxVangeli - Swedish Beauty          4:00
2.  Sander van Doorn - Reach Out                4:02
4.  Tommyboy & Agebeat Pres. Crazibiza - Spinning Around   3:37
    (Tommyboy Remix)
CD 2/2
1.  A - B    5:00
2.  C - D    6:00
"""
    d1, d2 = nfo.tracklist(text)
    assert [(c["artist"], c["start"]) for c in d1] == [("An21 & MaxVangeli", 0), ("Sander van Doorn", 240), ("Tommyboy & Agebeat Pres. Crazibiza", 482)]
    assert d1[2]["title"] == "Spinning Around (Tommyboy Remix)" and [c["start"] for c in d2] == [0, 300]
    assert [c["start"] for c in nfo.tracklist("[00:00] A - B\n[03:30] C - D\n[10:05] E - F")[0]] == [0, 210, 605]
    conn = db.connect(settings.data_dir)
    rid = conn.execute("INSERT INTO releases(path, name, parent, category, mtime, added_at, size, track_count, has_nfo)"
                       " VALUES ('m', 'm', '', 'Compilations', 0, 0, 1, 2, 1)").lastrowid
    for disc, length in ((1, 720), (2, 660)):
        conn.execute("INSERT INTO tracks(release_id, relpath, disc, size, duration) VALUES (?, ?, ?, 1, ?)", (rid, f"cd{disc}.mp3", disc, length))
    scanner._nfo_chapters(conn, rid, text)
    assert conn.execute("SELECT COUNT(*) FROM chapters").fetchone()[0] == 5
    scanner._nfo_chapters(conn, rid, text)  # déjà des chapitres : rien de plus
    assert conn.execute("SELECT COUNT(*) FROM chapters").fetchone()[0] == 5


def test_artist_photo_is_taken_from_the_first_matching_result(app, user_client, admin_client, settings, monkeypatch):
    import io
    from PIL import Image
    from app import coversearch
    buf = io.BytesIO()
    Image.new("RGB", (40, 40), "red").save(buf, "JPEG")
    monkeypatch.setattr(coversearch, "artist_photos", lambda name: [{"url": "https://x/a.jpg", "thumb": "t", "title": "Bob Sinclar & Co"},
                                                                    {"url": "https://x/b.jpg", "thumb": "t", "title": "bob sinclar"}])
    got = []
    monkeypatch.setattr(coversearch, "fetch", lambda url: got.append(url) or buf.getvalue())
    photo = lambda name, kind="artist": user_client.get("/api/photo", params={"kind": kind, "name": name}).status_code
    assert photo("Bob Sinclar") == 200 and got == ["https://x/b.jpg"]
    assert photo("VA") == 404 and photo("Personne") == 404 and len(got) == 1
    assert admin_client.delete("/api/admin/photo", params={"kind": "artist", "name": "Bob Sinclar"}, headers={"X-CSRF": "1"}).status_code == 204
    assert photo("Bob Sinclar") == 404 and len(got) == 1  # retirée : pas remise
    # label : Discogs, avec un jeton ; « Defected Records » et « Defected (2) » désignent le même label
    monkeypatch.setattr(coversearch, "label_photos", lambda name, token: [{"url": "https://x/l.jpg", "thumb": "t", "title": "Defected"}])
    assert photo("Defected Records", "label") == 404  # sans jeton : pas de recherche
    app.state.settings = app.state.settings.__class__(**{**app.state.settings.__dict__, "discogs_token": "t"})
    assert photo("Defected Records", "label") == 200 and got[-1] == "https://x/l.jpg"


def test_artist_page_ignores_case_and_caps_lock_spellings_merge(user_client, library, settings):
    from app import artists
    rid = user_client.get("/api/releases", params={"artist": "A-TRAK"}).json()["items"]
    assert len(rid) == 1 and user_client.get("/api/artist-info", params={"name": "a-trak"}).json()["name"] == "A-Trak"
    pairs = {1: ("BOB SINCLAR", None), 2: ("BOB SINCLAR", None), 3: ("Bob Sinclar", None)}
    assert {v[0] for v in artists._step(pairs, {}).values()} == {"Bob Sinclar"}
    conn = db.connect(settings.data_dir)
    rel = conn.execute("SELECT release_id FROM tracks LIMIT 1").fetchone()[0]
    for a in ("CUTEE B.", "CUTEE B.", "Cutee B."):
        conn.execute("INSERT INTO tracks(release_id, relpath, size, artist) VALUES (?, 'c.mp3', 1, ?)", (rel, a))
    db.merge_track_artists(conn)
    assert [r[0] for r in conn.execute("SELECT DISTINCT artist FROM tracks WHERE artist LIKE 'cutee b.'")] == ["Cutee B."]


def test_category_counts_of_a_label_or_a_group(user_client, library, settings):
    conn = db.connect(settings.data_dir)
    conn.execute("UPDATE releases SET label='Tiger Records'")
    conn.commit()
    rows = user_client.get("/api/groups", params={"by": "category", "label": "Tiger Records"}).json()
    assert sum(r["releases"] for r in rows) == 3
    assert user_client.get("/api/groups", params={"by": "category", "grp": "WUS"}).json()[0]["releases"] == 1


def test_lowercase_only_artist_gets_capitals(user_client, library, settings):
    conn = db.connect(settings.data_dir)
    rel = conn.execute("SELECT release_id FROM tracks LIMIT 1").fetchone()[0]
    conn.execute("INSERT INTO tracks(release_id, relpath, size, artist) VALUES (?, 's.mp3', 1, 'soul vision')", (rel,))
    db.merge_track_artists(conn)
    assert conn.execute("SELECT COUNT(*) FROM tracks WHERE artist='Soul Vision'").fetchone()[0] == 1
    assert user_client.get("/api/artist-info", params={"name": "soul vision"}).json()["name"] == "Soul Vision"


def test_titles_gather_every_version_of_a_song(user_client, library, settings):
    conn = db.connect(settings.data_dir)
    rel = conn.execute("SELECT release_id FROM tracks WHERE title='Glue'").fetchone()[0]
    conn.execute("INSERT INTO tracks(release_id, relpath, size, title, artist) VALUES (?, 'g2.mp3', 5, 'Glue (Dub)', 'Bicep')", (rel,))
    conn.commit()
    rows = {r["name"]: r for r in user_client.get("/api/titles").json()}
    assert rows["Glue"]["releases"] == 2 and "Ibanez Dub" not in rows
    assert user_client.get("/api/titles", params={"song": "glue"}).json()[0]["releases"] == 2
    assert sorted(t["title"] for t in user_client.get("/api/tracks", params={"song": "Glue"}).json()["items"]) == ["Glue", "Glue (Dub)"]
    assert user_client.get("/api/titles", params={"category": "Albums"}).json() == []


def test_titles_join_after_a_dash_strip_leading_signs_merge_by_hand_and_shuffle(admin_client, library, settings):
    conn = db.connect(settings.data_dir)
    rel = conn.execute("SELECT release_id FROM tracks WHERE title='Glue'").fetchone()[0]
    for t in ("Glue - Club Mix", "_Glue", "....Glue (Dub)", "Glue 2009", "Glue 2009"):
        conn.execute("INSERT INTO tracks(release_id, relpath, size, title, artist) VALUES (?, 'x.mp3', 1, ?, 'Bicep')", (rel, t))
    conn.commit()
    rows = {r["name"]: r["releases"] for r in admin_client.get("/api/titles").json()}
    assert rows["Glue"] == 4 and rows["Glue 2009"] == 2
    assert admin_client.put("/api/admin/titles/aliases", json={"alias": "Glue 2009", "target": "Glue"}, headers={"X-CSRF": "1"}).status_code == 204
    rows = {r["name"]: r["releases"] for r in admin_client.get("/api/titles").json()}
    assert rows == {**{k: v for k, v in rows.items() if k != "Glue"}, "Glue": 6} and "Glue 2009" not in rows
    assert len(admin_client.get("/api/tracks", params={"song": "Glue"}).json()["items"]) == 6
    assert {t["title"] for t in admin_client.get("/api/mix", params={"song": "glue", "limit": 50}).json()["items"]} >= {"Glue", "Glue 2009"}
    assert admin_client.delete("/api/admin/titles/aliases", params={"alias": "Glue 2009"}, headers={"X-CSRF": "1"}).status_code == 204
    ids = [rel]
    assert {t["release_id"] for t in admin_client.get("/api/mix", params={"release": ids}).json()["items"]} == {rel}


def test_nfo_tracklist_names_tracks_without_tags(app, settings):
    from app import nfo, scanner
    text = "01. Alpha - One\n02. Beta - Two\n    (Club Mix)\n05. Stray - Line\n"
    assert nfo.track_names(text) == [{"artist": "Alpha", "title": "One"}, {"artist": "Beta", "title": "Two (Club Mix)"}]
    conn = db.connect(settings.data_dir)
    rid = conn.execute("INSERT INTO releases(path, name, parent, category, mtime, added_at, size, track_count, has_nfo)"
                       " VALUES ('n', 'n', '', 'Singles', 0, 0, 1, 2, 1)").lastrowid
    for i in (1, 2):
        conn.execute("INSERT INTO tracks(release_id, relpath, size) VALUES (?, ?, 1)", (rid, f"0{i}.mp3"))
    scanner._nfo_titles(conn, rid, text)
    assert [tuple(r) for r in conn.execute("SELECT artist, title FROM tracks WHERE release_id=? ORDER BY relpath", (rid,))] == \
        [("Alpha", "One"), ("Beta", "Two (Club Mix)")]


def test_tracks_of_a_title_are_grouped_by_artist_and_sortable(user_client, library, settings):
    from app import artists
    assert artists.group_key("Axwell /\\ Ingrosso") == artists.group_key("Axwell and Ingrosso") == artists.group_key("Axwell & Ingrosso") == "axwellingrosso"
    assert artists.group_key("Funkstar De Luxe") == artists.group_key("Funkstar Deluxe")
    conn = db.connect(settings.data_dir)
    rel = conn.execute("SELECT release_id FROM tracks WHERE title='Glue'").fetchone()[0]
    for a, br in (("Zed", 128000), ("Axwell and Ingrosso", 320000), ("Axwell /\\ Ingrosso", 192000)):
        conn.execute("INSERT INTO tracks(release_id, relpath, size, title, artist, bitrate) VALUES (?, 'g.mp3', 1, 'Glue', ?, ?)", (rel, a, br))
    conn.commit()
    got = lambda **p: [t["artist"] for t in user_client.get("/api/tracks", params={"song": "Glue", **p}).json()["items"]]
    assert got()[:2] == ["Axwell /\\ Ingrosso", "Axwell and Ingrosso"] or got()[:2] == ["Axwell and Ingrosso", "Axwell /\\ Ingrosso"]
    assert got()[-1] == "Zed" and got(sort="bitrate", dir="desc")[0] == "Axwell and Ingrosso"
