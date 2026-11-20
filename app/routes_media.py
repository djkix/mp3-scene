import hashlib
import io
import os
import re
import shutil
import stat
import subprocess
import threading
import time
import zipfile
from array import array
from pathlib import Path
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse, StreamingResponse
from mutagen.id3 import ID3
from PIL import Image
from pydantic import BaseModel, Field

from . import db
from .deps import MAX_INT, Id, current_user, get_conn
from .security import CAST_TTL, check_track_sig, safe_path, sign_track

router = APIRouter(dependencies=[Depends(current_user)])
# seule route de fichier sans session : protégée par la signature, rien d'autre sur ce routeur
cast_router = APIRouter()

CHUNK = 256 * 1024
CAST_CORS = {"Access-Control-Allow-Origin": "*"}


def _disposition(name: str) -> str:
    # repli ASCII sans guillemet, barre oblique inverse ni caractère de contrôle (CR/LF) : pas d'injection d'en-tête
    fallback = re.sub(r'[^\x20-\x7e]|["\\]', "_", name)
    return f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{quote(name, safe='')}"


TRANSCODE_MAX = 5 * 1024 ** 3  # taille du cache des pistes converties (data/transcode)
_transcode_lock = threading.Lock()


def transcoded(src, cache: Path, track_id: int, mtime: float):
    """Chemin de la piste convertie en MP3 320 kbit/s, gardée dans `cache` ; None sans ffmpeg ou si la conversion échoue.

    Fichier entier, pour que le navigateur puisse s'y déplacer (requêtes Range), l'écouter hors ligne ou le diffuser."""
    out = cache / f"{track_id}-{int(mtime)}.mp3"
    if out.is_file():
        os.utime(out)  # dernière écoute : la purge retire les plus anciennes
        return out
    exe = shutil.which("ffmpeg")
    if exe is None:
        return None
    # ponytail: une conversion à la fois pour tout le serveur, et la première écoute attend sa fin (quelques secondes
    # par piste) ; convertir à l'avance la piste suivante de la file si l'attente gêne
    with _transcode_lock:
        if out.is_file():
            return out
        cache.mkdir(parents=True, exist_ok=True)
        tmp = out.with_suffix(".part")
        try:
            subprocess.run([exe, "-v", "error", "-nostdin", "-y", "-i", str(src), "-vn", "-map_metadata", "0",
                            "-codec:a", "libmp3lame", "-b:a", "320k", "-f", "mp3", str(tmp)],
                           stdin=subprocess.DEVNULL, capture_output=True, timeout=600, check=True)
            os.replace(tmp, out)
        except (subprocess.SubprocessError, OSError):
            tmp.unlink(missing_ok=True)
            return None
        files = sorted(cache.glob("*.mp3"), key=lambda p: p.stat().st_mtime)
        total = sum(p.stat().st_size for p in files)
        for old in files[:-1]:  # jamais celle qui vient d'être convertie
            if total <= TRANSCODE_MAX:
                break
            total -= old.stat().st_size
            old.unlink(missing_ok=True)
    return out


# formats servis tels quels à la demande (réglage « qualité d'origine » du lecteur) ; WMA, APE, WavPack restent convertis
ORIGINAL_TYPES = {".flac": "audio/flac", ".wav": "audio/wav", ".m4a": "audio/mp4", ".ogg": "audio/ogg", ".opus": "audio/ogg"}


