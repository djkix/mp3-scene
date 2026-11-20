import re
import time
from typing import Annotated, Literal

from pydantic import Field
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from .naming import complete_title
from .deps import MAX_INT, Id, current_user, get_conn
from .security import safe_path

router = APIRouter(dependencies=[Depends(current_user)])

MAX_LIMIT = 100
NFO_MAX = 1024 * 1024
_WORDS = re.compile(r"[\W_]+")

# débit moyen des pistes lues (NULL tant qu'aucun tag n'est lu)
# ponytail: sous-requête par ligne ; le tri par débit parcourt toutes les pistes — colonne releases.bitrate si trop lent
BITRATE = "(SELECT CAST(AVG(bitrate) AS INTEGER) FROM tracks WHERE release_id=r.id)"
# date affichée : celle du NFO, sinon celle de l'ajout
DATE = "COALESCE(NULLIF(r.released_at, 0), r.added_at)"
# artiste : tag commun s'il existe, sinon celui extrait du nom
RELEASE_COLS = """r.id, r.name, r.path, r.category, r.added_at, """ + DATE + """ AS date, r.size, r.track_count, r.has_nfo,
  COALESCE(r.tag_artist, r.artist) AS artist, r.title, r.source, r.year, r.grp, r.genre, r.duration,
  NULLIF(r.label, '') AS label, r.catalog, r.hidden,
  """ + BITRATE + """ AS bitrate, (f.item_id IS NOT NULL) AS favorite"""
RELEASE_FROM = "releases r LEFT JOIN favorites f ON f.user_id=? AND f.kind='release' AND f.item_id=r.id"
TRACK_COLS = """t.id, t.release_id, r.name AS release_name, r.source, r.grp, t.relpath, t.disc, t.size, t.title, t.artist,
  t.genre, t.duration, t.bitrate, (f.item_id IS NOT NULL) AS favorite"""
TRACK_FROM = ("tracks t JOIN releases r ON r.id=t.release_id "
              "LEFT JOIN favorites f ON f.user_id=? AND f.kind='track' AND f.item_id=t.id")


# tri des listes : colonnes autorisées (jamais de texte du client dans le SQL)
SORTS = {"name": "r.name COLLATE NOCASE", "genre": "r.genre COLLATE NOCASE", "date": DATE, "added": "r.added_at",
         "tracks": "r.track_count", "size": "r.size", "category": "r.category COLLATE NOCASE",
         "bitrate": BITRATE}
Sort = Literal["name", "genre", "date", "added", "tracks", "size", "category", "bitrate"]
Dir = Literal["asc", "desc"]


def _order(sort: str | None, direction: str, default: str) -> str:
    if sort is None:
        return default
    d = direction.upper()
    return f"{SORTS[sort]} {d}, r.id {d}"  # r.id départage : pagination stable


def _fts_query(q: str) -> str:
    words = [w for w in _WORDS.split(q) if w]
    if not words:
        return ""
    return " ".join(f'"{w}"' for w in words) + "*"


def _release(row) -> dict:
    d = dict(row)
    d["has_nfo"] = bool(d["has_nfo"])
    d["hidden"] = bool(d["hidden"])
    d["favorite"] = bool(d["favorite"])
    return d


def _track(row) -> dict:
    d = dict(row)
    d["filename"] = d.pop("relpath").rsplit("/", 1)[-1]
    d["title"] = complete_title(d.get("title"), d["filename"])  # tag ID3v1 coupé à 30 caractères
    d["artist"] = complete_title(d.get("artist"), d["filename"], artist=True)
    d["favorite"] = bool(d["favorite"])
    return d


def _page(conn, cols, source, where, params, order, uid, offset, limit, build):
    limit = min(limit, MAX_LIMIT)
    rows = conn.execute(f"SELECT {cols} FROM {source} {where} ORDER BY {order} LIMIT ? OFFSET ?",
                        [uid, *params, limit + 1, offset]).fetchall()
    return {"items": [build(r) for r in rows[:limit]], "has_more": len(rows) > limit}


# filtres à plusieurs valeurs : paramètre répété dans l'adresse (genre=House&genre=Techno)
Many = Annotated[list[Annotated[str, Field(max_length=200)]] | None, Query(max_length=100)]
Years = Annotated[list[Annotated[int, Field(ge=0, le=MAX_INT)]] | None, Query(max_length=100)]


