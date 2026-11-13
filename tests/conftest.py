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
