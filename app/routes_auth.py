import ipaddress
import time

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from . import config, db, security
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
        addr = ipaddress.ip_address(peer)
        addr = getattr(addr, "ipv4_mapped", None) or addr  # « ::ffff:203.0.113.5 » : l'adresse IPv4 réelle
        app = request.scope.get("app")
        nets = app.state.settings.trusted_proxies if app is not None else config.TRUSTED_DEFAULT
        trusted = any(addr in ipaddress.ip_network(n, strict=False) for n in nets)
        peer = str(addr)
    except ValueError:
        trusted = True  # pas une adresse (client de test) : jamais le cas d'une vraie connexion
    parts = [p.strip() for p in ",".join(request.headers.getlist("x-forwarded-for")).split(",") if p.strip()]
    if parts and trusted:
        try:
            last = ipaddress.ip_address(parts[-1])  # une valeur qui n'est pas une adresse est ignorée
            return str(getattr(last, "ipv4_mapped", None) or last)
        except ValueError:
            pass
    return peer


def limit_key(ip: str) -> str:
    """Clé du limiteur pour une adresse : une adresse IPv6 compte pour tout son /64 (un accès en a 2^64)."""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return ip
    return str(ipaddress.ip_network(f"{addr}/64", strict=False)) if addr.version == 6 else ip


@router.post("/login")
def login(body: Login, request: Request, response: Response, conn=Depends(get_conn)):
    limiter = request.app.state.limiter
    username = body.username.strip()
    ip = client_ip(request)
    net = limit_key(ip)
    # le blocage à 5 essais vise le couple identifiant + adresse (IPv6 : son /64), et l'adresse seule : un inconnu ne
    # peut pas bloquer un compte depuis chez lui. L'identifiant seul a un plafond large, contre une attaque répartie
    # sur beaucoup d'adresses ; une adresse d'où ce compte s'est déjà connecté (30 jours) n'y est pas soumise, pour que
    # le propriétaire ne soit jamais bloqué par cette attaque
    known = conn.execute("SELECT 1 FROM activity WHERE user=? AND action='Connexion' AND detail=? AND at>? LIMIT 1",
                         (username, ip, time.time() - 30 * 86400)).fetchone()
    keys = ((f"u:{username}|{net}", 5), (f"ip:{net}", 5)) + (() if known else ((f"u:{username}", 50),))
    now = time.time()
    if not limiter.attempt(keys, now):
        raise HTTPException(429, "Trop de tentatives échouées, réessayez dans 15 minutes.")
    row = conn.execute("SELECT id, username, role, password_hash FROM users WHERE username = ?", (username,)).fetchone()
    ok = security.verify_password(row["password_hash"] if row else security.DUMMY_HASH, body.password)
    if row is None or not ok:
        db.log(conn, username[:60] or "—", "Connexion refusée", client_ip(request))
        conn.commit()
        raise HTTPException(401, "Identifiant ou mot de passe incorrect.")
    limiter.reset(f"u:{username}|{net}")
    limiter.reset(f"u:{username}")
    # IP : on retire seulement l'essai de cette requête ; ses échecs passés comptent toujours
    limiter.forgive(f"ip:{net}")
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
    # même limite que la connexion : avec un cookie volé, le mot de passe actuel ne se devine pas sans fin
    limiter, net = request.app.state.limiter, limit_key(client_ip(request))
    if not limiter.attempt(((f"pw:{user['id']}", 5), (f"ip:{net}", 10)), time.time()):
        raise HTTPException(429, "Trop de tentatives échouées, réessayez dans 15 minutes.")
    h = conn.execute("SELECT password_hash FROM users WHERE id = ?", (user["id"],)).fetchone()[0]
    if not security.verify_password(h, body.current):
        raise HTTPException(400, "Le mot de passe actuel est incorrect.")
    limiter.reset(f"pw:{user['id']}")
    limiter.forgive(f"ip:{net}")
    if err := security.password_error(body.new):
        raise HTTPException(400, err)
    conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (security.hash_password(body.new), user["id"]))
    conn.commit()
    security.drop_sessions(conn, user["id"], keep=request.cookies[security.COOKIE])
    db.log(conn, user["username"], "Mot de passe changé")
    conn.commit()
