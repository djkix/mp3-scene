"""Pochettes proposées pour une release sans image : catalogues Deezer et iTunes (sans clé), et Discogs
si un jeton est fourni (DISCOGS_TOKEN). Le serveur ne télécharge que les adresses qu'il a lui-même proposées."""
import http.client
import ssl
import time
import hashlib
import hmac
import ipaddress
import json
import re
import socket
import unicodedata
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


_DISCS = re.compile(r"[-_ ]+\(?\d*x?(?:CD|DVD)\d*\)?\s*$", re.I)


def clean_title(title: str | None) -> str | None:
    """Titre sans le nombre de disques collé à la fin : « Mystery Land 2010-2CD » -> « Mystery Land 2010 »."""
    return _DISCS.sub("", title).strip() or title if title else title


def candidates(artist: str | None, title: str | None, discogs_token: str | None, name: str | None = None) -> list[dict]:
    """Images proposées, catalogues d'abord. Une source en panne ou muette est passée sans bruit."""
    title = clean_title(title)
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


def artist_photos(name: str) -> list[dict]:
    """Photos proposées pour un artiste, d'après le catalogue Deezer ; une panne ou un silence donne une liste vide."""
    try:
        data = _json("https://api.deezer.com/search/artist?" + urllib.parse.urlencode({"q": name, "limit": 6}))
    except (OSError, ValueError):
        return []
    # sans photo, Deezer renvoie une image générique dont l'adresse contient « /artist// »
    return [{"url": a["picture_xl"], "thumb": a["picture_medium"], "source": "Deezer", "title": a.get("name", "")}
            for a in data.get("data", []) if str(a.get("picture_xl", "")).startswith("https://")
            and str(a.get("picture_medium", "")).startswith("https://") and "/artist//" not in a["picture_xl"]]


def event_photos(name: str) -> list[dict]:
    """Pochettes d'albums proposées pour un festival ou une émission (Deezer, iTunes) ; titre = celui de l'album."""
    out = []
    for search in (_deezer, _itunes):
        try:
            out += [{**x, "title": x["title"].split(" - ", 1)[-1]} for x in search(name)]
        except (OSError, ValueError, KeyError, TypeError):
            pass
    out.sort(key=lambda x: not re.search(r"\b(19|20)\d\d\b", x["title"]))  # « Tomorrowland 2019 » avant le film « Tomorrowland »
    return [x for x in out if x["url"].startswith("https://") and x["thumb"].startswith("https://")]


def label_photos(name: str, token: str) -> list[dict]:
    """Logos proposés pour un label, d'après Discogs ; une panne ou un silence donne une liste vide."""
    try:
        data = _json("https://api.discogs.com/database/search?" + urllib.parse.urlencode({"type": "label", "q": name, "per_page": 6}),
                     {"Authorization": f"Discogs token={token}"})
    except (OSError, ValueError):
        return []
    # Discogs : « Nom (2) » pour un homonyme ; sans image, un pixel « spacer.gif »
    return [{"url": r["cover_image"], "thumb": r["thumb"] if str(r.get("thumb", "")).startswith("https://") else r["cover_image"],
             "source": "Discogs",
             "title": re.sub(r"\s*\(\d+\)$", "", r.get("title") or "")}
            for r in data.get("results", []) if str(r.get("cover_image", "")).startswith("https://") and "spacer.gif" not in r["cover_image"]]


DISCOGS_PAGES = 5  # 100 sorties par page : au-delà, la liste est tronquée (Discogs : 60 requêtes par minute)


def label_releases(name: str, token: str, key) -> dict | None:
    """Sorties d'un label sur Discogs : le label au même nom (`key` : clé de rapprochement des labels), puis ses
    sorties, une par artiste et titre (un même disque sort en vinyle, CD et fichier). None si le label est inconnu.
    Lève OSError ou ValueError si Discogs ne répond pas."""
    auth = {"Authorization": f"Discogs token={token}"}
    found = _json("https://api.discogs.com/database/search?" + urllib.parse.urlencode({"type": "label", "q": name, "per_page": 10}), auth)
    hit = next((r for r in found.get("results", []) if key(re.sub(r"\s*\(\d+\)$", "", r.get("title") or "")) == key(name)), None)
    if hit is None:
        return None
    out, seen, pages = [], {}, 1
    for page in range(1, DISCOGS_PAGES + 1):
        data = _json(f"https://api.discogs.com/labels/{int(hit['id'])}/releases?per_page=100&sort=year&sort_order=desc&page={page}", auth)
        pages = (data.get("pagination") or {}).get("pages") or 1
        for r in data.get("releases", []):
            artist = re.sub(r"\s*\(\d+\)$|\*$", "", (r.get("artist") or "").strip())
            k = (_key(artist), _key(r.get("title")))
            cat = r.get("catno") if r.get("catno") and r.get("catno").lower() != "none" else None
            if k in seen:  # autre édition du même disque : ses références servent aussi au rapprochement
                seen[k]["catnos"] += [cat] if cat else []
                continue
            seen[k] = {"id": r.get("id"), "artist": artist, "title": r.get("title") or "", "catnos": [cat] if cat else [],
                       "year": r.get("year") or None, "format": r.get("format") or "",
                       "thumb": r["thumb"] if str(r.get("thumb", "")).startswith("https://") else None,
                       "url": f"https://www.discogs.com/release/{int(r['id'])}" if r.get("id") else None}
            out.append(seen[k])
        if page >= pages:
            break
    uri = hit.get("uri") or ""
    return {"name": re.sub(r"\s*\(\d+\)$", "", hit.get("title") or name),
            "url": "https://www.discogs.com" + uri if uri.startswith("/") else None,
            "releases": out, "truncated": pages > DISCOGS_PAGES}


