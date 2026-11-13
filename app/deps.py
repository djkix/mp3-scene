from typing import Annotated

from fastapi import Depends, HTTPException, Path, Request


from . import db

# plus grand entier SQLite : au-delà, sqlite3 lève OverflowError (500) ; FastAPI répond 422 avant
MAX_INT = 2**63 - 1
Id = Annotated[int, Path(ge=1, le=MAX_INT)]


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