def _release_conds(category=None, genre=None, year=None, grp=None, artist=None, source=None, decade=None, appears=None,
                   collab=None, label=None):
    """Conditions SQL (et leurs paramètres) des filtres de release communs aux listes, au mix et aux playlists
    intelligentes. Les doublons masqués par un administrateur n'en font jamais partie."""
    conds, params = ["r.hidden=0"], []
    several = lambda v: [] if v is None else v if isinstance(v, list) else [v]  # un filtre accepte plusieurs valeurs
    for col, val in (("category", category), ("genre", genre), ("grp", grp), ("source", source), ("label", label)):
        if vals := several(val):
            conds.append(f"r.{col} IN ({','.join('?' * len(vals))})")
            params += vals
    # années et décennies cochées ensemble : l'une ou l'autre
    years, when = several(year), []
    if years:
        when.append(f"r.year IN ({','.join('?' * len(years))})")
        params += years
    for d in several(decade):
        when.append("r.year BETWEEN ? AND ?")
        params += [d, d + 9]
    if when:
        conds.append("(" + " OR ".join(when) + ")")
    if appears is not None:  # releases d'un autre artiste (compilations surtout) où celui-ci signe une piste
        # ponytail: égalité stricte sur le tag de la piste ; « X feat. Y » n'est pas une apparition de X
        conds.append("COALESCE(r.tag_artist, r.artist, '')!=? AND r.id IN (SELECT release_id FROM tracks WHERE artist=?)")
        params += [appears, appears]
    if collab is not None:  # releases dont le nom associe cet artiste à un autre (feat, vs, &)
        # ponytail: fonction Python appelée pour chaque release (~0,1 s pour 45 000)
        conds.append("collab(r.name, ?)")
        params.append(collab)
    if artist is not None:
        conds.append("COALESCE(r.tag_artist, r.artist)=?")
        params.append(artist)
    return conds, params


@router.get("/api/mix")
def mix(category: Many = None, genre: Many = None, year: Years = None,
        grp: str | None = None, artist: str | None = None, source: Many = None,
        decade: Years = None, appears: str | None = None,
        collab: str | None = Query(None, max_length=200), label: str | None = Query(None, max_length=200),
        limit: int = Query(50, ge=1, le=MAX_LIMIT), user=Depends(current_user), conn=Depends(get_conn)):
    """Pistes tirées au hasard parmi les releases qui passent les filtres."""
    conds, params = _release_conds(category, genre, year, grp, artist, source, decade, appears, collab, label)
    where = "WHERE " + " AND ".join(conds) if conds else ""
    # ponytail: ORDER BY RANDOM() trie tous les identifiants candidats (rapide jusqu'au million de pistes)
    rows = conn.execute(
        f"SELECT {TRACK_COLS} FROM {TRACK_FROM} WHERE t.id IN (SELECT t.id FROM tracks t JOIN releases r"
        f" ON r.id=t.release_id {where} ORDER BY RANDOM() LIMIT ?) ORDER BY RANDOM()", [user["id"], *params, limit])
    return {"items": [_track(r) for r in rows]}


@router.get("/api/new-count")
def new_count(since: float = Query(ge=0, le=1e12), conn=Depends(get_conn)):
    """Nombre de releases ajoutées après `since` (heure Unix de la visite précédente)."""
    return {"count": conn.execute("SELECT COUNT(*) FROM releases WHERE added_at>?", (since,)).fetchone()[0]}


@router.get("/api/releases")
def list_releases(q: str = "", category: Many = None, genre: Many = None, grp: str | None = None,
                  artist: str | None = None, source: Many = None, appears: str | None = None,
                  decade: Years = None, collab: str | None = Query(None, max_length=200),
                  year: Years = None, favorites: int = Query(0, ge=0, le=1),
                  label: str | None = Query(None, max_length=200), sort: Sort | None = None, dir: Dir = "asc",
                  offset: int = Query(0, ge=0, le=MAX_INT), limit: int = Query(50, ge=1, le=MAX_INT),
                  user=Depends(current_user), conn=Depends(get_conn)):
    conds, params = _release_conds(category, genre, year, grp, artist, source, decade, appears, collab, label)
    if favorites:  # un favori reste visible même masqué
        conds.remove("r.hidden=0")
    if match := _fts_query(q):
        conds.append("r.id IN (SELECT rowid FROM releases_fts WHERE releases_fts MATCH ?)")
        params.append(match)
    if favorites:
        conds.append("f.item_id IS NOT NULL")
    where = "WHERE " + " AND ".join(conds) if conds else ""
    return _page(conn, RELEASE_COLS, RELEASE_FROM, where, params, _order(sort, dir, "r.added_at DESC, r.id DESC"),
                 user["id"], offset, limit, _release)


