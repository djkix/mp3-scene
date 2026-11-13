import sqlite3
from pathlib import Path

SCHEMA = Path(__file__).with_name("schema.sql")


def connect(data_dir: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(data_dir / "mp3scene.db")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    conn.execute("INSERT OR IGNORE INTO scan_state(id) VALUES (1)")
    conn.commit()
    return conn
