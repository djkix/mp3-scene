import ipaddress
import time

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from . import db, security
from .deps import current_user, get_conn

router = APIRouter(prefix="/api")


class Login(BaseModel):
    username: str = Field(max_length=64)
    password: str = Field(max_length=1024)


class PasswordChange(BaseModel):
    current: str = Field(max_length=1024)
    new: str = Field(max_length=1024)


def client_ip(request: Request) -> str:
    # un seul proxy de confiance, qui ajoute l'adresse réelle en DERNIER ; les entrées précédentes viennent du client
    # plusieurs lignes possibles : un proxy qui ajoute sa propre ligne laisse celle du client en premier.
    # L'en-tête n'est cru que si la connexion vient du réseau local (le proxy, dans Docker) : un client d'Internet
    # qui joindrait directement le port de l'application ne peut pas choisir son adresse.
    peer = request.client.host if request.client else ""
    try:
        direct = ipaddress.ip_address(peer).is_global
    except ValueError:
        direct = False  # nom (client de test) : pas une adresse d'Internet
    parts = [p.strip() for p in ",".join(request.headers.getlist("x-forwarded-for")).split(",") if p.strip()]
    if parts and not direct:
        return parts[-1]
    return peer


@router.post("/login")
def login(body: Login, request: Request, response: Response, conn=Depends(get_conn)):
    limiter = request.app.state.limiter
    username = body.username.strip()
    ip = client_ip(request)
    # le blocage à 5 essais vise le couple identifiant + adresse, et l'adresse seule : un inconnu ne peut pas bloquer
    # un compte depuis chez lui. L'identifiant seul a un plafond large, contre une attaque répartie sur beaucoup d'adresses
    keys = ((f"u:{username}|{ip}", 5), (f"u:{username}", 50), (f"ip:{ip}", 5))
    now = time.time()
    if not limiter.attempt(keys, now):
        raise HTTPException(429, "Trop de tentatives échouées, réessayez dans 15 minutes.")
    row = conn.execute("SELECT id, username, role, password_hash FROM users WHERE username = ?", (username,)).fetchone()
    ok = security.verify_password(row["password_hash"] if row else security.DUMMY_HASH, body.password)
    if row is None or not ok:
        db.log(conn, username[:60] or "—", "Connexion refusée", client_ip(request))
        conn.commit()
        raise HTTPException(401, "Identifiant ou mot de passe incorrect.")
    limiter.reset(keys[0][0])
    limiter.reset(keys[1][0])
    # IP : on retire seulement l'essai de cette requête ; ses échecs passés comptent toujours
    limiter.forgive(keys[2][0])
    old = request.cookies.get(security.COOKIE)
    if old:
        security.drop_session(conn, old)
    security.set_session_cookie(response, security.create_session(conn, row["id"], now))
    db.log(conn, row["username"], "Connexion", client_ip(request))
    conn.commit()
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
    if err := security.password_error(body.new):
        raise HTTPException(400, err)
    conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (security.hash_password(body.new), user["id"]))
    conn.commit()
    security.drop_sessions(conn, user["id"], keep=request.cookies[security.COOKIE])
