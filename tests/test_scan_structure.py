import os
import shutil
import sys

import pytest

from app.scanner import ScanError, scan_structure


def mk(music, rel, files):
    d = music / rel
    d.mkdir(parents=True, exist_ok=True)
    for f in files:
        (d / f).write_bytes(b"x")
    return d


def add_user(conn):
    conn.execute("INSERT INTO users(id,username,password_hash,role) VALUES(1,'u','x','user')")


def test_detects_releases_at_variable_depth(conn, music):
    mk(music, "Singles/A/Art-One-WEB-2015-GRP", ["01-a.mp3", "02-b.MP3", "00-x.NFO", "00-x.sfv"])
    mk(music, "Albums/Art-Two-CD-2001-GRP", ["01-a.mp3"])
    mk(music, "Albums/Art-Two-CD-2001-GRP/Covers", ["front.jpg"])
    stats = scan_structure(conn, music, now=1000.0)
    assert stats["found"] == 2
    r = conn.execute("SELECT * FROM releases WHERE name='Art-One-WEB-2015-GRP'").fetchone()
    assert (r["category"], r["parent"], r["track_count"], r["has_nfo"], r["year"], r["grp"]) == ("Singles", "Singles/A", 2, 1, 2015, "GRP")
    assert {f["path"] for f in conn.execute("SELECT path FROM folders")} == {"Singles", "Singles/A", "Albums"}


def test_multi_disc_merged(conn, music):
    mk(music, "Albums/VA-Big-2CD-2003-GRP/CD1", ["01-a.mp3"]); mk(music, "Albums/VA-Big-2CD-2003-GRP/cd2", ["01-b.mp3"])
    scan_structure(conn, music, now=1.0)
    assert conn.execute("SELECT count(*) FROM releases").fetchone()[0] == 1
    assert [(t["disc"], t["relpath"]) for t in conn.execute("SELECT disc, relpath FROM tracks ORDER BY disc")] == [(1, "CD1/01-a.mp3"), (2, "cd2/01-b.mp3")]


def test_release_with_sub_release(conn, music):
    mk(music, "X/Parent-Rel-WEB-2010-GRP", ["01-a.mp3"]); mk(music, "X/Parent-Rel-WEB-2010-GRP/Child-Rel-WEB-2011-GRP", ["01-b.mp3"])
    assert scan_structure(conn, music, now=1.0)["found"] == 2


def test_unchanged_rescan_keeps_sub_release_of_skipped_parent(conn, music):
    mk(music, "X/Parent-Rel-WEB-2010-GRP", ["01-a.mp3"]); mk(music, "X/Parent-Rel-WEB-2010-GRP/Child-Rel-WEB-2011-GRP", ["01-b.mp3"])
    scan_structure(conn, music, now=1.0)
    ids = {r[0] for r in conn.execute("SELECT id FROM releases")}
    stats = scan_structure(conn, music, now=2.0)
    assert stats == {"found": 2, "added": 0, "moved": 0, "removed": 0}
    assert {r[0] for r in conn.execute("SELECT id FROM releases")} == ids


def test_incremental_keeps_tags_and_new_gets_scan_date(conn, music):
    mk(music, "S/Old-Rel-WEB-2015-GRP", ["01-a.mp3"])
    scan_structure(conn, music, now=1000.0)
    old = conn.execute("SELECT id, added_at, mtime FROM releases").fetchone()
    assert old["added_at"] == old["mtime"]                       # premier scan : date du dossier
    conn.execute("UPDATE tracks SET tags_read=1, title='T'"); conn.execute("UPDATE releases SET tags_done=1"); conn.commit()
    d = mk(music, "S/New-Rel-WEB-2016-GRP", ["01-a.mp3"]); os.utime(d, (5.0, 5.0))   # date d'origine conservée par la copie
    stats = scan_structure(conn, music, now=2000.0)
    assert stats["added"] == 1
    assert conn.execute("SELECT added_at FROM releases WHERE name LIKE 'New%'").fetchone()[0] == 2000.0
    assert conn.execute("SELECT title, tags_read FROM tracks WHERE release_id=?", (old["id"],)).fetchone()[:] == ("T", 1)


def test_changed_release_keeps_unchanged_tracks(conn, music):
    d = mk(music, "S/Art-One-WEB-2015-GRP", ["01-a.mp3", "02-b.mp3"]); os.utime(d, (10.0, 10.0))
    scan_structure(conn, music, now=1.0)
    rid, added_at = conn.execute("SELECT id, added_at FROM releases").fetchone()
    tid_a = conn.execute("SELECT id FROM tracks WHERE relpath='01-a.mp3'").fetchone()[0]
    tid_b = conn.execute("SELECT id FROM tracks WHERE relpath='02-b.mp3'").fetchone()[0]
    conn.execute("UPDATE tracks SET tags_read=1, title='T'"); conn.execute("UPDATE releases SET tags_done=1")
    add_user(conn)
    conn.execute("INSERT INTO favorites VALUES(1,'track',?,1)", (tid_a,))
    conn.execute("INSERT INTO favorites VALUES(1,'track',?,1)", (tid_b,)); conn.commit()
    (d / "02-b.mp3").unlink(); (d / "03-c.mp3").write_bytes(b"x"); os.utime(d, (20.0, 20.0))
    scan_structure(conn, music, now=2.0)
    r = conn.execute("SELECT id, added_at, mtime, track_count, tags_done FROM releases").fetchone()
    assert r[:] == (rid, added_at, 20.0, 2, 0)
    tracks = {t["relpath"]: t for t in conn.execute("SELECT * FROM tracks")}
    assert set(tracks) == {"01-a.mp3", "03-c.mp3"}
    assert (tracks["01-a.mp3"]["id"], tracks["01-a.mp3"]["title"], tracks["01-a.mp3"]["tags_read"]) == (tid_a, "T", 1)
    assert tracks["03-c.mp3"]["tags_read"] == 0
    # le favori de la piste disparue est supprimé, l'autre reste
    assert [f[0] for f in conn.execute("SELECT item_id FROM favorites")] == [tid_a]


