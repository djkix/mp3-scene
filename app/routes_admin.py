import io
import os
import re
import sqlite3
import time
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from PIL import Image
from pydantic import BaseModel, Field

from . import artists, backup, coversearch, db, genres, nfo, scanner, security
from .deps import MAX_INT, Id, get_conn, require_admin
from .naming import parse_release_name
from .routes_media import COVER_MAX, IMAGE_ERRORS, save_cover
from .routes_library import RELEASE_COLS, RELEASE_FROM, Dir, Sort, _all_series, _families, _order, _page, _release, titles, photo_candidates, photo_path, store_photo

# libellé au journal d'activité de chaque action d'administration : (méthode, route) -> libellé
_ACTIONS = {
    ("POST", "/users"): "Compte créé", ("PATCH", "/users/{user_id}"): "Compte modifié", ("DELETE", "/users/{user_id}"): "Compte supprimé",
    ("POST", "/scan"): "Scan lancé", ("PUT", "/scan/schedule"): "Scan quotidien réglé", ("POST", "/classify"): "Reclassement",
    ("PATCH", "/releases/{rid}"): "Correction", ("PATCH", "/releases"): "Correction en lot",
    ("PUT", "/releases/{rid}/cover"): "Pochette ajoutée", ("POST", "/releases/{rid}/cover/fetch"): "Pochette ajoutée", ("DELETE", "/releases/{rid}/cover"): "Pochette retirée",
    ("PUT", "/titles/aliases"): "Titres fusionnés", ("DELETE", "/titles/aliases"): "Titres séparés",
    ("PUT", "/releases/{rid}/keep"): "Version gardée", ("DELETE", "/releases/{rid}/keep"): "Versions réaffichées",
    ("PUT", "/artists/aliases"): "Artiste rattaché", ("DELETE", "/artists/aliases"): "Artiste détaché",
    ("PUT", "/labels/aliases"): "Label rattaché", ("DELETE", "/labels/aliases"): "Label détaché",
    ("PUT", "/artists/separate"): "Artiste gardé à part", ("DELETE", "/artists/separate"): "Artiste fusionné à nouveau",
}


def audit(request: Request, user=Depends(require_admin)):
    """Inscrit au journal chaque action d'administration qui a réussi (une erreur interrompt avant l'inscription)."""
    yield
    route = getattr(request.scope.get("route"), "path", "")[len("/api/admin"):]
    action = _ACTIONS.get((request.method, route))
    if action is None:
        return
    conn = db.connect(request.app.state.settings.data_dir)
    try:
        rid = request.path_params.get("rid")
        name = rid and conn.execute("SELECT name FROM releases WHERE id=?", (rid,)).fetchone()
        detail = name[0] if name else request.query_params.get("alias") or request.query_params.get("name") or ""
        db.log(conn, user["username"], action, detail)
        conn.commit()
    finally:
        conn.close()


router = APIRouter(prefix="/api/admin", dependencies=[Depends(audit)])

Role = Literal["admin", "user"]
# condition SQL : l'utilisateur ciblé n'est pas le dernier admin (évaluée dans la même requête que l'écriture)
NOT_LAST_ADMIN = "(role != 'admin' OR (SELECT count(*) FROM users WHERE role = 'admin') > 1)"


class NewUser(BaseModel):
    username: str
    password: str = Field(max_length=1024)
    role: Role


class UserPatch(BaseModel):
    password: str | None = Field(default=None, max_length=1024)
    role: Role | None = None


def _check(err: str | None) -> None:
    if err:
        raise HTTPException(400, err)


def _get_user(conn, user_id: int):
    row = conn.execute("SELECT id, role FROM users WHERE id = ?", (user_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "Utilisateur introuvable.")
    return row


@router.get("/version")
def version():
    return {"version": os.environ.get("APP_VERSION", "dev")}  # posée à la construction de l'image


@router.get("/users")
def list_users(conn=Depends(get_conn)):
    return [dict(r) for r in conn.execute("SELECT id, username, role FROM users ORDER BY username")]


@router.post("/users", status_code=201)
def create_user(body: NewUser, conn=Depends(get_conn)):
    username = body.username.strip()
    _check(security.username_error(username))
    _check(security.password_error(body.password))
    try:
        cur = conn.execute("INSERT INTO users(username, password_hash, role) VALUES (?,?,?)",
                           (username, security.hash_password(body.password), body.role))
        conn.commit()
    except sqlite3.IntegrityError:
        raise HTTPException(409, "Ce nom d'utilisateur existe déjà.")
    return {"id": cur.lastrowid, "username": username, "role": body.role}


@router.patch("/users/{user_id}", status_code=204)
def update_user(user_id: Id, body: UserPatch, conn=Depends(get_conn)):
    _get_user(conn, user_id)
    pw_hash = None
    if body.password is not None:
        _check(security.password_error(body.password))
        pw_hash = security.hash_password(body.password)  # avant toute écriture : le hachage dure ~100 ms
    if body.role == "user":
        cur = conn.execute(f"UPDATE users SET role = 'user' WHERE id = ? AND {NOT_LAST_ADMIN}", (user_id,))
        if cur.rowcount == 0:
            raise HTTPException(409, "Impossible de rétrograder le dernier administrateur.")
    elif body.role == "admin":
        conn.execute("UPDATE users SET role = 'admin' WHERE id = ?", (user_id,))
    if pw_hash is not None:
        conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (pw_hash, user_id))
        security.drop_sessions(conn, user_id)  # valide aussi la transaction
    conn.commit()