# ordre d'affichage des catégories, partout : singles, albums, compilations, live et radio, puis les autres dossiers
_CATEGORY_ORDER = (r"single", r"album", r"compil", r"live|radio")


def _category_rank(name: str):
    return next((i for i, pat in enumerate(_CATEGORY_ORDER) if re.search(pat, name, re.I)), len(_CATEGORY_ORDER)), name.lower()


@router.get("/api/filters")
def filters(conn=Depends(get_conn)):
    col = lambda sql: [r[0] for r in conn.execute(sql)]
    return {"categories": sorted(col("SELECT DISTINCT category FROM releases WHERE category IS NOT NULL ORDER BY category"),
                                 key=_category_rank),
            "genres": col("SELECT DISTINCT genre FROM releases WHERE genre IS NOT NULL ORDER BY genre"),
            "sources": col("SELECT DISTINCT source FROM releases WHERE source IS NOT NULL ORDER BY source"),
            "years": col("SELECT DISTINCT year FROM releases WHERE year IS NOT NULL ORDER BY year DESC")}


# regroupements de la page Explorer : colonnes autorisées (jamais de texte du client dans le SQL)
GROUP_BY = {"grp": "grp", "artist": "COALESCE(tag_artist, artist)", "genre": "genre", "label": "NULLIF(label, '')", "category": "category", "year": "year"}


@router.get("/api/groups")
def groups(by: Literal["grp", "artist", "genre", "label", "category", "year"] = "grp", name: str | None = None, genre: Many = None,
           year: Years = None, decade: Years = None, artist: str | None = Query(None, max_length=200), conn=Depends(get_conn)):
    """Releases regroupées par groupe, artiste, genre ou label : nombre et poids total, restreints au genre / à l'année."""
    col = GROUP_BY[by]
    conds, params = [f"{col} IS NOT NULL", "hidden=0"], []
    if name is not None:
        conds.append(f"{col}=?")
        params.append(name)
    if artist is not None:  # chronologie d'un artiste : ses releases par année (by=year)
        conds.append("COALESCE(tag_artist, artist)=?")
        params.append(artist)
    if genre:  # plusieurs genres, années ou décennies : l'un ou l'autre, comme dans les listes
        conds.append(f"genre IN ({','.join('?' * len(genre))})")
        params += genre
    when = [f"year IN ({','.join('?' * len(year))})"] if year else []
    params += year or []
    for d in decade or []:
        when.append("year BETWEEN ? AND ?")
        params += [d, d + 9]
    if when:
        conds.append("(" + " OR ".join(when) + ")")
    # ponytail: liste entière sans pagination (l'interface n'affiche que les 1000 premières lignes) ; paginer si lourd
    return [dict(r) for r in conn.execute(
        f"SELECT {col} AS name, COUNT(*) AS releases, SUM(size) AS size FROM releases WHERE " + " AND ".join(conds)
        + " GROUP BY 1 ORDER BY releases DESC, 1 COLLATE NOCASE", params)]


