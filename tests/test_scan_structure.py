import os
import sqlite3
import shutil
import sys

import pytest

import app.scanner as sc
from app.scanner import ScanError, _storable, scan_structure


def mk(music, rel, files):
    d = music / rel
    d.mkdir(parents=True, exist_ok=True)
    for f in files:
        (d / f).write_bytes(b"x")
    return d


def failing_list(monkeypatch, list_fails=(), stat_fails=()):
    """Remplace scanner._list : listage en échec pour les dossiers `list_fails`, stat en échec pour `stat_fails`."""
    real = sc._list

    class Entry:
        def __init__(self, e):
            self._e, self.name, self.path = e, e.name, e.path
            self.is_file, self.is_dir = e.is_file, e.is_dir

        def stat(self, **kw):
            if self.name in stat_fails:
                raise OSError("EIO")
            return self._e.stat(**kw)

    def fake(path):
        if os.path.basename(path) in list_fails:
            raise OSError("EIO")
        return [Entry(e) for e in real(path)]
    monkeypatch.setattr(sc, "_list", fake)


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


def test_numbered_subfolders_are_discs_and_a_former_disc_release_is_absorbed(conn, music):
    mk(music, "Albums/VA-Annual-3CD-2018-P2P/1", ["01-a.mp3"]); mk(music, "Albums/VA-Annual-3CD-2018-P2P/02", ["01-b.mp3"])
    mk(music, "Singles/2/Two-Song-WEB-2015-GRP", ["01-c.mp3"])                       # « 2 » sans piste directe : un dossier d'artiste
    mk(music, "Albums/VA-Other-2CD-2003-GRP/2003", ["01-d.mp3"])                     # quatre chiffres : pas un disque
    scan_structure(conn, music, now=1.0)
    names = lambda: {r["name"] for r in conn.execute("SELECT name FROM releases")}
    assert names() == {"VA-Annual-3CD-2018-P2P", "Two-Song-WEB-2015-GRP", "2003"}
    assert [(t["disc"], t["relpath"]) for t in conn.execute(
        "SELECT disc, relpath FROM tracks t JOIN releases r ON r.id=t.release_id WHERE r.name LIKE 'VA-Annual%' ORDER BY disc")] == [(1, "1/01-a.mp3"), (2, "02/01-b.mp3")]
    # indexé avant cette règle : chaque disque était une release à part ; le scan suivant les réunit
    conn.execute("DELETE FROM tracks WHERE release_id IN (SELECT id FROM releases WHERE name LIKE 'VA-Annual%')")
    conn.execute("DELETE FROM releases WHERE name LIKE 'VA-Annual%'")
    for d in ("1", "02"):
        conn.execute("INSERT INTO releases(path, name, parent, category, mtime, added_at, size, track_count, has_nfo)"
                     " VALUES (?,?,?,?,0,0,0,1,0)", (f"Albums/VA-Annual-3CD-2018-P2P/{d}", d, "Albums/VA-Annual-3CD-2018-P2P", "Albums"))
    conn.commit()
    scan_structure(conn, music, now=2.0)
    assert names() == {"VA-Annual-3CD-2018-P2P", "Two-Song-WEB-2015-GRP", "2003"}


def test_multi_disc_merged(conn, music):
    mk(music, "Albums/VA-Big-2CD-2003-GRP/CD1", ["01-a.mp3"]); mk(music, "Albums/VA-Big-2CD-2003-GRP/cd2", ["01-b.mp3"])
    scan_structure(conn, music, now=1.0)
    assert conn.execute("SELECT count(*) FROM releases").fetchone()[0] == 1
    assert [(t["disc"], t["relpath"]) for t in conn.execute("SELECT disc, relpath FROM tracks ORDER BY disc")] == [(1, "CD1/01-a.mp3"), (2, "cd2/01-b.mp3")]


