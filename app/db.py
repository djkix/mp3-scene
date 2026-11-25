import os
import re
import sqlite3
from pathlib import Path

from app import artists, genres, nfo
from app.naming import album_like, group, kind, one_song, parse_release_name, unwrap

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
        for p in data_dir.glob("mp3scene.db*"):  # base créée par une version antérieure (0644) : lisible par l'appli seule
            os.chmod(p, 0o600)
        # base neuve, ou existante non marquée (0) : le schéma actuel est la version 1
        conn.executescript(SCHEMA.read_text(encoding="utf-8"))
        # colonne ajoutée en 1.17.0 ; sans changer VERSION, pour qu'une image plus ancienne ouvre encore la base
        if "has_cover" not in {r[1] for r in conn.execute("PRAGMA table_info(releases)")}:
            conn.execute("ALTER TABLE releases ADD COLUMN has_cover INTEGER")
        if "released_at" not in {r[1] for r in conn.execute("PRAGMA table_info(releases)")}:  # ajoutée en 1.29.0
            conn.execute("ALTER TABLE releases ADD COLUMN released_at REAL")
        if "daily_at" not in {r[1] for r in conn.execute("PRAGMA table_info(scan_state)")}:  # ajoutée en 1.34.0
            conn.execute("ALTER TABLE scan_state ADD COLUMN daily_at INTEGER")
        # 1.80.0 : un .txt tient lieu de NFO ; les releases sans NFO sont relistées une fois au prochain scan
        # (mtime remis à zéro) pour découvrir le leur. Pistes, favoris et écoutes sont conservés.
        if "txt_nfo" not in {r[1] for r in conn.execute("PRAGMA table_info(scan_state)")}:
            conn.execute("ALTER TABLE scan_state ADD COLUMN txt_nfo INTEGER")
            conn.execute("UPDATE releases SET mtime=0 WHERE has_nfo=0")
        # colonnes ajoutées en 1.36.0 (année corrigée) et en 1.37.0
        for table, col, kind in (("overrides", "year", "INTEGER"), ("overrides", "hidden", "INTEGER"), ("overrides", "cover", "INTEGER"),
                                 ("releases", "label", "TEXT"), ("releases", "catalog", "TEXT"),
                                 ("releases", "hidden", "INTEGER NOT NULL DEFAULT 0"), ("playlists", "rules", "TEXT"),
                                 ("releases", "cue_done", "INTEGER"),  # NULL : fichiers .cue pas encore lus
                                 ("tracks", "bpm", "REAL"), ("tracks", "key", "TEXT"),  # ajoutées en 1.61.0
                                 ("releases", "nfo_indexed", "INTEGER"),  # NULL : texte du NFO pas encore indexé (1.65.0)
                                 ("waveforms", "loudness", "REAL")):  # volume moyen, 1.79.0
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
    # artistes lus dans les tags par une version antérieure : sans le symbole qui les encadre (« ✖ … ✖ »)
    for table, col in (("tracks", "artist"), ("releases", "tag_artist")):
        for (a,) in conn.execute(f"SELECT DISTINCT {col} FROM {table} WHERE {col} IS NOT NULL").fetchall():
            if unwrap(a) != a:
                conn.execute(f"UPDATE {table} SET {col}=? WHERE {col}=?", (unwrap(a), a))
    # artiste et titre lus du nom par une version antérieure : relus, s'ils n'ont pas été corrigés depuis
    # ponytail: deux analyses par release à chaque passage (~1 s pour 45 000) ; à retirer quand les bases sont à jour
    for r in conn.execute("SELECT id, name, artist, title FROM releases").fetchall():
        old, new = parse_release_name(r["name"], legacy=True), parse_release_name(r["name"])
        for col in ("artist", "title"):
            # à la casse près : « ultra dance 03 » est devenu « Ultra Dance 03 » en rejoignant les autres artistes
            if old[col] != new[col] and (r[col] or "").casefold() == (old[col] or "").casefold():
                conn.execute(f"UPDATE releases SET {col}=? WHERE id=?", (new[col], r["id"]))
    merge_track_artists(conn)
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