@router.delete("/users/{user_id}", status_code=204)
def delete_user(user_id: Id, conn=Depends(get_conn)):
    _get_user(conn, user_id)
    cur = conn.execute(f"DELETE FROM users WHERE id = ? AND {NOT_LAST_ADMIN}", (user_id,))
    conn.commit()
    if cur.rowcount == 0:
        raise HTTPException(409, "Impossible de supprimer le dernier administrateur.")


@router.post("/scan", status_code=202)
def start_scan(request: Request):
    if not request.app.state.runner.start():
        raise HTTPException(409, "Un scan est déjà en cours.")
    return {"started": True}


@router.post("/scan/retag", status_code=202)
def reread_tags(request: Request, conn=Depends(get_conn)):
    """Relit les tags de toutes les pistes (BPM et tonalité, indexés depuis la 1.61.0). Les valeurs déjà lues restent
    affichées jusqu'à leur relecture ; rien n'est écrit dans le dossier de musique."""
    conn.execute("UPDATE tracks SET tags_read=0")
    conn.commit()
    if not request.app.state.runner._launch(structure=False):
        raise HTTPException(409, "Un scan est déjà en cours : la relecture suivra au prochain scan.")
    return {"started": True}


class Schedule(BaseModel):
    hour: int | None = Field(default=None, ge=0, le=23)


@router.put("/scan/schedule", status_code=204)
def schedule_scan(body: Schedule, conn=Depends(get_conn)):
    """Heure (du serveur) du scan quotidien ; null : scan manuel seulement."""
    conn.execute("UPDATE scan_state SET daily_at=? WHERE id=1", (body.hour,))
    conn.commit()


@router.post("/classify", status_code=204)
def classify(conn=Depends(get_conn)):
    """Réapplique les règles de classement (genres, groupes, artistes, catégories) à toute la bibliothèque."""
    db.classify(conn)
    conn.commit()


@router.get("/usage")
def usage(days: int = Query(30, ge=0, le=36500), conn=Depends(get_conn)):
    """Usage de l'application par tous les comptes sur les `days` derniers jours (0 : depuis le début) : écoutes par
    jour et par utilisateur, artistes, releases, pistes et genres les plus écoutés."""
    since = time.time() - days * 86400 if days else 0
    src = "plays p JOIN tracks t ON t.id=p.track_id JOIN releases r ON r.id=t.release_id"
    rows = lambda sql, *a: [dict(x) for x in conn.execute(sql, (since, *a))]
    top = lambda col, limit=15: rows(
        f"SELECT {col} AS name, COUNT(*) AS n, COALESCE(SUM(t.duration), 0) AS duration FROM {src} WHERE p.played_at>=?"
        f" AND {col} IS NOT NULL GROUP BY 1 ORDER BY n DESC, 1 COLLATE NOCASE LIMIT {limit}")
    total = conn.execute(f"SELECT COUNT(*) AS plays, COALESCE(SUM(t.duration), 0) AS duration, COUNT(DISTINCT p.user_id) AS active,"
                         f" COUNT(DISTINCT p.track_id) AS distinct_tracks FROM {src} WHERE p.played_at>=?", (since,)).fetchone()
    one = lambda sql: conn.execute(sql).fetchone()[0]
    return {**dict(total),
            "accounts": one("SELECT COUNT(*) FROM users"), "playlists": one("SELECT COUNT(*) FROM playlists"),
            "favorites": one("SELECT COUNT(*) FROM favorites"),
            "days": rows("SELECT strftime('%Y-%m-%d', p.played_at, 'unixepoch', 'localtime') AS name, COUNT(*) AS n,"
                         f" COALESCE(SUM(t.duration), 0) AS duration FROM {src} WHERE p.played_at>=? GROUP BY 1 ORDER BY 1 DESC LIMIT 31"),
            "users": rows("SELECT u.username AS name, COUNT(*) AS n, COALESCE(SUM(t.duration), 0) AS duration FROM plays p"
                          " JOIN users u ON u.id=p.user_id JOIN tracks t ON t.id=p.track_id WHERE p.played_at>=?"
                          " GROUP BY u.id ORDER BY n DESC, 1"),
            "artists": top("COALESCE(t.artist, r.tag_artist, r.artist)"), "releases": top("r.name"),
            "tracks": top("COALESCE(t.artist || ' - ', '') || COALESCE(t.title, t.relpath)"),
            "genres": top("COALESCE(t.genre, r.genre)")}


@router.get("/activity")
def activity(plays: int = Query(1, ge=0, le=1), offset: int = Query(0, ge=0, le=MAX_INT), limit: int = Query(100, ge=1, le=500),
             conn=Depends(get_conn)):
    """Journal d'activité, le plus récent d'abord : connexions, actions d'administration, sauvegardes et, avec
    `plays`, les écoutes de tous les comptes."""
    sql = "SELECT at, user, action, detail FROM activity"
    if plays:
        sql += (" UNION ALL SELECT p.played_at, u.username, 'Écoute', COALESCE(t.artist || ' - ', '') || COALESCE(t.title, t.relpath)"
                " FROM plays p JOIN users u ON u.id=p.user_id JOIN tracks t ON t.id=p.track_id")
    rows = conn.execute(sql + " ORDER BY 1 DESC LIMIT ? OFFSET ?", (limit + 1, offset)).fetchall()
    return {"items": [dict(zip(("at", "user", "action", "detail"), r)) for r in rows[:limit]], "has_more": len(rows) > limit}