def test_series_subfolders_with_tracks_are_discs_whatever_their_name(conn, music):
    base = "Compilations/-=DMC Commercial=-/Dmc Commercial Collection 047"
    mk(music, f"{base}/DMC 047 - Previews (December 1986)", ["01-c.mp3"]); mk(music, f"{base}/DMC 047 - Mixes 2", ["01-b.mp3"])
    mk(music, f"{base}/International", ["01-a.mp3"]); mk(music, f"{base}/Covers", ["front.jpg"])
    mk(music, f"{base}/International/title", ["02-a.mp3"])  # sous-dossier d'un disque : le même disque
    mk(music, "Compilations/-=DMC Commercial=-/!Collection/Some Release", ["01-d.mp3"])  # dossier de collection : à part
    scan_structure(conn, music, now=1.0)
    assert {r["path"] for r in conn.execute("SELECT path FROM releases")} == {base, "Compilations/-=DMC Commercial=-/!Collection/Some Release"}
    assert [(t["disc"], t["relpath"]) for t in conn.execute("SELECT disc, relpath FROM tracks t JOIN releases r ON r.id=t.release_id"
            " WHERE r.path=? ORDER BY disc", (base,))] == [(1, "DMC 047 - Previews (December 1986)/01-c.mp3"),
                                                        (2, "DMC 047 - Mixes 2/01-b.mp3"), (3, "International/01-a.mp3"),
                                                        (3, "International/title/02-a.mp3")]


def test_release_with_sub_release(conn, music):
    mk(music, "X/Parent-Rel-WEB-2010-GRP", ["01-a.mp3"]); mk(music, "X/Parent-Rel-WEB-2010-GRP/Child-Rel-WEB-2011-GRP", ["01-b.mp3"])
    assert scan_structure(conn, music, now=1.0)["found"] == 2


def test_unchanged_rescan_keeps_sub_release_of_skipped_parent(conn, music):
    mk(music, "X/Parent-Rel-WEB-2010-GRP", ["01-a.mp3"]); mk(music, "X/Parent-Rel-WEB-2010-GRP/Child-Rel-WEB-2011-GRP", ["01-b.mp3"])
    scan_structure(conn, music, now=1.0)
    ids = {r[0] for r in conn.execute("SELECT id FROM releases")}
    stats = scan_structure(conn, music, now=2.0)
    assert stats == {"found": 2, "added": 0, "moved": 0, "removed": 0, "skipped": 0, "unreadable": 0}
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
    conn.execute("INSERT INTO favorites VALUES(1,'release',?,1)", (rid,))
    tid = conn.execute("SELECT id FROM tracks").fetchone()[0]
    conn.execute("UPDATE tracks SET tags_read=1, title='T'"); conn.commit()
    (music / "T").mkdir(); (music / "S/A/Art-One-WEB-2015-GRP").rename(music / "T/Art-One-WEB-2015-GRP")
    stats = scan_structure(conn, music, now=2.0)
    assert (stats["found"], stats["added"], stats["moved"], stats["removed"]) == (1, 0, 1, 0)
    assert conn.execute("SELECT id, path, category FROM releases").fetchone()[:] == (rid, "T/Art-One-WEB-2015-GRP", "T")
    assert conn.execute("SELECT count(*) FROM favorites").fetchone()[0] == 1
    assert [t[:] for t in conn.execute("SELECT id, release_id, title, tags_read FROM tracks")] == [(tid, rid, "T", 1)]


def test_interrupted_move_scan_keeps_identity_on_rescan(conn, music, monkeypatch):
    mk(music, "S/A/Art-One-WEB-2015-GRP", ["01-a.mp3"]); mk(music, "S/Keep-WEB-2015-GRP", ["01-a.mp3"])
    scan_structure(conn, music, now=1.0)
    rid = conn.execute("SELECT id FROM releases WHERE name LIKE 'Art%'").fetchone()[0]
    add_user(conn); conn.execute("INSERT INTO favorites VALUES(1,'release',?,1)", (rid,)); conn.commit()
    (music / "T").mkdir(); (music / "S/A/Art-One-WEB-2015-GRP").rename(music / "T/Art-One-WEB-2015-GRP")
    monkeypatch.setattr(sc, "BATCH", 1)   # la release provisionnelle est validée pendant le parcours
    real_name = sc._name
    monkeypatch.setattr(sc, "_name", lambda p: (_ for _ in ()).throw(KeyboardInterrupt()))  # coupure en phase finale
    with pytest.raises(KeyboardInterrupt):
        scan_structure(conn, music, now=2.0)
    monkeypatch.setattr(sc, "_name", real_name)
    stats = scan_structure(conn, music, now=3.0)
    assert (stats["found"], stats["moved"], stats["removed"]) == (2, 1, 0)
    assert conn.execute("SELECT id FROM releases WHERE path='T/Art-One-WEB-2015-GRP'").fetchone()[0] == rid
    assert conn.execute("SELECT count(*) FROM releases").fetchone()[0] == 2
    assert [f[0] for f in conn.execute("SELECT item_id FROM favorites")] == [rid]


