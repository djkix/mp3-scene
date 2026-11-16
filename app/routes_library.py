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
# artiste : tag commun s'il existe, sinon celui extrait du nom
RELEASE_COLS = """r.id, r.name, r.path, r.category, r.added_at, r.size, r.track_count, r.has_nfo,
  COALESCE(r.tag_artist, r.artist) AS artist, r.title, r.source, r.year, r.grp, r.genre, r.duration,
  """ + BITRATE + """ AS bitrate, (f.item_id IS NOT NULL) AS favorite"""
RELEASE_FROM = "releases r LEFT JOIN favorites f ON f.user_id=? AND f.kind='release' AND f.item_id=r.id"
TRACK_COLS = """t.id, t.release_id, r.name AS release_name, t.relpath, t.disc, t.size, t.title, t.artist,
  t.duration, t.bitrate, (f.item_id IS NOT NULL) AS favorite"""
TRACK_FROM = ("tracks t JOIN releases r ON r.id=t.release_id "
              "LEFT JOIN favorites f ON f.user_id=? AND f.kind='track' AND f.item_id=t.id")


# tri des listes : colonnes autorisées (jamais de texte du client dans le SQL)
SORTS = {"name": "r.name COLLATE NOCASE", "genre": "r.genre COLLATE NOCASE", "date": "r.added_at",
         "tracks": "r.track_count", "size": "r.size", "category": "r.category COLLATE NOCASE",
         "bitrate": BITRATE}
Sort = Literal["name", "genre", "date", "tracks", "size", "category", "bitrate"]
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


@router.get("/api/releases")
def list_releases(q: str = "", category: str | None = None, genre: str | None = None,
                  year: int | None = Query(None, ge=0, le=MAX_INT), favorites: int = Query(0, ge=0, le=1),
                  sort: Sort | None = None, dir: Dir = "asc",
                  offset: int = Query(0, ge=0, le=MAX_INT), limit: int = Query(50, ge=1, le=MAX_INT),
                  user=Depends(current_user), conn=Depends(get_conn)):
    conds, params = [], []
    if match := _fts_query(q):
        conds.append("r.id IN (SELECT rowid FROM releases_fts WHERE releases_fts MATCH ?)")
        params.append(match)
    for col, val in (("category", category), ("genre", genre), ("year", year)):
        if val is not None:
            conds.append(f"r.{col}=?")
            params.append(val)
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
            "years": col("SELECT DISTINCT year FROM releases WHERE year IS NOT NULL ORDER BY year DESC")}


@router.get("/api/folders")
def folders(path: str = "", sort: Sort | None = None, dir: Dir = "asc", offset: int = Query(0, ge=0, le=MAX_INT), limit: int = Query(50, ge=1, le=MAX_INT),
            user=Depends(current_user), conn=Depends(get_conn)):
    if path and conn.execute("SELECT 1 FROM folders WHERE path=?", (path,)).fetchone() is None:
        raise HTTPException(404, "Dossier introuvable.")
    subs = []
    if offset == 0:
        subs = [{"path": r["path"], "name": r["path"].rsplit("/", 1)[-1]} for r in conn.execute(
            "SELECT path FROM folders WHERE parent=? ORDER BY path COLLATE NOCASE", (path,))]
    rels = _page(conn, RELEASE_COLS, RELEASE_FROM, "WHERE r.parent=?", [path],
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
