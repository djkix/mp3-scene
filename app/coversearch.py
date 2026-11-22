"""Pochettes proposées pour une release sans image : catalogues Deezer et iTunes (sans clé), et Discogs
si un jeton est fourni (DISCOGS_TOKEN). Le serveur ne télécharge que les adresses qu'il a lui-même proposées."""
import hashlib
import hmac
import ipaddress
import json
import re
import socket
import urllib.error
import urllib.parse
import urllib.request

MAX = 8 * 1024 * 1024
_UA = {"User-Agent": "Mozilla/5.0 (cover search)", "Accept": "*/*"}  # sans nom ni adresse : rien de personnel n'est envoyé


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):  # une redirection pourrait mener à une adresse interne
        return None


_opener = urllib.request.build_opener(_NoRedirect)


def _json(url: str, headers: dict | None = None) -> dict:
    with urllib.request.urlopen(urllib.request.Request(url, headers={**_UA, **(headers or {})}), timeout=6) as r:
        return json.loads(r.read(2 * 1024 * 1024))


def _deezer(q: str) -> list[dict]:
    data = _json("https://api.deezer.com/search/album?" + urllib.parse.urlencode({"q": q, "limit": 4}))
    return [{"url": a["cover_xl"], "thumb": a["cover_medium"], "source": "Deezer",
             "title": f"{(a.get('artist') or {}).get('name', '')} - {a.get('title', '')}"}
            for a in data.get("data", []) if a.get("cover_xl") and a.get("cover_medium")]


def _itunes(q: str) -> list[dict]:
    data = _json("https://itunes.apple.com/search?" + urllib.parse.urlencode({"term": q, "entity": "album", "limit": 4}))
    size = lambda a, n: a["artworkUrl100"].replace("100x100bb", f"{n}x{n}bb")
    return [{"url": size(a, 1000), "thumb": size(a, 300), "source": "iTunes",
             "title": f"{a.get('artistName', '')} - {a.get('collectionName', '')}"}
            for a in data.get("results", []) if a.get("artworkUrl100")]


_SUFFIX = re.compile(r"[-_ ]*\([^)]*\)\s*$|[-_ ](EP|WEB|VLS|CDS|CDM|Promo|Remixes)\b.*$", re.I)
_CATNO = re.compile(r"\(([A-Z0-9][A-Z0-9 ._-]*\d[A-Z0-9 ._-]*)\)")  # « (BL-16188-X) », « (579_737-2) » dans le nom du dossier
_DATE = re.compile(r"\d{1,2}-\d{1,2}-\d{2,4}$")


def _discogs(token: str, **args) -> list[dict]:
    data = _json("https://api.discogs.com/database/search?" + urllib.parse.urlencode({"type": "release", "per_page": 6, **args}),
                 {"Authorization": f"Discogs token={token}"})
    # sans image, Discogs renvoie un pixel « spacer.gif »
    return [{"url": r["cover_image"], "thumb": r["thumb"], "source": "Discogs", "title": r.get("title") or ""}
            for r in data.get("results", []) if r.get("thumb") and "spacer.gif" not in r.get("cover_image", "spacer.gif")]


def _discogs_any(artist: str | None, title: str, name: str | None, token: str) -> list[dict]:
    """Titre exact d'abord ; à défaut le titre sans son suffixe (« … EP », « …-(Remixes) »), puis la référence de
    catalogue lue entre parenthèses dans le nom du dossier."""
    who = {"artist": artist} if artist else {}
    out = _discogs(token, release_title=title, **who)
    short = _SUFFIX.sub("", title).strip()
    if not out and short and short != title:
        out = _discogs(token, release_title=short, **who)
    cat = _CATNO.search(name or "")
    if not out and cat and not _DATE.match(cat[1]):
        out = _discogs(token, catno=cat[1].replace("_", " "))
    return out


def candidates(artist: str | None, title: str | None, discogs_token: str | None, name: str | None = None) -> list[dict]:
    """Images proposées, catalogues d'abord. Une source en panne ou muette est passée sans bruit."""
    va = (artist or "").lower() in ("", "va", "various", "various artists")
    q = " ".join(filter(None, [None if va else artist, title]))
    if not q.strip():
        return []
    # ponytail: sources interrogées l'une après l'autre (une à deux secondes en tout) ; en parallèle si c'est trop long
    out = []
    for search in (lambda: _deezer(q), lambda: _itunes(q),
                   lambda: _discogs_any(None if va else artist, title, name, discogs_token) if discogs_token and title else []):
        try:
            out += search()
        except (OSError, ValueError, KeyError, TypeError):  # réseau, JSON, réponse inattendue
            pass
    return [x for x in out if x["url"].startswith("https://") and x["thumb"].startswith("https://")]


def sign(secret: str, url: str) -> str:
    return hmac.new(secret.encode(), b"cover:" + url.encode(), hashlib.sha256).hexdigest()[:32]


def check(secret: str, url: str, sig: str) -> bool:
    return hmac.compare_digest(sign(secret, url), sig or "")


def public_host(host: str) -> bool:
    """Vrai si le nom ne mène qu'à des adresses d'Internet : jamais le serveur lui-même ni le réseau local."""
    try:
        infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    except OSError:
        return False
    return bool(infos) and all(ipaddress.ip_address(i[4][0]).is_global for i in infos)


def fetch(url: str) -> bytes:
    """Télécharge l'image proposée : https seulement, hôte public, sans redirection, 8 Mo au plus. ValueError sinon."""
    parts = urllib.parse.urlsplit(url)
    # ponytail: le nom est résolu ici puis à nouveau par la requête ; l'adresse vient d'une proposition signée par le
    # serveur et seul un administrateur peut la valider — épingler l'adresse IP si cela ne suffit plus
    if parts.scheme != "https" or not parts.hostname or not public_host(parts.hostname):
        raise ValueError("adresse refusée")
    try:
        with _opener.open(urllib.request.Request(url, headers=_UA), timeout=10) as r:
            data = r.read(MAX + 1)
    except (OSError, urllib.error.URLError) as e:
        raise ValueError("image inaccessible") from e
    if not data or len(data) > MAX:
        raise ValueError("image vide ou trop lourde")
    return data