def two_same_named(conn, music, singles_tags_done):
    """Albums/X et Singles/X indexés, chacun avec un favori release et piste d'un utilisateur différent."""
    mk(music, "Albums/Art-X-WEB-2015-GRP", ["01-a.mp3"]); mk(music, "Singles/Art-X-WEB-2015-GRP", ["01-a.mp3"])
    scan_structure(conn, music, now=1.0)
    ids = {}
    for user, cat in ((1, "Albums"), (2, "Singles")):
        rid = conn.execute("SELECT id FROM releases WHERE category=?", (cat,)).fetchone()[0]
        tid = conn.execute("SELECT id FROM tracks WHERE release_id=?", (rid,)).fetchone()[0]
        read = cat == "Albums" or singles_tags_done
        conn.execute("UPDATE releases SET tags_done=? WHERE id=?", (read, rid))
        conn.execute("UPDATE tracks SET tags_read=?, title=? WHERE id=?", (read, cat if read else None, tid))
        conn.execute("INSERT INTO users(id,username,password_hash,role) VALUES(?,?,'x','user')", (user, f"u{user}"))
        conn.execute("INSERT INTO favorites VALUES(?,'release',?,1)", (user, rid))
        conn.execute("INSERT INTO favorites VALUES(?,'track',?,1)", (user, tid))
        ids[cat] = rid, tid
    conn.commit()
    shutil.rmtree(music / "Albums")
    return ids


def test_deleted_duplicate_merges_into_indexed_survivor(conn, music):
    ids = two_same_named(conn, music, singles_tags_done=1)
    stats = scan_structure(conn, music, now=2.0)
    # Singles/X n'a pas bougé : Albums/X est supprimé, ses favoris rejoignent Singles/X
    assert (stats["found"], stats["moved"], stats["removed"]) == (1, 0, 1)
    sid, stid = ids["Singles"]
    assert conn.execute("SELECT id, path FROM releases").fetchall()[0][:] == (sid, "Singles/Art-X-WEB-2015-GRP")
    assert [t[:] for t in conn.execute("SELECT id, title, tags_read FROM tracks")] == [(stid, "Singles", 1)]
    assert {f[:] for f in conn.execute("SELECT user_id, kind, item_id FROM favorites")} == \
        {(1, "release", sid), (1, "track", stid), (2, "release", sid), (2, "track", stid)}


def test_deleted_duplicate_survives_over_unread_on_disk_row(conn, music):
    ids = two_same_named(conn, music, singles_tags_done=0)
    stats = scan_structure(conn, music, now=2.0)
    # Singles/X sans tags lus (ex. ligne provisoire) : Albums/X garde son identité au chemin présent
    assert (stats["found"], stats["moved"], stats["removed"]) == (1, 1, 0)
    aid, atid = ids["Albums"]
    assert conn.execute("SELECT id, path FROM releases").fetchall()[0][:] == (aid, "Singles/Art-X-WEB-2015-GRP")
    assert [t[:] for t in conn.execute("SELECT id, title, tags_read FROM tracks")] == [(atid, "Albums", 1)]
    assert {f[:] for f in conn.execute("SELECT user_id, kind, item_id FROM favorites")} == \
        {(1, "release", aid), (1, "track", atid), (2, "release", aid), (2, "track", atid)}


