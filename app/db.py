import re
import sqlite3
from pathlib import Path

from app import genres
from app.naming import album_like, group, kind, one_song

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
        if "released_at" not in {r[1] for r in conn.execute("PRAGMA table_info(releases)")}:  # ajoutée en 1.29.0
            conn.execute("ALTER TABLE releases ADD COLUMN released_at REAL")
        genres.apply(conn)  # genres lus avant la 1.21.0 : même regroupement que le scanner
        # groupes analysés avant la 1.22.0 : « AOV_INT » rejoint AOV, une année ou « 320 » passe en P2P, comme à
        # l'analyse du nom
        for (g,) in conn.execute("SELECT DISTINCT grp FROM releases WHERE grp IS NOT NULL").fetchall():
            new, year = group(g)
            if new != g:
                conn.execute("UPDATE releases SET grp=?, year=COALESCE(year, ?) WHERE grp=?", (new, year, g))
        merge_group_case(conn)
        categorize(conn)
        conn.execute("INSERT OR IGNORE INTO scan_state(id) VALUES (1)")
        conn.execute(f"PRAGMA user_version = {VERSION}")
        conn.commit()
    finally:
        conn.close()


def merge_group_case(conn) -> None:
    """Réunit les groupes qui ne diffèrent que par la casse (« dh » / « DH ») sous la graphie la plus répandue."""
    # ponytail: lower() de SQLite, donc ASCII seulement ; suffisant pour des noms de groupes de la scène
    for (k,) in conn.execute("SELECT lower(grp) FROM releases WHERE grp IS NOT NULL GROUP BY 1"
                             " HAVING COUNT(DISTINCT grp)>1").fetchall():
        best = conn.execute("SELECT grp FROM releases WHERE lower(grp)=? GROUP BY grp ORDER BY COUNT(*) DESC, grp"
                            " LIMIT 1", (k,)).fetchone()[0]
        conn.execute("UPDATE releases SET grp=? WHERE lower(grp)=? AND grp!=?", (best, k, best))


_KIND_FOLDER = {"live": r"live|radio", "comp": r"compil", "single": r"single"}


def categorize(conn) -> None:
    """Catégorie de chaque release : celle que les tags de son nom indiquent, sinon son dossier racine.

    Dans le dossier des singles, une release sans tag de single et d'au moins dix pistes est rangée dans « Albums »,
    seule catégorie sans dossier à elle.

    Une catégorie est toujours un dossier racine existant : « live » désigne celui dont le nom contient « live » ou
    « radio », etc. Sans dossier correspondant, la release garde le sien."""
    rows = conn.execute("SELECT id, name, path, category, track_count FROM releases").fetchall()
    tops = sorted({r["path"].split("/", 1)[0] for r in rows})
    target = {k: next((t for t in tops if re.search(p, t, re.I)), None) for k, p in _KIND_FOLDER.items()}
    # ponytail: toutes les releases sont réanalysées à chaque démarrage et à chaque scan (moins d'une seconde pour
    # 50 000) ; ne traiter que les nouvelles si cela devient sensible
    titles = {}  # pistes des candidats albums : dix versions d'un même morceau restent un single
    for rid, title in conn.execute(
            "SELECT t.release_id, COALESCE(t.title, t.relpath) FROM tracks t JOIN releases r ON r.id=t.release_id"
            " WHERE r.track_count>=10 AND r.path LIKE ? ESCAPE '!'",
            (re.sub(r"([!%_])", r"!\1", target["single"] or "\0") + "/%",)):
        titles.setdefault(rid, []).append(title)

    def category(r):
        top, k = r["path"].split("/", 1)[0], kind(r["name"])
        if k is None and top == target["single"] and album_like(r["name"], r["track_count"]) \
                and not one_song(titles.get(r["id"], [])):
            return "Albums"
        return target.get(k) or top

    conn.executemany("UPDATE releases SET category=? WHERE id=?",
                     [(want, r["id"]) for r in rows if (want := category(r)) != r["category"]])


def connect(data_dir: Path) -> sqlite3.Connection:
    # une connexion par requête, utilisée séquentiellement mais depuis plusieurs threads du pool FastAPI
    conn = sqlite3.connect(data_dir / "mp3scene.db", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn
