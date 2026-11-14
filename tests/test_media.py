import io
import os
import shutil
import time
import zipfile
from pathlib import Path

import pytest

from app.security import CAST_TTL, sign_track

A = "Singles/A/A-Trak--Ibanez-(SP983)-WEB-2015-WUS"
V = "Albums/VA-Big_Mix-2CD-2003-GRP"


def track(conn, release_path, relpath):
    return conn.execute("SELECT t.id FROM tracks t JOIN releases r ON r.id=t.release_id WHERE r.path=? AND t.relpath=?",
                        (release_path, relpath)).fetchone()[0]


def release(conn, path):
    return conn.execute("SELECT id, name FROM releases WHERE path=?", (path,)).fetchone()


def add_track(conn, release_path, relpath):
    """Piste indexée à la main (fichier hors scanner : nom piégé, lien symbolique…)."""
    rid = release(conn, release_path)["id"]
    tid = conn.execute("INSERT INTO tracks(release_id, relpath, size) VALUES (?,?,0)", (rid, relpath)).lastrowid
    conn.commit()
    return tid


def cast_path(tid, exp=None):
    exp = int(time.time()) + 60 if exp is None else exp
    return f"/cast/{tid}?exp={exp}&sig={sign_track('test', tid, exp)}"


def snapshot(root):
    return {str(p): (p.lstat().st_size, p.lstat().st_mtime_ns) for p in [root, *root.rglob("*")]}


@pytest.fixture
def tid(conn, library):
    return track(conn, A, "01-a-trak--ibanez.mp3")


def test_stream_full_and_range(user_client, settings, tid):
    full = user_client.get(f"/api/tracks/{tid}/stream")
    assert full.status_code == 200 and full.headers["content-type"] == "audio/mpeg"
    assert full.headers["accept-ranges"] == "bytes" and "content-disposition" not in full.headers
    assert full.content == (settings.music_root / A / "01-a-trak--ibanez.mp3").read_bytes()
    part = user_client.get(f"/api/tracks/{tid}/stream", headers={"Range": "bytes=10-19"})
    assert part.status_code == 206 and part.content == full.content[10:20]
    assert part.headers["content-range"] == f"bytes 10-19/{len(full.content)}"
    assert user_client.get("/api/tracks/99999/stream").status_code == 404


def test_download_disposition(user_client, tid):
    r = user_client.get(f"/api/tracks/{tid}/stream?download=1")
    assert r.status_code == 200 and r.headers["content-type"] == "audio/mpeg"
    assert r.headers["content-disposition"] == ('attachment; filename="01-a-trak--ibanez.mp3"; '
                                                "filename*=UTF-8''01-a-trak--ibanez.mp3")


def test_waveform_reduce_and_cache(user_client, conn, monkeypatch, library):
    from app import routes_media
    assert routes_media.reduce_peaks([]) == b""
    assert routes_media.reduce_peaks([10, 20, 5]) == bytes([127, 255, 63])          # normalisée sur la plus forte
    assert routes_media.reduce_peaks([1, 9, 2, 4], points=2) == bytes([255, 113])   # crête de chaque moitié
    tid = conn.execute("SELECT id FROM tracks ORDER BY id LIMIT 1").fetchone()[0]
    calls = []
    monkeypatch.setattr(routes_media, "compute_waveform", lambda path: calls.append(path) or bytes([0, 128, 255]))
    for _ in range(2):  # le second appel vient du cache
        assert user_client.get(f"/api/tracks/{tid}/waveform").json() == {"peaks": [0, 128, 255]}
    assert len(calls) == 1
    assert user_client.get("/api/tracks/99999/waveform").status_code == 404
    monkeypatch.setattr(routes_media, "compute_waveform", lambda path: None)  # décodeur absent ou fichier illisible
    other = conn.execute("SELECT id FROM tracks ORDER BY id DESC LIMIT 1").fetchone()[0]
    assert user_client.get(f"/api/tracks/{other}/waveform").status_code == 404


