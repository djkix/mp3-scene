from fastapi import FastAPI

from . import config
from .config import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(title="Mp3 Scene")
    app.state.settings = settings or config.load()

    @app.get("/api/health")
    def health():
        return {"ok": True}

    return app
