import hashlib
import json
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

SONG = {"id": "s1", "title": "Strobe", "artist": "deadmau5", "album": "For Lack", "albumId": "al1", "duration": 600,
        "bitRate": 320, "suffix": "flac", "coverArt": "al1", "path": "deadmau5/For Lack/01 Strobe.flac", "track": 1}
AUDIO = bytes(range(256)) * 40  # 10 240 octets


class Fake(BaseHTTPRequestHandler):
    """Serveur Subsonic minimal : vérifie le jeton (md5 du mot de passe et du sel), répond en JSON."""
    calls = []

    def log_message(self, *a):
        pass

    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        q = dict(urllib.parse.parse_qsl(url.query))
        method = url.path.rsplit("/", 1)[-1]
        Fake.calls.append((method, q))
        if q.get("t") != hashlib.md5(("secret" + q.get("s", "")).encode()).hexdigest():
            return self._json({"status": "failed", "error": {"code": 40, "message": "Wrong username or password"}})
        if method == "stream":
            if q["id"] != "s1":
                return self._json({"status": "failed", "error": {"code": 70, "message": "not found"}})
            body, status, extra = AUDIO, 200, {}
            if rng := self.headers.get("Range"):
                start = int(rng.split("=")[1].split("-")[0])
                body, status = AUDIO[start:], 206
                extra = {"Content-Range": f"bytes {start}-{len(AUDIO) - 1}/{len(AUDIO)}"}
            self.send_response(status)
            self.send_header("Content-Type", "audio/flac" if "format" not in q else "audio/mpeg")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Accept-Ranges", "bytes")
            for k, v in extra.items():
                self.send_header(k, v)
            self.end_headers()
            return self.wfile.write(body)
        if method == "getCoverArt":
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.end_headers()
            return self.wfile.write(b"\xff\xd8jpeg")
        data = {"ping": {}, "getAlbumList2": {"albumList2": {"album": [{"id": "al1", "name": "For Lack", "artist": "deadmau5",
                                                                        "coverArt": "al1", "songCount": 1, "year": 2008}]}},
                "getAlbum": {"album": {"name": "For Lack", "artist": "deadmau5", "song": [SONG]}},
                "getArtists": {"artists": {"index": [{"artist": [{"id": "ar1", "name": "deadmau5", "albumCount": 1}]}]}},
                "search3": {"searchResult3": {"song": [SONG]}},
                "getRandomSongs": {"randomSongs": {"song": [SONG]}},
                "getArtist": {"artist": {"name": "deadmau5", "album": [{"id": "al1", "name": "For Lack", "year": 2008}]}},
                "getSong": {"song": SONG}}[method]
        self._json({"status": "ok", **data})

    def _json(self, data):
        body = json.dumps({"subsonic-response": {"version": "1.16.1", **data}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture
def navidrome(settings):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    settings.navidrome_url = f"http://127.0.0.1:{srv.server_port}"
    settings.navidrome_user, settings.navidrome_password = "kix", "secret"
    yield srv
    srv.shutdown()


def test_navidrome_absent_hides_the_tab(user_client):
    assert user_client.get("/api/navidrome/status").json() == {"enabled": False}
    assert user_client.get("/api/navidrome/albums").status_code == 404


def test_navidrome_browse_search_stream_and_cast(navidrome, settings, user_client, client):
    assert user_client.get("/api/navidrome/status").json() == {"enabled": True, "ok": True}
    assert user_client.get("/api/navidrome/albums").json()[0]["cover"] == "/api/navidrome/cover/al1"
    assert user_client.get("/api/navidrome/artists").json() == [{"id": "ar1", "name": "deadmau5", "albums": 1}]
    t = user_client.get("/api/navidrome/album/al1").json()["tracks"][0]
    assert (t["id"], t["nd"], t["title"], t["release_name"], t["bitrate"], t["suffix"]) == ("nd:s1", "s1", "Strobe", "For Lack", 320000, "flac")
    assert user_client.get("/api/navidrome/search", params={"q": "strobe"}).json()["tracks"][0]["id"] == "nd:s1"
    # morceaux à l'unité : les listes et la page d'un artiste se montrent en pistes
    assert [t["id"] for t in user_client.get("/api/navidrome/tracks").json()] == ["nd:s1"]
    assert [t["id"] for t in user_client.get("/api/navidrome/tracks", params={"type": "random"}).json()] == ["nd:s1"]
    assert [t["title"] for t in user_client.get("/api/navidrome/artist/ar1").json()["tracks"]] == ["Strobe"]
    # le son passe par Mp3 Scene, déplacement compris ; le mot de passe ne sort jamais vers le navigateur
    r = user_client.get("/api/navidrome/stream/s1", params={"original": 1})
    assert r.status_code == 200 and r.content == AUDIO and r.headers["content-type"] == "audio/flac"
    r = user_client.get("/api/navidrome/stream/s1", params={"original": 1}, headers={"Range": "bytes=10000-"})
    assert r.status_code == 206 and r.content == AUDIO[10000:] and r.headers["content-range"] == "bytes 10000-10239/10240"
    assert user_client.get("/api/navidrome/stream/s1").headers["content-type"] == "audio/mpeg"  # sans original : MP3
    assert Fake.calls[-1][1].get("format") == "mp3" and all("secret" not in json.dumps(q) for _, q in Fake.calls)
    assert user_client.get("/api/navidrome/stream/zz").status_code == 404
    assert user_client.get("/api/navidrome/stream/..%2F..").status_code == 404
    assert user_client.get("/api/navidrome/cover/al1").content == b"\xff\xd8jpeg"
    assert client.get("/api/navidrome/albums").status_code == 401  # sans session : rien
    # Chromecast : URL signée vers /cast/nd/…, lisible sans session
    url = user_client.post("/api/cast/urls", json={"nd_ids": ["s1"]}, headers={"X-CSRF": "1"}).json()["urls"]["nd:s1"]
    path = url.removeprefix(settings.public_url)
    r = client.get(path)
    assert r.status_code == 200 and r.headers["access-control-allow-origin"] == "*"
    assert client.get(path.replace("sig=", "sig=0")).status_code == 403
    assert client.get(path.replace("?", "/cover?")).content == b"\xff\xd8jpeg"


def test_navidrome_wrong_password_is_a_clear_error(navidrome, settings, user_client):
    settings.navidrome_password = "faux"
    s = user_client.get("/api/navidrome/status").json()
    assert s["ok"] is False and "Wrong username or password" in s["error"]
    assert user_client.get("/api/navidrome/albums").status_code == 502