def _track_file(request: Request, conn, track_id: int, download: bool = False, headers: dict | None = None,
                original: bool = False):
    row = conn.execute("SELECT r.path, t.relpath FROM tracks t JOIN releases r ON r.id=t.release_id WHERE t.id=?",
                       (track_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "Piste introuvable.")
    path = safe_path(request.app.state.settings.music_root, row["path"], row["relpath"])
    try:
        st = os.stat(path)
        if not stat.S_ISREG(st.st_mode):  # avant open() : ouvrir une FIFO bloquerait le thread
            raise OSError
        with open(path, "rb"):  # lecture seule : vérifie que le fichier s'ouvre (NFS indisponible, droits)
            pass
    except OSError:
        raise HTTPException(404, "Fichier introuvable.") from None
    headers = dict(headers or {})
    mp3 = row["relpath"].lower().endswith(".mp3")
    if download:  # toujours le fichier d'origine
        headers["Content-Disposition"] = _disposition(row["relpath"].rsplit("/", 1)[-1])
        return FileResponse(path, media_type="audio/mpeg" if mp3 else "application/octet-stream", stat_result=st, headers=headers)
    native = ORIGINAL_TYPES.get(os.path.splitext(row["relpath"])[1].lower())
    if original and native:
        return FileResponse(path, media_type=native, stat_result=st, headers=headers)
    if not mp3:  # FLAC, WAV, WMA, M4A… : écoutés en MP3 320 kbit/s, que tout navigateur et tout Chromecast lit
        path = transcoded(path, request.app.state.settings.data_dir / "transcode", track_id, st.st_mtime)
        if path is None:
            raise HTTPException(503, "Conversion impossible : ffmpeg est absent ou le fichier est illisible.")
        st = os.stat(path)
    return FileResponse(path, media_type="audio/mpeg", stat_result=st, headers=headers)


@router.get("/api/tracks/{track_id}/stream")
def stream(track_id: Id, request: Request, download: bool = False, original: bool = False, conn=Depends(get_conn)):
    """`original` : le fichier tel quel pour un format que les navigateurs savent lire (FLAC, WAV, M4A, OGG, Opus),
    au lieu de sa conversion en MP3 ; ignoré pour les autres formats."""
    return _track_file(request, conn, track_id, download, original=original)


IMAGE_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}
COVER_MAX = 8 * 1024 * 1024
COVER_CACHE = {"Cache-Control": "private, max-age=86400"}
_FRONT = ("front", "cover", "folder")
_NOT_FRONT = ("back", "inlay", "inside", "cd", "cd1", "cd2", "disc", "booklet", "proof")


def custom_cover(data_dir: Path, release_path: str) -> Path:
    """Fichier de la pochette déposée à la main pour cette release : nommé d'après son chemin, il survit aux scans."""
    return data_dir / "covers" / (hashlib.sha1(release_path.encode("utf-8")).hexdigest() + ".jpg")


def save_cover(data_dir: Path, release_path: str, rid: int, data: bytes | None) -> None:
    """Enregistre (ou retire, `data` None) la pochette déposée à la main et oublie la vignette déjà calculée."""
    target = custom_cover(data_dir, release_path)
    if data is None:
        target.unlink(missing_ok=True)
    else:
        with Image.open(io.BytesIO(data)) as img:  # lève une erreur si ce n'est pas une image
            img = img.convert("RGB")
            img.thumbnail((1600, 1600))
            target.parent.mkdir(exist_ok=True)
            tmp = target.with_suffix(".tmp")
            img.save(tmp, "JPEG", quality=88)
        os.replace(tmp, target)
    (data_dir / "thumbs" / f"{rid}.jpg").unlink(missing_ok=True)


def pick_cover(names: list[str]) -> str | None:
    """Image de pochette parmi les fichiers d'un dossier : « front/cover/folder » d'abord, « back/cd/… » en dernier."""
    def rank(name: str):
        stem = name.lower().rsplit(".", 1)[0]
        return (0 if stem.endswith(_FRONT) else 2 if stem.endswith(_NOT_FRONT) else 1, name.lower())
    images = [n for n in names if os.path.splitext(n)[1].lower() in IMAGE_TYPES]
    return min(images, key=rank, default=None)


