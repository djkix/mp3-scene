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
    db.connect(settings.data_dir).close(); db.connect(settings.data_dir).close()
