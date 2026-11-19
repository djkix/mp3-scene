"""Regroupe les artistes des releases qui ne diffèrent que par la casse, la ponctuation ou un invité (feat, vs, &)."""
import re
import unicodedata
from collections import Counter, defaultdict
from functools import lru_cache

_FEAT = re.compile(r"\s*[(\[]?\s*\b(?:feat|ft|featuring)\b\.?\s.*$", re.I)
_VS = re.compile(r"\s+(?:vs|versus)\b\.?\s.*$", re.I)
_AMP = re.compile(r"\s+(?:&|and|\+)\s+", re.I)
_VA = {"va", "various", "variousartists"}
_JUNK = {"unknown", "unknownartist"}


def main(artist: str) -> str:
    """Artiste principal : « Zedd Feat Bright Lights », « Argy (feat. Bajka) », « Daft Punk Vs Madonna » -> Zedd, Argy,
    Daft Punk."""
    artist = " ".join(artist.replace("_", " ").split())  # « Tristan_Garner », « Daft  Punk »
    for cut in (_FEAT, _VS):
        artist = cut.sub("", artist).strip(" -,(") or artist
    # une année seule n'est pas un artiste : compilation
    return "VA" if re.fullmatch(r"(19|20)\d\d", artist) or fold(artist) in _VA else artist


def fold(artist: str) -> str:
    """Clé de rapprochement : sans casse, accents, espaces, points ni apostrophes ; « and » vaut « & », « pres. » « presents »."""
    a = "".join(c for c in unicodedata.normalize("NFKD", artist) if not unicodedata.combining(c)).casefold()
    a = re.sub(r"\b(?:pres|present|presents)\b", "presents", re.sub(r"\band\b|\+", "&", re.sub(r"['’`´.]", "", a)))
    return "".join(re.sub(r"\bversus\b", "vs", a).split())  # sans espaces : « 2ManyDJs » vaut « 2 Many DJs »


def _clean(artist):
    """Artiste principal, ou None s'il n'y en a pas (« . », « Unknown Artist »)."""
    if not artist or not any(c.isalnum() for c in artist) or fold(artist) in _JUNK:
        return None
    return main(artist)


def _step(pairs: dict) -> dict:
    """Un passage du regroupement sur {id: (artiste du nom, artiste des tags)}."""
    out = {}
    for i, (name, tag) in pairs.items():
        name, tag = _clean(name), _clean(tag)
        # tag tronqué (« A » pour A-Trak, « DJ » pour DJ Sneak) : l'artiste du nom fait foi
        if name and tag and len(tag) <= 2 and tag != "VA" and len(name) > len(tag) \
                and name.lower().startswith(tag.lower()) and not name[len(tag)].isalnum():
            tag = None
        out[i] = name, tag
    count = Counter(fold(a) for n, t in out.values() if (a := t or n))  # releases par artiste affiché

    def lead(a):
        """« Chocolate Puma & Firebeatz » -> Chocolate Puma, qui a plus de releases seul ; « Block & Crown », « Dimitri
        Vegas & Like Mike » restent des duos."""
        # ponytail: un duo moins fourni que son premier membre seul (« Axwell & Ingrosso ») rejoint ce membre ;
        # liste d'exceptions si cela gêne
        return a and next((a[:m.start()] for m in _AMP.finditer(a) if count[fold(a[:m.start()])] > count[fold(a)]), a)

    out = {i: (lead(n), lead(t)) for i, (n, t) in out.items()}
    spellings = defaultdict(Counter)
    for pair in out.values():
        for a in {*pair} - {None}:
            spellings[fold(a)][a.title() if a.islower() else a] += 1
    best = {k: min(c, key=lambda s: (-c[s], s)) for k, c in spellings.items()}
    return {i: (n and best[fold(n)], t and best[fold(t)]) for i, (n, t) in out.items()}


def apply(conn) -> int:
    """Réécrit artist et tag_artist des releases sous la graphie la plus répandue de leur artiste principal.

    Renvoie le nombre de releases modifiées ; sans effet au second passage."""
    # ponytail: toutes les releases relues à chaque démarrage et à chaque scan (cinq secondes pour 45 000 sur le NAS) ;
    # les artistes des pistes ne sont pas touchés, un invité y a son sens
    start = {r["id"]: (r["artist"], r["tag_artist"]) for r in conn.execute(
        "SELECT id, artist, tag_artist FROM releases WHERE artist IS NOT NULL OR tag_artist IS NOT NULL")}
    pairs = start
    for _ in range(8):  # un regroupement peut en permettre un autre : jusqu'à stabilité
        pairs, before = _step(pairs), pairs
        if pairs == before:
            break
    changed = [(*pair, i) for i, pair in pairs.items() if pair != start[i]]
    conn.executemany("UPDATE releases SET artist=?, tag_artist=? WHERE id=?", changed)
    return len(changed)


_GUEST = r"(?:feat|ft|featuring|vs|versus|and|with|&|\+)"


@lru_cache(maxsize=64)
def _collab_re(artist):
    a = r"[\W_]+".join(map(re.escape, re.split(r"[\W_]+", artist.strip())))
    return re.compile(rf"(?<![^\W_]){_GUEST}[\W_]+{a}(?![^\W_])|(?<![^\W_]){a}[\W_]+{_GUEST}(?![^\W_])", re.I)


def collab(name: str, artist: str) -> bool:
    """Vrai si le nom de la release associe l'artiste à un autre : « X_Feat_Artiste », « Artiste_Vs_Y », « Artiste_and_Y »."""
    # ponytail: cherche la graphie exacte de l'artiste dans le nom (« Tiesto » ne trouve pas « Tiësto ») ; garder le
    # crédit complet en base si cela manque
    return bool(artist.strip()) and _collab_re(artist).search(name) is not None
