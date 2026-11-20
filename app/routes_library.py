import re
import time
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

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
    d["favorite"] = bool(d["favorite"])
    return d


def _track(row) -> dict:
    d = dict(row)
    d["filename"] = d.pop("relpath").rsplit("/", 1)[-1]
    d["favorite"] = bool(d["favorite"])
    return d


def _page(conn, cols, source, where, params, order, uid, offset, limit, build):
    limit = min(limit, MAX_LIMIT)
    rows = conn.execute(f"SELECT {cols} FROM {source} {where} ORDER BY {order} LIMIT ? OFFSET ?",
                        [uid, *params, limit + 1, offset]).fetchall()
    return {"items": [build(r) for r in rows[:limit]], "has_more": len(rows) > limit}


def _release_conds(category=None, genre=None, year=None, grp=None, artist=None, source=None, decade=None, appears=None,
                   collab=None):
    """Conditions SQL (et leurs paramètres) des filtres de release communs aux listes et au mix."""
    conds, params = [], []
    for col, val in (("category", category), ("genre", genre), ("year", year), ("grp", grp), ("source", source)):
        if val is not None:
            conds.append(f"r.{col}=?")
            params.append(val)
    if decade is not None:
        conds.append("r.year BETWEEN ? AND ?")
        params += [decade, decade + 9]
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
def mix(category: str | None = None, genre: str | None = None, year: int | None = Query(None, ge=0, le=MAX_INT),
        grp: str | None = None, artist: str | None = None, source: str | None = None,
        decade: int | None = Query(None, ge=0, le=MAX_INT), appears: str | None = None,
        collab: str | None = Query(None, max_length=200), limit: int = Query(50, ge=1, le=MAX_LIMIT), user=Depends(current_user), conn=Depends(get_conn)):
    """Pistes tirées au hasard parmi les releases qui passent les filtres."""
    conds, params = _release_conds(category, genre, year, grp, artist, source, decade, appears, collab)
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
def list_releases(q: str = "", category: str | None = None, genre: str | None = None, grp: str | None = None,
                  artist: str | None = None, source: str | None = None, appears: str | None = None,
                  decade: int | None = Query(None, ge=0, le=MAX_INT), collab: str | None = Query(None, max_length=200),
                  year: int | None = Query(None, ge=0, le=MAX_INT), favorites: int = Query(0, ge=0, le=1),
                  sort: Sort | None = None, dir: Dir = "asc",
                  offset: int = Query(0, ge=0, le=MAX_INT), limit: int = Query(50, ge=1, le=MAX_INT),
                  user=Depends(current_user), conn=Depends(get_conn)):
    conds, params = _release_conds(category, genre, year, grp, artist, source, decade, appears, collab)
    if match := _fts_query(q):
        conds.append("r.id IN (SELECT rowid FROM releases_fts WHERE releases_fts MATCH ?)")
        params.append(match)
    if favorites:
        conds.append("f.item_id IS NOT NULL")
    where = "WHERE " + " AND ".join(conds) if conds else ""
    return _page(conn, RELEASE_COLS, RELEASE_FROM, where, params, _order(sort, dir, "r.added_at DESC, r.id DESC"),
                 user["id"], offset, limit, _release)


@router.get("/api/filters")
def filters(conn=Depends(get_conn)):
    col = lambda sql: [r[0] for r in conn.execute(sql)]
    return {"categories": col("SELECT DISTINCT category FROM releases WHERE category IS NOT NULL ORDER BY category"),
            "genres": col("SELECT DISTINCT genre FROM releases WHERE genre IS NOT NULL ORDER BY genre"),
            "sources": col("SELECT DISTINCT source FROM releases WHERE source IS NOT NULL ORDER BY source"),
            "years": col("SELECT DISTINCT year FROM releases WHERE year IS NOT NULL ORDER BY year DESC")}


# regroupements de la page Explorer : colonnes autorisées (jamais de texte du client dans le SQL)
GROUP_BY = {"grp": "grp", "artist": "COALESCE(tag_artist, artist)", "genre": "genre"}


@router.get("/api/groups")
def groups(by: Literal["grp", "artist", "genre"] = "grp", name: str | None = None, genre: str | None = None,
           year: int | None = Query(None, ge=0, le=MAX_INT), decade: int | None = Query(None, ge=0, le=MAX_INT),
           conn=Depends(get_conn)):
    """Releases regroupées par groupe, artiste ou genre : nombre et poids total, restreints au genre / à l'année."""
    col = GROUP_BY[by]
    conds, params = [f"{col} IS NOT NULL"], []
    for c, val in ((col, name), ("genre", genre), ("year", year)):
        if val is not None:
            conds.append(f"{c}=?")
            params.append(val)
    if decade is not None:
        conds.append("year BETWEEN ? AND ?")
        params += [decade, decade + 9]
    # ponytail: liste entière sans pagination (l'interface n'affiche que les 1000 premières lignes) ; paginer si lourd
    return [dict(r) for r in conn.execute(
        f"SELECT {col} AS name, COUNT(*) AS releases, SUM(size) AS size FROM releases WHERE " + " AND ".join(conds)
        + " GROUP BY 1 ORDER BY releases DESC, 1 COLLATE NOCASE", params)]


@router.get("/api/tracks")
def search_tracks(q: str = Query("", max_length=200), offset: int = Query(0, ge=0, le=MAX_INT),
                  limit: int = Query(50, ge=1, le=MAX_INT), user=Depends(current_user), conn=Depends(get_conn)):
    """Recherche dans les tags : chaque mot doit figurer dans le titre ou l'artiste de la piste."""
    words = [w for w in _WORDS.split(q) if w][:8]
    if not words:
        return {"items": [], "has_more": False}
    # ponytail: LIKE parcourt toutes les pistes (~0,1 s pour 500 000) ; index FTS sur les pistes si trop lent
    conds = " AND ".join("(t.title LIKE ? OR t.artist LIKE ?)" for _ in words)
    params = [f"%{w}%" for w in words for _ in range(2)]  # mots sans % ni _ : _WORDS les a retirés
    return _page(conn, TRACK_COLS, TRACK_FROM, "WHERE " + conds, params,
                 "t.artist COLLATE NOCASE, t.title COLLATE NOCASE, t.id", user["id"], offset, limit, _track)


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


@router.get("/api/releases/{rid}/similar")
def similar(rid: Id, user=Depends(current_user), conn=Depends(get_conn)):
    """Jusqu'à 12 releases proches : même artiste d'abord, puis même genre la même année (même groupe en tête)."""
    r = _release_row(conn, user["id"], rid)
    artist, art = _seed_artist(r), "COALESCE(r.tag_artist, r.artist)"
    # identifiants d'abord : le débit moyen (sous-requête) n'est calculé que pour les lignes retenues
    ids = [x[0] for x in conn.execute(
        f"SELECT r.id FROM releases r WHERE r.id!=? AND ({art}=? OR (r.genre=? AND r.year=?))"
        f" ORDER BY COALESCE({art}=?, 0) DESC, COALESCE(r.grp=?, 0) DESC, r.added_at DESC, r.id DESC LIMIT 12",
        (rid, artist, r["genre"], r["year"], artist, r["grp"]))]
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
    return {"plays": total["plays"], "duration": total["duration"], "tracks": tracks,
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
