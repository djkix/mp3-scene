import os
import re
import stat
import time
import zipfile
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse, StreamingResponse
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


def _track_file(request: Request, conn, track_id: int, download: bool = False, headers: dict | None = None):
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
    if download:
        headers["Content-Disposition"] = _disposition(row["relpath"].rsplit("/", 1)[-1])
    return FileResponse(path, media_type="audio/mpeg", stat_result=st, headers=headers)


@router.get("/api/tracks/{track_id}/stream")
def stream(track_id: Id, request: Request, download: bool = False, conn=Depends(get_conn)):
    return _track_file(request, conn, track_id, download)


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


@cast_router.options("/cast/{track_id}")
def cast_preflight(track_id: int):
    return Response(status_code=204, headers={**CAST_CORS, "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
                                              "Access-Control-Allow-Headers": "Range"})
