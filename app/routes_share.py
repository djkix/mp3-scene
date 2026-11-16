"""Liens de partage : une release ou une playlist écoutable sans compte, pendant 7 jours, par un lien secret révocable."""
import secrets
import time
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from . import db
from .deps import MAX_INT, Id, current_user, get_conn
from .routes_media import _track_file
from .security import SHARE_TTL, check_share

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
    kind = body.kind[0]
    row = conn.execute(NAME[kind] + (" AND user_id=?" if kind == "p" else ""),
                       (body.id, user["id"]) if kind == "p" else (body.id,)).fetchone()
    if row is None:
        raise HTTPException(404, "Élément introuvable.")
    now = time.time()
    token = secrets.token_urlsafe(18)
    conn.execute("DELETE FROM shares WHERE expires_at<?", (now,))
    conn.execute("INSERT INTO shares(token, user_id, kind, item_id, created_at, expires_at) VALUES (?,?,?,?,?,?)",
                 (token, user["id"], kind, body.id, now, now + SHARE_TTL))
    conn.commit()
    return {"url": f"{request.app.state.settings.public_url}/s/{token}", "expires": int(now + SHARE_TTL)}


@router.get("/api/shares")
def list_shares(request: Request, user=Depends(current_user), conn=Depends(get_conn)):
    """Liens de partage en cours de l'utilisateur, les plus récents d'abord."""
    base = request.app.state.settings.public_url
    return [{"id": r["id"], "kind": "release" if r["kind"] == "r" else "playlist", "name": r["name"],
             "url": f"{base}/s/{r['token']}", "created_at": r["created_at"], "expires_at": r["expires_at"],
             "opens": r["opens"]} for r in conn.execute(
        "SELECT s.*, COALESCE(r.name, p.name) AS name FROM shares s LEFT JOIN releases r ON s.kind='r' AND r.id=s.item_id"
        " LEFT JOIN playlists p ON s.kind='p' AND p.id=s.item_id WHERE s.user_id=? AND s.expires_at>=?"
        " ORDER BY s.created_at DESC, s.id DESC", (user["id"], time.time()))]


@router.delete("/api/shares/{share_id}", status_code=204)
def revoke_share(share_id: Id, user=Depends(current_user), conn=Depends(get_conn)):
    conn.execute("DELETE FROM shares WHERE id=? AND user_id=?", (share_id, user["id"]))
    conn.commit()


def _shared(request: Request, token: str, opened: bool = False):
    """(connexion, kind, id) d'un lien valide ; 404 sinon, sans distinguer invalide, expiré ou révoqué."""
    settings = request.app.state.settings
    conn = db.connect(settings.data_dir)
    row = conn.execute("SELECT id, kind, item_id FROM shares WHERE token=? AND expires_at>=?", (token, time.time())).fetchone()
    if row is not None:
        if opened:
            conn.execute("UPDATE shares SET opens=opens+1 WHERE id=?", (row["id"],))
            conn.commit()
        return conn, row["kind"], row["item_id"]
    # ponytail: liens signés de la 1.15.0, sans ligne en base donc non révocables ; à retirer après le 24/11/2026
    found = check_share(settings.secret_key, token, time.time())
    if found is None:
        conn.close()
        raise HTTPException(404, "Lien de partage invalide ou expiré.")
    return conn, *found


@public_router.get("/s/{token}")
def share_page(token: str, request: Request):
    conn, _, _ = _shared(request, token)
    conn.close()
    return FileResponse(SHARE_PAGE, media_type="text/html", headers={"Cache-Control": "no-cache", "Referrer-Policy": "no-referrer"})


@public_router.get("/s/{token}/info")
def share_info(token: str, request: Request):
    conn, kind, item_id = _shared(request, token, opened=True)
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