@router.get("/api/tracks")
def search_tracks(q: str = Query("", max_length=200), category: Many = None, genre: Many = None, year: Years = None,
                  decade: Years = None, source: Many = None, mixes: str | None = Query(None, min_length=1, max_length=200),
                  offset: int = Query(0, ge=0, le=MAX_INT),
                  limit: int = Query(50, ge=1, le=MAX_INT), user=Depends(current_user), conn=Depends(get_conn)):
    """Recherche dans les tags : chaque mot doit figurer dans le titre ou l'artiste de la piste. Les filtres sont
    ceux des listes de releases, appliqués à la release de la piste."""
    words = [w for w in _WORDS.split(q) if w][:8]
    if not words and not mixes:
        return {"items": [], "has_more": False}
    # ponytail: LIKE parcourt toutes les pistes (~0,1 s pour 500 000) ; index FTS sur les pistes si trop lent
    # un titre ou un artiste de 30 caractères est peut-être coupé (ID3v1) : sa suite est dans le nom du fichier
    conds = " AND ".join("(t.title LIKE ? OR t.artist LIKE ? OR ((length(t.title)=30 OR length(t.artist)=30)"
                         " AND t.relpath LIKE ?))" for _ in words)
    params = [f"%{w}%" for w in words for _ in range(3)]  # mots sans % ni _ : _WORDS les a retirés
    # ou un chapitre d'un long mix (fichier .cue) dont l'artiste et le titre contiennent tous les mots
    in_chapter = " AND ".join("(c.title LIKE ? OR c.artist LIKE ?)" for _ in words)
    conds = f"(({conds}) OR t.id IN (SELECT c.track_id FROM chapters c WHERE {in_chapter}))"
    likes = [f"%{w}%" for w in words for _ in range(2)]
    params += likes
    if mixes:  # page d'un artiste : les longs mixes où un chapitre est de lui
        # ponytail: égalité à la casse près sur l'artiste du chapitre ; « X feat. Y » n'est pas une apparition de X
        in_chapter, likes = "c.artist=? COLLATE NOCASE", [mixes]
        conds, params = f"t.id IN (SELECT c.track_id FROM chapters c WHERE {in_chapter})", [mixes]
    more, extra = _release_conds(category, genre, year, source=source, decade=decade)
    conds, params = " AND ".join([conds, *more]), params + extra
    page = _page(conn, TRACK_COLS, TRACK_FROM, "WHERE " + conds, params,
                 "COALESCE(t.title, t.relpath) COLLATE NOCASE, t.artist COLLATE NOCASE, t.id",  # par titre, puis par artiste
                 user["id"], offset, limit, _track)
    for item in page["items"]:  # le chapitre trouvé, pour l'afficher et lancer la piste à cet endroit
        c = conn.execute(f"SELECT c.start, c.artist, c.title FROM chapters c WHERE c.track_id=? AND {in_chapter} ORDER BY c.pos LIMIT 1",
                         (item["id"], *likes)).fetchone()
        if c:
            item["chapter"] = dict(c)
    return page


@router.get("/api/folders")
def folders(path: str = "", sort: Sort | None = None, dir: Dir = "asc", offset: int = Query(0, ge=0, le=MAX_INT), limit: int = Query(50, ge=1, le=MAX_INT),
            user=Depends(current_user), conn=Depends(get_conn)):
    if path and conn.execute("SELECT 1 FROM folders WHERE path=?", (path,)).fetchone() is None:
        raise HTTPException(404, "Dossier introuvable.")
    subs = []
    if offset == 0:
        subs = [{"path": r["path"], "name": r["path"].rsplit("/", 1)[-1]} for r in conn.execute(
            "SELECT path FROM folders WHERE parent=? ORDER BY path COLLATE NOCASE", (path,))]
    # sous une catégorie, seules ses releases : un album ou un live rangé avec les singles se trouve dans la sienne
    where, params = ("WHERE r.parent=? AND r.category=?", [path, path.split("/", 1)[0]]) if path else ("WHERE r.parent=?", [path])
    rels = _page(conn, RELEASE_COLS, RELEASE_FROM, where, params,
                 _order(sort, dir, "r.name COLLATE NOCASE, r.id"), user["id"], offset, limit, _release)
    return {"path": path, "folders": subs, "releases": rels}


def _release_row(conn, uid, rid):
    row = conn.execute(f"SELECT {RELEASE_COLS} FROM {RELEASE_FROM} WHERE r.id=?", (uid, rid)).fetchone()
    if row is None:
        raise HTTPException(404, "Release introuvable.")
    return row


@router.get("/api/release-by-name")
def release_by_name(name: str = Query(max_length=1024), user=Depends(current_user), conn=Depends(get_conn)):
    # adresse lisible de la fiche (#/release/<nom>)
    # ponytail: deux releases de même nom dans deux dossiers -> la plus récente ; l'autre reste joignable par #/release/<id>
    row = conn.execute("SELECT id FROM releases WHERE name=? ORDER BY added_at DESC, id DESC LIMIT 1", (name,)).fetchone()
    if row is None:
        raise HTTPException(404, "Release introuvable.")
    return release_detail(row["id"], user, conn)


@router.get("/api/releases/{rid}")
def release_detail(rid: Id, user=Depends(current_user), conn=Depends(get_conn)):
    d = _release(_release_row(conn, user["id"], rid))
    d["series"] = _series(d["title"])  # la fiche demande les autres volumes à /api/series
    d["custom_cover"] = conn.execute("SELECT 1 FROM overrides WHERE path=? AND cover=1", (d["path"],)).fetchone() is not None
    d["tracks"] = [_track(r) for r in conn.execute(
        f"SELECT {TRACK_COLS} FROM {TRACK_FROM} WHERE t.release_id=? ORDER BY t.disc, t.relpath",
        (user["id"], rid))]
    return d