def test_moved_release_keeps_identity_and_favorites(conn, music):
    mk(music, "S/A/Art-One-WEB-2015-GRP", ["01-a.mp3"]); scan_structure(conn, music, now=1.0)
    rid = conn.execute("SELECT id FROM releases").fetchone()[0]
    conn.execute("INSERT INTO users(id,username,password_hash,role) VALUES(1,'u','x','user')")
    conn.execute("INSERT INTO favorites VALUES(1,'release',?,1)", (rid,)); conn.commit()
    (music / "T").mkdir(); (music / "S/A/Art-One-WEB-2015-GRP").rename(music / "T/Art-One-WEB-2015-GRP")
    stats = scan_structure(conn, music, now=2.0)
    assert (stats["moved"], stats["removed"]) == (1, 0)
    assert conn.execute("SELECT id, path, category FROM releases").fetchone()[:] == (rid, "T/Art-One-WEB-2015-GRP", "T")
    assert conn.execute("SELECT count(*) FROM favorites").fetchone()[0] == 1


def test_removed_release_drops_favorites(conn, music):
    mk(music, "S/Keep-Rel-WEB-2015-GRP", ["01-a.mp3"])
    mk(music, "S/Gone-Rel-WEB-2015-GRP", ["01-a.mp3"])
    scan_structure(conn, music, now=1.0)
    rid = conn.execute("SELECT id FROM releases WHERE name LIKE 'Gone%'").fetchone()[0]
    tid = conn.execute("SELECT id FROM tracks WHERE release_id=?", (rid,)).fetchone()[0]
    add_user(conn)
    conn.execute("INSERT INTO favorites VALUES(1,'release',?,1)", (rid,))
    conn.execute("INSERT INTO favorites VALUES(1,'track',?,1)", (tid,)); conn.commit()
    shutil.rmtree(music / "S/Gone-Rel-WEB-2015-GRP")
    stats = scan_structure(conn, music, now=2.0)
    assert stats["removed"] == 1
    assert conn.execute("SELECT count(*) FROM favorites").fetchone()[0] == 0
    assert [r[0] for r in conn.execute("SELECT name FROM releases")] == ["Keep-Rel-WEB-2015-GRP"]
    assert conn.execute("SELECT count(*) FROM tracks WHERE release_id=?", (rid,)).fetchone()[0] == 0


def test_guard_empty_or_missing_root_changes_nothing(conn, music):
    mk(music, "S/Art-One-WEB-2015-GRP", ["01-a.mp3"]); scan_structure(conn, music, now=1.0)
    shutil.rmtree(music / "S")
    with pytest.raises(ScanError): scan_structure(conn, music, now=2.0)
    with pytest.raises(ScanError): scan_structure(conn, music / "absent", now=2.0)
    assert conn.execute("SELECT count(*) FROM releases").fetchone()[0] == 1


@pytest.mark.skipif(os.geteuid() == 0, reason="root lit les dossiers en mode 000")
def test_unreadable_dir_is_skipped_and_keeps_known_releases(conn, music):
    mk(music, "Locked/Art-One-WEB-2015-GRP", ["01-a.mp3"])
    mk(music, "Open/Art-Two-WEB-2015-GRP", ["01-a.mp3"])
    scan_structure(conn, music, now=1.0)
    mk(music, "Open/Art-Three-WEB-2016-GRP", ["01-a.mp3"])
    os.chmod(music / "Locked", 0)
    try:
        stats = scan_structure(conn, music, now=2.0)
    finally:
        os.chmod(music / "Locked", 0o755)
    assert (stats["added"], stats["removed"]) == (1, 0)
    assert conn.execute("SELECT count(*) FROM releases").fetchone()[0] == 3


@pytest.mark.skipif(sys.platform == "darwin", reason="APFS refuse les noms non UTF-8")
def test_non_utf8_names_do_not_crash(conn, music):            # Review Focus 1
    d = os.fsencode(music) + b"/S/Art-Caf\xe9-WEB-2015-GRP"; os.makedirs(d); open(d + b"/01-caf\xe9.mp3", "wb").close()
    assert scan_structure(conn, music, now=1.0)["found"] == 1
    t = conn.execute("SELECT r.path, t.relpath FROM tracks t JOIN releases r ON r.id=t.release_id").fetchone()
    assert os.path.exists(os.fsencode(music / t["path"] / t["relpath"]))
