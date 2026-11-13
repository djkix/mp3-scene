import time
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from . import config, db, routes_admin, routes_auth, routes_library, routes_media, security
from .config import Settings
from .deps import csrf
from .scanner import Runner

PUBLIC_API = ("/api/login", "/api/health")


def _bootstrap_admin(settings: Settings) -> None:
    if not (settings.admin_user and settings.admin_password):
        return
    conn = db.connect(settings.data_dir)
    try:
        if conn.execute("SELECT 1 FROM users LIMIT 1").fetchone() is None:
            conn.execute("INSERT INTO users(username, password_hash, role) VALUES (?,?,'admin')",
                         (settings.admin_user.strip(), security.hash_password(settings.admin_password)))
            conn.commit()
    finally:
        conn.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    _bootstrap_admin(app.state.settings)
    app.state.runner.resume()
    yield
    app.state.runner.stop()


def _session_valid(settings: Settings, token: str) -> bool:
    conn = db.connect(settings.data_dir)
    try:
        return security.session_user(conn, token, time.time()) is not None
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
        token = request.cookies.get(security.COOKIE)
        if not token or not await run_in_threadpool(_session_valid, app.state.settings, token):
            return JSONResponse({"detail": "Authentification requise."}, status_code=401)
        response = await call_next(request)
        if "set-cookie" not in response.headers:
            security.set_session_cookie(response, token)  # 30 jours glissants côté navigateur aussi
        return response

    @app.get("/api/health")
    def health():
        return {"ok": True}

    for module in (routes_auth, routes_admin, routes_library, routes_media):
        app.include_router(module.router)
    return app
