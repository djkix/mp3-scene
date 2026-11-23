import builtins
import io
import sqlite3
import threading

import pytest

import app.scanner as sc
from app.scanner import Runner, scan_structure, scan_tags


def release(music, make_mp3, *tracks):
    d = music / "S/Art-One-WEB-2015-GRP"
    d.mkdir(parents=True)
    for name, kw in tracks:
        make_mp3(d / name, **kw)
    return d


def test_tags_read_and_release_aggregates(conn, music, make_mp3):
    release(music, make_mp3, ("01-a.mp3", dict(title="Alpha", artist="Art", genre="House")),
            ("02-b.mp3", dict(title="Beta", artist="Art", genre="Techno")))
    scan_structure(conn, music, now=1.0)
    assert scan_tags(conn, music) == 2
    t = conn.execute("SELECT title, artist, bitrate, duration FROM tracks ORDER BY relpath").fetchone()
    assert (t["title"], t["artist"], t["bitrate"]) == ("Alpha", "Art", 128000) and 0.9 < t["duration"] < 1.2
    r = conn.execute("SELECT genre, tag_artist, tags_done, duration FROM releases").fetchone()
    assert (r["genre"], r["tag_artist"], r["tags_done"]) == ("House", "Art", 1) and r["duration"] > 1.8


def test_mixed_artists_leave_tag_artist_null(conn, music, make_mp3):
    release(music, make_mp3, ("01-a.mp3", dict(artist="One")), ("02-b.mp3", dict(artist="Two")))
    scan_structure(conn, music, now=1.0)
    assert scan_tags(conn, music) == 2
    r = conn.execute("SELECT tag_artist, tags_done FROM releases").fetchone()
    assert (r["tag_artist"], r["tags_done"]) == (None, 1)


def test_blank_tags_become_null(conn, music, make_mp3):
    release(music, make_mp3, ("01-a.mp3", dict(title="  ", artist=" Art ")))
    scan_structure(conn, music, now=1.0)
    scan_tags(conn, music)
    t = conn.execute("SELECT title, artist, genre FROM tracks").fetchone()
    assert (t["title"], t["artist"], t["genre"]) == (None, "Art", None)


def test_broken_files_are_marked_and_skipped(conn, music, make_mp3):
    d = release(music, make_mp3, ("03-notags.mp3", {}))
    (d / "01-empty.mp3").write_bytes(b""); (d / "02-junk.mp3").write_bytes(b"not an mp3" * 50)
    scan_structure(conn, music, now=1.0)
    assert scan_tags(conn, music) == 3
    assert conn.execute("SELECT count(*) FROM tracks WHERE tags_read=1").fetchone()[0] == 3
    assert conn.execute("SELECT tags_done FROM releases").fetchone()[0] == 1
    assert scan_tags(conn, music) == 0


def test_missing_file_stays_pending(conn, music, make_mp3):
    d = release(music, make_mp3, ("01-a.mp3", {}), ("02-b.mp3", {}))
    scan_structure(conn, music, now=1.0)
    (d / "02-b.mp3").unlink()  # NFS indisponible ou fichier disparu depuis la phase structure
    assert scan_tags(conn, music) == 1
    assert [r[0] for r in conn.execute("SELECT tags_read FROM tracks ORDER BY relpath")] == [1, 0]
    assert conn.execute("SELECT tags_done FROM releases").fetchone()[0] == 0
    make_mp3(d / "02-b.mp3")
    assert scan_tags(conn, music) == 1
    assert conn.execute("SELECT tags_done FROM releases").fetchone()[0] == 1


def test_tags_resumable(conn, music, make_mp3, monkeypatch):
    release(music, make_mp3, *[(f"0{i}-x.mp3", {}) for i in range(3)])
    scan_structure(conn, music, now=1.0)
    monkeypatch.setattr(sc, "TAG_BATCH", 1)
    calls = []

    def stop_after_first_batch():
        calls.append(1)
        return len(calls) > 1
    first = scan_tags(conn, music, should_stop=stop_after_first_batch)
    assert 0 < first < 3
    assert first + scan_tags(conn, music) == 3
    assert conn.execute("SELECT count(*) FROM tracks WHERE tags_read=0").fetchone()[0] == 0


