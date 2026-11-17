import sqlite3
from pathlib import Path

SCHEMA = Path(__file__).with_name("schema.sql")
VERSION = 1  # PRAGMA user_version ; à incrémenter avec une migration si le schéma change


def init(data_dir: Path) -> None:
    """Crée le répertoire, la base et le schéma. Appelé une fois au démarrage, avant tout `connect`."""
    data_dir.mkdir(parents=True, exist_ok=True)
    conn = connect(data_dir)
    try:
        found = conn.execute("PRAGMA user_version").fetchone()[0]
        if found > VERSION:
            raise RuntimeError(f"La base {data_dir / 'mp3scene.db'} est en version {found}, plus récente que celle "
                               f"de cette application ({VERSION}) : mettez l'application à jour ou restaurez une "
                               "sauvegarde de data/.")
        conn.execute("PRAGMA journal_mode=WAL")  # persistant dans le fichier
        # base neuve, ou existante non marquée (0) : le schéma actuel est la version 1
        conn.executescript(SCHEMA.read_text(encoding="utf-8"))
        # colonne ajoutée en 1.17.0 ; sans changer VERSION, pour qu'une image plus ancienne ouvre encore la base
        if "has_cover" not in {r[1] for r in conn.execute("PRAGMA table_info(releases)")}:
            conn.execute("ALTER TABLE releases ADD COLUMN has_cover INTEGER")
        conn.execute("INSERT OR IGNORE INTO scan_state(id) VALUES (1)")
        conn.execute(f"PRAGMA user_version = {VERSION}")
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