def test_cover_prefers_front_image(user_client, settings, library):
    from app.routes_media import pick_cover
    assert pick_cover(["a.nfo", "00-x-2cd-2008-back.jpg", "00-x-2cd-2008-front.JPG", "zz.png"]) == "00-x-2cd-2008-front.JPG"
    assert pick_cover(["x-back.jpg"]) == "x-back.jpg" and pick_cover(["a.mp3", "a.nfo"]) is None
    rid = user_client.get("/api/releases", params={"q": "ibanez"}).json()["items"][0]["id"]
    assert user_client.get(f"/api/releases/{rid}/cover").status_code == 404  # ni image ni tag
    (settings.music_root / A / "00-a-trak--ibanez-front.jpg").write_bytes(b"\xff\xd8jpeg")
    r = user_client.get(f"/api/releases/{rid}/cover")
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg" and r.content == b"\xff\xd8jpeg"
    assert user_client.get("/api/releases/99999/cover").status_code == 404


def test_thumb_is_small_and_cached(user_client, settings, library):
    import io
    from PIL import Image
    a, b = (user_client.get("/api/releases", params={"q": q}).json()["items"][0]["id"] for q in ("ibanez", "bicep"))
    buf = io.BytesIO()
    Image.new("RGB", (900, 600), "red").save(buf, "PNG")
    (settings.music_root / A / "cover.png").write_bytes(buf.getvalue())
    r = user_client.get(f"/api/releases/{a}/thumb")
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
    assert Image.open(io.BytesIO(r.content)).size == (128, 85)  # proportions gardées
    (settings.music_root / A / "cover.png").unlink()  # la vignette vient maintenant du cache
    assert user_client.get(f"/api/releases/{a}/thumb").content == r.content
    assert user_client.get(f"/api/releases/{b}/thumb").status_code == 404  # sans pochette : retenu par un fichier vide
    assert (settings.data_dir / "thumbs" / f"{b}.jpg").stat().st_size == 0
    assert user_client.get(f"/api/releases/{b}/thumb").status_code == 404
    assert user_client.get("/api/releases/99999/thumb").status_code == 404
    assert not (settings.data_dir / "thumbs" / "99999.jpg").exists()


def test_download_name_cannot_inject_headers(user_client, conn, settings, library):
    name = 'Café "live"\r\nX-Evil: 1.mp3'
    (settings.music_root / A / name).write_bytes(b"\xff\xfb\x90\x64" * 10)
    r = user_client.get(f"/api/tracks/{add_track(conn, A, name)}/stream?download=1")
    assert r.status_code == 200 and "x-evil" not in r.headers
    assert r.headers["content-disposition"] == ('attachment; filename="Caf_ _live___X-Evil: 1.mp3"; '
                                                "filename*=UTF-8''Caf%C3%A9%20%22live%22%0D%0AX-Evil%3A%201.mp3")


def test_zip_has_exactly_the_folder_files(user_client, conn, settings, library):
    for path in (A, V):
        rid, name = release(conn, path)
        r = user_client.get(f"/api/releases/{rid}/zip")
        assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
        assert r.headers["content-disposition"].startswith(f'attachment; filename="{name}.zip"')
        z = zipfile.ZipFile(io.BytesIO(r.content))
        assert z.testzip() is None
        folder = settings.music_root / path
        on_disk = [p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file()]
        assert sorted(z.namelist()) == sorted(f"{name}/{p}" for p in on_disk)
        assert all(i.compress_type == zipfile.ZIP_STORED for i in z.infolist())
        for p in on_disk:
            assert z.read(f"{name}/{p}") == (folder / p).read_bytes()
    assert any(n.endswith(".nfo") for n in zipfile.ZipFile(io.BytesIO(
        user_client.get(f"/api/releases/{release(conn, A)['id']}/zip").content)).namelist())
    assert user_client.get("/api/releases/99999/zip").status_code == 404


def test_cast_url_roundtrip_without_session(user_client, client, tid):
    before = int(time.time())
    url = user_client.post("/api/cast/urls", json={"track_ids": [tid, 99999]}).json()["urls"]
    assert list(url) == [str(tid)]                                           # id inconnu : omis
    url = url[str(tid)]
    assert url.startswith(f"https://mp3.test/cast/{tid}?exp=")
    exp = int(url.split("exp=")[1].split("&")[0])
    assert before + CAST_TTL <= exp <= int(time.time()) + CAST_TTL
    path = url.removeprefix("https://mp3.test")
    full = client.get(path)                                                  # client sans cookie
    assert full.status_code == 200 and full.headers["content-type"] == "audio/mpeg"
    assert full.headers["access-control-allow-origin"] == "*"
    assert {"content-range", "accept-ranges", "content-length"} <= {
        h.strip().lower() for h in full.headers["access-control-expose-headers"].split(",")}
    part = client.get(path, headers={"Range": "bytes=0-9"})
    assert part.status_code == 206 and part.content == full.content[:10]
    head = client.head(path)
    assert head.status_code == 200 and head.content == b"" and head.headers["content-length"] == str(len(full.content))
    assert head.headers["access-control-allow-origin"] == "*"


