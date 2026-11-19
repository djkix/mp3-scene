"""Regroupe les artistes des releases qui ne diffèrent que par la casse, la ponctuation ou un featuring."""
import re
import unicodedata
from collections import Counter, defaultdict

_FEAT = re.compile(r"\s*[(\[]?\s*\b(?:feat|ft|featuring)\b\.?\s.*$", re.I)


def main(artist: str) -> str:
    """Artiste principal : « Zedd Feat Bright Lights », « Argy (feat. Bajka) » -> Zedd, Argy."""
    artist = " ".join(artist.replace("_", " ").split())  # « Tristan_Garner », « Daft  Punk »
    return _FEAT.sub("", artist).strip(" -,(") or artist


def fold(artist: str) -> str:
    """Clé de rapprochement : sans casse, accents, points ni apostrophes ; « and » vaut « & », « pres. » « presents »."""
    a = "".join(c for c in unicodedata.normalize("NFKD", artist) if not unicodedata.combining(c)).casefold()
    a = re.sub(r"\b(?:pres|present|presents)\b", "presents", re.sub(r"\band\b|\+", "&", re.sub(r"['’`´.]", "", a)))
    return " ".join(re.sub(r"\bversus\b", "vs", a).split())


def apply(conn) -> int:
    """Réécrit artist et tag_artist des releases sous la graphie la plus répandue de leur artiste principal.

    Renvoie le nombre de releases modifiées ; sans effet au second passage."""
    # ponytail: toutes les releases relues à chaque démarrage et à chaque scan (moins d'une seconde pour 50 000) ;
    # les artistes des pistes ne sont pas touchés, un featuring y a son sens
    rows = conn.execute("SELECT id, artist, tag_artist FROM releases WHERE artist IS NOT NULL OR tag_artist IS NOT NULL").fetchall()
    spellings = defaultdict(Counter)
    for r in rows:
        for a in {r["artist"], r["tag_artist"]} - {None}:
            m = main(a)
            spellings[fold(m)][m.title() if m.islower() else m] += 1
    best = {k: min(c, key=lambda s: (-c[s], s)) for k, c in spellings.items()}
    canon = lambda a: a and best[fold(main(a))]
    changed = [(canon(r["artist"]), canon(r["tag_artist"]), r["id"]) for r in rows
               if (canon(r["artist"]), canon(r["tag_artist"])) != (r["artist"], r["tag_artist"])]
    conn.executemany("UPDATE releases SET artist=?, tag_artist=? WHERE id=?", changed)
    return len(changed)