@pytest.mark.parametrize("fail", [{"list_fails": {b"CD1"}}, {"stat_fails": {b"02-b.mp3"}}])
def test_unreadable_disc_or_file_changes_nothing(conn, music, monkeypatch, fail):
    d = mk(music, "S/VA-Big-WEB-2015-GRP", ["02-b.mp3"]); mk(music, "S/VA-Big-WEB-2015-GRP/CD1", ["01-a.mp3"])
    mk(music, "S/Keep-WEB-2015-GRP", ["01-a.mp3"])
    scan_structure(conn, music, now=1.0)
    rid = conn.execute("SELECT id FROM releases WHERE name LIKE 'VA%'").fetchone()[0]
    add_user(conn)
    conn.execute("INSERT INTO favorites VALUES(1,'release',?,1)", (rid,))
    conn.execute("INSERT INTO favorites SELECT 1,'track',id,1 FROM tracks WHERE release_id=?", (rid,))
    conn.execute("UPDATE releases SET tags_done=1"); conn.commit()
    before = [t[:] for t in conn.execute("SELECT * FROM tracks ORDER BY id")]
    (d / "x.jpg").write_bytes(b"x"); os.utime(d, (99.0, 99.0))   # mtime changé : la release est relistée
    failing_list(monkeypatch, **fail)
    stats = scan_structure(conn, music, now=2.0)
    assert (stats["found"], stats["removed"]) == (2, 0)
    assert [t[:] for t in conn.execute("SELECT * FROM tracks ORDER BY id")] == before
    assert conn.execute("SELECT count(*) FROM favorites").fetchone()[0] == 3
    assert conn.execute("SELECT tags_done FROM releases WHERE id=?", (rid,)).fetchone()[0] == 1


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


def test_storable_rejects_non_utf8_names():
    assert _storable("Art-Café-WEB-2015-GRP")
    assert not _storable(os.fsdecode(b"caf\xe9"))


def test_unstorable_names_are_skipped_any_platform(conn, music, monkeypatch):
    # même scénario que ci-dessous, « BAD » simulant un nom non UTF-8 là où le FS les refuse
    monkeypatch.setattr("app.scanner._storable", lambda name: "BAD" not in name)
    mk(music, "S/Art-Good-WEB-2015-GRP", ["01-a.mp3", "02-BAD.mp3"])
    mk(music, "S/Art-BAD-WEB-2015-GRP", ["01-a.mp3"])
    stats = scan_structure(conn, music, now=1.0)
    assert (stats["found"], stats["skipped"]) == (1, 2)
    assert [t[0] for t in conn.execute("SELECT relpath FROM tracks")] == ["01-a.mp3"]


@pytest.mark.skipif(sys.platform == "darwin", reason="APFS refuse les noms non UTF-8")
def test_non_utf8_names_are_skipped(conn, music):            # Review Focus 1
    good = mk(music, "S/Art-Good-WEB-2015-GRP", ["01-a.mp3"])
    open(os.fsencode(good) + b"/02-caf\xe9.mp3", "wb").close()
    bad = os.fsencode(music) + b"/S/Art-Caf\xe9-WEB-2015-GRP"; os.makedirs(bad); open(bad + b"/01-a.mp3", "wb").close()
    stats = scan_structure(conn, music, now=1.0)
    assert (stats["found"], stats["skipped"]) == (1, 2)
    assert [t[0] for t in conn.execute("SELECT relpath FROM tracks")] == ["01-a.mp3"]
    assert [r[0] for r in conn.execute("SELECT name FROM releases")] == ["Art-Good-WEB-2015-GRP"]


def test_no_write_lock_held_while_listing(settings, conn, music, monkeypatch):
    for i in range(3):
        mk(music, f"S/Art-R{i}-WEB-2015-GRP", ["01-a.mp3"])
    other = sqlite3.connect(settings.data_dir / "mp3scene.db", timeout=0)
    real, errors = sc._list, []

    def listing(path):
        try:
            other.execute("UPDATE scan_state SET error='x' WHERE id=1"); other.commit()
        except sqlite3.OperationalError as e:
            errors.append(e)
        return real(path)
    monkeypatch.setattr(sc, "_list", listing)
    assert scan_structure(conn, music, now=1.0)["found"] == 3
    other.close()
    assert errors == []
    assert conn.execute("SELECT count(*) FROM tracks").fetchone()[0] == 3


