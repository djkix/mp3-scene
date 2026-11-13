import pytest

from fastapi.testclient import TestClient

from app import db, security
from app.config import Settings


@pytest.fixture
def settings(tmp_path):
    s = Settings(music_root=tmp_path / "music", data_dir=tmp_path / "data",
                 secret_key="test", public_url="https://mp3.test")
    s.data_dir.mkdir()
    return s


@pytest.fixture
def conn(settings):
    c = db.connect(settings.data_dir)
    yield c
    c.close()


@pytest.fixture
def music(settings):
    settings.music_root.mkdir()
    return settings.music_root


@pytest.fixture
def make_mp3():
    from mutagen.id3 import ID3, TCON, TIT2, TPE1

    def make(path, title=None, artist=None, genre=None, frames=40):
        # trames MPEG-1 Layer III, 128 kbit/s, 44,1 kHz : en-tête + 413 octets nuls = 417 octets
        path.write_bytes((b"\xff\xfb\x90\x64" + b"\x00" * 413) * frames)
        tags = [f(encoding=3, text=v) for f, v in ((TIT2, title), (TPE1, artist), (TCON, genre)) if v]
        if tags:
            id3 = ID3()
            for t in tags:
                id3.add(t)
            id3.save(path)
        return path
    return make


@pytest.fixture
def app(settings):
    from app.main import create_app
    settings.music_root.mkdir()
    settings.admin_user, settings.admin_password = "admin", "adminpass"
    a = create_app(settings)
    with TestClient(a):  # exécute le lifespan (admin initial, runner.resume) une seule fois
        yield a


def _client(app, login=None):
    c = TestClient(app, base_url="https://testserver", headers={"X-CSRF": "1"})
    if login:
        r = c.post("/api/login", json={"username": login[0], "password": login[1]})
        assert r.status_code == 200
    return c


@pytest.fixture
def client(app):
    return _client(app)


@pytest.fixture
def admin_client(app):
    return _client(app, ("admin", "adminpass"))


@pytest.fixture
def user_client(app, settings):
    c = db.connect(settings.data_dir)
    c.execute("INSERT INTO users(username, password_hash, role) VALUES ('user', ?, 'user')",
              (security.hash_password("userpass1"),))
    c.commit()
    c.close()
    return _client(app, ("user", "userpass1"))
