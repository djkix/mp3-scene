import os
import sqlite3
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from . import security
from .deps import Id, get_conn, require_admin

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
