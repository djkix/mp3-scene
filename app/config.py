import os
from dataclasses import dataclass
from pathlib import Path


MIN_SECRET = 32


@dataclass
class Settings:
    music_root: Path
    data_dir: Path
    secret_key: str
    public_url: str = ""
    admin_user: str | None = None
    admin_password: str | None = None


def load() -> Settings:
    secret = os.environ.get("SECRET_KEY")
    if not secret:
        raise RuntimeError("La variable d'environnement SECRET_KEY est obligatoire.")
    if len(secret) < MIN_SECRET:  # la valeur n'apparaît jamais dans le message
        raise RuntimeError(f"La variable d'environnement SECRET_KEY doit contenir au moins {MIN_SECRET} caractères ; "
                           "générez-en une avec : python3 -c \"import secrets; print(secrets.token_urlsafe(48))\"")
    return Settings(
        music_root=Path(os.environ.get("MUSIC_ROOT", "/music")),
        data_dir=Path(os.environ.get("DATA_DIR", "/data")),
        secret_key=secret,
        public_url=os.environ.get("PUBLIC_URL", "").rstrip("/"),
        admin_user=os.environ.get("ADMIN_USER") or None,
        admin_password=os.environ.get("ADMIN_PASSWORD") or None,
    )
