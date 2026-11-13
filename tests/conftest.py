import pytest

from app import db
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
