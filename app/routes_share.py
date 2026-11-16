"""Liens de partage : une release ou une playlist écoutable sans compte, pendant 7 jours, par un lien signé."""
import time
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from . import db
from .deps import MAX_INT, current_user, get_conn
from .routes_media import _track_file
from .security import SHARE_TTL, check_share, sign_share

router = APIRouter(dependencies=[Depends(current_user)])
public_router = APIRouter()  # hors /api/ : sans session, protégé par le jeton signé
SHARE_PAGE = __import__("pathlib").Path(__file__).resolve().parent.parent / "static" / "share.html"

# pistes d'un partage, dans l'ordre d'écoute
TRACKS = {"r": "SELECT t.id, t.title, t.artist, t.duration, t.relpath FROM tracks t WHERE t.release_id=?"
               " ORDER BY t.disc, t.relpath",
          "p": "SELECT t.id, t.title, t.artist, t.duration, t.relpath FROM playlist_tracks pt JOIN tracks t"
               " ON t.id=pt.track_id WHERE pt.playlist_id=? ORDER BY pt.position, t.id"}
NAME = {"r": "SELECT name FROM releases WHERE id=?", "p": "SELECT name FROM playlists WHERE id=?"}


class Share(BaseModel):
    kind: Literal["release", "playlist"]
    id: int = Field(ge=1, le=MAX_INT)


@router.post("/api/share")
def create_share(body: Share, request: Request, user=Depends(current_user), conn=Depends(get_conn)):
    # ponytail: pas de révocation, le lien vit jusqu'à son échéance ; table de partages si on veut les annuler
    kind = body.kind[0]
    row = conn.execute(NAME[kind] + (" AND user_id=?" if kind == "p" else ""),
                       (body.id, user["id"]) if kind == "p" else (body.id,)).fetchone()
    if row is None:
        raise HTTPException(404, "Élément introuvable.")
    settings = request.app.state.settings
    exp = int(time.time()) + SHARE_TTL
    return {"url": f"{settings.public_url}/s/{sign_share(settings.secret_key, kind, body.id, exp)}", "expires": exp}


def _shared(request: Request, token: str):
    """(connexion, kind, id) d'un jeton valide ; 404 sinon, sans distinguer invalide, expiré ou supprimé."""
    settings = request.app.state.settings
    found = check_share(settings.secret_key, token, time.time())
    if found is None:
        raise HTTPException(404, "Lien de partage invalide ou expiré.")
    return db.connect(settings.data_dir), *found


@public_router.get("/s/{token}")
def share_page(token: str, request: Request):
    conn, _, _ = _shared(request, token)
    conn.close()
    return FileResponse(SHARE_PAGE, media_type="text/html", headers={"Cache-Control": "no-cache", "Referrer-Policy": "no-referrer"})


@public_router.get("/s/{token}/info")
def share_info(token: str, request: Request):
    conn, kind, item_id = _shared(request, token)
    try:
        row = conn.execute(NAME[kind], (item_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "Lien de partage invalide ou expiré.")
        tracks = [{"id": t["id"], "title": t["title"] or t["relpath"].rsplit("/", 1)[-1], "artist": t["artist"],
                   "duration": t["duration"]} for t in conn.execute(TRACKS[kind], (item_id,))]
        return {"name": row["name"], "tracks": tracks}
    finally:
        conn.close()


@public_router.get("/s/{token}/track/{track_id}")
def share_track(token: str, track_id: int, request: Request):
    conn, kind, item_id = _shared(request, token)
    try:
        if not 1 <= track_id <= MAX_INT or all(t["id"] != track_id for t in conn.execute(TRACKS[kind], (item_id,))):
            raise HTTPException(404, "Piste introuvable.")  # le jeton ne donne accès qu'à ses propres pistes
        return _track_file(request, conn, track_id)
    finally:
        conn.close()