def merge_track_artists(conn) -> None:
    """Artistes des pistes qui ne diffèrent que par la casse (« AXWELL » / « Axwell ») : la graphie la plus fréquente
    pour tous. Sans effet au second passage ; une relecture des tags rend la graphie du fichier jusqu'au passage suivant."""
    seen = {}
    for a, n in conn.execute("SELECT artist, COUNT(*) FROM tracks WHERE artist IS NOT NULL GROUP BY artist"):
        seen.setdefault(a.casefold(), []).append((n, a))
    for names in seen.values():
        # une graphie mixte l'emporte sur le tout-majuscules ou le tout-minuscules, puis la plus fréquente ; sans
        # graphie mixte, le tout-minuscules prend des capitales (« soul vision » -> « Soul Vision »)
        best = max(names, key=lambda x: (not (x[1].isupper() or x[1].islower()), x[0], x[1]))[1]
        best = artists.capitalize(best)
        conn.executemany("UPDATE tracks SET artist=? WHERE artist=?", [(best, a) for _, a in names if a != best])


def merge_case(conn, col: str) -> None:
    """Réunit les groupes (ou les labels) qui ne diffèrent que par la casse (« dh » / « DH ») sous la graphie la
    plus répandue. `col` : grp ou label, jamais un texte du client."""
    # ponytail: lower() de SQLite, donc ASCII seulement ; suffisant pour des noms de groupes de la scène
    for (k,) in conn.execute(f"SELECT lower({col}) FROM releases WHERE {col} IS NOT NULL GROUP BY 1"
                             f" HAVING COUNT(DISTINCT {col})>1").fetchall():
        best = conn.execute(f"SELECT {col} FROM releases WHERE lower({col})=? GROUP BY {col} ORDER BY COUNT(*) DESC, {col}"
                            " LIMIT 1", (k,)).fetchone()[0]
        conn.execute(f"UPDATE releases SET {col}=? WHERE lower({col})=? AND {col}!=?", (best, k, best))


def log(conn, user: str, action: str, detail: str = "") -> None:
    """Inscrit une ligne au journal d'activité (sans valider la transaction : l'appelant le fait)."""
    import time
    conn.execute("INSERT INTO activity(at, user, action, detail) VALUES (?,?,?,?)", (time.time(), user, action, detail[:300]))
    # ponytail: on garde les 20 000 dernières lignes ; archiver ailleurs si un historique plus long est voulu
    conn.execute("DELETE FROM activity WHERE rowid <= (SELECT MAX(rowid) FROM activity) - 20000")


def merge_labels(conn) -> None:
    """Nettoie les labels (restes de mise en forme du NFO) et réunit ceux qui ne diffèrent que par la casse, les
    espaces, la ponctuation ou un « Records » final, sous la graphie la plus répandue. Sans effet au second passage."""
    rows = conn.execute("SELECT label, COUNT(*) FROM releases WHERE label IS NOT NULL AND label!='' GROUP BY label").fetchall()
    aliases = dict(conn.execute("SELECT key, target FROM label_aliases").fetchall())  # rattachements manuels

    def clean(label):
        c = nfo.clean_label(label)
        return aliases.get(nfo.label_key(c), c) if c else ""

    groups = {}  # clé -> {graphie nettoyée: nombre de releases}
    for label, n in rows:
        if c := clean(label):
            spellings = groups.setdefault(nfo.label_key(c), {})
            spellings[c] = spellings.get(c, 0) + n
    best = {k: min(s, key=lambda x: (-s[x], x)) for k, s in groups.items()}
    conn.executemany("UPDATE releases SET label=? WHERE label=?", [
        (new, label) for label, _ in rows if (new := best[nfo.label_key(c)] if (c := clean(label)) else "") != label])


_KIND_FOLDER = {"live": r"live|radio", "comp": r"compil", "single": r"single"}


