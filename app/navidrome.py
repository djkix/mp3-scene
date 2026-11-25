"""Onglet Navidrome : le catalogue d'un serveur Navidrome (API Subsonic) parcouru et écouté depuis Mp3 Scene.

Le serveur Mp3 Scene sert d'intermédiaire : l'adresse et le compte Navidrome restent dans ses variables
d'environnement (NAVIDROME_URL, NAVIDROME_USER, NAVIDROME_PASSWORD) et ne parviennent jamais au navigateur, qui
ne parle qu'à Mp3 Scene. Les pistes ont pour identifiant « nd:<identifiant Subsonic> » côté lecteur.
"""
import hashlib
import json
import re
import secrets
import time
from concurrent.futures import ThreadPoolExecutor
import urllib.error
import urllib.parse
import urllib.request
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import StreamingResponse

from .deps import current_user
from .security import check_track_sig

router = APIRouter(prefix="/api/navidrome", dependencies=[Depends(current_user)])
cast_router = APIRouter()  # /cast/nd/… : sans session, URL signée (Chromecast)

ND_ID = r"^[A-Za-z0-9_.-]{1,80}$"  # identifiants Subsonic (Navidrome : 22 caractères alphanumériques)
TIMEOUT = 15
CHUNK = 256 * 1024
# formats que les navigateurs et le Chromecast lisent tels quels ; le reste est converti en MP3 par Navidrome
NATIVE = {"mp3", "m4a", "aac", "mp4", "flac", "ogg", "oga", "opus", "wav"}


def _settings(request: Request):
    s = request.app.state.settings
    if not s.navidrome_url:
        raise HTTPException(404, "Navidrome n'est pas configuré.")
    return s


def _query(s, **params) -> str:
    """Paramètres d'authentification Subsonic (jeton : md5 du mot de passe et d'un sel neuf) et ceux de l'appel."""
    salt = secrets.token_hex(8)
    token = hashlib.md5((s.navidrome_password + salt).encode()).hexdigest()  # noqa: S324 (imposé par l'API Subsonic)
    return urllib.parse.urlencode({"u": s.navidrome_user, "t": token, "s": salt, "v": "1.16.1", "c": "mp3scene", "f": "json",
                                   **{k: v for k, v in params.items() if v is not None}})


def _url(s, method: str, **params) -> str:
    return f"{s.navidrome_url}/rest/{method}?{_query(s, **params)}"


def call(s, method: str, **params) -> dict:
    """Réponse Subsonic (`subsonic-response`) ; 502 si Navidrome est injoignable ou refuse."""
    try:
        with urllib.request.urlopen(_url(s, method, **params), timeout=TIMEOUT) as r:
            data = json.loads(r.read(8 * 1024 * 1024))["subsonic-response"]
    except (urllib.error.URLError, OSError, ValueError, KeyError) as e:
        raise HTTPException(502, f"Navidrome injoignable ({type(e).__name__}).") from None
    if data.get("status") != "ok":
        raise HTTPException(502, "Navidrome : " + str((data.get("error") or {}).get("message") or "refus"))
    return data


def _song(x: dict) -> dict:
    """Piste Subsonic -> piste du lecteur Mp3 Scene (mêmes champs que les pistes de la bibliothèque, plus `nd`)."""
    return {"id": f"nd:{x['id']}", "nd": x["id"], "title": x.get("title"), "artist": x.get("artist"),
            "release_name": x.get("album") or "", "nd_album": x.get("albumId"), "duration": x.get("duration"),
            "bitrate": (x.get("bitRate") or 0) * 1000 or None, "genre": x.get("genre"), "disc": x.get("discNumber") or 1,
            "track": x.get("track"), "year": x.get("year"), "suffix": (x.get("suffix") or "").lower(),
            "cover": f"/api/navidrome/cover/{urllib.parse.quote(x['coverArt'])}" if x.get("coverArt") else None,
            "filename": x.get("path", "").rsplit("/", 1)[-1] or x.get("title") or ""}