@router.get("/backup")
def backup_status(request: Request, conn=Depends(get_conn)):
    """État de la sauvegarde : configurée ou non, dernière tentative, retard."""
    return backup.status(conn, request.app.state.settings)


@router.post("/backup")
def backup_now(request: Request):
    """Lance une sauvegarde tout de suite et attend sa fin (quelques secondes pour une centaine de Mo)."""
    if request.app.state.settings.backup_dir is None:
        raise HTTPException(400, "Sauvegarde non configurée : renseignez BACKUP_DIR et montez le dossier.")
    result = backup.run(request.app.state.settings)
    if not result["ok"]:
        raise HTTPException(409 if "en cours" in result["message"] else 500, result["message"])
    return result


@router.get("/overrides")
def overrides(conn=Depends(get_conn)):
    """Corrections manuelles en vigueur, avec la release concernée."""
    return [dict(r) for r in conn.execute(
        "SELECT r.id, r.name, o.artist, o.category, o.genre, o.year, o.hidden FROM overrides o JOIN releases r ON r.path=o.path"
        " ORDER BY r.name COLLATE NOCASE")]


@router.get("/overview")
def overview(request: Request, conn=Depends(get_conn)):
    """Chiffres de la page Administration que les autres routes ne donnent pas."""
    one = lambda sql, *args: conn.execute(sql, args).fetchone()[0]
    data = request.app.state.settings.data_dir
    size = lambda paths: sum(p.stat().st_size for p in paths if p.is_file())
    now = time.time()
    return {"artists": one("SELECT COUNT(DISTINCT COALESCE(tag_artist, artist)) FROM releases"),
            "groups": one("SELECT COUNT(DISTINCT grp) FROM releases"), "genres": one("SELECT COUNT(DISTINCT genre) FROM releases"),
            "categories": one("SELECT COUNT(DISTINCT category) FROM releases"),
            "overrides": dict(conn.execute("SELECT COUNT(*) AS total, COUNT(artist) AS artist, COUNT(category) AS category,"
                                           " COUNT(genre) AS genre, COUNT(year) AS year, COUNT(hidden) AS hidden FROM overrides").fetchone()),
            "shares": one("SELECT COUNT(*) FROM shares WHERE expires_at>?", now),
            "share_opens": one("SELECT COALESCE(SUM(opens), 0) FROM shares WHERE expires_at>?", now),
            "users": one("SELECT COUNT(*) FROM users"),
            "db_size": size(data.glob("mp3scene.db*")),
            # ponytail: parcourt data/thumbs/ à chaque appel (une entrée par release, ~0,1 s pour 45 000)
            "thumbs_size": size((data / "thumbs").glob("*")) if (data / "thumbs").is_dir() else 0,
            "transcode_size": size((data / "transcode").glob("*")) if (data / "transcode").is_dir() else 0}


@router.delete("/transcode", status_code=204)
def clear_transcode(request: Request):
    """Vide le cache des pistes converties pour la lecture (data/transcode) ; une piste relue est reconvertie."""
    for p in (request.app.state.settings.data_dir / "transcode").glob("*"):
        if p.is_file():
            p.unlink(missing_ok=True)


_LABEL_WORDS = re.compile(r"(?<=...)(?:productions?|recordings?|records?|recs?|music|digital|limited|ltd|inc)$")