def _find_cover(request: Request, conn, rid: int):
    """Pochette d'une release : (chemin, None, type) pour une image du dossier, (None, octets, type) pour celle
    incluse dans les tags de la première piste. 404 s'il n'y en a pas."""
    root = request.app.state.settings.music_root
    row = conn.execute("SELECT path FROM releases WHERE id=?", (rid,)).fetchone()
    if row is None:
        raise HTTPException(404, "Release introuvable.")
    custom = custom_cover(request.app.state.settings.data_dir, row["path"])
    if custom.is_file():  # pochette déposée par un administrateur : elle passe avant celle du dossier
        return custom, None, "image/jpeg"
    try:
        name = pick_cover([p.name for p in safe_path(root, row["path"]).iterdir()])
        if name:
            path = safe_path(root, row["path"], name)
            st = os.stat(path)
            if stat.S_ISREG(st.st_mode) and st.st_size <= COVER_MAX:
                return path, None, IMAGE_TYPES[os.path.splitext(name)[1].lower()]
        first = conn.execute("SELECT relpath FROM tracks WHERE release_id=? ORDER BY disc, relpath LIMIT 1",
                             (rid,)).fetchone()
        if first:
            with open(safe_path(root, row["path"], first["relpath"]), "rb") as fh:  # lecture seule
                pics = ID3(fh).getall("APIC")
            if pics and pics[0].mime in IMAGE_TYPES.values() and len(pics[0].data) <= COVER_MAX:
                return None, pics[0].data, pics[0].mime
    except HTTPException:
        raise
    except Exception:  # dossier illisible, tags absents ou corrompus : pas de pochette
        pass
    raise HTTPException(404, "Pochette introuvable.")


@router.get("/api/releases/{rid}/cover")
def cover(rid: Id, request: Request, conn=Depends(get_conn)):
    path, data, mime = _find_cover(request, conn, rid)
    if path:
        return FileResponse(path, media_type=mime, headers=COVER_CACHE)
    return Response(data, media_type=mime, headers=COVER_CACHE)


THUMB_SIZE = 128  # affichée en 40 px : nette sur écran haute densité


@router.get("/api/releases/{rid}/thumb")
def thumb(rid: Id, request: Request, conn=Depends(get_conn)):
    """Vignette de la pochette, pour les listes. Créée à la première demande puis gardée dans data/thumbs/ ;
    un fichier vide y retient qu'une release n'a pas de pochette (pas de nouvelle recherche sur le NAS)."""
    # ponytail: jamais invalidée ni nettoyée (environ 5 Ko par release) ; supprimer data/thumbs/ pour tout refaire
    folder = request.app.state.settings.data_dir / "thumbs"
    cached = folder / f"{rid}.jpg"
    try:
        size = cached.stat().st_size
    except OSError:
        size = None
    if size is None:
        folder.mkdir(exist_ok=True)
        tmp = folder / f"{rid}.{threading.get_ident()}.tmp"
        try:
            path, data, _ = _find_cover(request, conn, rid)
            with Image.open(path or io.BytesIO(data)) as img:
                img = img.convert("RGB")
                img.thumbnail((THUMB_SIZE, THUMB_SIZE))
                img.save(tmp, "JPEG", quality=80)
        except HTTPException as err:
            if err.detail != "Pochette introuvable.":
                raise  # release inconnue : rien à retenir
            tmp.write_bytes(b"")
        except Exception:  # image illisible
            tmp.write_bytes(b"")
        os.replace(tmp, cached)  # écriture atomique : jamais de vignette à moitié écrite
        size = cached.stat().st_size
    if not size:
        raise HTTPException(404, "Pochette introuvable.")
    return FileResponse(cached, media_type="image/jpeg", headers=COVER_CACHE)


WAVE_POINTS = 800   # largeur de la forme d'onde, en barres
WAVE_RATE = 8000    # décodage en mono 8 kHz : largement assez pour une enveloppe
WAVE_WINDOW = 800   # échantillons par crête intermédiaire (0,1 s)
WAVE_TIMEOUT = 600
# ponytail: un seul calcul à la fois pour tout le serveur (un mix de 2 h occupe un cœur 20 à 60 s) ;
# passer à un verrou par piste si l'attente devient gênante à plusieurs utilisateurs.
_wave_lock = threading.Lock()


def _decode_cmd(path) -> list[str] | None:
    """Commande qui écrit la piste en PCM 16 bits mono sur sa sortie ; None si aucun décodeur n'est installé."""
    if str(path).lower().endswith(".mp3") and (exe := shutil.which("mpg123")):  # petit et rapide, MP3 seulement
        return [exe, "-q", "-s", "-m", "-r", str(WAVE_RATE), "-e", "s16", str(path)]
    if exe := shutil.which("ffmpeg"):
        return [exe, "-v", "error", "-nostdin", "-i", str(path), "-vn", "-ac", "1", "-ar", str(WAVE_RATE),
                "-f", "s16le", "-"]
    return None


