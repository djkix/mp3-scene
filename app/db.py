import sqlite3
from pathlib import Path

SCHEMA = Path(__file__).with_name("schema.sql")


def init(data_dir: Path) -> None:
    """Crée le répertoire, la base et le schéma. Appelé une fois au démarrage, avant tout `connect`."""
    data_dir.mkdir(parents=True, exist_ok=True)
    conn = connect(data_dir)
    try:
        conn.execute("PRAGMA journal_mode=WAL")  # persistant dans le fichier
        conn.executescript(SCHEMA.read_text(encoding="utf-8"))
        conn.execute("INSERT OR IGNORE INTO scan_state(id) VALUES (1)")
        conn.commit()
    finally:
        conn.close()


def connect(data_dir: Path) -> sqlite3.Connection:
    # une connexion par requête, utilisée séquentiellement mais depuis plusieurs threads du pool FastAPI
    conn = sqlite3.connect(data_dir / "mp3scene.db", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn
