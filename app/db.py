import datetime
import os
import re
import sqlite3
from pathlib import Path

from app import artists, genres, nfo
from app.naming import album_like, group, kind, known_show, looks_live, one_song, parse_release_name, unwrap

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
        # 1.83.0 : l'année est aussi lue dans les tags ; les pistes des releases sans année sont relues une fois
        if "tag_year" not in {r[1] for r in conn.execute("PRAGMA table_info(scan_state)")}:
            conn.execute("ALTER TABLE scan_state ADD COLUMN tag_year INTEGER")
            conn.execute("UPDATE tracks SET tags_read=0 WHERE release_id IN (SELECT id FROM releases WHERE year IS NULL)")
            conn.execute("UPDATE releases SET tags_done=0 WHERE year IS NULL")
            conn.execute("UPDATE releases SET has_cover=NULL WHERE has_cover=0")  # image cherchée aussi dans les pistes suivantes
        # 1.84.5 : forme d'onde en volume moyen (RMS) au lieu des crêtes ; les formes d'onde gardées sont recalculées
        # à la prochaine écoute de chaque piste
        if "wave_rms" not in {r[1] for r in conn.execute("PRAGMA table_info(scan_state)")}:
            conn.execute("ALTER TABLE scan_state ADD COLUMN wave_rms INTEGER")
            conn.execute("DELETE FROM waveforms")
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
                                 ("waveforms", "loudness", "REAL"),  # volume moyen, 1.79.0
                                 ("tracks", "year", "INTEGER")):  # année des tags, 1.83.0
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

    Leur nom affiché devient « série - titre » : « 2010 - Ministry of Sound - Clubbers Guide 2010 [3CD] » s'affiche
    « Ministry_of_Sound_-_Clubbers_Guide_2010 » (l'année et le nombre de disques restent dans les informations).
    Seul le nom en base change : le dossier sur le disque garde le sien (la release est retrouvée par son chemin).
    Le nom est relu sur le dossier, pour que celui donné par une version antérieure (« VA-…-2CD-1995 ») suive."""
    # ponytail: deux séries connues, en dur ; une table de séries si d'autres collections datées arrivent
    dated = "'[12][0-9][0-9][0-9][ _]-[ _]*'"
    for r in conn.execute(f"SELECT id, name, path FROM releases WHERE name GLOB {dated} OR path GLOB '*'||{dated}").fetchall():
        folder = r["path"].rsplit("/", 1)[-1]
        m = _DATED.match(folder) if re.match(r"[12]\d{3}[ _]-[ _]", folder) else _DATED.match(r["name"])
        if got := _dated(m):
            conn.execute("UPDATE releases SET name=?, artist='VA', tag_artist=NULL, title=?, year=?, label=? WHERE id=?", (*got, r["id"]))


def _dated(m) -> tuple | None:
    """(nom affiché, titre, année, label) d'une compilation datée d'une série connue (`m` : _DATED), sinon None."""
    known = m and DATED_SERIES.get(re.sub(r"[^a-z]", "", m[2].lower()))
    if not known:
        return None
    tail = re.search(r"\s*\[([^\]]*)\]?\s*$", m[3])  # « [2CD] », « [WEB] », ou un crochet jamais refermé
    rest = " ".join(re.sub(r"[-_]", " ", m[3][:tail.start()] if tail else m[3]).split())
    return f"{known[0]} - {rest}".replace(" ", "_"), f"{known[0]} {rest}", int(m[1]), known[1]


# épisode daté d'une émission : « 2002-06-09_-_Essential_Mix_-_Michel_de_Hey », « 2002-04-28__Essential_mix_-_Roger_sanchez »,
# « 2002-04-21_Essential_Mix » (sans artiste)
_EPISODE_NAME = re.compile(r"(\d{4})-(\d{2})-(\d{2})[ _]*(?:-[ _]*)?(.+?)(?:[ _]+-[ _]+(.+))?$")


def dated_episodes(conn) -> None:
    """Épisodes d'une émission connue rangés « date - émission - artiste » : nom affiché « Artiste-Émission-date »
    comme les autres (« Michel_de_Hey-Essential_Mix-2002-06-09 », sans artiste « Essential_Mix-2002-04-21 »),
    artiste et titre renseignés, année et date de diffusion tirées du nom. Un lieu après « @ » rejoint le titre
    (« Essential Mix @ Coachella Festival »). Le nom est relu sur le dossier ; le dossier sur le disque ne change pas."""
    for r in conn.execute("SELECT id, path, released_at FROM releases WHERE path GLOB '*[12][0-9][0-9][0-9]-[01][0-9]-[0-3][0-9]*'").fetchall():
        m = _EPISODE_NAME.fullmatch(r["path"].rsplit("/", 1)[-1])
        show = m and known_show(m[4])
        if not show:
            continue
        who, _, where = (m[5] or "").partition("@")
        who = " ".join(who.replace("_", " ").split())
        title = show + (" @ " + " ".join(where.replace("_", " ").split()) if where.strip(" _") else "")
        name = "-".join(filter(None, [who, title, f"{m[1]}-{m[2]}-{m[3]}"])).replace(" ", "_")
        try:
            aired = datetime.datetime(int(m[1]), int(m[2]), int(m[3]), 12, tzinfo=datetime.timezone.utc).timestamp()
        except ValueError:  # 2002-13-45
            aired = None
        conn.execute("UPDATE releases SET name=?, artist=?, tag_artist=NULL, title=?, year=?,"
                     " released_at=CASE WHEN COALESCE(released_at, 0)=0 THEN ? ELSE released_at END WHERE id=?",
                     (name, who or None, title, int(m[1]), aired, r["id"]))


# dossiers supplémentaires (MUSIC_EXTRA « Nom=/chemin>albums ») rangés comme les albums ou comme les singles plutôt
# qu'en catégorie à part : nom du dossier racine -> « albums » | « singles ». Renseigné au démarrage (main).
# ponytail: réglage global du processus, comme la configuration qu'il reflète ; passer `settings` si cela gêne
EXTRA_KINDS: dict = {}


# Essential Mix : tous les formats de noms ramenés à « Artiste-Essential_Mix-date » (voir essential_mixes)
_EM = re.compile(r"(?:bbc\s+)?(?:radio\s*1'?s?\s+)?essential\s+mix(?:\s*#\s*\d+)?", re.I)
_EM_JUNK = re.compile(r"(?i)\b(?:qrip|bbc\s*radio\s*1|radio\s*1'?s?|mixesdb\.com)\b")
_EM_DATE = re.compile(r"(?<!\d)(?:((?:19|20)\d\d)[-_. ]{1,3}(\d\d)[-_. ]{1,3}(\d\d)|(\d\d)[-_. ](\d\d)[-_. ]((?:19|20)\d\d))(?!\d)")
_EM_WEEK = re.compile(r"(?<!\d)((?:19|20)\d\d)\s+week\s+(\d{1,2})\b", re.I)
_NOT_ARTIST = {"", "essential mix", "bbc radio 1", "radio 1", "various", "va", "various artists"}


_EM_SRC = {"SAT", "CABLE", "DAB", "DVBS", "DVBC", "DVBT", "DVB", "STREAM", "WEB", "FM", "LINE", "PROPER", "REPACK", "READ_NFO", "INT"}
_EM_LIVE = re.compile(r"(?i)\s+((?:live\s+(?:at|@|from|in)|@)\s+.+)$")


def _em_parse(text: str):
    """(date « AAAA-MM-JJ » ou « AAAA-S50 » ou None, [artiste, précisions…]) d'un nom d'Essential Mix, sans l'émission,
    la date ni les mentions inutiles (qrip, BBC Radio 1, tags et groupe d'un nom scene)."""
    t = text.replace("_", " ")
    date = None
    if m := _EM_DATE.search(t):
        if m[1]:
            y, mo, d = int(m[1]), int(m[2]), int(m[3])
        else:  # date scene « 10-09-1994 » : mois d'abord, sauf si le premier nombre dépasse 12
            a, b, y = int(m[4]), int(m[5]), int(m[6])
            mo, d = (b, a) if a > 12 else (a, b)
        if 1 <= mo <= 12 and 1 <= d <= 31:
            date = f"{y:04d}-{mo:02d}-{d:02d}"
    elif m := _EM_WEEK.search(t):
        date = f"{m[1]}-S{int(m[2]):02d}"
    # nom scene (« Artiste_-_Essential_Mix-SAT-10-09-1994-GROUPE ») : ce qui précède la source
    segs = text.split("-")
    cut = next((i for i, x in enumerate(segs) if i and x.strip("_ ").upper() in _EM_SRC), None)
    if cut is not None:  # segments séparés par des tirets : artiste, titre…
        t = " - ".join(segs[:cut]).replace("_", " ")
    if m and cut is None:
        t = t[:m.start()] + " " + t[m.end():]
    t = re.sub(r"(?i)\(([^()]*?)\b(?:bbc\s+)?(?:radio\s*1'?s?\s+)?essential\s+mix\b([^()]*)\)", lambda x: f"({(x[1] + x[2]).strip()})", t)
    t = re.sub(r"\(\s*\)", " ", t)
    t = _EM.sub(" - ", t, count=1)  # la première mention : « Celebrate 20 Years of Essential Mix » garde la sienne
    t = _EM_JUNK.sub(" ", t)
    t = re.sub(r"\bEM\b|\bREAD NFO\b", " ", t)
    parts = [" ".join(p.split()).strip(" -:#,") for p in re.split(r"\s+-\s*|\s*-\s+|\s+-$", t)]
    parts = [p for p in parts if p and not re.fullmatch(r"[\d\s#.]+", p)]
    if parts and (lm := _EM_LIVE.search(parts[0])):  # « John Digweed Live @ Heavens » : le lieu rejoint le titre
        parts = [parts[0][:lm.start()].strip(" ,"), lm[1], *parts[1:]]
    return date, parts


def em_name(folder: str, tag_artist: str | None, tag_title: str | None, filename: str | None):
    """(nom affiché, artiste, titre, date) d'un Essential Mix, d'après le nom de son dossier ou de son fichier et les
    tags de sa piste ; None sans date. Voir essential_mixes."""
    date, parts = _em_parse(folder)
    if not date:
        return None
    tag = (tag_artist or "").strip()
    # l'artiste des tags, s'il figure dans le nom ailleurs qu'en tête (« Master Series 05 - Dave Clarke »), passe devant
    if tag.lower() not in _NOT_ARTIST and len(parts) > 1 and any(p.lower() == tag.lower() for p in parts[1:]):
        parts = [next(p for p in parts if p.lower() == tag.lower()), *[p for p in parts if p.lower() != tag.lower()]]
    artist, extra = (parts[0], parts[1:]) if parts else ("", [])
    if re.match(r"(?i)(?:at|of|from|in|part)\b", artist):  # « Essential Mix at 25 », « Part 2 » : une précision
        artist, extra = "", parts
    if artist.lower() in _NOT_ARTIST or re.fullmatch(r"(?i)essential mix collection.*", artist):
        artist = ""
    if not artist:  # pas d'artiste dans le nom : les tags de la piste, sinon le nom de son fichier
        if tag.lower() not in _NOT_ARTIST:
            artist = tag
        elif (tag_title or "").strip() and not _EM.search(tag_title) and not _EM_DATE.search(tag_title):
            artist = tag_title.strip()  # « BBC Radio 1 | Alan Fitzpatrick »
        elif filename and (_EM.search(Path(filename).stem.replace("_", " ")) or _EM_DATE.search(filename)):
            _, fparts = _em_parse(Path(filename).stem)  # un nom de fichier qui décrit l'épisode, pas « 01-a.mp3 »
            artist = next((p for p in fparts if p.lower() not in _NOT_ARTIST and not re.match(r"(?i)part\b", p)), "")
    title = " ".join(extra) if extra and extra[0].lower().startswith("essential mix") else " ".join(["Essential Mix", *extra])
    return "-".join(filter(None, [artist, title, date])).replace(" ", "_"), artist or None, title, date


# sous-dossier d'une release qui n'a pas un nom de release : « SALSOUL_CD1 », « Uncovered_1 », « Mix_Cut »,
# « The House That Garage Built M.O.S [Disc 2] », « 25 Avant Nova - 1980 » (un CD par année)
_SCENE_END = re.compile(r"-(?:19|20)\d\d(?:-[^-]+)?$")
_DATED_DIR = re.compile(r"^[12]\d{3}[ _]-[ _]")
_MULTI_CD = re.compile(r"(?i)(?:^|[-_ (\[])\d+ ?x? ?CD(?:$|[-_ )\]])")
_DISC_NO = re.compile(r"(?i)(?<![a-z])(?:cd|disc|disk)[ _\-.]*(\d{1,2})(?!\d)|[ _](\d{1,2})$")
_WORDS = lambda s: set(re.findall(r"[a-z0-9]{2,}", s.lower()))  # sans les lettres seules (« M.O.S »)


def disc_children(conn) -> None:
    """Sous-dossiers d'une release (son dossier a un nom de release ou de compilation datée) dont le nom n'en est pas
    un : ils prennent le nom de la release parente, suivi de leur disque (« VA-The_Salsoul_Acapellas-2CD-2005_(CD1) »)
    et de ce que leur nom ajoute (« …_(CD1_-_Als_Mixe) », « …_(Mix_Cut) »). Sans numéro, des dossiers tous datés sont
    numérotés dans l'ordre de leurs années (« …-25CD-2010_(CD1_-_1956) »). Artiste, titre, année et groupe sont ceux
    de la release parente. Seul le nom en base change, relu sur le dossier à chaque fois."""
    groups = {}
    for r in conn.execute("SELECT id, path FROM releases WHERE path LIKE '%/%/%'"):
        *up, parent, child = r["path"].split("/")
        if not _SCENE_END.search(child) and (_SCENE_END.search(parent) or _DATED_DIR.match(parent) or _MULTI_CD.search(parent)):
            groups.setdefault("/".join([*up, parent]), []).append((r["id"], child))
    for ppath, kids in groups.items():
        base = ppath.rsplit("/", 1)[-1]
        p = conn.execute("SELECT name, artist, title, year, grp, label FROM releases WHERE path=?", (ppath,)).fetchone()
        series = _dated(_DATED.match(base)) if _DATED_DIR.match(base) else None  # dossier daté sans pistes à lui
        info = dict(p) if p else dict(zip(("name", "title", "year", "label"), series), artist="VA", grp=None) if series \
            else {**parse_release_name(base.replace(" ", "_")), "name": base, "label": None}
        pwords = _WORDS(info["name"] + " " + (info["title"] or ""))
        kids.sort(key=lambda k: k[1].lower())
        dated = len(kids) > 1 and all(re.search(r"\b(?:19|20)\d\d\b", c) and not _DISC_NO.search(c) for _, c in kids)
        for rank, (rid, child) in enumerate(kids, 1):
            m = _DISC_NO.search(child)
            n = int(m[1] or m[2]) if m else rank if dated else None
            rest = re.search(r"\b(?:19|20)\d\d\b", child)[0] if dated else (child[:m.start()] + " " + child[m.end():] if m else child)
            rest = " ".join(re.sub(r"[\[\]()_.]+", " ", rest).split()).strip(" -")
            if not dated:  # début qui répète la release (« Gatecrasher Forever - The Folio ») : retiré
                while (w := re.match(r"([A-Za-z0-9']+)[\s,-]*", rest)) and (len(w[1]) < 2 or w[1].lower() in pwords) and w.end() < len(rest):
                    rest = rest[w.end():]
            if rest and not dated and len(_WORDS(rest) - pwords) <= len(_WORDS(rest)) // 3:
                rest = ""  # le nom répète la release (« Ministry of Sound - Chillout Sessions X - CD1 ») : rien à ajouter
            part = " - ".join(x for x in (f"CD{n}" if n else "", rest) if x)
            if not part:
                continue
            conn.execute("UPDATE releases SET name=?, artist=?, tag_artist=NULL, title=?, year=?, grp=?, label=COALESCE(label, ?) WHERE id=?",
                         (f"{info['name']} ({part})".replace(" ", "_"), info["artist"], f"{info['title'] or base} ({part})",
                          info["year"], info["grp"], info["label"], rid))


def essential_mixes(conn) -> None:
    """Essential Mix (BBC Radio 1) : nom affiché « Artiste-Essential_Mix-date » quel que soit le format du dossier
    (« 2016-03-19_-_Riva_Starr_&_Axwell_-_Essential_Mix », « Essential Mix_2012_01_07_qrip », « 2015 12 05 Essential Mix
    #1141 - Matthias Tanzmann », « Carl_Cox_-_Essential_Mix-SAT-10-09-1994-TALiON »…). L'artiste vient du nom, sinon
    des tags de la première piste, sinon du nom de son fichier ; une précision (« Live at Drumsheds », « Master
    Series 05 », « Part 1 ») rejoint le titre. Artiste, titre, année et date de diffusion sont renseignés. Le nom est
    relu sur le dossier à chaque fois ; le dossier sur le disque ne change pas. Un dossier « Collection » qui réunit
    plusieurs mixes garde son nom : ses fichiers sont des sets à part (pages de Live & Radio)."""
    rows = conn.execute(
        "SELECT r.id, r.path, t.artist, t.title, t.relpath FROM releases r LEFT JOIN tracks t ON t.id="
        "(SELECT id FROM tracks WHERE release_id=r.id ORDER BY disc, relpath LIMIT 1)"
        " WHERE lower(replace(r.path, '_', ' ')) LIKE '%essential mix%'").fetchall()
    for r in rows:
        folder = r["path"].rsplit("/", 1)[-1]
        if re.search(r"(?i)collection", folder):
            continue
        got = em_name(folder, r["artist"], r["title"], r["relpath"])
        if not got:
            continue
        name, artist, title, date = got
        year = int(date[:4])
        aired = None
        if len(date) == 10:
            try:
                aired = datetime.datetime(year, int(date[5:7]), int(date[8:10]), 12, tzinfo=datetime.timezone.utc).timestamp()
            except ValueError:
                pass
        conn.execute("UPDATE releases SET name=?, artist=?, tag_artist=NULL, title=?, year=?,"
                     " released_at=CASE WHEN COALESCE(released_at, 0)=0 THEN ? ELSE released_at END WHERE id=?",
                     (name, artist, title, year, aired, r["id"]))


def categorize(conn) -> None:
    """Catégorie de chaque release : celle que les tags de son nom indiquent, sinon son dossier racine.

    Dans le dossier des singles, une release sans tag de single et d'au moins dix pistes est rangée dans « Albums »,
    seule catégorie sans dossier à elle ; un live sans tag de diffusion (festival cité, « Live at… ») dans Live & Radio.

    Une catégorie est toujours un dossier racine existant : « live » désigne celui dont le nom contient « live » ou
    « radio », etc. Sans dossier correspondant, la release garde le sien."""
    dated_series(conn)
    dated_episodes(conn)
    disc_children(conn)
    essential_mixes(conn)
    rows = conn.execute("SELECT id, name, path, category, track_count FROM releases").fetchall()
    tops = sorted({r["path"].split("/", 1)[0] for r in rows})
    target = {k: next((t for t in tops if re.search(p, t, re.I)), None) for k, p in _KIND_FOLDER.items()}
    # ponytail: toutes les releases sont réanalysées à chaque démarrage et à chaque scan (moins d'une seconde pour
    # 50 000) ; ne traiter que les nouvelles si cela devient sensible
    # dossiers rangés comme les singles : le leur, et les dossiers supplémentaires qui le rejoignent
    singles = {target["single"]} | {n for n, k in EXTRA_KINDS.items() if k == "singles"}
    singles.discard(None)
    titles = {}  # pistes des candidats albums : dix versions d'un même morceau restent un single
    for top in singles:
        for rid, title in conn.execute(
                "SELECT t.release_id, COALESCE(t.title, t.relpath) FROM tracks t JOIN releases r ON r.id=t.release_id"
                " WHERE r.track_count>=10 AND r.path LIKE ? ESCAPE '!'", (re.sub(r"([!%_])", r"!\1", top) + "/%",)):
            titles.setdefault(rid, []).append(title)

    def category(r):
        top, k = r["path"].split("/", 1)[0], kind(r["name"])
        extra = EXTRA_KINDS.get(top)
        # dans le dossier des singles, un live sans tag de diffusion (« Live at Tomorrowland », un festival cité)
        if k is None and (top in singles or extra) and looks_live(r["name"]):
            k = "live"
        if k is None and extra == "albums":
            return "Albums"
        if k is None and top in singles and album_like(r["name"], r["track_count"]) \
                and not one_song(titles.get(r["id"], [])):
            return "Albums"
        if k is None and extra == "singles":
            k = "single"
        # release d'un artiste glissée dans le dossier d'une compilation VA (« Axer-123__321-Promo_Vinyl-2006-TGX » dans
        # « VA-Sunshine_Live_House_Edition_Vol._1-3CD-2006-JiM ») : rangée comme dans le dossier des singles
        if k is None and top == target["comp"] and re.match(r"(VA|Various)\b", r["path"].rsplit("/", 2)[-2], re.I) \
                and (parse_release_name(r["name"])["artist"] or "").lower() not in ("", "va", "various", "various artists"):
            if album_like(r["name"], r["track_count"]):
                return "Albums"
            k = "single"
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
