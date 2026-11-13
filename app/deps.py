import time

from fastapi import Depends, HTTPException, Request

from . import db, security


def get_conn(request: Request):
    conn = db.connect(request.app.state.settings.data_dir)
    try:
        yield conn
    finally:
        conn.close()


def current_user(request: Request, conn=Depends(get_conn)):
    token = request.cookies.get(security.COOKIE)
    user = security.session_user(conn, token, time.time()) if token else None
    if user is None:
        raise HTTPException(401, "Authentification requise.")
    return user


def require_admin(user=Depends(current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "Accès réservé aux administrateurs.")
    return user


def csrf(request: Request):
    if (request.method not in ("GET", "HEAD") and request.scope["path"].startswith("/api/")
            and request.headers.get("x-csrf") != "1"):
        raise HTTPException(403, "En-tête X-CSRF manquant.")
