import os
import sqlite3
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from . import security
from .deps import MAX_INT, Id, get_conn, require_admin
from .routes_library import RELEASE_COLS, RELEASE_FROM, Dir, Sort, _order, _page, _release

router = APIRouter(prefix="/api/admin", dependencies=[Depends(require_admin)])

Role = Literal["admin", "user"]
# condition SQL : l'utilisateur ciblé n'est pas le dernier admin (évaluée dans la même requête que l'écriture)
NOT_LAST_ADMIN = "(role != 'admin' OR (SELECT count(*) FROM users WHERE role = 'admin') > 1)"


class NewUser(BaseModel):
    username: str
    password: str = Field(max_length=1024)
    role: Role


class UserPatch(BaseModel):
    password: str | None = Field(default=None, max_length=1024)
    role: Role | None = None


def _check(err: str | None) -> None:
    if err:
        raise HTTPException(400, err)


def _get_user(conn, user_id: int):
    row = conn.execute("SELECT id, role FROM users WHERE id = ?", (user_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "Utilisateur introuvable.")
    return row


@router.get("/version")
def version():
    return {"version": os.environ.get("APP_VERSION", "dev")}  # posée à la construction de l'image


@router.get("/users")
def list_users(conn=Depends(get_conn)):
    return [dict(r) for r in conn.execute("SELECT id, username, role FROM users ORDER BY username")]


@router.post("/users", status_code=201)
def create_user(body: NewUser, conn=Depends(get_conn)):
    username = body.username.strip()
    _check(security.username_error(username))
    _check(security.password_error(body.password))
    try:
        cur = conn.execute("INSERT INTO users(username, password_hash, role) VALUES (?,?,?)",
                           (username, security.hash_password(body.password), body.role))
        conn.commit()
    except sqlite3.IntegrityError:
        raise HTTPException(409, "Ce nom d'utilisateur existe déjà.")
    return {"id": cur.lastrowid, "username": username, "role": body.role}


@router.patch("/users/{user_id}", status_code=204)
def update_user(user_id: Id, body: UserPatch, conn=Depends(get_conn)):
    _get_user(conn, user_id)
    pw_hash = None
    if body.password is not None:
        _check(security.password_error(body.password))
        pw_hash = security.hash_password(body.password)  # avant toute écriture : le hachage dure ~100 ms
    if body.role == "user":
        cur = conn.execute(f"UPDATE users SET role = 'user' WHERE id = ? AND {NOT_LAST_ADMIN}", (user_id,))
        if cur.rowcount == 0:
            raise HTTPException(409, "Impossible de rétrograder le dernier administrateur.")
    elif body.role == "admin":
        conn.execute("UPDATE users SET role = 'admin' WHERE id = ?", (user_id,))
    if pw_hash is not None:
        conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (pw_hash, user_id))
        security.drop_sessions(conn, user_id)  # valide aussi la transaction
    conn.commit()


@router.delete("/users/{user_id}", status_code=204)
def delete_user(user_id: Id, conn=Depends(get_conn)):
    _get_user(conn, user_id)
    cur = conn.execute(f"DELETE FROM users WHERE id = ? AND {NOT_LAST_ADMIN}", (user_id,))
    conn.commit()
    if cur.rowcount == 0:
        raise HTTPException(409, "Impossible de supprimer le dernier administrateur.")


@router.post("/scan", status_code=202)
def start_scan(request: Request):
    if not request.app.state.runner.start():
        raise HTTPException(409, "Un scan est déjà en cours.")
    return {"started": True}


@router.get("/scan")
def scan_status(request: Request, conn=Depends(get_conn)):
    return request.app.state.runner.status(conn)


@router.get("/library")
def library_stats(conn=Depends(get_conn)):
    """Tableau de bord : totaux et répartitions de la bibliothèque."""
    def rows(sql):
        return [dict(r) for r in conn.execute(sql)]

    def by(col, order="n DESC", limit=15):
        return rows(f"SELECT {col} AS name, COUNT(*) AS n, SUM(size) AS size FROM releases WHERE {col} IS NOT NULL"
                    f" GROUP BY 1 ORDER BY {order} LIMIT {limit}")

    total = dict(conn.execute("SELECT COUNT(*) AS releases, COALESCE(SUM(size), 0) AS size, COALESCE(SUM(track_count), 0)"
                              " AS tracks, COALESCE(SUM(duration), 0) AS duration FROM releases").fetchone())
    return {**total, "years": by("year", "1 DESC", 40), "genres": by("genre"), "sources": by("source"),
            "categories": by("category"),
            "bitrates": rows("SELECT CASE WHEN bitrate>=320000 THEN '320' WHEN bitrate>=256000 THEN '256' WHEN bitrate>=192000"
                             " THEN '192' WHEN bitrate>=128000 THEN '128' ELSE '<128' END AS name, COUNT(*) AS n,"
                             " SUM(size) AS size FROM tracks WHERE bitrate IS NOT NULL GROUP BY 1 ORDER BY MIN(bitrate) DESC"),
            "months": rows("SELECT strftime('%Y-%m', added_at, 'unixepoch') AS name, COUNT(*) AS n, SUM(size) AS size"
                           " FROM releases GROUP BY 1 ORDER BY 1 DESC LIMIT 24")}


# contrôles qualité : condition SQL sur la release r (jamais de texte du client dans le SQL)
QUALITY = {
    "no_nfo": "r.has_nfo=0",
    "no_tracks": "r.track_count=0",
    "no_tags": "r.tags_done=1 AND r.track_count>0 AND NOT EXISTS (SELECT 1 FROM tracks WHERE release_id=r.id AND title IS NOT NULL)",
    "unreadable": "EXISTS (SELECT 1 FROM tracks WHERE release_id=r.id AND tags_read=1 AND duration IS NULL)",
    "low_bitrate": "(SELECT AVG(bitrate) FROM tracks WHERE release_id=r.id)<192000",
    "no_year": "r.year IS NULL",
    "no_cover": "r.has_cover=0",  # NULL : pas encore vérifié par le scan
}


@router.get("/quality")
def quality(kind: Literal["no_nfo", "no_tracks", "no_tags", "unreadable", "low_bitrate", "no_year", "no_cover"] | None = None,
            sort: Sort | None = None, dir: Dir = "asc", offset: int = Query(0, ge=0, le=MAX_INT),
            limit: int = Query(50, ge=1, le=MAX_INT), user=Depends(require_admin), conn=Depends(get_conn)):
    """Sans `kind` : nombre de releases par contrôle. Avec : la page de releases concernées."""
    if kind is None:
        return {k: conn.execute(f"SELECT COUNT(*) FROM releases r WHERE {cond}").fetchone()[0] for k, cond in QUALITY.items()}
    return _page(conn, RELEASE_COLS, RELEASE_FROM, "WHERE " + QUALITY[kind], [],
                 _order(sort, dir, "r.name COLLATE NOCASE, r.id"), user["id"], offset, limit, _release)