def test_unreadable_dirs_are_counted_and_logged(conn, music, monkeypatch, caplog):
    mk(music, "S/Keep-WEB-2015-GRP", ["01-a.mp3"])
    mk(music, "S/Locked-WEB-2015-GRP", ["01-a.mp3"])
    mk(music, "S/Nostat-WEB-2015-GRP", ["01-a.mp3"])
    mk(music, "S/Disc-WEB-2015-GRP", ["01-a.mp3"]); mk(music, "S/Disc-WEB-2015-GRP/CD1", ["01-b.mp3"])
    failing_list(monkeypatch, list_fails={b"Locked-WEB-2015-GRP", b"CD1"}, stat_fails={b"Nostat-WEB-2015-GRP"})
    with caplog.at_level("WARNING", logger="app.scanner"):
        stats = scan_structure(conn, music, now=1.0)
    assert (stats["found"], stats["unreadable"]) == (1, 3)
    assert caplog.text.count("dossier illisible ignoré") == 3
    assert all(n in caplog.text for n in ("Locked-WEB-2015-GRP", "Nostat-WEB-2015-GRP", "Disc-WEB-2015-GRP"))


def test_no_known_release_found_changes_nothing(conn, music, monkeypatch):
    mk(music, "S/Art-One-WEB-2015-GRP", ["01-a.mp3"]); mk(music, "S/Art-Two-WEB-2015-GRP", ["01-a.mp3"])
    scan_structure(conn, music, now=1.0)
    rid = conn.execute("SELECT id FROM releases").fetchone()[0]
    add_user(conn); conn.execute("INSERT INTO favorites VALUES(1,'release',?,1)", (rid,)); conn.commit()
    before = [r[:] for r in conn.execute("SELECT * FROM releases ORDER BY id")]
    shutil.rmtree(music / "S")   # racine lisible mais fausse : autre export, dossiers système
    mk(music, "@eaDir/thumbs", ["x.jpg"])
    mk(music, "Other/New-One-WEB-2016-GRP", ["01-a.mp3"]); mk(music, "Other/New-Two-WEB-2016-GRP", ["01-a.mp3"])
    monkeypatch.setattr(sc, "BATCH", 1)   # les nouvelles releases ne doivent pas être validées pendant le parcours
    with pytest.raises(ScanError, match="aucune release connue retrouvée"):
        scan_structure(conn, music, now=2.0)
    assert [r[:] for r in conn.execute("SELECT * FROM releases ORDER BY id")] == before
    assert conn.execute("SELECT count(*) FROM tracks").fetchone()[0] == 2
    assert conn.execute("SELECT count(*) FROM favorites").fetchone()[0] == 1


def test_releases_found_updated_at_each_batch(settings, conn, music, monkeypatch):
    for i in range(3):
        mk(music, f"S/Art-R{i}-WEB-2015-GRP", ["01-a.mp3"])
    monkeypatch.setattr(sc, "BATCH", 1)
    other = sqlite3.connect(settings.data_dir / "mp3scene.db", timeout=0)
    real, counts = sc._list, []

    def listing(path):
        counts.append(other.execute("SELECT releases_found FROM scan_state").fetchone()[0])
        return real(path)
    monkeypatch.setattr(sc, "_list", listing)
    scan_structure(conn, music, now=1.0)
    other.close()
    assert counts == [0, 0, 0, 1, 2]


