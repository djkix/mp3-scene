import time
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from . import config, db, routes_admin, routes_auth, routes_library, routes_media, security
from .config import Settings
from .deps import csrf
from .scanner import Runner

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
PUBLIC_API = ("/api/login", "/api/health")


class NoCacheStatic(StaticFiles):
    # revalidation (ETag) à chaque chargement : un redéploiement est pris en compte tout de suite
    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-cache"
        return response


def _bootstrap_admin(settings: Settings) -> None:
    if not (settings.admin_user and settings.admin_password):
        return
    conn = db.connect(settings.data_dir)
    try:
        if conn.execute("SELECT 1 FROM users LIMIT 1").fetchone() is None:
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


@asynccontextmanager
async def lifespan(app: FastAPI):
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


def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(title="Mp3 Scene", lifespan=lifespan, dependencies=[Depends(csrf)],
                  docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = settings or config.load()
    app.state.runner = Runner(app.state.settings)
    app.state.limiter = security.LoginLimiter()

    @app.middleware("http")
    async def require_session(request: Request, call_next):
        # avant le routage : toute URL /api/ (même inconnue) exige une session
        path = request.scope["path"]
        if not path.startswith("/api/") or path in PUBLIC_API:
            return await call_next(request)
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

    @app.get("/api/health")
    def health():
        return {"ok": True}

    for module in (routes_auth, routes_admin, routes_library, routes_media):
        app.include_router(module.router)
    app.include_router(routes_media.cast_router)  # hors /api/ : sans session, URL signée
    app.mount("/", NoCacheStatic(directory=STATIC_DIR, html=True), name="static")  # après les routeurs
    return app