# compilations rangées par année : « 1999 - Hed Kandi - Nu Cool Vol. 2 [2CD] ». Clé : le nom de la série réduit à ses
# lettres (casse, ponctuation et la faute « Minisrry » ignorées) ; valeur : (série, label), comme les autres releases
# de la série déjà dans la bibliothèque (artiste VA, label « Ministry of Sound » ou « Hed Kandi Records »).
DATED_SERIES = {"ministryofsound": ("Ministry of Sound", "Ministry of Sound"), "minisrryofsound": ("Ministry of Sound", "Ministry of Sound"),
                "hedkandi": ("Hed Kandi", "Hed Kandi Records")}
_DATED = re.compile(r"(\d{4})[ _]-[ _](.+?)[ _]-[ _](.+)$")


def dated_series(conn) -> None:
    """Range les compilations « année - série - titre » comme le reste de leur série : artiste VA, année du nom,
    label de la série, titre « série + titre » sans le suffixe « [2CD] ». L'artiste des tags est écarté.

    Leur nom affiché prend aussi la forme des autres releases de la série : « 1995_-_Ministry_of_Sound_-_The_Annual_1_[2CD] »
    devient « VA-Ministry_of_Sound_The_Annual_1-2CD-1995 ». Seul le nom en base change : le dossier sur le disque
    garde le sien (la release est retrouvée par son chemin)."""
    # ponytail: deux séries connues, en dur ; une table de séries si d'autres collections datées arrivent
    for r in conn.execute("SELECT id, name, artist, tag_artist, title, year, label FROM releases"
                          " WHERE name GLOB '[12][0-9][0-9][0-9][ _]-[ _]*'").fetchall():
        m = _DATED.match(r["name"])
        known = m and DATED_SERIES.get(re.sub(r"[^a-z]", "", m[2].lower()))
        if not known:
            continue
        tail = re.search(r"\s*\[([^\]]*)\]?\s*$", m[3])  # « [2CD] », « [WEB] », ou un crochet jamais refermé
        rest = " ".join(re.sub(r"[-_]", " ", m[3][:tail.start()] if tail else m[3]).split())
        tag = re.sub(r"[^A-Za-z0-9]", "", tail[1]) if tail else ""
        name = "-".join(filter(None, [f"VA-{known[0]} {rest}".replace(" ", "_"), tag, m[1]]))
        conn.execute("UPDATE releases SET name=?, artist='VA', tag_artist=NULL, title=?, year=?, label=? WHERE id=?",
                     (name, f"{known[0]} {rest}", int(m[1]), known[1], r["id"]))


def categorize(conn) -> None:
    """Catégorie de chaque release : celle que les tags de son nom indiquent, sinon son dossier racine.

    Dans le dossier des singles, une release sans tag de single et d'au moins dix pistes est rangée dans « Albums »,
    seule catégorie sans dossier à elle.

    Une catégorie est toujours un dossier racine existant : « live » désigne celui dont le nom contient « live » ou
    « radio », etc. Sans dossier correspondant, la release garde le sien."""
    dated_series(conn)
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


# valeurs d'un tag « artiste » qui ne nomment personne : laissées par un encodeur ou un tagueur
JUNK_ARTISTS = ("[notag]", "notag", "no tag", "artist", "no artist", "unknown", "unknown artist", "untitled", "inconnu",
                "artiste inconnu")


def apply_overrides(conn) -> None:
    """Corrections manuelles : elles l'emportent sur l'artiste, la catégorie, le genre et l'année calculés.

    Appelée en fin de categorize(), donc après chaque regroupement d'artistes et chaque lecture de tags."""
    # un artiste de tag vide de sens (« [Notag] ») est écarté : l'artiste lu dans le nom de la release le remplace
    conn.execute(f"UPDATE releases SET tag_artist=NULL WHERE lower(tag_artist) IN ({','.join('?' * len(JUNK_ARTISTS))})", JUNK_ARTISTS)
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
    conn.create_function("remixed", 2, artists.remixed, deterministic=True)  # ligne « Remixes » de la page d'un artiste
    conn.create_function("group_key", 1, artists.group_key, deterministic=True)  # pistes d'un titre, groupées par artiste  # ligne « Remixes » de la page d'un artiste
    conn.create_function("collab", 2, artists.collab, deterministic=True)  # filtre « Avec » de la page d'un artiste
    return conn
