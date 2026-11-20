import re
import sqlite3
from pathlib import Path

from app import artists, genres, nfo
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
        if "daily_at" not in {r[1] for r in conn.execute("PRAGMA table_info(scan_state)")}:  # ajoutée en 1.34.0
            conn.execute("ALTER TABLE scan_state ADD COLUMN daily_at INTEGER")
        # colonnes ajoutées en 1.36.0 (année corrigée) et en 1.37.0
        for table, col, kind in (("overrides", "year", "INTEGER"), ("overrides", "hidden", "INTEGER"),
                                 ("releases", "label", "TEXT"), ("releases", "catalog", "TEXT"),
                                 ("releases", "hidden", "INTEGER NOT NULL DEFAULT 0"), ("playlists", "rules", "TEXT")):
            if col not in {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {kind}")
        classify(conn)  # données rangées par une version antérieure : mêmes règles que le scanner d'aujourd'hui
        conn.execute("INSERT OR IGNORE INTO scan_state(id) VALUES (1)")
        conn.execute(f"PRAGMA user_version = {VERSION}")
        conn.commit()
    finally:
        conn.close()


def classify(conn) -> None:
    """Réapplique toutes les règles de classement aux releases en base : genres, groupes, année, artistes,
    catégories, puis corrections manuelles. Sans effet au second passage."""
    genres.apply(conn)
    # « AOV_INT » rejoint AOV, une année ou « 320 » passe en P2P, comme à l'analyse du nom
    for (g,) in conn.execute("SELECT DISTINCT grp FROM releases WHERE grp IS NOT NULL").fetchall():
        new, year = group(g)
        if new != g:
            conn.execute("UPDATE releases SET grp=?, year=COALESCE(year, ?) WHERE grp=?", (new, year, g))
    merge_case(conn, "grp")
    merge_labels(conn)
    year_from_nfo(conn)
    artists.apply(conn)
    categorize(conn)


def merge_case(conn, col: str) -> None:
    """Réunit les groupes (ou les labels) qui ne diffèrent que par la casse (« dh » / « DH ») sous la graphie la
    plus répandue. `col` : grp ou label, jamais un texte du client."""
    # ponytail: lower() de SQLite, donc ASCII seulement ; suffisant pour des noms de groupes de la scène
    for (k,) in conn.execute(f"SELECT lower({col}) FROM releases WHERE {col} IS NOT NULL GROUP BY 1"
                             f" HAVING COUNT(DISTINCT {col})>1").fetchall():
        best = conn.execute(f"SELECT {col} FROM releases WHERE lower({col})=? GROUP BY {col} ORDER BY COUNT(*) DESC, {col}"
                            " LIMIT 1", (k,)).fetchone()[0]
        conn.execute(f"UPDATE releases SET {col}=? WHERE lower({col})=? AND {col}!=?", (best, k, best))


def merge_labels(conn) -> None:
    """Nettoie les labels (restes de mise en forme du NFO) et réunit ceux qui ne diffèrent que par la casse, les
    espaces, la ponctuation ou un « Records » final, sous la graphie la plus répandue. Sans effet au second passage."""
    rows = conn.execute("SELECT label, COUNT(*) FROM releases WHERE label IS NOT NULL AND label!='' GROUP BY label").fetchall()
    groups = {}  # clé -> {graphie nettoyée: nombre de releases}
    for label, n in rows:
        clean = nfo.clean_label(label)
        if clean:
            spellings = groups.setdefault(nfo.label_key(clean), {})
            spellings[clean] = spellings.get(clean, 0) + n
    best = {k: min(s, key=lambda x: (-s[x], x)) for k, s in groups.items()}
    conn.executemany("UPDATE releases SET label=? WHERE label=?", [
        (new, label) for label, _ in rows
        if (new := best[nfo.label_key(c)] if (c := nfo.clean_label(label)) else "") != label])


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
    apply_overrides(conn)


def apply_overrides(conn) -> None:
    """Corrections manuelles : elles l'emportent sur l'artiste, la catégorie, le genre et l'année calculés.

    Appelée en fin de categorize(), donc après chaque regroupement d'artistes et chaque lecture de tags."""
    conn.execute(
        "UPDATE releases SET tag_artist=COALESCE((SELECT artist FROM overrides WHERE path=releases.path), tag_artist),"
        " category=COALESCE((SELECT category FROM overrides WHERE path=releases.path), category),"
        " genre=COALESCE((SELECT genre FROM overrides WHERE path=releases.path), genre),"
        " year=COALESCE((SELECT year FROM overrides WHERE path=releases.path), year),"
        " hidden=COALESCE((SELECT hidden FROM overrides WHERE path=releases.path), 0)"
        " WHERE path IN (SELECT path FROM overrides)")
    conn.execute("UPDATE releases SET hidden=0 WHERE hidden=1 AND path NOT IN (SELECT path FROM overrides WHERE hidden=1)")


def year_from_nfo(conn) -> None:
    """Sans année dans le nom, celle de la date du NFO."""
    conn.execute("UPDATE releases SET year=CAST(strftime('%Y', released_at, 'unixepoch') AS INTEGER)"
                 " WHERE year IS NULL AND released_at>0")


def connect(data_dir: Path) -> sqlite3.Connection:
    # une connexion par requête, utilisée séquentiellement mais depuis plusieurs threads du pool FastAPI
    conn = sqlite3.connect(data_dir / "mp3scene.db", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.create_function("collab", 2, artists.collab, deterministic=True)  # filtre « Avec » de la page d'un artiste
    return conn