def test_runner_refuses_concurrent_scan(settings, conn, music, monkeypatch):  # conn : db.init
    entered, release_ = threading.Event(), threading.Event()

    def blocked(conn, root, now):
        entered.set()
        release_.wait(5)
        return {"found": 0}
    monkeypatch.setattr(sc, "scan_structure", blocked)
    r = Runner(settings)
    assert r.start() is True
    assert entered.wait(5)
    assert r.start() is False
    release_.set()
    r._thread.join(5); assert not r._thread.is_alive()


def test_runner_error_then_success(settings, conn, music, make_mp3):
    r = Runner(settings)
    assert r.start() is True; r._thread.join(5); assert not r._thread.is_alive()
    s = r.status(conn); assert s["status"] == "error" and s["error"] and s["finished_at"]
    release(music, make_mp3, ("01-a.mp3", {}))
    assert r.start() is True; r._thread.join(5); assert not r._thread.is_alive()
    s = r.status(conn)
    assert (s["status"], s["releases_found"], s["tracks_pending"], s["error"]) == ("idle", 1, 0, None)
    assert s["finished_at"] >= s["started_at"] > 0


def test_runner_stop_interrupts_tags(settings, conn, music, monkeypatch):
    entered = threading.Event()

    def slow_tags(conn, root, should_stop=lambda: False):
        entered.set()
        while not should_stop():
            r._stop.wait(5)
        return 0
    monkeypatch.setattr(sc, "scan_structure", lambda conn, root, now: {"found": 0})
    monkeypatch.setattr(sc, "scan_tags", slow_tags)
    r = Runner(settings)
    assert r.start() is True
    assert entered.wait(5)
    r.stop()
    assert not r._thread.is_alive()
    assert r.status(conn)["status"] == "idle"


def test_resume_resets_stale_status_and_reads_pending_tags(settings, conn, music, make_mp3):
    release(music, make_mp3, ("01-a.mp3", dict(title="Alpha")))
    scan_structure(conn, music, now=1.0)
    conn.execute("UPDATE scan_state SET status='structure'"); conn.commit()
    r = Runner(settings)
    r.resume()
    r._thread.join(5); assert not r._thread.is_alive()
    s = r.status(conn)
    assert (s["status"], s["tracks_pending"]) == ("idle", 0)
    assert s["error"] == "scan interrompu pendant l'analyse des dossiers — à relancer"   # survit à la reprise des tags
    assert conn.execute("SELECT title FROM tracks").fetchone()[0] == "Alpha"


def test_resume_without_pending_only_resets(settings, conn):
    conn.execute("UPDATE scan_state SET status='tags'"); conn.commit()
    r = Runner(settings)
    r.resume()
    assert r._thread is None
    assert r.status(conn)["status"] == "idle"


@pytest.mark.parametrize("fail_after", [0, 1, 2, 3, 4])  # 1 : mutagen renvoie None ; sinon ValueError(contexte OSError)
def test_read_error_after_open_stays_pending(conn, music, make_mp3, monkeypatch, fail_after):
    d = release(music, make_mp3, ("01-a.mp3", dict(title="Alpha")))
    scan_structure(conn, music, now=1.0)
    real_open = builtins.open

    class Flaky(io.BytesIO):
        n = 0

        def read(self, *a):
            self.n += 1
            if self.n > fail_after:
                raise OSError(5, "EIO")
            return super().read(*a)

    def fake_open(path, *a, **k):
        if str(path) == str(d / "01-a.mp3"):
            with real_open(path, "rb") as f:
                return Flaky(f.read())
        return real_open(path, *a, **k)
    monkeypatch.setattr(builtins, "open", fake_open)
    from app import security
    real_regular = security.open_regular  # le scan ouvre les fichiers par security.open_regular (sans suivre de lien)
    monkeypatch.setattr(security, "open_regular", lambda path, root=None: fake_open(path) if str(path) == str(d / "01-a.mp3")
                        else real_regular(path, root))
    assert scan_tags(conn, music) == 0
    assert conn.execute("SELECT tags_read FROM tracks").fetchone()[0] == 0