_VARIOUS = {"va", "various", "variousartists"}


def _key(s: str | None) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s or "").casefold() if c.isalnum())


def exact(artist: str | None, title: str | None, found: str) -> bool:
    """Vrai si la proposition (« Artiste - Titre ») désigne sans doute la release : même artiste et même titre, à la
    casse, aux accents et à la ponctuation près. Une compilation n'accepte qu'un « Various »."""
    title = clean_title(title)
    who, sep, what = found.partition(" - ")
    who = re.sub(r"\s*\(\d+\)$|\*$", "", who.strip())  # Discogs : « Artiste (2) », « Artiste* »
    if not sep or not _key(title) or _key(what) != _key(title):
        return False
    return _key(who) in _VARIOUS if _key(artist) in _VARIOUS | {""} else _key(who) == _key(artist)


SIGN_TTL = 3600  # une proposition se valide dans l'heure


def sign(secret: str, url: str, now: float | None = None) -> str:
    """« échéance.signature » d'une adresse proposée : valable une heure, préfixe « cover: » propre à cet usage."""
    exp = int((now if now is not None else time.time()) + SIGN_TTL)
    return f"{exp}." + hmac.new(secret.encode(), f"cover:{exp}:{url}".encode(), hashlib.sha256).hexdigest()[:32]


def check(secret: str, url: str, sig: str, now: float | None = None) -> bool:
    exp, _, mac = (sig or "").partition(".")
    if not exp.isdigit() or int(exp) < (now if now is not None else time.time()):
        return False
    good = hmac.new(secret.encode(), f"cover:{exp}:{url}".encode(), hashlib.sha256).hexdigest()[:32]
    return hmac.compare_digest(good, mac)


def public_host(host: str) -> bool:
    """Vrai si le nom ne mène qu'à des adresses d'Internet : jamais le serveur lui-même ni le réseau local."""
    try:
        infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    except OSError:
        return False
    return bool(infos) and all(ipaddress.ip_address(i[4][0]).is_global for i in infos)


class _Pinned(http.client.HTTPSConnection):
    """Connexion HTTPS à une adresse IP déjà vérifiée, le nom servant au certificat (SNI) : pas de seconde résolution
    DNS entre la vérification et la connexion (rebinding)."""

    def __init__(self, host: str, ip: str):
        super().__init__(host, 443, timeout=10, context=ssl.create_default_context())
        self._ip = ip

    def connect(self):
        self.sock = self._context.wrap_socket(socket.create_connection((self._ip, 443), self.timeout), server_hostname=self.host)


def _global(ip: str) -> bool:
    addr = ipaddress.ip_address(ip)
    return (getattr(addr, "ipv4_mapped", None) or addr).is_global


def fetch(url: str) -> bytes:
    """Télécharge l'image proposée : https sur le port 443 seulement, hôte dont toutes les adresses sont publiques,
    connexion à l'adresse vérifiée, sans redirection, 8 Mo au plus. ValueError sinon."""
    parts = urllib.parse.urlsplit(url)
    try:
        port = parts.port
    except ValueError:
        raise ValueError("adresse refusée") from None
    if parts.scheme != "https" or not parts.hostname or port not in (None, 443):
        raise ValueError("adresse refusée")
    try:
        ips = [i[4][0] for i in socket.getaddrinfo(parts.hostname, 443, proto=socket.IPPROTO_TCP)]
    except OSError as e:
        raise ValueError("image inaccessible") from e
    if not ips or not all(_global(ip) for ip in ips):
        raise ValueError("adresse refusée")
    conn = _Pinned(parts.hostname, ips[0])
    try:
        conn.request("GET", (parts.path or "/") + (f"?{parts.query}" if parts.query else ""), headers={**_UA, "Host": parts.netloc})
        r = conn.getresponse()
        if r.status != 200:  # une redirection n'est jamais suivie
            raise ValueError("image inaccessible")
        data = r.read(MAX + 1)
    except (OSError, http.client.HTTPException) as e:
        raise ValueError("image inaccessible") from e
    finally:
        conn.close()
    if not data or len(data) > MAX:
        raise ValueError("image vide ou trop lourde")
    return data