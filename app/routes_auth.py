import time

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from . import security
from .deps import current_user, get_conn

router = APIRouter(prefix="/api")


class Login(BaseModel):
    username: str = Field(max_length=64)
    password: str = Field(max_length=1024)


class PasswordChange(BaseModel):
    current: str = Field(max_length=1024)
    new: str = Field(max_length=1024)


def client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else ""


@router.post("/login")
def login(body: Login, request: Request, response: Response, conn=Depends(get_conn)):
    limiter = request.app.state.limiter
    username = body.username.strip()
    keys = (f"u:{username}", f"ip:{client_ip(request)}")
    now = time.time()
    if any(limiter.blocked(k, now) for k in keys):
        raise HTTPException(429, "Trop de tentatives échouées, réessayez dans 15 minutes.")
    row = conn.execute("SELECT id, username, role, password_hash FROM users WHERE username = ?", (username,)).fetchone()
    ok = security.verify_password(row["password_hash"] if row else security.DUMMY_HASH, body.password)
    if row is None or not ok:
        for k in keys:
            limiter.fail(k, now)
        raise HTTPException(401, "Identifiant ou mot de passe incorrect.")
    limiter.reset(keys[0])  # jamais la clé IP : un compte valide ne doit pas lever le blocage d'une IP
    old = request.cookies.get(security.COOKIE)
    if old:
        security.drop_session(conn, old)
    security.set_session_cookie(response, security.create_session(conn, row["id"], now))
    return {"username": row["username"], "role": row["role"]}


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, conn=Depends(get_conn), user=Depends(current_user)):
    security.drop_session(conn, request.cookies[security.COOKIE])
    response.delete_cookie(security.COOKIE, path="/", httponly=True, secure=True, samesite="lax")


@router.get("/me")
def me(user=Depends(current_user)):
    return {"username": user["username"], "role": user["role"]}


@router.post("/me/password", status_code=204)
def change_password(body: PasswordChange, request: Request, conn=Depends(get_conn), user=Depends(current_user)):
    h = conn.execute("SELECT password_hash FROM users WHERE id = ?", (user["id"],)).fetchone()[0]
    if not security.verify_password(h, body.current):
        raise HTTPException(400, "Le mot de passe actuel est incorrect.")
    if len(body.new) < 8:
        raise HTTPException(400, "Le nouveau mot de passe doit contenir au moins 8 caractères.")
    conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (security.hash_password(body.new), user["id"]))
    conn.commit()
    security.drop_sessions(conn, user["id"], keep=request.cookies[security.COOKIE])