def test_cast_cover_without_session(client, settings, tid):
    cover = cast_path(tid).replace("?", "/cover?")
    assert client.get(cover).status_code == 404                              # signature valide, pas de pochette
    (settings.music_root / A / "front.jpg").write_bytes(b"\xff\xd8jpeg")
    r = client.get(cover)                                                    # client sans cookie
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg" and r.content == b"\xff\xd8jpeg"
    assert r.headers["access-control-allow-origin"] == "*"
    assert client.get(f"/cast/{tid}/cover?exp={int(time.time()) + 60}&sig={'0' * 64}").status_code == 403
    assert client.get(f"/cast/{tid}/cover").status_code == 403


def test_cast_preflight(client, tid):
    r = client.options(f"/cast/{tid}", headers={"Origin": "https://cast.example", "Access-Control-Request-Method": "GET",
                                               "Access-Control-Request-Headers": "range"})
    assert r.status_code == 204 and r.headers["access-control-allow-origin"] == "*"
    assert r.headers["access-control-allow-methods"] == "GET, HEAD, OPTIONS"
    assert r.headers["access-control-allow-headers"] == "Range"


def test_cast_url_rejected(client, tid):                                     # critère 8
    exp_past = int(time.time()) - 1
    assert client.get(cast_path(tid, exp_past)).status_code == 403
    good_exp = int(time.time()) + 60
    sig = sign_track("test", tid, good_exp)
    assert client.get(f"/cast/{tid + 1}?exp={good_exp}&sig={sig}").status_code == 403    # jeton lié à une piste
    assert client.get(f"/cast/{tid}?exp={good_exp + 1}&sig={sig}").status_code == 403
    assert client.get(f"/cast/{tid}?exp={good_exp}&sig={sign_track('autre', tid, good_exp)}").status_code == 403
    assert client.get(f"/cast/{tid}?exp={good_exp}").status_code == 403
    assert client.get(f"/cast/{tid}").status_code == 403
    assert client.get(f"/cast/{tid}?exp={good_exp}&sig={sig.upper()}").status_code == 403
    far = int(time.time()) + CAST_TTL + 3600                                 # signé, mais trop lointain
    assert client.get(cast_path(tid, far)).status_code == 403
    assert client.get(cast_path(99999)).status_code == 404                   # signature valide, piste inconnue
    assert client.get(f"/cast/99999?exp={good_exp}&sig={sig}").status_code == 403   # signature invalide : 403 d'abord


@pytest.mark.parametrize("qs", ["exp=abc&sig=00", "exp=-5&sig=00", "exp=1e12&sig=00", "exp=&sig=", "exp=1.5&sig=00",
                                "exp=99999999999999999999999999&sig=00", "exp={exp}&sig=zz", "exp={exp}&sig=%C3%A9",
                                "exp={exp}&sig=%00", "exp={exp}&sig=" + "a" * 5000, "exp=%00&sig=00"])
def test_cast_malformed_is_403(client, tid, qs):
    assert client.get(f"/cast/{tid}?" + qs.format(exp=int(time.time()) + 60)).status_code == 403


def test_cast_urls_validation(user_client, client, tid):
    assert client.post("/api/cast/urls", json={"track_ids": [tid]}).status_code == 401
    assert user_client.post("/api/cast/urls", json={"track_ids": [tid]}, headers={"X-CSRF": ""}).status_code == 403
    for body in ({"track_ids": []}, {"track_ids": list(range(501))}, {"track_ids": "1"}, {"track_ids": ["x"]}, {}):
        assert user_client.post("/api/cast/urls", json=body).status_code == 422, body
    assert user_client.post("/api/cast/urls", json={"track_ids": list(range(1, 501))}).status_code == 200


