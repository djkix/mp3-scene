import re
import time

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from .deps import current_user, get_conn
from .security import safe_path

router = APIRouter(dependencies=[Depends(current_user)])

MAX_LIMIT = 100
NFO_MAX = 1024 * 1024
_WORDS = re.compile(r"[\W_]+")

# artiste : tag commun s'il existe, sinon celui extrait du nom
RELEASE_COLS = """r.id, r.name, r.path, r.category, r.added_at, r.size, r.track_count, r.has_nfo,
  COALESCE(r.tag_artist, r.artist) AS artist, r.title, r.source, r.year, r.grp, r.genre, r.duration,
  (f.item_id IS NOT NULL) AS favorite"""
RELEASE_FROM = "releases r LEFT JOIN favorites f ON f.user_id=? AND f.kind='release' AND f.item_id=r.id"
TRACK_COLS = """t.id, t.release_id, r.name AS release_name, t.relpath, t.disc, t.size, t.title, t.artist,
  t.duration, t.bitrate, (f.item_id IS NOT NULL) AS favorite"""
TRACK_FROM = ("tracks t JOIN releases r ON r.id=t.release_id "
              "LEFT JOIN favorites f ON f.user_id=? AND f.kind='track' AND f.item_id=t.id")


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
def list_releases(q: str = "", category: str | None = None, genre: str | None = None, year: int | None = None,
                  favorites: int = Query(0, ge=0, le=1), offset: int = Query(0, ge=0), limit: int = Query(50, ge=1),
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
    return _page(conn, RELEASE_COLS, RELEASE_FROM, where, params, "r.added_at DESC, r.id DESC",
                 user["id"], offset, limit, _release)


@router.get("/api/filters")
def filters(conn=Depends(get_conn)):
    col = lambda sql: [r[0] for r in conn.execute(sql)]
    return {"categories": col("SELECT DISTINCT category FROM releases WHERE category IS NOT NULL ORDER BY category"),
            "genres": col("SELECT DISTINCT genre FROM releases WHERE genre IS NOT NULL ORDER BY genre"),
            "years": col("SELECT DISTINCT year FROM releases WHERE year IS NOT NULL ORDER BY year DESC")}


@router.get("/api/folders")
def folders(path: str = "", offset: int = Query(0, ge=0), limit: int = Query(50, ge=1),
            user=Depends(current_user), conn=Depends(get_conn)):
    if path and conn.execute("SELECT 1 FROM folders WHERE path=?", (path,)).fetchone() is None:
        raise HTTPException(404, "Dossier introuvable.")
    subs = []
    if offset == 0:
        subs = [{"path": r["path"], "name": r["path"].rsplit("/", 1)[-1]} for r in conn.execute(
            "SELECT path FROM folders WHERE parent=? ORDER BY path COLLATE NOCASE", (path,))]
    rels = _page(conn, RELEASE_COLS, RELEASE_FROM, "WHERE r.parent=?", [path], "r.name COLLATE NOCASE, r.id",
                 user["id"], offset, limit, _release)
    return {"path": path, "folders": subs, "releases": rels}


def _release_row(conn, uid, rid):
    row = conn.execute(f"SELECT {RELEASE_COLS} FROM {RELEASE_FROM} WHERE r.id=?", (uid, rid)).fetchone()
    if row is None:
        raise HTTPException(404, "Release introuvable.")
    return row


@router.get("/api/releases/{rid}")
def release_detail(rid: int, user=Depends(current_user), conn=Depends(get_conn)):
    d = _release(_release_row(conn, user["id"], rid))
    d["tracks"] = [_track(r) for r in conn.execute(
        f"SELECT {TRACK_COLS} FROM {TRACK_FROM} WHERE t.release_id=? ORDER BY t.disc, t.relpath",
        (user["id"], rid))]
    return d


@router.get("/api/releases/{rid}/nfo")
def release_nfo(rid: int, request: Request, conn=Depends(get_conn)):
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
def favorite_tracks(offset: int = Query(0, ge=0), limit: int = Query(50, ge=1),
                    user=Depends(current_user), conn=Depends(get_conn)):
    return _page(conn, TRACK_COLS, TRACK_FROM, "WHERE f.item_id IS NOT NULL", [],
                 "f.created_at DESC, t.id DESC", user["id"], offset, limit, _track)


def _check_item(conn, kind, item_id):
    table = {"release": "releases", "track": "tracks"}.get(kind)
    if table is None or conn.execute(f"SELECT 1 FROM {table} WHERE id=?", (item_id,)).fetchone() is None:
        raise HTTPException(404, "Élément introuvable.")


@router.put("/api/favorites/{kind}/{item_id}", status_code=204)
def add_favorite(kind: str, item_id: int, user=Depends(current_user), conn=Depends(get_conn)):
    _check_item(conn, kind, item_id)
    conn.execute("INSERT OR IGNORE INTO favorites(user_id, kind, item_id, created_at) VALUES (?,?,?,?)",
                 (user["id"], kind, item_id, time.time()))
    conn.commit()


@router.delete("/api/favorites/{kind}/{item_id}", status_code=204)
def remove_favorite(kind: str, item_id: int, user=Depends(current_user), conn=Depends(get_conn)):
    if kind not in ("release", "track"):
        raise HTTPException(404, "Élément introuvable.")
    conn.execute("DELETE FROM favorites WHERE user_id=? AND kind=? AND item_id=?", (user["id"], kind, item_id))
    conn.commit()