def _seed_artist(r):
    """Artiste servant à rapprocher d'autres releases ; None pour une compilation, qui n'a pas d'artiste à suivre."""
    return None if (r["artist"] or "").lower() in ("va", "various", "various artists") else r["artist"]


@router.get("/api/releases/{rid}/radio")
def radio(rid: Id, limit: int = Query(50, ge=1, le=MAX_LIMIT), user=Depends(current_user), conn=Depends(get_conn)):
    """Pistes tirées au hasard dans les releases proches : même artiste, ou même genre à deux ans près."""
    r = _release_row(conn, user["id"], rid)
    y = r["year"]
    # ponytail: tirage uniforme parmi les pistes candidates, comme le mix ; pondérer (artiste > genre) si la radio dérive trop
    rows = conn.execute(
        f"SELECT {TRACK_COLS} FROM {TRACK_FROM} WHERE t.id IN (SELECT t.id FROM tracks t JOIN releases r"
        " ON r.id=t.release_id WHERE r.id!=? AND (COALESCE(r.tag_artist, r.artist)=? OR (r.genre=? AND r.year BETWEEN ? AND ?))"
        " ORDER BY RANDOM() LIMIT ?) ORDER BY RANDOM()",
        (user["id"], rid, _seed_artist(r), r["genre"], y and y - 2, y and y + 2, limit))
    return {"items": [_track(x) for x in rows]}


_VOL = {"vol", "volume", "issue", "part", "pt", "no", "nr", "episode", "#"}


def _series(title: str | None) -> str | None:
    """Début du titre commun à une série : « Global Underground 47 Joseph Capriati » -> « Global Underground ».
    Les mots avant le premier qui contient un chiffre ; None s'il y en a moins de deux ou moins de huit caractères."""
    words = []
    for w in (title or "").split():
        if any(c.isdigit() for c in w):
            break
        words.append(w)
    ok = lambda ws: len(ws) >= 2 and len(" ".join(ws)) >= 8
    if not ok(words) or len(words) == len((title or "").split()):
        return None
    # « Kontor Top Of The Clubs Vol 63 » et « Kontor Top Of The Clubs 64 » : la même série
    short = words[:-1] if words[-1].rstrip(".").lower() in _VOL else words
    return " ".join(short if ok(short) else words)


@router.get("/api/series")
def series(name: str = Query(min_length=1, max_length=200), user=Depends(current_user), conn=Depends(get_conn)):
    """Volumes d'une série, dans l'ordre de leur numéro, et les numéros absents de la bibliothèque."""
    like = re.sub(r"([!%_])", r"!\1", name) + " %"
    items = [_release(x) for x in conn.execute(
        f"SELECT {RELEASE_COLS} FROM {RELEASE_FROM} WHERE r.hidden=0 AND r.title LIKE ? ESCAPE '!'", (user["id"], like))]
    # « Global Underground Nubreed 8 » commence comme « Global Underground » : c'est une autre série
    items = [x for x in items if (_series(x["title"]) or "").casefold() == name.casefold()] if _series(name + " 1") else []
    for x in items:
        x["volume"] = int(re.search(r"\d+", x["title"][len(name):])[0])
    items.sort(key=lambda x: (x["volume"], x["year"] or 0, x["name"].lower()))
    vols = {x["volume"] for x in items}
    vols = {v for v in vols if v < 1000}  # une année (« Hed Kandi 2005 ») n'est pas un numéro de volume
    # ponytail: numéros absents entre le plus petit et le plus grand présents, à partir de trois volumes ; rien au-delà
    # de 60 trous, où le nombre n'est sans doute pas un volume
    missing = sorted(set(range(min(vols), max(vols))) - vols) if len(vols) >= 3 else []
    return {"name": name, "items": items, "missing": missing if len(missing) <= 60 else []}


