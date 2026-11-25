import logging
import os
import mimetypes
import time
import urllib.parse
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from . import config, db, navidrome, routes_admin, routes_auth, routes_library, routes_media, routes_playlists, routes_share, security
from .config import Settings
from .deps import csrf
from .scanner import Runner

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
PUBLIC_API = ("/api/login", "/api/health")
log = logging.getLogger("uvicorn.error")
mimetypes.add_type("application/manifest+json", ".webmanifest")  # absent de la table de certaines plateformes


class NoCacheStatic(StaticFiles):
    # revalidation (ETag) à chaque chargement : un redéploiement est pris en compte tout de suite
    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-cache"
        return response


# media-src data: : son silencieux qui autorise le second élément audio sur mobile (enchaînement sans blanc) ;
# style 'unsafe-inline' : attributs style posés par l'interface (largeur des barres, couleurs des graphiques) ;
# aucun script en ligne n'est servi. « www.gstatic.com » sans schéma : celui de la page (https en production), le SDK
# Cast chargeant ses fichiers par des adresses sans schéma
CSP = ("default-src 'self'; script-src 'self' www.gstatic.com; style-src 'self' 'unsafe-inline'; "
       "img-src 'self' https: data: blob:; media-src 'self' blob: data:; connect-src 'self' https://api.github.com; "
       "frame-src 'self' www.gstatic.com; font-src 'self'; object-src 'none'; base-uri 'self'; "
       "form-action 'self'; frame-ancestors 'none'")

def _bootstrap_admin(settings: Settings) -> None:
    conn = db.connect(settings.data_dir)
    try:
        if conn.execute("SELECT 1 FROM users LIMIT 1").fetchone() is None:
            if not (settings.admin_user and settings.admin_password):
                log.warning("Aucun utilisateur et ADMIN_USER / ADMIN_PASSWORD non renseignés : impossible de se "
                            "connecter. Renseignez-les dans .env puis relancez le conteneur.")
                return
            username = settings.admin_user.strip()
            if err := security.username_error(username):
                raise RuntimeError(f"ADMIN_USER invalide : {err}")
            if err := security.password_error(settings.admin_password):
                raise RuntimeError(f"ADMIN_PASSWORD invalide : {err}")
            conn.execute("INSERT INTO users(username, password_hash, role) VALUES (?,?,'admin')",
                         (username, security.hash_password(settings.admin_password)))
            conn.commit()
    finally:
        conn.close()


def _setup_logging() -> None:
    """Journaux de l'appli (logger « app », dont le scan) avec horodatage, sans toucher à ceux d'uvicorn."""
    logger = logging.getLogger("app")
    logger.setLevel(logging.INFO)
    if not logger.handlers:  # create_app peut être appelé plusieurs fois (tests)
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        logger.addHandler(handler)


@asynccontextmanager
async def lifespan(app: FastAPI):
    url = urllib.parse.urlsplit(app.state.settings.public_url)
    if url.scheme == "http" and url.hostname not in ("localhost", "127.0.0.1", "::1"):
        # liens de cast et de partage en clair : refusé (le réglage attendu est l'adresse https du proxy)
        raise RuntimeError("PUBLIC_URL doit être en https (seul un poste local peut rester en http).")
    if not app.state.settings.public_url.startswith(("http://", "https://")):
        log.warning("PUBLIC_URL est vide ou invalide (attendu : https://mp3.exemple.fr) : les URL envoyées au "
                    "Chromecast seraient relatives et le cast ne fonctionnera pas.")
    db.EXTRA_KINDS = dict(app.state.settings.extra_kinds)  # avant init : la catégorie des releases en dépend
    db.init(app.state.settings.data_dir)
    _bootstrap_admin(app.state.settings)
    app.state.runner.resume()
    yield
    app.state.runner.stop()


def _with_conn(settings: Settings, fn, *args):
    conn = db.connect(settings.data_dir)
    try:
        return fn(conn, *args, time.time())
    finally:
        conn.close()


MAX_BODY = 1024 * 1024                 # corps de requête au plus (JSON) ; au-delà : 413
MAX_BODY_COVER = 8 * 1024 * 1024 + 65536  # pochette déposée par un administrateur (8 Mo et l'enveloppe)


