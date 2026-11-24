"""Paroles d'une piste, lues sur LRCLIB (gratuit, sans compte) : synchronisées (format LRC) quand elles existent,
sinon en texte simple. Seuls l'artiste et le titre du morceau sont envoyés."""
import json
import re
import urllib.parse
import urllib.request

from .artists import fold, main

_UA = {"User-Agent": "Mp3-Scene (lyrics)", "Accept": "application/json"}  # rien de personnel


def clean_title(title: str) -> str:
    """Titre sans sa version : « Show Me Love (Club Mix) », « Show Me Love - Radio Edit » -> « Show Me Love »."""
    return re.split(r"\s*[(\[]|\s+-\s+", title, maxsplit=1)[0].strip() or title.strip()


def _get(path: str, **q) -> object:
    url = "https://lrclib.net/api/" + path + "?" + urllib.parse.urlencode(q)
    with urllib.request.urlopen(urllib.request.Request(url, headers=_UA), timeout=6) as r:
        return json.loads(r.read(2 * 1024 * 1024))


def find(artist: str, title: str) -> dict:
    """{"synced", "plain", "duration", "instrumental"} ; valeurs None si rien n'est trouvé. OSError ou ValueError en
    cas de panne (rien n'est alors retenu)."""
    none = {"synced": None, "plain": None, "duration": None, "instrumental": False}
    title = clean_title(title)
    # plusieurs fiches pour un même morceau (certaines d'une seule ligne) : parmi celles au même artiste principal et
    # au même titre, la plus complète, minutée de préférence
    hits = _get("search", artist_name=artist, track_name=title)
    same = lambda h: (isinstance(h, dict) and fold(main(str(h.get("artistName") or ""))) == fold(main(artist))
                      and fold(clean_title(str(h.get("trackName") or ""))) == fold(title))
    hits = [h for h in hits if same(h)] if isinstance(hits, list) else []
    with_text = [h for h in hits if h.get("syncedLyrics") or h.get("plainLyrics")]
    hit = max(with_text, key=lambda h: (bool(h.get("syncedLyrics")), len(h.get("plainLyrics") or h.get("syncedLyrics") or ""))) \
        if with_text else next(iter(hits), None)
    if not isinstance(hit, dict):
        return none
    return {"synced": hit.get("syncedLyrics") or None, "plain": hit.get("plainLyrics") or None,
            "duration": hit.get("duration"), "instrumental": bool(hit.get("instrumental"))}