class SeriesRule(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    family: str = Field(default="", max_length=200)


@router.get("/series/rules")
def series_rules(conn=Depends(get_conn)):
    """Familles de séries réglées à la main : série (ou famille) -> famille ; vide : jamais regroupée."""
    return [dict(r) for r in conn.execute("SELECT name, family FROM series_rules ORDER BY name COLLATE NOCASE")]


@router.put("/series/rules", status_code=204)
def set_series_rule(body: SeriesRule, conn=Depends(get_conn)):
    """Rattache une série à une famille, ou (famille vide) la garde à part ; au nom d'une famille, vide la défait.
    Un nom rattaché à lui-même (« Kontor » -> « Kontor ») réunit toutes les séries qui commencent par ce nom."""
    name, family = body.name.strip(), body.family.strip()
    if not name:
        raise HTTPException(400, "Nom de série manquant.")
    conn.execute("INSERT OR REPLACE INTO series_rules(key, name, family) VALUES (?,?,?)", (name.casefold(), name, family))
    conn.commit()


@router.delete("/series/rules", status_code=204)
def drop_series_rule(name: str = Query(max_length=200), conn=Depends(get_conn)):
    if conn.execute("DELETE FROM series_rules WHERE key=?", (name.strip().casefold(),)).rowcount == 0:
        raise HTTPException(404, "Règle introuvable.")
    conn.commit()


class PhotoPick(BaseModel):
    kind: Literal["artist", "label"] = "artist"
    name: str = Field(min_length=1, max_length=200)
    url: str = Field(max_length=2000)
    sig: str = Field(max_length=64)


@router.get("/photo/search")
def search_photo(request: Request, kind: Literal["artist", "label"], name: str = Query(min_length=1, max_length=200)):
    """Photos proposées pour un artiste (Deezer) ou un label (Discogs). Chaque adresse est signée : seule une image
    proposée ici peut être validée."""
    settings = request.app.state.settings
    return {"items": [{**x, "sig": coversearch.sign(settings.secret_key, x["url"])} for x in photo_candidates(settings, kind, name)]}


@router.post("/photo", status_code=204)
def save_photo(body: PhotoPick, request: Request):
    """Télécharge la photo choisie et la garde dans les données de l'application."""
    settings = request.app.state.settings
    if not coversearch.check(settings.secret_key, body.url, body.sig):
        raise HTTPException(400, "Cette image n'a pas été proposée par la recherche.")
    try:
        store_photo(settings.data_dir, body.kind, body.name, body.url)
    except IMAGE_ERRORS as e:
        raise HTTPException(400, f"Photo refusée : {e}") from None


@router.delete("/photo", status_code=204)
def drop_photo(request: Request, kind: Literal["artist", "label"], name: str = Query(min_length=1, max_length=200)):
    """Retire la photo ; un fichier vide empêche la recherche automatique de la remettre."""
    path = photo_path(request.app.state.settings.data_dir, kind, name)
    path.parent.mkdir(exist_ok=True)
    path.write_bytes(b"")


@router.get("/suggestions")
def suggestions(conn=Depends(get_conn)):
    """Rapprochements proposés : labels et artistes qui ne diffèrent que par « & » / « and », un mot final de label
    (« Productions », « Digital »…) ou un « The » / « DJ » initial. Le plus fourni reçoit les autres ; rien n'est
    rattaché sans un clic (PUT …/aliases)."""
    def pairs(sql, key, skip=frozenset()):
        groups = {}
        for name, n in conn.execute(sql):
            if artists.norm(name) not in skip and (k := key(name)):
                groups.setdefault(k, []).append((n, name))
        out = []
        for names in groups.values():
            if len(names) > 1:
                (tn, target), *rest = sorted(names, key=lambda x: (-x[0], x[1]))
                out += [{"alias": a, "releases": n, "target": target, "target_releases": tn} for n, a in rest]
        return sorted(out, key=lambda x: (-x["target_releases"], x["target"].casefold(), x["alias"].casefold()))[:100]
    keep = frozenset(artists.norm(n) for (n,) in conn.execute("SELECT name FROM artist_separate"))
    return {
        "labels": pairs("SELECT label, COUNT(*) FROM releases WHERE NULLIF(label, '') IS NOT NULL GROUP BY 1",
                        lambda v: _LABEL_WORDS.sub("", artists.fold(v))),
        "artists": pairs("SELECT COALESCE(tag_artist, artist), COUNT(*) FROM releases WHERE COALESCE(tag_artist, artist) IS NOT NULL"
                         " GROUP BY 1", lambda v: artists.fold(re.sub(r"^(?:the|dj)[\s_.]+", "", v.strip(), flags=re.I)), keep)}


@router.get("/scan")
def scan_status(request: Request, conn=Depends(get_conn)):
    return request.app.state.runner.status(conn)


@router.get("/library/extras")
def library_extras(request: Request, conn=Depends(get_conn)):
    """Statistiques des enrichissements : BPM et tonalité, chapitres, titres à plusieurs versions, séries et familles,
    photos et logos, rattachements manuels. À part de /library : le regroupement des titres prend près d'une seconde."""
    one = lambda sql: conn.execute(sql).fetchone()[0]
    data = request.app.state.settings.data_dir
    photos = lambda kind: sum(1 for p in (data / kind).glob("*.jpg") if p.stat().st_size) if (data / kind).is_dir() else 0
    every = _all_series(conn)
    fam = _families(every, dict(conn.execute("SELECT key, family FROM series_rules").fetchall()))
    sizes = {}
    for g in every:
        f = fam.get(g["name"].casefold(), g["name"])
        sizes[f] = sizes.get(f, 0) + g["releases"]
    top_titles = titles(genre=None, year=None, decade=None, category=None, song=None, conn=conn)
    return {
        "tracks": one("SELECT COUNT(*) FROM tracks"), "bpm": one("SELECT COUNT(bpm) FROM tracks"), "key": one("SELECT COUNT(key) FROM tracks"),
        "chaptered": one("SELECT COUNT(DISTINCT t.release_id) FROM chapters c JOIN tracks t ON t.id=c.track_id"),
        "chapters": one("SELECT COUNT(*) FROM chapters"),
        "titles": len(top_titles), "versions": sum(t["releases"] for t in top_titles),
        "series": len(every), "families": len(set(fam.values())),
        "artist_photos": photos("artists"), "label_logos": photos("labels"),
        "artist_aliases": one("SELECT COUNT(*) FROM artist_aliases"), "label_aliases": one("SELECT COUNT(*) FROM label_aliases"),
        "title_aliases": one("SELECT COUNT(*) FROM title_aliases"),
        "top_titles": [{"name": t["name"], "n": t["releases"], "size": t["size"]} for t in top_titles[:15]],
        "top_series": [{"name": k, "n": v} for k, v in sorted(sizes.items(), key=lambda kv: -kv[1])[:15]],
        # tempo des pistes qui en ont un, par tranche de 10 BPM
        "bpm_ranges": [dict(r) for r in conn.execute(
            "SELECT CAST(bpm / 10 AS INTEGER) * 10 AS name, COUNT(*) AS n FROM tracks WHERE bpm IS NOT NULL GROUP BY 1 ORDER BY 1")]}


@router.get("/library")
def library_stats(conn=Depends(get_conn)):
    """Tableau de bord : totaux et répartitions de la bibliothèque."""
    def rows(sql):
        return [dict(r) for r in conn.execute(sql)]

    def by(col, order="n DESC", limit=15):
        return rows(f"SELECT {col} AS name, COUNT(*) AS n, SUM(size) AS size FROM releases WHERE {col} IS NOT NULL"
                    f" GROUP BY 1 ORDER BY {order} LIMIT {limit}")

    total = dict(conn.execute("SELECT COUNT(*) AS releases, COALESCE(SUM(size), 0) AS size, COALESCE(SUM(track_count), 0)"
                              " AS tracks, COALESCE(SUM(duration), 0) AS duration FROM releases").fetchone())
    return {**total, "years": by("year", "1 DESC", 40), "genres": by("genre"), "sources": by("source"),
            "groups": by("grp"),
            "categories": by("category"),
            "bitrates": rows("SELECT CASE WHEN bitrate>=320000 THEN '320' WHEN bitrate>=256000 THEN '256' WHEN bitrate>=192000"
                             " THEN '192' WHEN bitrate>=128000 THEN '128' ELSE '<128' END AS name, COUNT(*) AS n,"
                             " SUM(size) AS size FROM tracks WHERE bitrate IS NOT NULL GROUP BY 1 ORDER BY MIN(bitrate) DESC"),
            # extension du fichier : ce qui suit le dernier point du chemin
            "formats": rows("SELECT lower(replace(relpath, rtrim(relpath, replace(relpath, '.', '')), '')) AS name,"
                            " COUNT(*) AS n, SUM(size) AS size FROM tracks GROUP BY 1 ORDER BY n DESC"),
            "months": rows("SELECT strftime('%Y-%m', added_at, 'unixepoch') AS name, COUNT(*) AS n, SUM(size) AS size"
                           " FROM releases GROUP BY 1 ORDER BY 1 DESC LIMIT 24")}


class Correction(BaseModel):
    artist: str | None = Field(default=None, max_length=200)
    category: str | None = Field(default=None, max_length=200)
    genre: str | None = Field(default=None, max_length=200)
    year: int | None = Field(default=None, ge=1900, le=2100)
    hidden: bool | None = None  # doublon masqué des listes


def _correct(conn, rids, fields):
    """Enregistre la correction `fields` (colonne -> valeur, None : retour à l'automatique) pour les releases `rids`."""
    found = [r for rid in rids for r in conn.execute("SELECT path, name FROM releases WHERE id=?", (rid,))]
    paths = [r["path"] for r in found]
    if len(paths) != len(rids):
        raise HTTPException(404, "Release introuvable.")
    if fields.get("category") and conn.execute("SELECT 1 FROM releases WHERE category=? LIMIT 1",
                                               (fields["category"],)).fetchone() is None:
        raise HTTPException(400, "Catégorie inconnue.")
    if "hidden" in fields:
        fields["hidden"] = 1 if fields["hidden"] else None
    if fields.get("genre"):
        fields["genre"] = genres.normalize(fields["genre"]) or fields["genre"]
    for path in paths:
        conn.execute("INSERT OR IGNORE INTO overrides(path) VALUES (?)", (path,))
        for col, val in fields.items():  # noms de colonnes issus du modèle, jamais du client
            conn.execute(f"UPDATE overrides SET {col}=? WHERE path=?", (val, path))
    conn.execute("DELETE FROM overrides WHERE artist IS NULL AND category IS NULL AND genre IS NULL AND year IS NULL"
                 " AND hidden IS NULL AND cover IS NULL")
    if "year" in fields and fields["year"] is None:  # retour à l'automatique : année du nom, sinon celle du NFO
        conn.executemany("UPDATE releases SET year=? WHERE id=?",
                         [(parse_release_name(r["name"])["year"], rid) for r, rid in zip(found, rids)])
        db.year_from_nfo(conn)
    # valeurs automatiques recalculées, puis corrections réappliquées (un artiste rendu à l'automatique n'est regroupé
    # avec les autres graphies qu'au prochain scan ou démarrage)
    scanner._aggregate(conn, rids)
    db.categorize(conn)
    conn.commit()


@router.patch("/releases/{rid}", status_code=204)
def correct_release(rid: Id, body: Correction, conn=Depends(get_conn)):
    """Corrige l'artiste, la catégorie, le genre ou l'année d'une release. Champ absent : inchangé ; vide : retour à la valeur
    automatique. La correction est gardée par chemin et réappliquée après chaque scan."""
    _correct(conn, [rid], {k: (v.strip() or None) if isinstance(v, str) else v
                           for k, v in body.model_dump(exclude_unset=True).items()})


class BulkCorrection(Correction):
    ids: list[Id] = Field(min_length=1, max_length=100_000)


@router.patch("/releases", status_code=204)
def correct_releases(body: BulkCorrection, conn=Depends(get_conn)):
    """Même correction pour plusieurs releases ; seuls les champs remplis sont modifiés."""
    fields = {k: v for k, raw in body.model_dump(exclude={"ids"}).items()
              if (v := raw.strip() if isinstance(raw, str) else raw)}
    if not fields:
        raise HTTPException(400, "Aucun champ à corriger.")
    _correct(conn, list(dict.fromkeys(body.ids)), fields)


def _release_path(conn, rid):
    row = conn.execute("SELECT path FROM releases WHERE id=?", (rid,)).fetchone()
    if row is None:
        raise HTTPException(404, "Release introuvable.")
    return row["path"]


@router.put("/releases/{rid}/cover", status_code=204)
async def upload_cover(rid: Id, request: Request):
    """Dépose une pochette pour cette release (corps de la requête : l'image, JPEG ou PNG). Elle est gardée dans les
    données de l'application, jamais dans le dossier de musique, et passe avant celle du dossier."""
    if int(request.headers.get("content-length") or 0) > COVER_MAX:
        raise HTTPException(413, "Image trop lourde (8 Mo au plus).")
    data = await request.body()
    if not data or len(data) > COVER_MAX:
        raise HTTPException(413 if data else 400, "Image trop lourde (8 Mo au plus)." if data else "Image manquante.")
    settings = request.app.state.settings
    conn = db.connect(settings.data_dir)
    try:
        path = _release_path(conn, rid)
        try:
            save_cover(settings.data_dir, path, rid, data)
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(400, "Ce fichier n'est pas une image lisible (JPEG ou PNG).") from None
        conn.execute("INSERT OR IGNORE INTO overrides(path) VALUES (?)", (path,))
        conn.execute("UPDATE overrides SET cover=1 WHERE path=?", (path,))
        conn.commit()
    finally:
        conn.close()


@router.get("/releases/{rid}/cover/search")
def search_cover(rid: Id, request: Request, conn=Depends(get_conn)):
    """Pochettes proposées pour cette release, trouvées sur Deezer, iTunes et, avec un jeton, Discogs. Chaque adresse est signée : seule une image proposée ici peut ensuite être validée."""
    r = conn.execute("SELECT COALESCE(tag_artist, artist) AS artist, title, name FROM releases WHERE id=?", (rid,)).fetchone()
    if r is None:
        raise HTTPException(404, "Release introuvable.")
    settings = request.app.state.settings
    items = coversearch.candidates(r["artist"], r["title"], settings.discogs_token, r["name"])
    return {"web": bool(settings.discogs_token),
            # exact : la proposition porte le même artiste et le même titre (pochettes automatiques)
            "items": [{**x, "sig": coversearch.sign(settings.secret_key, x["url"]),
                       "exact": coversearch.exact(r["artist"], r["title"], x["title"])} for x in items]}


class CoverPick(BaseModel):
    url: str = Field(max_length=2000)
    sig: str = Field(max_length=64)


@router.post("/releases/{rid}/cover/fetch", status_code=204)
def fetch_cover(rid: Id, body: CoverPick, request: Request, conn=Depends(get_conn)):
    """Valide une pochette proposée : le serveur la télécharge et la garde comme une pochette déposée à la main."""
    settings = request.app.state.settings
    if not coversearch.check(settings.secret_key, body.url, body.sig):
        raise HTTPException(400, "Cette image n'a pas été proposée par la recherche.")
    path = _release_path(conn, rid)
    try:
        save_cover(settings.data_dir, path, rid, coversearch.fetch(body.url))
    except Exception:
        raise HTTPException(502, "Image inaccessible ou illisible : essayez-en une autre.") from None
    conn.execute("INSERT OR IGNORE INTO overrides(path) VALUES (?)", (path,))
    conn.execute("UPDATE overrides SET cover=1 WHERE path=?", (path,))
    conn.commit()


@router.delete("/releases/{rid}/cover", status_code=204)
def remove_cover(rid: Id, request: Request, conn=Depends(get_conn)):
    """Retire la pochette déposée à la main ; celle du dossier ou des tags, s'il y en a une, revient."""
    path = _release_path(conn, rid)
    save_cover(request.app.state.settings.data_dir, path, rid, None)
    conn.execute("UPDATE overrides SET cover=NULL WHERE path=?", (path,))
    conn.execute("DELETE FROM overrides WHERE artist IS NULL AND category IS NULL AND genre IS NULL AND year IS NULL"
                 " AND hidden IS NULL AND cover IS NULL")
    conn.commit()


def _versions(conn, rid):
    """Identifiants des autres versions de la release : même artiste et même titre dans le nom."""
    return [r[0] for r in conn.execute(
        "SELECT r.id FROM releases r JOIN releases o ON o.id=? AND r.id!=o.id AND lower(r.artist)=lower(o.artist)"
        " AND lower(r.title)=lower(o.title)", (rid,))]


@router.put("/releases/{rid}/keep", status_code=204)
def keep_version(rid: Id, conn=Depends(get_conn)):
    """Garde cette version d'un doublon : les autres sont masquées des listes (rien n'est supprimé du disque)."""
    _correct(conn, [rid], {"hidden": None})
    _correct(conn, _versions(conn, rid), {"hidden": True})


@router.delete("/releases/{rid}/keep", status_code=204)
def show_versions(rid: Id, conn=Depends(get_conn)):
    """Réaffiche toutes les versions de cette release."""
    _correct(conn, [rid, *_versions(conn, rid)], {"hidden": None})


class Alias(BaseModel):
    alias: str = Field(min_length=1, max_length=200)
    target: str = Field(min_length=1, max_length=200)


@router.get("/artists/aliases")
def artist_aliases(conn=Depends(get_conn)):
    """Artistes rattachés à la main."""
    return [dict(r) for r in conn.execute("SELECT alias, target FROM artist_aliases ORDER BY alias COLLATE NOCASE")]


@router.put("/artists/aliases", status_code=204)
def attach_artist(body: Alias, conn=Depends(get_conn)):
    """Rattache un artiste à un autre ; la règle est gardée et réappliquée à chaque regroupement."""
    alias, target = body.alias.strip(), body.target.strip()
    if not target or artists.fold(alias) == artists.fold(target):
        raise HTTPException(400, "Choisissez un autre artiste que lui-même.")
    conn.execute("INSERT OR REPLACE INTO artist_aliases(key, alias, target) VALUES (?,?,?)", (artists.fold(alias), alias, target))
    artists.apply(conn)
    db.categorize(conn)  # réapplique les corrections manuelles
    conn.commit()


@router.delete("/artists/aliases", status_code=204)
def detach_artist(alias: str = Query(max_length=200), conn=Depends(get_conn)):
    """Retire un rattachement : les releases de la cible retrouvent l'artiste de leur nom et de leurs tags, puis
    sont regroupées à nouveau."""
    row = conn.execute("SELECT target FROM artist_aliases WHERE key=?", (artists.fold(alias),)).fetchone()
    if row is None:
        raise HTTPException(404, "Rattachement introuvable.")
    conn.execute("DELETE FROM artist_aliases WHERE key=?", (artists.fold(alias),))
    shown = conn.execute("SELECT COALESCE(tag_artist, artist) FROM releases WHERE COALESCE(tag_artist, artist)=? COLLATE NOCASE"
                         " LIMIT 1", (row["target"],)).fetchone()
    if shown:
        artists.reset(conn, shown[0])
    artists.apply(conn)
    db.categorize(conn)
    conn.commit()


def _title_key(t: str) -> str:
    """Clé d'un titre, comme dans l'onglet Titres : minuscules, sans la version entre parenthèses ou après un tiret."""
    t = t.lstrip("_.-*~#>| ").replace("_", " ").strip(" '\"")
    return re.split(r"\s*[(\[]|\s+-\s+", t.strip(), maxsplit=1)[0].strip().lower()


@router.get("/titles/aliases")
def title_aliases(conn=Depends(get_conn)):
    """Titres fusionnés à la main."""
    return [dict(r) for r in conn.execute("SELECT alias, target FROM title_aliases ORDER BY alias COLLATE NOCASE")]


@router.put("/titles/aliases", status_code=204)
def attach_title(body: Alias, conn=Depends(get_conn)):
    """Réunit un titre à un autre (« Show Me Love 2009 » à « Show Me Love ») dans l'onglet Titres."""
    alias, target = body.alias.strip(), body.target.strip()
    if not target or _title_key(alias) == _title_key(target):
        raise HTTPException(400, "Ces deux titres sont déjà réunis.")
    conn.execute("INSERT OR REPLACE INTO title_aliases(key, alias, target) VALUES (?,?,?)", (_title_key(alias), alias, target))
    conn.commit()


@router.delete("/titles/aliases", status_code=204)
def detach_title(alias: str = Query(max_length=300), conn=Depends(get_conn)):
    if conn.execute("DELETE FROM title_aliases WHERE key=?", (_title_key(alias),)).rowcount == 0:
        raise HTTPException(404, "Rattachement introuvable.")
    conn.commit()


@router.get("/labels/aliases")
def label_aliases(conn=Depends(get_conn)):
    """Labels rattachés à la main."""
    return [dict(r) for r in conn.execute("SELECT alias, target FROM label_aliases ORDER BY alias COLLATE NOCASE")]


@router.put("/labels/aliases", status_code=204)
def attach_label(body: Alias, conn=Depends(get_conn)):
    """Rattache un label à un autre (« ZYX Germany » à « ZYX ») ; la règle est gardée et réappliquée à chaque scan."""
    alias, target = body.alias.strip(), body.target.strip()
    if not target or nfo.label_key(alias) == nfo.label_key(target):
        raise HTTPException(400, "Ces deux noms sont déjà réunis.")
    conn.execute("INSERT OR REPLACE INTO label_aliases(key, alias, target) VALUES (?,?,?)", (nfo.label_key(alias), alias, target))
    db.merge_labels(conn)
    conn.commit()


@router.delete("/labels/aliases", status_code=204)
def detach_label(alias: str = Query(max_length=200), conn=Depends(get_conn)):
    """Retire un rattachement. Le label d'origine n'est plus en base : les releases du label cible sont marquées à
    relire, et retrouvent le leur au prochain scan."""
    row = conn.execute("SELECT target FROM label_aliases WHERE key=?", (nfo.label_key(alias),)).fetchone()
    if row is None:
        raise HTTPException(404, "Rattachement introuvable.")
    conn.execute("DELETE FROM label_aliases WHERE key=?", (nfo.label_key(alias),))
    conn.execute("UPDATE releases SET label=NULL WHERE has_nfo=1 AND label=? COLLATE NOCASE", (row["target"],))
    conn.commit()


def _regroup(conn, name):
    """Défait puis refait le regroupement des artistes de même clé que `name` (règle de séparation ajoutée ou retirée)."""
    k = artists.fold(name)
    for (shown,) in conn.execute("SELECT DISTINCT COALESCE(tag_artist, artist) FROM releases"
                                 " WHERE COALESCE(tag_artist, artist) IS NOT NULL").fetchall():
        if artists.fold(shown) == k:
            artists.reset(conn, shown)
    artists.apply(conn)
    db.categorize(conn)
    conn.commit()


class Separate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


@router.get("/artists/separate")
def separate_list(conn=Depends(get_conn)):
    """Graphies d'artistes à ne jamais fusionner avec une autre."""
    return [r[0] for r in conn.execute("SELECT name FROM artist_separate ORDER BY name COLLATE NOCASE")]


@router.put("/artists/separate", status_code=204)
def separate_artist(body: Separate, conn=Depends(get_conn)):
    """« Florida » n'est pas « Flo Rida » : cette graphie garde ses releases, à ce scan et aux suivants."""
    name = " ".join(body.name.replace("_", " ").split())
    if not name:
        raise HTTPException(400, "Nom vide.")
    conn.execute("INSERT OR IGNORE INTO artist_separate(name) VALUES (?)", (name,))
    _regroup(conn, name)


@router.delete("/artists/separate", status_code=204)
def merge_artist(name: str = Query(max_length=200), conn=Depends(get_conn)):
    if conn.execute("DELETE FROM artist_separate WHERE name=?", (name,)).rowcount == 0:
        raise HTTPException(404, "Règle introuvable.")
    _regroup(conn, name)


# contrôles qualité : condition SQL sur la release r (jamais de texte du client dans le SQL)
QUALITY = {
    "no_nfo": "r.has_nfo=0",
    "no_tracks": "r.track_count=0",
    "no_tags": "r.tags_done=1 AND r.track_count>0 AND NOT EXISTS (SELECT 1 FROM tracks WHERE release_id=r.id AND title IS NOT NULL)",
    # sous-requête non corrélée : une seule passe sur les pistes. En EXISTS corrélé, SQLite prenait l'index de
    # tags_read (toutes les pistes) pour chaque release, soit plusieurs minutes sur 340 000 pistes
    "unreadable": "r.id IN (SELECT release_id FROM tracks WHERE tags_read=1 AND duration IS NULL)",
    "low_bitrate": "(SELECT AVG(bitrate) FROM tracks WHERE release_id=r.id)<192000",
    "no_year": "r.year IS NULL",
    "no_genre": "r.genre IS NULL AND r.track_count>0",
    # NULL : pas encore vérifié par le scan ; une pochette déposée à la main compte
    "no_cover": "r.has_cover=0 AND r.path NOT IN (SELECT path FROM overrides WHERE cover=1)",
    "no_artist": "COALESCE(r.tag_artist, r.artist) IS NULL",
    # même artiste et même titre dans le nom qu'une autre release (index idx_releases_dupe)
    # ; un doublon est réglé dès qu'une version est gardée et les autres masquées
    "dupes": "r.hidden=0 AND EXISTS (SELECT 1 FROM releases d WHERE lower(d.artist)=lower(r.artist) AND lower(d.title)=lower(r.title)"
             " AND d.id!=r.id AND d.hidden=0)",
}


def _genre_guesses(conn) -> dict:
    """{identifiant: genre proposé} pour les releases sans genre : le genre le plus fréquent de leur artiste (hors
    compilations), à défaut de leur label, s'il couvre au moins la moitié de ses releases classées et deux d'entre elles."""
    def majority(col, skip=()):
        seen = {}
        for who, genre, n in conn.execute(f"SELECT {col}, genre, COUNT(*) FROM releases r WHERE genre IS NOT NULL AND {col} IS NOT NULL"
                                          " GROUP BY 1, 2"):
            seen.setdefault(who, {})[genre] = n
        return {who: max(g, key=g.get) for who, g in seen.items()
                if who.lower() not in skip and max(g.values()) >= 2 and 2 * max(g.values()) >= sum(g.values())}
    artist, label = majority("COALESCE(r.tag_artist, r.artist)", ("va", "various", "various artists")), majority("NULLIF(r.label, '')")
    out = {}
    for r in conn.execute("SELECT r.id, COALESCE(r.tag_artist, r.artist) AS artist, NULLIF(r.label, '') AS label FROM releases r WHERE "
                          + QUALITY["no_genre"]):
        if g := artist.get(r["artist"]) or label.get(r["label"]):
            out[r["id"]] = g
    return out


@router.get("/genres/guess")
def guess_genres(conn=Depends(get_conn)):
    """Genres proposés pour les releases sans genre : combien en recevraient un, et quelques exemples."""
    found = _genre_guesses(conn)
    names = dict(conn.execute(f"SELECT id, name FROM releases WHERE id IN ({','.join('?' * min(len(found), 8))})", list(found)[:8]).fetchall()) if found else {}
    return {"count": len(found), "sample": [{"name": names[i], "genre": found[i]} for i in names]}


@router.post("/genres/guess", status_code=204)
def apply_genres(conn=Depends(get_conn)):
    """Applique les genres proposés, comme autant de corrections manuelles (gardées après les scans, modifiables)."""
    by_genre = {}
    for rid, g in _genre_guesses(conn).items():
        by_genre.setdefault(g, []).append(rid)
    for g, rids in by_genre.items():
        _correct(conn, rids, {"genre": g})


@router.get("/quality")
def quality(kind: Literal["no_nfo", "no_tracks", "no_tags", "unreadable", "low_bitrate", "no_year", "no_genre", "no_cover", "no_artist", "dupes"] | None = None,
            sort: Sort | None = None, dir: Dir = "asc", offset: int = Query(0, ge=0, le=MAX_INT),
            limit: int = Query(50, ge=1, le=MAX_INT), ids: int = Query(0, ge=0, le=1),
            user=Depends(require_admin), conn=Depends(get_conn)):
    """Sans `kind` : nombre de releases par contrôle. Avec : la page de releases concernées, ou tous leurs
    identifiants (`ids=1`, pour « Tout cocher »)."""
    if kind is None:
        return {k: conn.execute(f"SELECT COUNT(*) FROM releases r WHERE {cond}").fetchone()[0] for k, cond in QUALITY.items()}
    if ids:
        return {"ids": [r[0] for r in conn.execute(f"SELECT r.id FROM releases r WHERE {QUALITY[kind]}")]}
    return _page(conn, RELEASE_COLS, RELEASE_FROM, "WHERE " + QUALITY[kind], [],
                 _order(sort, dir, "r.name COLLATE NOCASE, r.id"), user["id"], offset, limit, _release)