def test_no_write_lock_held_while_reading_files(settings, conn, music, make_mp3, monkeypatch):
    release(music, make_mp3, ("01-a.mp3", {}), ("02-b.mp3", {}))
    scan_structure(conn, music, now=1.0)
    other = sqlite3.connect(settings.data_dir / "mp3scene.db", timeout=0)
    real, errors = sc._read_tags, []

    def reading(path):
        try:
            other.execute("UPDATE scan_state SET error='x' WHERE id=1"); other.commit()
        except sqlite3.OperationalError as e:
            errors.append(e)
        return real(path)
    monkeypatch.setattr(sc, "_read_tags", reading)
    assert scan_tags(conn, music) == 2
    other.close()
    assert errors == []


def test_resume_after_kill_in_structure_leaves_hint(settings, conn):
    conn.execute("UPDATE scan_state SET status='structure'"); conn.commit()
    r = Runner(settings)
    r.resume()
    assert r._thread is None
    s = r.status(conn)
    assert (s["status"], s["error"]) == ("idle", "scan interrompu pendant l'analyse des dossiers — à relancer")


def test_runner_stores_warning_but_stays_idle_and_logs(settings, conn, music, make_mp3, monkeypatch, caplog):
    release(music, make_mp3, ("01-a.mp3", {}))
    (music / "S/Locked").mkdir(); (music / "S/BAD").mkdir()
    monkeypatch.setattr(sc, "_storable", lambda name: "BAD" not in name)
    real = sc._list

    def listing(path):
        if path.endswith(b"/Locked"):
            raise OSError("EIO")
        return real(path)
    monkeypatch.setattr(sc, "_list", listing)
    r = Runner(settings)
    with caplog.at_level("INFO", logger="app.scanner"):
        assert r.start() is True; r._thread.join(5); assert not r._thread.is_alive()
    s = r.status(conn)
    assert (s["status"], s["releases_found"]) == ("idle", 1)
    assert s["error"] == "1 dossier(s) illisible(s) et 1 nom(s) non UTF-8 ignorés — voir les journaux"
    assert "scan lancé" in caplog.text and "phase structure terminée" in caplog.text
    assert "'unreadable': 1" in caplog.text and "phase tags terminée : 1 piste(s)" in caplog.text
    # un scan propre efface l'avertissement
    monkeypatch.setattr(sc, "_list", real); monkeypatch.setattr(sc, "_storable", lambda name: True)
    assert r.start() is True; r._thread.join(5)
    assert r.status(conn)["error"] is None


def test_bpm_tag_is_read_as_a_plausible_number():
    from app.scanner import _bpm
    assert [_bpm(v) for v in ("128", "127.98", "128,0 BPM", "0", "?", None, "999")] == [128.0, 128.0, 128.0, None, None, None, None]


def test_scan_never_follows_a_symlinked_nfo_or_cue(conn, music, make_mp3, tmp_path):
    """SEC-01 : un lien « 00.nfo » ou « evil.cue » vers un fichier hors de la bibliothèque n'est jamais lu."""
    import os
    from app import cue, scanner
    secret = tmp_path / "secret.txt"
    secret.write_text("SECRET_KEY=topsecretvalue\nFILE \"01-a.mp3\" MP3\n  TRACK 01 AUDIO\n    INDEX 01 00:00:00\n"
                      "  TRACK 02 AUDIO\n    INDEX 01 01:00:00\n")
    d = release(music, make_mp3, ("01-a.mp3", dict(title="Alpha")))
    (d / "99-ok.nfo").write_text("ok nfo")
    os.symlink(secret, d / "00-evil.nfo")
    os.symlink(secret, d / "evil.cue")
    scan_structure(conn, music, now=1.0)
    rid = conn.execute("SELECT id FROM releases").fetchone()[0]
    scanner._scan_nfo_text(conn, music, lambda: False)
    assert conn.execute("SELECT COUNT(*) FROM nfo_fts WHERE nfo_fts MATCH 'topsecretvalue'").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM nfo_fts WHERE nfo_fts MATCH 'ok'").fetchone()[0] == 1
    tid = conn.execute("SELECT id, relpath FROM tracks").fetchone()
    assert cue.for_tracks(d, [(tid[0], tid[1])]) == {}