def test_moved_release_keeps_its_corrections_and_custom_cover(conn, music):
    """BUG-02 : les corrections et la pochette déposée sont rangées sous le chemin ; elles suivent le déplacement."""
    import hashlib
    from pathlib import Path
    mk(music, "S/A/Art-Two-WEB-2015-GRP", ["01-a.mp3"]); scan_structure(conn, music, now=1.0)
    conn.execute("INSERT INTO overrides(path, genre) VALUES ('S/A/Art-Two-WEB-2015-GRP', 'Disco')"); conn.commit()
    covers = Path(conn.execute("PRAGMA database_list").fetchone()[2]).parent / "covers"
    covers.mkdir(exist_ok=True)
    name = lambda p: covers / (hashlib.sha1(p.encode()).hexdigest() + ".jpg")
    name("S/A/Art-Two-WEB-2015-GRP").write_bytes(b"jpg")
    (music / "T").mkdir(); (music / "S/A/Art-Two-WEB-2015-GRP").rename(music / "T/Art-Two-WEB-2015-GRP")
    assert scan_structure(conn, music, now=2.0)["moved"] == 1
    assert conn.execute("SELECT path, genre FROM overrides").fetchone()[:] == ("T/Art-Two-WEB-2015-GRP", "Disco")
    assert name("T/Art-Two-WEB-2015-GRP").read_bytes() == b"jpg" and not name("S/A/Art-Two-WEB-2015-GRP").exists()


def test_named_disc_folders_join_their_album(conn, music):
    from app import db
    base = "Compilations/MoS/2010 - Ministry of Sound - Clubbers Guide 2010 [3CD]"
    for i, d in enumerate(["CD1 - Mixed by Hook N Sling", "CD2 [Sunset Disc]", "CD3 Mixed by Axwell"], 1):
        mk(music, f"{base}/{d}", [f"0{i}-a.mp3"])
    mk(music, "Compilations/MoS/VA-Old_Skool-WEB-2016-P2P/CD1-TDG", ["01-a.mp3"])
    mk(music, "Compilations/MoS/VA-Old_Skool-WEB-2016-P2P/CDM", ["01-b.mp3"])  # pas un disque : une release à part
    scan_structure(conn, music, now=1.0)
    db.categorize(conn)
    rels = {r["path"].rsplit("/", 1)[1]: r for r in conn.execute("SELECT * FROM releases")}
    assert set(rels) == {"2010 - Ministry of Sound - Clubbers Guide 2010 [3CD]", "VA-Old_Skool-WEB-2016-P2P", "CDM"}
    mos = rels["2010 - Ministry of Sound - Clubbers Guide 2010 [3CD]"]
    assert [t["disc"] for t in conn.execute("SELECT disc FROM tracks WHERE release_id=? ORDER BY disc", (mos["id"],))] == [1, 2, 3]
    assert (mos["name"], mos["title"], mos["year"]) == ("Ministry_of_Sound_-_Clubbers_Guide_2010-P2P", "Ministry of Sound Clubbers Guide 2010", 2010)
    conn.execute("UPDATE releases SET name='VA-Ministry_of_Sound_Clubbers_Guide_2010-3CD-2010' WHERE id=?", (mos["id"],))
    db.categorize(conn)  # nom donné par une version antérieure : relu sur le dossier
    assert conn.execute("SELECT name FROM releases WHERE id=?", (mos["id"],)).fetchone()[0] == "Ministry_of_Sound_-_Clubbers_Guide_2010-P2P"