@router.get("/api/releases/{rid}/similar")
def similar(rid: Id, user=Depends(current_user), conn=Depends(get_conn)):
    """Jusqu'à 12 releases proches : même artiste d'abord, puis même série (début du titre avant son numéro), même
    label, enfin même genre la même année (même groupe en tête). Une compilation n'a pas d'artiste à suivre : la série
    et le label lui en tiennent lieu."""
    r = _release_row(conn, user["id"], rid)
    artist, art = _seed_artist(r), "COALESCE(r.tag_artist, r.artist)"
    series = _series(r["title"])
    like = series and re.sub(r"([!%_])", r"!\1", series) + " %"
    label = r["label"] or None
    # identifiants d'abord : le débit moyen (sous-requête) n'est calculé que pour les lignes retenues
    ids = [x[0] for x in conn.execute(
        f"SELECT r.id FROM releases r WHERE r.id!=? AND r.hidden=0 AND ({art}=? OR r.title LIKE ? ESCAPE '!' OR r.label=?"
        f" OR (r.genre=? AND r.year=?))"
        f" ORDER BY COALESCE({art}=?, 0) DESC, COALESCE(r.title LIKE ? ESCAPE '!', 0) DESC, COALESCE(r.label=?, 0) DESC,"
        f" COALESCE(r.grp=?, 0) DESC, r.added_at DESC, r.id DESC LIMIT 12",
        (rid, artist, like, label, r["genre"], r["year"], artist, like, label, r["grp"]))]
    rows = {x["id"]: _release(x) for x in conn.execute(
        f"SELECT {RELEASE_COLS} FROM {RELEASE_FROM} WHERE r.id IN ({','.join('?' * len(ids))})", (user["id"], *ids))}
    return [rows[i] for i in ids]


@router.get("/api/releases/{rid}/versions")
def versions(rid: Id, user=Depends(current_user), conn=Depends(get_conn)):
    """Autres sorties du même titre : même artiste et même titre dans le nom (autre groupe, autre source, réédition)."""
    # ponytail: rapprochement sur le nom seul, à la casse près ; « Title » et « Title_(Remixes) » sont réunis exprès
    return [_release(x) for x in conn.execute(
        f"SELECT {RELEASE_COLS} FROM {RELEASE_FROM} JOIN releases o ON o.id=? AND r.id!=o.id"
        " AND lower(r.artist)=lower(o.artist) AND lower(r.title)=lower(o.title) ORDER BY r.name COLLATE NOCASE LIMIT 50",
        (user["id"], rid))]


@router.get("/api/releases/{rid}/nfo")
def release_nfo(rid: Id, request: Request, conn=Depends(get_conn)):
    settings = request.app.state.settings
    row = conn.execute("SELECT path FROM releases WHERE id=?", (rid,)).fetchone()
    if row is None:
        raise HTTPException(404, "Release introuvable.")
    folder = safe_path(settings.music_root, row["path"])
    try:
        nfo = next(n for n in sorted(p.name for p in folder.iterdir()) if n.lower().endswith(".nfo"))
        with open(safe_path(settings.music_root, row["path"], nfo), "rb") as fh:  # lecture seule
            data = fh.read(NFO_MAX)
    except (StopIteration, OSError):
        raise HTTPException(404, "NFO introuvable.") from None
    return Response(data.decode("cp437"), media_type="text/plain; charset=utf-8")


@router.get("/api/favorites/tracks")
def favorite_tracks(offset: int = Query(0, ge=0, le=MAX_INT), limit: int = Query(50, ge=1, le=MAX_INT),
                    user=Depends(current_user), conn=Depends(get_conn)):
    return _page(conn, TRACK_COLS, TRACK_FROM, "WHERE f.item_id IS NOT NULL", [],
                 "f.created_at DESC, t.id DESC", user["id"], offset, limit, _track)


@router.get("/api/history")
def history(offset: int = Query(0, ge=0, le=MAX_INT), limit: int = Query(50, ge=1, le=MAX_INT),
            user=Depends(current_user), conn=Depends(get_conn)):
    # ponytail: l'historique grossit sans limite (quelques octets par écoute) ; purger par ancienneté si besoin
    return _page(conn, TRACK_COLS + ", p.played_at", "plays p JOIN " + TRACK_FROM,
                 "WHERE p.track_id=t.id AND p.user_id=?", [user["id"]], "p.played_at DESC, p.rowid DESC",
                 user["id"], offset, limit, _track)


