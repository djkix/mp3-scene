"""Sauvegarde de la base vers un dossier (NAS monté) : un dossier daté par jour, sept gardés.

Ce qui est sauvegardé : la base SQLite (comptes, favoris, playlists, historique, corrections, règles) et, si le dossier
de la pile est monté, son fichier compose et son .env. Ni la musique (déjà sur le NAS), ni les vignettes, ni les pistes
converties (reconstruites à la demande). Sans chiffrement."""
import logging
import shutil
import sqlite3
import threading
import time
from pathlib import Path

from . import db

log = logging.getLogger(__name__)
KEEP = 7
STALE = 36 * 3600  # sans sauvegarde réussie depuis ce délai, l'administration alerte
_lock = threading.Lock()  # une seule sauvegarde à la fois (planifiée ou à la main)
_CONFIG = ("compose.yaml", "compose.yml", "docker-compose.yml", "docker-compose.yaml", ".env")


def _copy(settings, tmp: Path) -> int:
    """Écrit la sauvegarde dans `tmp` ; renvoie la taille de la base copiée."""
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    # copie à chaud par l'API de sauvegarde de SQLite : cohérente même pendant un scan
    src = sqlite3.connect(f"file:{settings.data_dir / 'mp3scene.db'}?mode=ro", uri=True)
    try:
        dst = sqlite3.connect(tmp / "mp3scene.db")
        try:
            src.backup(dst)
            if dst.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RuntimeError("copie de la base corrompue")
        finally:
            dst.close()
    finally:
        src.close()
    covers = settings.data_dir / "covers"  # pochettes déposées à la main : elles n'existent nulle part ailleurs
    if covers.is_dir():
        shutil.copytree(covers, tmp / "covers")
    for name in _CONFIG:  # configuration de la pile, si son dossier est monté
        if (settings.stack_dir / name).is_file():
            (tmp / "config").mkdir(exist_ok=True)
            shutil.copy2(settings.stack_dir / name, tmp / "config" / name)
    size = (tmp / "mp3scene.db").stat().st_size
    (tmp / "sauvegarde.txt").write_text(f"date : {time.strftime('%Y-%m-%d %H:%M:%S')}\nbase : {size} octets\n", encoding="utf-8")
    return size


def run(settings, now: float | None = None) -> dict:
    """Fait la sauvegarde du jour et l'inscrit dans backup_runs. Une tentative ratée ne supprime rien."""
    now = now or time.time()
    if settings.backup_dir is None:
        return {"ok": False, "message": "Sauvegarde non configurée (BACKUP_DIR)."}
    if not _lock.acquire(blocking=False):
        return {"ok": False, "message": "Sauvegarde déjà en cours."}
    try:
        target = settings.backup_dir / time.strftime("%Y-%m-%d", time.localtime(now))
        tmp = settings.backup_dir / ".en-cours"
        size, message = 0, ""
        try:
            size = _copy(settings, tmp)
            shutil.rmtree(target, ignore_errors=True)  # une deuxième sauvegarde le même jour remplace la première
            tmp.rename(target)
            days = sorted(p for p in settings.backup_dir.iterdir() if p.is_dir() and len(p.name) == 10 and p.name[4] == "-")
            for old in days[:-KEEP]:
                shutil.rmtree(old, ignore_errors=True)
        except Exception as e:  # dossier absent ou en lecture seule, NAS éteint, disque plein…
            log.exception("sauvegarde")
            message = f"{type(e).__name__} : {e}"[:300]
        ok = not message
        conn = db.connect(settings.data_dir)
        try:
            conn.execute("INSERT INTO backup_runs(started_at, finished_at, ok, message, size) VALUES (?,?,?,?,?)",
                         (now, time.time(), int(ok), message, size))
            conn.commit()
        finally:
            conn.close()
        return {"ok": ok, "message": message, "size": size}
    finally:
        _lock.release()


def due(conn, settings, now: float) -> bool:
    """Vrai si la sauvegarde du jour reste à faire : heure atteinte, pas encore réussie aujourd'hui (une nuit manquée
    est donc rattrapée dès que l'application tourne), et aucune tentative depuis une heure."""
    if settings.backup_dir is None or time.localtime(now).tm_hour < settings.backup_hour:
        return False
    today = time.mktime(time.localtime(now)[:3] + (0, 0, 0, 0, 0, -1))
    done = conn.execute("SELECT 1 FROM backup_runs WHERE ok=1 AND started_at>=?", (today,)).fetchone()
    last = conn.execute("SELECT MAX(started_at) FROM backup_runs").fetchone()[0] or 0
    return done is None and now - last > 3600


def status(conn, settings, now: float | None = None) -> dict:
    """État affiché dans l'administration."""
    now = now or time.time()
    last = conn.execute("SELECT started_at, finished_at, ok, message, size FROM backup_runs ORDER BY started_at DESC LIMIT 1").fetchone()
    last_ok = conn.execute("SELECT MAX(started_at) FROM backup_runs WHERE ok=1").fetchone()[0]
    return {"configured": settings.backup_dir is not None, "hour": settings.backup_hour,
            "last": last and {**dict(last), "ok": bool(last["ok"])}, "last_ok_at": last_ok,
            # en retard : configurée, et rien de réussi depuis 36 heures (ou jamais, une fois la première tentative faite)
            "late": settings.backup_dir is not None and last is not None and now - (last_ok or 0) > STALE}
