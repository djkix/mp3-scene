import json
import time

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from .deps import MAX_INT, Id, current_user, get_conn
from .routes_library import TRACK_COLS, TRACK_FROM, _page, _release_conds, _track

router = APIRouter(dependencies=[Depends(current_user)])


class Name(BaseModel):
    name: str = Field(min_length=1, max_length=100)


Text = Annotated[str, Field(max_length=200)]
Int = Annotated[int, Field(ge=0, le=MAX_INT)]
Texts = Text | Annotated[list[Text], Field(min_length=1, max_length=100)]
Ints = Int | Annotated[list[Int], Field(min_length=1, max_length=100)]


class Rules(BaseModel):
    """Filtres d'une playlist intelligente : les mêmes que ceux des listes de releases."""
    # catégorie, genre, année, décennie et source acceptent plusieurs valeurs, comme les filtres des listes
    category: Texts | None = None
    genre: Texts | None = None
    year: Ints | None = None
    decade: Ints | None = None
    source: Texts | None = None
    grp: str | None = Field(default=None, max_length=200)
    artist: str | None = Field(default=None, max_length=200)
    label: str | None = Field(default=None, max_length=200)


class NewPlaylist(Name):
    rules: Rules | None = None


def _smart(rules: str):
    """(source SQL, condition, paramètres) des pistes d'une playlist intelligente : celles des releases qui passent
    ses filtres aujourd'hui, donc à jour après chaque scan sans rien recalculer."""
    conds, params = _release_conds(**json.loads(rules))
    return "WHERE " + " AND ".join(conds), params


class Add(BaseModel):
    track_ids: list[int] = Field(default=[], max_length=1000)
    release_id: int | None = Field(default=None, ge=1, le=MAX_INT)


def _name(body: Name) -> str:
    name = body.name.strip()
    if not name:
        raise HTTPException(422, "Nom vide.")
    return name


def _own(conn, uid, pid):
    """La playlist `pid` si elle appartient à l'utilisateur ; 404 sinon (on ne révèle pas celles des autres)."""
    row = conn.execute("SELECT id, name, rules FROM playlists WHERE id=? AND user_id=?", (pid, uid)).fetchone()
    if row is None:
        raise HTTPException(404, "Playlist introuvable.")
    return row


def _manual(conn, uid, pid):
    """Comme _own, pour une modification des pistes : refusée sur une playlist intelligente."""
    if _own(conn, uid, pid)["rules"] is not None:
        raise HTTPException(400, "Les pistes d'une playlist intelligente viennent de ses filtres.")


@router.get("/api/playlists")
def list_playlists(user=Depends(current_user), conn=Depends(get_conn)):
    out = []
    for r in conn.execute(
            "SELECT p.id, p.name, p.rules, COUNT(t.id) AS tracks, COALESCE(SUM(t.duration), 0) AS duration FROM playlists p"
            " LEFT JOIN playlist_tracks pt ON pt.playlist_id=p.id LEFT JOIN tracks t ON t.id=pt.track_id"
            " WHERE p.user_id=? GROUP BY p.id ORDER BY p.name COLLATE NOCASE, p.id", (user["id"],)).fetchall():
        d = {"id": r["id"], "name": r["name"], "tracks": r["tracks"], "duration": r["duration"], "smart": r["rules"] is not None}
        if d["smart"]:  # ponytail: un comptage par playlist intelligente à chaque affichage de la liste
            where, params = _smart(r["rules"])
            d["tracks"], d["duration"] = conn.execute(
                "SELECT COUNT(*), COALESCE(SUM(t.duration), 0) FROM tracks t JOIN releases r ON r.id=t.release_id " + where,
                params).fetchone()
        out.append(d)
    return out


@router.post("/api/playlists", status_code=201)
def create_playlist(body: NewPlaylist, user=Depends(current_user), conn=Depends(get_conn)):
    """Avec `rules`, une playlist intelligente : ses pistes sont celles des releases qui passent ces filtres."""
    name = _name(body)
    rules = body.rules and body.rules.model_dump(exclude_none=True)
    if body.rules and not rules:
        raise HTTPException(400, "Choisissez au moins un filtre.")
    pid = conn.execute("INSERT INTO playlists(user_id, name, created_at, rules) VALUES (?,?,?,?)",
                       (user["id"], name, time.time(), json.dumps(rules) if rules else None)).lastrowid
    conn.commit()
    return {"id": pid, "name": name}


@router.put("/api/playlists/{pid}", status_code=204)
def rename_playlist(pid: Id, body: Name, user=Depends(current_user), conn=Depends(get_conn)):
    _own(conn, user["id"], pid)
    conn.execute("UPDATE playlists SET name=? WHERE id=?", (_name(body), pid))
    conn.commit()


@router.delete("/api/playlists/{pid}", status_code=204)
def delete_playlist(pid: Id, user=Depends(current_user), conn=Depends(get_conn)):
    conn.execute("DELETE FROM playlists WHERE id=? AND user_id=?", (pid, user["id"]))
    conn.commit()


@router.get("/api/playlists/{pid}")
def playlist(pid: Id, offset: int = Query(0, ge=0, le=MAX_INT), limit: int = Query(50, ge=1, le=MAX_INT),
             user=Depends(current_user), conn=Depends(get_conn)):
    row = _own(conn, user["id"], pid)
    if row["rules"] is not None:
        where, params = _smart(row["rules"])
        page = _page(conn, TRACK_COLS, TRACK_FROM, where, params, "r.name COLLATE NOCASE, r.id, t.disc, t.relpath",
                     user["id"], offset, limit, _track)
        return {"id": row["id"], "name": row["name"], "smart": True, "rules": json.loads(row["rules"]), **page}
    page = _page(conn, TRACK_COLS, "playlist_tracks pt JOIN " + TRACK_FROM, "WHERE pt.track_id=t.id AND pt.playlist_id=?",
                 [pid], "pt.position, t.id", user["id"], offset, limit, _track)
    return {"id": row["id"], "name": row["name"], **page}