def _album(x: dict) -> dict:
    return {"id": x["id"], "name": x.get("name") or x.get("title"), "artist": x.get("artist"), "artist_id": x.get("artistId"),
            "year": x.get("year"), "songs": x.get("songCount"), "duration": x.get("duration"), "genre": x.get("genre"),
            "cover": f"/api/navidrome/cover/{urllib.parse.quote(x['coverArt'])}" if x.get("coverArt") else None}


@router.get("/status")
def status(request: Request):
    """Navidrome configuré et joignable ? (l'onglet n'est proposé que si `enabled`)."""
    s = request.app.state.settings
    if not s.navidrome_url:
        return {"enabled": False}
    try:
        call(s, "ping")
        return {"enabled": True, "ok": True}
    except HTTPException as e:
        return {"enabled": True, "ok": False, "error": e.detail}


@router.get("/albums")
def albums(request: Request, type: Literal["newest", "recent", "frequent", "random", "alphabeticalByName", "starred"] = "newest",
           offset: int = Query(0, ge=0, le=100000), size: int = Query(60, ge=1, le=500)):
    data = call(_settings(request), "getAlbumList2", type=type, size=size, offset=offset)
    return [_album(a) for a in (data.get("albumList2") or {}).get("album", [])]


def _songs(s, albums: list[dict]) -> list[dict]:
    """Pistes d'une liste d'albums, dans l'ordre des albums. Dans une bibliothèque de morceaux à l'unité, chaque
    « album » n'a qu'une piste : la liste se montre en pistes. Albums lus en parallèle (serveur local, rapide)."""
    # ponytail: un getAlbum par album (60 au plus par page, 8 à la fois) ; Subsonic n'a pas de liste de pistes récentes
    with ThreadPoolExecutor(8) as pool:
        found = list(pool.map(lambda a: (call(s, "getAlbum", id=a["id"]).get("album") or {}).get("song", []), albums))
    return [_song(x) for songs in found for x in songs]


@router.get("/tracks")
def tracks(request: Request, type: Literal["newest", "recent", "frequent", "random", "starred"] = "newest",
           offset: int = Query(0, ge=0, le=100000), size: int = Query(60, ge=1, le=100)):
    """Pistes des derniers ajouts, des dernières écoutées, des plus écoutées ou au hasard (pages de `size` albums)."""
    s = _settings(request)
    if type == "random":
        return [_song(x) for x in (call(s, "getRandomSongs", size=size).get("randomSongs") or {}).get("song", [])]
    albums = (call(s, "getAlbumList2", type=type, size=size, offset=offset).get("albumList2") or {}).get("album", [])
    return _songs(s, albums)


@router.get("/artists")
def artists(request: Request):
    data = call(_settings(request), "getArtists")
    return [{"id": a["id"], "name": a.get("name"), "albums": a.get("albumCount")}
            for i in (data.get("artists") or {}).get("index", []) for a in i.get("artist", [])]


@router.get("/artist/{aid}")
def artist(aid: str, request: Request):
    if not re.match(ND_ID, aid):
        raise HTTPException(404, "Artiste introuvable.")
    s = _settings(request)
    a = call(s, "getArtist", id=aid).get("artist") or {}
    albums = sorted(a.get("album", []), key=lambda x: -(x.get("year") or 0))
    # ponytail: toutes les pistes de l'artiste d'un coup ; paginer si un artiste dépasse quelques centaines d'albums
    return {"id": aid, "name": a.get("name"), "albums": [_album(x) for x in albums], "tracks": _songs(s, albums[:300])}


@router.get("/album/{aid}")
def album(aid: str, request: Request):
    if not re.match(ND_ID, aid):
        raise HTTPException(404, "Album introuvable.")
    a = call(_settings(request), "getAlbum", id=aid).get("album") or {}
    return {**_album({"id": aid, **a}), "tracks": [_song(x) for x in a.get("song", [])]}


@router.get("/search")
def search(request: Request, q: str = Query(min_length=1, max_length=200)):
    r = call(_settings(request), "search3", query=q, artistCount=20, albumCount=40, songCount=60).get("searchResult3") or {}
    return {"artists": [{"id": a["id"], "name": a.get("name"), "albums": a.get("albumCount")} for a in r.get("artist", [])],
            "albums": [_album(a) for a in r.get("album", [])], "tracks": [_song(x) for x in r.get("song", [])]}


