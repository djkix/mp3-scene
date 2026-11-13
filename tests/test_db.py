def test_schema_and_fts(conn):
    conn.execute("INSERT INTO releases(path,name,parent,category,mtime,added_at,size,track_count,has_nfo)"
                 " VALUES('S/A/A-Trak--Ibanez-(SP983)-WEB-2015-WUS','A-Trak--Ibanez-(SP983)-WEB-2015-WUS','S/A','S',1,1,1,1,0)")
    hit = conn.execute("SELECT rowid FROM releases_fts WHERE releases_fts MATCH 'ibanez'").fetchall()
    assert len(hit) == 1
    conn.execute("DELETE FROM releases")
    assert conn.execute("SELECT count(*) FROM releases_fts WHERE releases_fts MATCH 'ibanez'").fetchone()[0] == 0
    assert conn.execute("SELECT status FROM scan_state WHERE id=1").fetchone()[0] == "idle"


def test_connect_is_idempotent(settings):
    from app import db
    db.init(settings.data_dir); db.init(settings.data_dir)


def test_init_creates_data_dir(tmp_path):
    from app import db
    db.init(tmp_path / "neuf" / "data")
    assert (tmp_path / "neuf" / "data" / "mp3scene.db").is_file()


def test_fts_follows_rename(conn):
    conn.execute("INSERT INTO releases(path,name,parent,category,mtime,added_at,size,track_count,has_nfo)"
                 " VALUES('S/A/Old','Ancien-Nom','S/A','S',1,1,1,1,0)")
    conn.execute("UPDATE releases SET name='Nouveau-Titre'")
    match = "SELECT count(*) FROM releases_fts WHERE releases_fts MATCH ?"
    assert conn.execute(match, ("ancien",)).fetchone()[0] == 0
    assert conn.execute(match, ("nouveau",)).fetchone()[0] == 1


def test_config_requires_secret_key(monkeypatch):
    import pytest
    from app import config
    monkeypatch.delenv("SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError):
        config.load()


def test_schema_version_stamped_and_checked(settings):
    import pytest
    from app import db
    db.init(settings.data_dir)
    c = db.connect(settings.data_dir)
    assert c.execute("PRAGMA user_version").fetchone()[0] == 1
    c.execute("INSERT INTO users(username, password_hash, role) VALUES ('u','x','user')"); c.commit()
    c.execute("PRAGMA user_version = 0"); c.commit()            # base existante non marquée : traitée comme v1
    db.init(settings.data_dir)
    assert c.execute("PRAGMA user_version").fetchone()[0] == 1
    assert c.execute("SELECT count(*) FROM users").fetchone()[0] == 1
    c.execute("PRAGMA user_version = 2"); c.commit()            # base d'une version plus récente de l'appli
    with pytest.raises(RuntimeError, match="version"):
        db.init(settings.data_dir)
    assert c.execute("PRAGMA user_version").fetchone()[0] == 2
    c.close()


def test_config_rejects_short_secret_key(monkeypatch):
    import pytest
    from app import config
    monkeypatch.setenv("SECRET_KEY", "k" * 31)
    with pytest.raises(RuntimeError) as e:
        config.load()
    assert "SECRET_KEY" in str(e.value) and "32" in str(e.value) and "k" * 31 not in str(e.value)
    monkeypatch.setenv("SECRET_KEY", "k" * 32)
    assert config.load().secret_key == "k" * 32
