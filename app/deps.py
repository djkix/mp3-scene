from fastapi import Depends, HTTPException, Request

from . import db


def get_conn(request: Request):
    conn = db.connect(request.app.state.settings.data_dir)
    try:
        yield conn
    finally:
        conn.close()


def current_user(request: Request):
    """Utilisateur posé par le middleware de session (toute route protégée est sous /api/)."""
    user = getattr(request.state, "user", None)
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