def test_dated_radio_episodes_are_named_artist_show_date(conn, music):
    from app import db
    for d in ["2002-06-09_-_Essential_Mix_-_Michel_de_Hey", "2002-05-05_Essential_Mix_-_Pete_Tong_&_BT_@_Coachella_Festival",
              "2002-04-21_Essential_Mix", "2002-01-13_-_Essential_Mix_-_H-Foundation"]:
        mk(music, f"Live And Radio/Essential Mix/{d}", ["01-a.mp3"])
    mk(music, "Live And Radio/Divers/2002-01-13_-_Random_Show_-_Bob", ["01-a.mp3"])
    scan_structure(conn, music, now=1.0)
    db.categorize(conn)
    got = {r["path"].rsplit("/", 1)[1]: r for r in conn.execute("SELECT * FROM releases")}
    m = got["2002-06-09_-_Essential_Mix_-_Michel_de_Hey"]
    assert (m["name"], m["artist"], m["title"], m["year"]) == ("Michel_de_Hey-Essential_Mix-2002-06-09-P2P", "Michel de Hey", "Essential Mix", 2002)
    assert m["released_at"] == 1023624000  # 9 juin 2002, midi UTC
    # Essential Mix : toujours « Artiste-Essential_Mix-date », quel que soit le format
    from app.db import em_name
    assert em_name("2016-03-19_-_Riva_Starr_&_Axwell_-_Essential_Mix", None, None, None)[0] == "Riva_Starr_&_Axwell-Essential_Mix-2016-03-19"
    assert em_name("Essential Mix_2012_01_07_qrip", "L-Vis 1990", "", "x.mp3")[:2] == ("L-Vis_1990-Essential_Mix-2012-01-07", "L-Vis 1990")
    assert em_name("Carl_Cox_-_Essential_Mix-SAT-10-09-1994-TALiON", None, None, None)[0] == "Carl_Cox-Essential_Mix-1994-10-09"
    assert em_name("2015 10 31 Essential Mix #1136 - Master Series 05 - Dave Clarke", "Dave Clarke", "", None)[0] == "Dave_Clarke-Essential_Mix_Master_Series_05-2015-10-31"
    assert em_name("2002-01-13 Essential Mix - H-Foundation", None, None, None)[0] == "H-Foundation-Essential_Mix-2002-01-13"
    assert em_name("Pete_Tong_-_Live_at_Circus_Liverpool_(500th_Essential_Mix)-SAT-04-23-2010-TALiON", None, None, None)[0] == "Pete_Tong-Essential_Mix_Live_at_Circus_Liverpool_(500th)-2010-04-23"
    assert em_name("BBC Radio 1s Essential Mix 2021 Week 50 - Alan Fitpatrick", None, None, None)[0] == "Alan_Fitpatrick-Essential_Mix-2021-S50"
    assert em_name("Mauro Picotto - BBC Radio1 Essential Mix", None, None, None) is None  # sans date : nom gardé
    assert got["2002-05-05_Essential_Mix_-_Pete_Tong_&_BT_@_Coachella_Festival"]["name"] == "Pete_Tong_&_BT-Essential_Mix_@_Coachella_Festival-2002-05-05-P2P"
    assert got["2002-04-21_Essential_Mix"]["name"] == "Essential_Mix-2002-04-21-P2P"  # sans artiste : rien à sa place
    assert got["2002-01-13_-_Essential_Mix_-_H-Foundation"]["name"] == "H-Foundation-Essential_Mix-2002-01-13-P2P"
    assert got["2002-01-13_-_Random_Show_-_Bob"]["name"] == "2002-01-13_-_Random_Show_-_Bob"  # émission inconnue : intact


def test_file_removed_from_a_disc_subfolder_is_dropped_at_the_next_scan(conn, music, make_mp3):
    from app.scanner import _scan_covers
    rel = music / "Compilations/VA-Big-2CD-2014-GRP"
    (rel / "CD1").mkdir(parents=True)
    make_mp3(rel / "CD1/01-a.mp3"); make_mp3(rel / "CD1/01-a(1).mp3"); make_mp3(rel / "CD1/02-b.mp3")
    os.utime(rel, (1, 1))
    scan_structure(conn, music, now=1.0)
    rid = conn.execute("SELECT id FROM releases").fetchone()[0]
    (rel / "CD1/01-a(1).mp3").unlink()  # le dossier de la release ne change pas : son mtime non plus
    os.utime(rel, (1, 1)); scan_structure(conn, music, now=2.0)
    assert conn.execute("SELECT COUNT(*) FROM tracks").fetchone()[0] == 3  # pas vu par le scan
    conn.execute("UPDATE releases SET has_cover=NULL"); conn.commit()
    _scan_covers(conn, music, lambda: False)                       # la pochette cherchée dans un fichier disparu…
    assert conn.execute("SELECT mtime FROM releases WHERE id=?", (rid,)).fetchone()[0] == 0  # … release relue
    scan_structure(conn, music, now=3.0)
    assert sorted(r[0] for r in conn.execute("SELECT relpath FROM tracks")) == ["CD1/01-a.mp3", "CD1/02-b.mp3"]