def _cover(s, cid: str, size: int | None):
    if not re.match(ND_ID, cid):
        raise HTTPException(404, "Pochette introuvable.")
    try:
        with urllib.request.urlopen(_url(s, "getCoverArt", id=cid, size=size), timeout=TIMEOUT) as r:
            kind = r.headers.get("Content-Type", "image/jpeg")
            data = r.read(10 * 1024 * 1024)
    except (urllib.error.URLError, OSError):
        raise HTTPException(404, "Pochette introuvable.") from None
    if not kind.startswith("image/"):  # erreur Subsonic en JSON : pas d'image
        raise HTTPException(404, "Pochette introuvable.")
    return Response(data, media_type=kind, headers={"Cache-Control": "private, max-age=86400"})


@router.get("/cover/{cid}")
def cover(cid: str, request: Request, size: int | None = Query(None, ge=32, le=1500)):
    return _cover(_settings(request), cid, size)


def _stream(s, request: Request, sid: str, original: bool, headers: dict | None = None):
    """Son d'une piste relayé depuis Navidrome, requêtes Range comprises (déplacement dans la piste)."""
    if not re.match(ND_ID, sid):
        raise HTTPException(404, "Piste introuvable.")
    params = {"id": sid} if original else {"id": sid, "format": "mp3", "maxBitRate": 320}
    req = urllib.request.Request(_url(s, "stream", **params))
    if rng := request.headers.get("range"):
        req.add_header("Range", rng)
    try:
        r = urllib.request.urlopen(req, timeout=TIMEOUT)  # noqa: SIM115 (refermé par le générateur)
    except urllib.error.HTTPError as e:
        raise HTTPException(416 if e.code == 416 else 404, "Piste introuvable.") from None
    except (urllib.error.URLError, OSError):
        raise HTTPException(502, "Navidrome injoignable.") from None
    kind = r.headers.get("Content-Type", "audio/mpeg")
    if kind.startswith(("application/json", "text/")):  # erreur Subsonic (piste inconnue…) renvoyée en 200
        r.close()
        raise HTTPException(404, "Piste introuvable.")
    out = {k: r.headers[k] for k in ("Content-Length", "Content-Range", "Accept-Ranges") if r.headers.get(k)}

    def body():
        with r:
            while chunk := r.read(CHUNK):
                yield chunk
    return StreamingResponse(body(), status_code=r.status, media_type=kind, headers={**out, **(headers or {})})


@router.get("/stream/{sid}")
def stream(sid: str, request: Request, original: bool = False):
    return _stream(_settings(request), request, sid, original)


# --- Chromecast : URL signées, comme pour les pistes de la bibliothèque ------------------------------------------
CAST_CORS = {"Access-Control-Allow-Origin": "*", "Access-Control-Expose-Headers": "Content-Range, Accept-Ranges, Content-Length"}


def _signed(request: Request, sid: str, exp: str, sig: str):
    s = request.app.state.settings
    if not check_track_sig(s.secret_key, f"nd:{sid}", exp, sig, time.time()):
        raise HTTPException(403, "Lien de diffusion invalide ou expiré.")
    if not s.navidrome_url:
        raise HTTPException(404, "Navidrome n'est pas configuré.")
    return s


@cast_router.api_route("/cast/nd/{sid}", methods=["GET", "HEAD"])
def cast_stream(sid: str, request: Request, exp: str = "", sig: str = "", original: bool = False):
    return _stream(_signed(request, sid, exp, sig), request, sid, original, CAST_CORS)


@cast_router.get("/cast/nd/{sid}/cover")
def cast_cover(sid: str, request: Request, exp: str = "", sig: str = ""):
    s = _signed(request, sid, exp, sig)
    song = call(s, "getSong", id=sid).get("song") or {}
    if not song.get("coverArt"):
        raise HTTPException(404, "Pochette introuvable.")
    return _cover(s, song["coverArt"], 600)
