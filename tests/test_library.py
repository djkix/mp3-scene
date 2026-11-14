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
    assert f["categories"] == ["Albums", "Singles"] and "House" in f["genres"] and f["years"] == [2017, 2015, 2003]
    assert [x["name"] for x in user_client.get("/api/releases?genre=House&year=2015").json()["items"]] == [A]
    assert [x["name"] for x in user_client.get("/api/releases?category=Albums").json()["items"]] == ["VA-Big_Mix-2CD-2003-GRP"]


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


def test_sort(user_client, library):
    get = lambda **p: user_client.get("/api/releases", params=p).json()["items"]
    sizes = [r["size"] for r in get(sort="size", dir="desc")]
    assert sizes == sorted(sizes, reverse=True) and len(sizes) > 1
    names = [r["name"].lower() for r in get(sort="name")]
    assert names == sorted(names)
    assert get() == get(sort="date", dir="desc")  # l'ordre par défaut est inchangé
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