def test_missing_file_is_404_not_500(user_client, client, conn, settings, tid):   # Review Focus 4
    rid = release(conn, A)["id"]
    (settings.music_root / A / "01-a-trak--ibanez.mp3").unlink()
    assert user_client.get(f"/api/tracks/{tid}/stream").status_code == 404
    assert client.get(cast_path(tid)).status_code == 404                     # signature valide, fichier disparu
    r = user_client.get(f"/api/releases/{rid}/zip")
    assert r.status_code == 200                                              # le zip saute le fichier
    assert zipfile.ZipFile(io.BytesIO(r.content)).namelist() == [
        f"{release(conn, A)['name']}/02-a-trak--ibanez_(dub).mp3", f"{release(conn, A)['name']}/a-trak--ibanez.nfo"]
    shutil.rmtree(settings.music_root / A)
    assert user_client.get(f"/api/releases/{rid}/nfo").status_code == 404
    assert user_client.get(f"/api/releases/{rid}/zip").status_code == 404


@pytest.mark.skipif(os.geteuid() == 0, reason="root lit tout")
def test_unreadable_file_is_404_and_skipped(user_client, conn, settings, tid):
    f = settings.music_root / A / "01-a-trak--ibanez.mp3"
    f.chmod(0)
    try:
        assert user_client.get(f"/api/tracks/{tid}/stream").status_code == 404
        names = zipfile.ZipFile(io.BytesIO(user_client.get(f"/api/releases/{release(conn, A)['id']}/zip").content)).namelist()
        assert len(names) == 2 and not any(n.endswith("/01-a-trak--ibanez.mp3") for n in names)
    finally:
        f.chmod(0o644)


def test_path_escape_is_refused(user_client, client, conn, tid):            # critère 8
    conn.execute("UPDATE tracks SET relpath='../../../../etc/hosts' WHERE id=?", (tid,))
    conn.commit()
    assert user_client.get(f"/api/tracks/{tid}/stream").status_code == 404
    assert client.get(cast_path(tid)).status_code == 404


def test_symlink_out_of_library_is_refused(user_client, client, conn, settings, tmp_path, library):
    secret = tmp_path / "secret"
    secret.mkdir()
    (secret / "secret.mp3").write_bytes(b"SECRET")
    folder = settings.music_root / A
    (folder / "evil.mp3").symlink_to(secret / "secret.mp3")
    (folder / "evil_dir").symlink_to(secret, target_is_directory=True)
    tid = add_track(conn, A, "evil.mp3")
    assert user_client.get(f"/api/tracks/{tid}/stream").status_code == 404
    assert client.get(cast_path(tid)).status_code == 404
    r = user_client.get(f"/api/releases/{release(conn, A)['id']}/zip")
    z = zipfile.ZipFile(io.BytesIO(r.content))
    assert not any("evil" in n for n in z.namelist()) and len(z.namelist()) == 3
    assert b"SECRET" not in r.content


def test_nothing_written_under_music(user_client, client, conn, settings, tid):   # critère 9
    root = settings.music_root
    before = snapshot(root)
    rid = release(conn, A)["id"]
    for url in ["/api/releases", f"/api/releases/{rid}", f"/api/releases/{rid}/nfo", f"/api/tracks/{tid}/stream",
                f"/api/tracks/{tid}/stream?download=1", f"/api/releases/{rid}/zip",
                f"/api/releases/{release(conn, V)['id']}/zip"]:
        assert user_client.get(url).status_code == 200, url
    assert client.get(cast_path(tid)).status_code == 200
    assert user_client.post("/api/cast/urls", json={"track_ids": [tid]}).status_code == 200
    assert snapshot(root) == before
    assert not list(Path(settings.data_dir).glob("*.zip"))


def test_zip_keeps_non_utf8_name_under_safe_name(tmp_path):
    from app.routes_media import _zip_stream
    f = tmp_path / "a.sfv"
    f.write_bytes(b"data")
    data = b"".join(_zip_stream("Rel", [("ok.sfv", f), (os.fsdecode(b"caf\xe9.sfv"), f)]))
    z = zipfile.ZipFile(io.BytesIO(data))
    assert z.testzip() is None
    assert z.namelist() == ["Rel/ok.sfv", "Rel/caf�.sfv"]
    assert z.read("Rel/caf�.sfv") == b"data"


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="pas de FIFO sur cette plateforme")
def test_fifo_is_404_and_skipped_by_zip(user_client, conn, settings, library):
    os.mkfifo(settings.music_root / A / "pipe.mp3")
    tid = add_track(conn, A, "pipe.mp3")
    assert user_client.get(f"/api/tracks/{tid}/stream").status_code == 404
    names = zipfile.ZipFile(io.BytesIO(user_client.get(f"/api/releases/{release(conn, A)['id']}/zip").content)).namelist()
    assert len(names) == 3 and not any("pipe" in n for n in names)
