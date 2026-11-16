import time

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from .deps import MAX_INT, Id, current_user, get_conn
from .routes_library import TRACK_COLS, TRACK_FROM, _page, _track

router = APIRouter(dependencies=[Depends(current_user)])


class Name(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class Add(BaseModel):
    track_ids: list[int] = Field(default=[], max_length=1000)
    release_id: int | None = Field(default=None, ge=1, le=MAX_INT)


def _name(body: Name) -> str:
    name = body.name.strip()
    if not name:
        raise HTTPException(422, "Nom vide.")
    return name


def _own(conn, uid, pid):
    """La playlist `pid` si elle appartient à l'utilisateur ; 404 sinon (on ne révèle pas celles des autres)."""
    row = conn.execute("SELECT id, name FROM playlists WHERE id=? AND user_id=?", (pid, uid)).fetchone()
    if row is None:
        raise HTTPException(404, "Playlist introuvable.")
    return row


@router.get("/api/playlists")
def list_playlists(user=Depends(current_user), conn=Depends(get_conn)):
    return [dict(r) for r in conn.execute(
        "SELECT p.id, p.name, COUNT(t.id) AS tracks, COALESCE(SUM(t.duration), 0) AS duration FROM playlists p"
        " LEFT JOIN playlist_tracks pt ON pt.playlist_id=p.id LEFT JOIN tracks t ON t.id=pt.track_id"
        " WHERE p.user_id=? GROUP BY p.id ORDER BY p.name COLLATE NOCASE, p.id", (user["id"],))]


@router.post("/api/playlists", status_code=201)
def create_playlist(body: Name, user=Depends(current_user), conn=Depends(get_conn)):
    name = _name(body)
    pid = conn.execute("INSERT INTO playlists(user_id, name, created_at) VALUES (?,?,?)",
                       (user["id"], name, time.time())).lastrowid
    conn.commit()
    return {"id": pid, "name": name}


@router.put("/api/playlists/{pid}", status_code=204)
def rename_playlist(pid: Id, body: Name, user=Depends(current_user), conn=Depends(get_conn)):
    _own(conn, user["id"], pid)
    conn.execute("UPDATE playlists SET name=? WHERE id=?", (_name(body), pid))
    conn.commit()


@router.delete("/api/playlists/{pid}", status_code=204)
def delete_playlist(pid: Id, user=Depends(current_user), conn=Depends(get_conn)):
    conn.execute("DELETE FROM playlists WHERE id=? AND user_id=?", (pid, user["id"]))
    conn.commit()


@router.get("/api/playlists/{pid}")
def playlist(pid: Id, offset: int = Query(0, ge=0, le=MAX_INT), limit: int = Query(50, ge=1, le=MAX_INT),
             user=Depends(current_user), conn=Depends(get_conn)):
    row = _own(conn, user["id"], pid)
    page = _page(conn, TRACK_COLS, "playlist_tracks pt JOIN " + TRACK_FROM, "WHERE pt.track_id=t.id AND pt.playlist_id=?",
                 [pid], "pt.position, t.id", user["id"], offset, limit, _track)
    return {"id": row["id"], "name": row["name"], **page}


@router.post("/api/playlists/{pid}/tracks", status_code=204)
def add_tracks(pid: Id, body: Add, user=Depends(current_user), conn=Depends(get_conn)):
    """Ajoute des pistes (ou toutes celles d'une release) à la fin ; celles déjà présentes sont ignorées."""
    _own(conn, user["id"], pid)
    ids = list(body.track_ids)
    if body.release_id is not None:
        ids += [r[0] for r in conn.execute("SELECT id FROM tracks WHERE release_id=? ORDER BY disc, relpath",
                                           (body.release_id,))]
    pos = conn.execute("SELECT COALESCE(MAX(position), 0) FROM playlist_tracks WHERE playlist_id=?", (pid,)).fetchone()[0]
    # les identifiants inconnus sont écartés par la sous-requête (pas d'erreur de clé étrangère)
    conn.executemany("INSERT OR IGNORE INTO playlist_tracks(playlist_id, track_id, position)"
                     " SELECT ?, id, ? FROM tracks WHERE id=?",
                     [(pid, pos + n, tid) for n, tid in enumerate(ids, 1) if 0 < tid <= MAX_INT])
    conn.commit()


@router.delete("/api/playlists/{pid}/tracks/{track_id}", status_code=204)
def remove_track(pid: Id, track_id: Id, user=Depends(current_user), conn=Depends(get_conn)):
    _own(conn, user["id"], pid)
    conn.execute("DELETE FROM playlist_tracks WHERE playlist_id=? AND track_id=?", (pid, track_id))
    conn.commit()