@router.get("/api/history/releases")
def history_releases(sort: Sort | None = None, dir: Dir = "asc", offset: int = Query(0, ge=0, le=MAX_INT),
                     limit: int = Query(50, ge=1, le=MAX_INT), user=Depends(current_user), conn=Depends(get_conn)):
    """Releases écoutées par l'utilisateur, la plus récemment écoutée d'abord."""
    return _page(conn, RELEASE_COLS, RELEASE_FROM + " JOIN (SELECT t.release_id, MAX(p.played_at) AS last FROM plays p"
                 " JOIN tracks t ON t.id=p.track_id WHERE p.user_id=? GROUP BY 1) h ON h.release_id=r.id",
                 "", [user["id"]], _order(sort, dir, "h.last DESC, r.id DESC"), user["id"], offset, limit, _release)


@router.get("/api/stats")
def stats(days: int = Query(0, ge=0, le=36500), user=Depends(current_user), conn=Depends(get_conn)):
    """Statistiques d'écoute de l'utilisateur sur les `days` derniers jours (0 : tout l'historique)."""
    uid, since = user["id"], time.time() - days * 86400 if days else 0
    src = "plays p JOIN tracks t ON t.id=p.track_id JOIN releases r ON r.id=t.release_id"
    where = "WHERE p.user_id=? AND p.played_at>=?"
    total = conn.execute(f"SELECT COUNT(*) AS plays, COALESCE(SUM(t.duration), 0) AS duration FROM {src} {where}",
                         (uid, since)).fetchone()

    def top(col):
        return [dict(r) for r in conn.execute(
            f"SELECT {col} AS name, COUNT(*) AS plays FROM {src} {where} AND {col} IS NOT NULL"
            " GROUP BY 1 ORDER BY plays DESC, 1 COLLATE NOCASE LIMIT 10", (uid, since))]

    tracks = [_track(r) for r in conn.execute(
        f"SELECT {TRACK_COLS}, n.plays FROM (SELECT track_id, COUNT(*) AS plays FROM plays p {where} GROUP BY track_id"
        f" ORDER BY plays DESC, track_id LIMIT 10) n JOIN {TRACK_FROM} WHERE t.id=n.track_id"
        " ORDER BY n.plays DESC, t.id", (uid, since, uid))]
    days = [dict(r) for r in conn.execute(
        f"SELECT strftime('%Y-%m-%d', p.played_at, 'unixepoch', 'localtime') AS name, COUNT(*) AS n, COALESCE(SUM(t.duration), 0) AS duration"
        f" FROM {src} {where} GROUP BY 1 ORDER BY 1 DESC LIMIT 31", (uid, since))]
    return {"plays": total["plays"], "duration": total["duration"], "tracks": tracks, "days": days,
            "artists": top("COALESCE(t.artist, r.tag_artist, r.artist)"), "genres": top("COALESCE(t.genre, r.genre)"),
            "groups": top("r.grp")}


@router.post("/api/history/{track_id}", status_code=204)
def add_play(track_id: Id, user=Depends(current_user), conn=Depends(get_conn)):
    _check_item(conn, "track", track_id)
    conn.execute("INSERT INTO plays(user_id, track_id, played_at) VALUES (?,?,?)", (user["id"], track_id, time.time()))
    conn.commit()


@router.delete("/api/history", status_code=204)
def clear_history(user=Depends(current_user), conn=Depends(get_conn)):
    conn.execute("DELETE FROM plays WHERE user_id=?", (user["id"],))
    conn.commit()


def _check_item(conn, kind, item_id):
    table = {"release": "releases", "track": "tracks"}.get(kind)
    if table is None or conn.execute(f"SELECT 1 FROM {table} WHERE id=?", (item_id,)).fetchone() is None:
        raise HTTPException(404, "Élément introuvable.")


@router.put("/api/favorites/{kind}/{item_id}", status_code=204)
def add_favorite(kind: str, item_id: Id, user=Depends(current_user), conn=Depends(get_conn)):
    _check_item(conn, kind, item_id)
    conn.execute("INSERT OR IGNORE INTO favorites(user_id, kind, item_id, created_at) VALUES (?,?,?,?)",
                 (user["id"], kind, item_id, time.time()))
    conn.commit()


@router.delete("/api/favorites/{kind}/{item_id}", status_code=204)
def remove_favorite(kind: str, item_id: Id, user=Depends(current_user), conn=Depends(get_conn)):
    if kind not in ("release", "track"):
        raise HTTPException(404, "Élément introuvable.")
    conn.execute("DELETE FROM favorites WHERE user_id=? AND kind=? AND item_id=?", (user["id"], kind, item_id))
    conn.commit()