class BodyLimit:
    """Coupe tout corps de requête au-delà du plafond, annoncé (Content-Length) ou reçu par morceaux (chunked), avant
    que l'application ne le lise en mémoire : même /api/login, sans compte, ne peut pas épuiser la mémoire."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        path = scope["path"]
        cap = MAX_BODY_COVER if scope["method"] == "PUT" and path.startswith("/api/admin/releases/") and path.endswith("/cover") \
            else MAX_BODY
        declared = dict(scope["headers"]).get(b"content-length")
        if declared is not None and (not declared.isdigit() or int(declared) > cap):
            return await self._refuse(scope, receive, send, 413 if declared.isdigit() else 400)
        seen = 0

        async def limited():
            nonlocal seen
            msg = await receive()
            if msg["type"] == "http.request":
                seen += len(msg.get("body", b""))
                if seen > cap:
                    raise _TooLarge
            return msg
        try:
            await self.app(scope, limited, send)
        except _TooLarge:
            await self._refuse(scope, receive, send, 413)

    @staticmethod
    async def _refuse(scope, receive, send, status):
        await JSONResponse({"detail": "Corps de requête trop volumineux." if status == 413 else "Longueur invalide."},
                           status_code=status)(scope, receive, send)


class _TooLarge(Exception):
    pass


def create_app(settings: Settings | None = None) -> FastAPI:
    _setup_logging()
    app = FastAPI(title="Mp3 Scene", lifespan=lifespan, dependencies=[Depends(csrf)],
                  docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = settings or config.load()
    app.state.runner = Runner(app.state.settings)
    app.state.limiter = security.LoginLimiter()
    app.add_middleware(BodyLimit)
    # fichiers créés par l'application (base, sauvegardes, vignettes) lisibles par elle seule
    os.umask(0o077)

    @app.middleware("http")
    async def require_session(request: Request, call_next):
        # avant le routage : toute URL /api/ (même inconnue) exige une session
        path = request.scope["path"]
        if not path.startswith("/api/") or path in PUBLIC_API:
            return await call_next(request)
        # une requête déclenchée par un autre site (lien, image, formulaire) : refusée même en GET, car certaines
        # lectures écrivent (photos d'artistes) ; ni l'application ni les liens publics n'appellent /api/ ainsi
        if request.headers.get("sec-fetch-site") == "cross-site":
            return JSONResponse({"detail": "Requête d'un autre site refusée."}, status_code=403)
        settings = app.state.settings
        token = request.cookies.get(security.COOKIE)
        user = token and await run_in_threadpool(_with_conn, settings, security.session_user, token)
        if not user:
            return JSONResponse({"detail": "Authentification requise."}, status_code=401)
        request.state.user = user  # lu par deps.current_user, sans seconde requête
        response = await call_next(request)
        # échéance repoussée : le cookie glisse aussi, sauf si le traitement a posé un cookie ou invalidé la session
        if (user["renewed"] and "set-cookie" not in response.headers
                and await run_in_threadpool(_with_conn, settings, security.session_exists, token)):
            security.set_session_cookie(response, token)
        return response

    @app.middleware("http")  # déclaré en dernier : enveloppe tout, y compris les 401 et les fichiers statiques
    async def nosniff(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        # pas d'affichage dans le cadre d'un autre site (clic forcé d'un administrateur connecté) ; scripts de
        # l'application et du SDK Cast seulement ; images distantes pour les pochettes proposées (Deezer, iTunes, Discogs)
        response.headers["Content-Security-Policy"] = CSP
        response.headers["X-Frame-Options"] = "DENY"
        response.headers.setdefault("Referrer-Policy", "same-origin")  # la page d'un partage garde son no-referrer
        return response

    @app.get("/api/health")
    async def health():  # sur la boucle d'événements : répond même si tous les threads sont occupés
        return {"ok": True}

    for module in (routes_auth, routes_admin, routes_library, routes_media, routes_playlists, routes_share, navidrome):
        app.include_router(module.router)
    app.include_router(routes_media.cast_router)  # hors /api/ : sans session, URL signée
    app.include_router(navidrome.cast_router)  # idem, pour les pistes de Navidrome
    app.include_router(routes_share.public_router)  # idem : lien de partage signé
    app.mount("/", NoCacheStatic(directory=STATIC_DIR, html=True), name="static")  # après les routeurs
    return app