def reduce_peaks(peaks: list[int], points: int = WAVE_POINTS) -> bytes:
    """Ramène une suite de crêtes à `points` valeurs au plus, de 0 à 255 (255 = crête la plus forte de la piste)."""
    if not peaks:
        return b""
    n = min(points, len(peaks))
    out = [max(peaks[i * len(peaks) // n:(i + 1) * len(peaks) // n]) for i in range(n)]
    top = max(out) or 1
    return bytes(v * 255 // top for v in out)


def compute_waveform(path) -> bytes | None:
    cmd = _decode_cmd(path)
    if cmd is None:
        return None
    peaks, deadline = [], time.monotonic() + WAVE_TIMEOUT
    proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    try:
        while chunk := proc.stdout.read(WAVE_WINDOW * 2):
            if time.monotonic() > deadline:
                return None
            samples = array("h", chunk[:len(chunk) & ~1])  # ordre des octets natif : petit-boutiste sur x86 et ARM
            if samples:
                peaks.append(max(max(samples), -min(samples)))
    finally:
        proc.kill()
        proc.wait()
    return reduce_peaks(peaks) or None


@router.get("/api/tracks/{track_id}/waveform")
def waveform(track_id: Id, request: Request, conn=Depends(get_conn)):
    """Forme d'onde de la piste : calculée à la première demande, puis gardée en base."""
    def cached():
        row = conn.execute("SELECT peaks FROM waveforms WHERE track_id=?", (track_id,)).fetchone()
        return row and {"peaks": list(row["peaks"])}
    if hit := cached():
        return hit
    row = conn.execute("SELECT r.path, t.relpath FROM tracks t JOIN releases r ON r.id=t.release_id WHERE t.id=?",
                       (track_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "Piste introuvable.")
    path = safe_path(request.app.state.settings.music_root, row["path"], row["relpath"])
    with _wave_lock:
        if hit := cached():  # calculée par une autre requête pendant l'attente
            return hit
        peaks = compute_waveform(path)  # aucune écriture SQLite pendant la lecture du fichier
        if not peaks:
            raise HTTPException(404, "Forme d'onde indisponible.")
        conn.execute("INSERT OR REPLACE INTO waveforms(track_id, peaks) VALUES (?,?)", (track_id, peaks))
        conn.commit()
    return {"peaks": list(peaks)}


class _Sink:
    """Fichier en écriture seule, non positionnable : zipfile y écrit avec des descripteurs de données."""

    def __init__(self):
        self.chunks = []

    def write(self, b):
        self.chunks.append(bytes(b))
        return len(b)

    def flush(self):
        pass

    def drain(self):
        chunks, self.chunks = self.chunks, []
        return chunks


def _release_files(folder):
    """[(nom relatif, chemin)] des fichiers ordinaires du dossier, récursivement, sans suivre les liens."""
    files = []
    for dirpath, dirnames, filenames in os.walk(folder):  # followlinks=False : liens de dossiers ignorés
        dirnames.sort()
        for name in sorted(filenames):
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, folder)
            try:
                if os.path.islink(full):
                    continue
                p = safe_path(folder, rel)  # revérifié : sous le dossier de la release
                if not stat.S_ISREG(os.lstat(p).st_mode):
                    continue
            except (HTTPException, OSError):
                continue
            files.append((rel.replace(os.sep, "/"), p))
    return files


def _zip_stream(name, files):
    sink = _Sink()
    with zipfile.ZipFile(sink, "w", zipfile.ZIP_STORED, allowZip64=True) as zf:
        for rel, p in files:
            # nom non UTF-8 (surrogateescape) : zipfile ne peut pas l'écrire, il est gardé sous un nom sûr
            arcname = f"{name}/{os.fsencode(rel).decode('utf-8', 'replace')}"
            try:
                info = zipfile.ZipInfo.from_file(p, arcname, strict_timestamps=False)
                src = open(p, "rb")  # lecture seule
            except OSError:
                continue  # fichier illisible au moment de l'archive : sauté
            # une erreur de lecture en cours de fichier interrompt le flux plutôt que livrer un fichier tronqué
            with src, zf.open(info, "w") as dst:
                while chunk := src.read(CHUNK):
                    dst.write(chunk)
                    yield from sink.drain()
            yield from sink.drain()
    yield from sink.drain()


@router.get("/api/releases/{rid}/zip")
def release_zip(rid: Id, request: Request, conn=Depends(get_conn)):
    row = conn.execute("SELECT path, name FROM releases WHERE id=?", (rid,)).fetchone()
    if row is None:
        raise HTTPException(404, "Release introuvable.")
    folder = safe_path(request.app.state.settings.music_root, row["path"])
    if not folder.is_dir():
        raise HTTPException(404, "Dossier introuvable.")
    return StreamingResponse(_zip_stream(row["name"], _release_files(folder)), media_type="application/zip",
                             headers={"Content-Disposition": _disposition(f"{row['name']}.zip")})


class CastRequest(BaseModel):
    track_ids: Annotated[list[Annotated[int, Field(ge=1, le=MAX_INT)]], Field(min_length=1, max_length=500)]


@router.post("/api/cast/urls")
def cast_urls(body: CastRequest, request: Request, conn=Depends(get_conn)):
    settings = request.app.state.settings
    ids = sorted(set(body.track_ids))
    found = conn.execute(f"SELECT id FROM tracks WHERE id IN ({','.join('?' * len(ids))})", ids).fetchall()
    exp = int(time.time()) + CAST_TTL
    return {"urls": {str(r["id"]): f"{settings.public_url}/cast/{r['id']}?exp={exp}"
                                    f"&sig={sign_track(settings.secret_key, r['id'], exp)}" for r in found}}


@cast_router.api_route("/cast/{track_id}", methods=["GET", "HEAD"])
def cast(track_id: int, request: Request, exp: str = "", sig: str = ""):
    # signature vérifiée avant toute base ou lecture : un tiers n'apprend rien sur l'existence d'une piste
    settings = request.app.state.settings
    if not check_track_sig(settings.secret_key, track_id, exp, sig, time.time()):
        raise HTTPException(403, "Lien de diffusion invalide ou expiré.")
    if not 1 <= track_id <= MAX_INT:  # hors bornes SQLite : vérifié après la signature, comme toute piste inconnue
        raise HTTPException(404, "Piste introuvable.")
    conn = db.connect(settings.data_dir)
    try:
        return _track_file(request, conn, track_id, headers={
            **CAST_CORS, "Access-Control-Expose-Headers": "Content-Range, Accept-Ranges, Content-Length"})
    finally:
        conn.close()


@cast_router.get("/cast/{track_id}/cover")
def cast_cover(track_id: int, request: Request, exp: str = "", sig: str = ""):
    """Pochette de la release d'une piste, pour l'écran du Chromecast : même signature que la piste."""
    settings = request.app.state.settings
    if not check_track_sig(settings.secret_key, track_id, exp, sig, time.time()):
        raise HTTPException(403, "Lien de diffusion invalide ou expiré.")
    if not 1 <= track_id <= MAX_INT:
        raise HTTPException(404, "Piste introuvable.")
    conn = db.connect(settings.data_dir)
    try:
        row = conn.execute("SELECT release_id FROM tracks WHERE id=?", (track_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "Piste introuvable.")
        path, data, mime = _find_cover(request, conn, row["release_id"])
    finally:
        conn.close()
    headers = {**CAST_CORS, **COVER_CACHE}
    return FileResponse(path, media_type=mime, headers=headers) if path else Response(data, media_type=mime, headers=headers)


@cast_router.options("/cast/{track_id}")
def cast_preflight(track_id: int):
    return Response(status_code=204, headers={**CAST_CORS, "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
                                              "Access-Control-Allow-Headers": "Range"})