@router.post("/api/playlists/{pid}/tracks", status_code=204)
def add_tracks(pid: Id, body: Add, user=Depends(current_user), conn=Depends(get_conn)):
    """Ajoute des pistes (ou toutes celles d'une release) à la fin ; celles déjà présentes sont ignorées."""
    _manual(conn, user["id"], pid)
    ids = list(body.track_ids)
    if body.release_id is not None:
        ids += [r[0] for r in conn.execute("SELECT id FROM tracks WHERE release_id=? ORDER BY disc, relpath",
                                           (body.release_id,))]
    pos = conn.execute("SELECT COALESCE(MAX(position), 0) FROM playlist_tracks WHERE playlist_id=?", (pid,)).fetchone()[0]
    # les identifiants inconnus sont écartés par la sous-requête (pas d'erreur de clé étrangère)
    conn.executemany("INSERT OR IGNORE INTO playlist_tracks(playlist_id, track_id, position)"
                     " SELECT ?, id, ? FROM tracks WHERE id=?",
                     [(pid, pos + n, tid) for n, tid in enumerate(ids, 1) if 0 < tid <= MAX_INT])
    conn.commit()


@router.post("/api/playlists/{pid}/tracks/{track_id}/move", status_code=204)
def move_track(pid: Id, track_id: Id, dir: Literal["up", "down"], user=Depends(current_user), conn=Depends(get_conn)):
    """Échange la piste avec sa voisine du dessus ou du dessous ; sans effet en bout de liste."""
    _manual(conn, user["id"], pid)
    me = conn.execute("SELECT position FROM playlist_tracks WHERE playlist_id=? AND track_id=?", (pid, track_id)).fetchone()
    if me is None:
        raise HTTPException(404, "Piste introuvable.")
    op, order = ("<", "DESC") if dir == "up" else (">", "ASC")
    other = conn.execute(f"SELECT track_id, position FROM playlist_tracks WHERE playlist_id=? AND position{op}?"
                         f" ORDER BY position {order} LIMIT 1", (pid, me["position"])).fetchone()
    if other is not None:
        conn.execute("UPDATE playlist_tracks SET position=? WHERE playlist_id=? AND track_id=?", (other["position"], pid, track_id))
        conn.execute("UPDATE playlist_tracks SET position=? WHERE playlist_id=? AND track_id=?",
                     (me["position"], pid, other["track_id"]))
        conn.commit()


@router.delete("/api/playlists/{pid}/tracks/{track_id}", status_code=204)
def remove_track(pid: Id, track_id: Id, user=Depends(current_user), conn=Depends(get_conn)):
    _manual(conn, user["id"], pid)
    conn.execute("DELETE FROM playlist_tracks WHERE playlist_id=? AND track_id=?", (pid, track_id))
    conn.commit()


class Position(BaseModel):
    pos: float = Field(ge=0, le=1e7)


@router.get("/api/positions/{track_id}")
def get_position(track_id: Id, user=Depends(current_user), conn=Depends(get_conn)):
    """Position gardée dans cette piste par l'utilisateur (secondes), 0 s'il n'y en a pas."""
    row = conn.execute("SELECT pos FROM positions WHERE user_id=? AND track_id=?", (user["id"], track_id)).fetchone()
    return {"pos": row["pos"] if row else 0}


@router.put("/api/positions/{track_id}", status_code=204)
def put_position(track_id: Id, body: Position, user=Depends(current_user), conn=Depends(get_conn)):
    """Garde la position d'écoute d'une longue piste ; 0 l'oublie (piste finie ou reprise du début)."""
    if body.pos <= 0:
        conn.execute("DELETE FROM positions WHERE user_id=? AND track_id=?", (user["id"], track_id))
    else:
        conn.execute("INSERT INTO positions(user_id, track_id, pos, updated_at) SELECT ?, id, ?, ? FROM tracks WHERE id=?"
                     " ON CONFLICT(user_id, track_id) DO UPDATE SET pos=excluded.pos, updated_at=excluded.updated_at",
                     (user["id"], body.pos, time.time(), track_id))
    conn.commit()


STATE_MAX = 512 * 1024


@router.get("/api/player-state")
def get_player_state(user=Depends(current_user), conn=Depends(get_conn)):
    row = conn.execute("SELECT data, updated_at FROM player_state WHERE user_id=?", (user["id"],)).fetchone()
    return {"state": json.loads(row["data"]), "updated_at": row["updated_at"]} if row else {"state": None, "updated_at": 0}


@router.put("/api/player-state")
def put_player_state(state: dict = Body(), user=Depends(current_user), conn=Depends(get_conn)):
    """Dernier état du lecteur de l'utilisateur. Contenu opaque : seul son propre navigateur le relit."""
    data = json.dumps(state, separators=(",", ":"))
    if len(data) > STATE_MAX:
        raise HTTPException(413, "File de lecture trop longue pour être synchronisée.")
    now = time.time()
    conn.execute("INSERT INTO player_state(user_id, data, updated_at) VALUES (?,?,?)"
                 " ON CONFLICT(user_id) DO UPDATE SET data=excluded.data, updated_at=excluded.updated_at",
                 (user["id"], data, now))
    conn.commit()
    return {"updated_at": now}
