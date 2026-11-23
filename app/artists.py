"""Regroupe les artistes des releases qui ne diffèrent que par la casse, la ponctuation ou un invité (feat, vs, &)."""
import re
import unicodedata
from collections import Counter, defaultdict
from functools import lru_cache

_FEAT = re.compile(r"\s*[(\[]?\s*\b(?:feat|ft|featuring)\b\.?\s.*$", re.I)
_VS = re.compile(r"\s+(?:vs|versus)\b\.?\s.*$", re.I)
_AMP = re.compile(r"\s+(?:&|and|\+)\s+", re.I)
_SUFFIX = re.compile(r"\s+-\s+\S|\s*\[")  # début d'une mention après l'artiste : « - Live », « [groupe] »
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


def norm(artist: str) -> str:
    """Graphie comparée à celles à ne jamais fusionner : sans casse, soulignés ni espaces en double."""
    return " ".join(artist.replace("_", " ").casefold().split())


def _step(pairs: dict, aliases: dict, keep=frozenset()) -> dict:
    """Un passage du regroupement sur {id: (artiste du nom, artiste des tags)} ; `aliases` : rattachements manuels
    {clé de l'artiste rattaché: artiste cible} ; `keep` : graphies (norm) qui ne rejoignent aucune autre."""
    key = lambda a: "\0" + norm(a) if norm(a) in keep else fold(a)  # « Florida » gardé à part de « Flo Rida »
    out = {}
    for i, (name, tag) in pairs.items():
        name, tag = _clean(name), _clean(tag)
        # tag tronqué (« A » pour A-Trak, « DJ » pour DJ Sneak) : l'artiste du nom fait foi
        if name and tag and len(tag) <= 2 and tag != "VA" and len(name) > len(tag) \
                and name.lower().startswith(tag.lower()) and not name[len(tag)].isalnum():
            tag = None
        # tag qui ajoute une mention à l'artiste du nom (« Daft Punk - Live », « Daft Punk [BMi D0MiNAti0N] ») : idem
        if name and tag and (m := _SUFFIX.search(tag)) and fold(tag[:m.start()]) == fold(name):
            tag = None
        out[i] = name, tag
    count = Counter(key(a) for n, t in out.values() if (a := t or n))  # releases par artiste affiché

    def lead(a):
        """« Chocolate Puma & Firebeatz » -> Chocolate Puma, qui a plus de releases seul ; « Block & Crown », « Dimitri
        Vegas & Like Mike » restent des duos."""
        # ponytail: un duo moins fourni que son premier membre seul (« Axwell & Ingrosso ») rejoint ce membre ;
        # liste d'exceptions si cela gêne
        return a and next((a[:m.start()] for m in _AMP.finditer(a) if count[key(a[:m.start()])] > count[key(a)]), a)

    manual = lambda a: a and aliases.get(key(a), a)
    out = {i: (manual(lead(n)), manual(lead(t))) for i, (n, t) in out.items()}
    spellings = defaultdict(Counter)
    for pair in out.values():
        for a in {*pair} - {None}:
            spellings[key(a)][a.title() if a.islower() else a] += 1
    best = {k: min(c, key=lambda s: (-c[s], s)) for k, c in spellings.items()}
    return {i: (n and best[key(n)], t and best[key(t)]) for i, (n, t) in out.items()}


def apply(conn) -> int:
    """Réécrit artist et tag_artist des releases sous la graphie la plus répandue de leur artiste principal.

    Renvoie le nombre de releases modifiées ; sans effet au second passage."""
    # ponytail: toutes les releases relues à chaque démarrage et à chaque scan (cinq secondes pour 45 000 sur le NAS) ;
    # les artistes des pistes ne sont pas touchés, un invité y a son sens
    start = {r["id"]: (r["artist"], r["tag_artist"]) for r in conn.execute(
        "SELECT id, artist, tag_artist FROM releases WHERE artist IS NOT NULL OR tag_artist IS NOT NULL")}
    aliases = dict(conn.execute("SELECT key, target FROM artist_aliases").fetchall())
    keep = frozenset(norm(n) for (n,) in conn.execute("SELECT name FROM artist_separate"))
    pairs = start
    for _ in range(8):  # un regroupement peut en permettre un autre : jusqu'à stabilité
        pairs, before = _step(pairs, aliases, keep), pairs
        if pairs == before:
            break
    changed = [(*pair, i) for i, pair in pairs.items() if pair != start[i]]
    conn.executemany("UPDATE releases SET artist=?, tag_artist=? WHERE id=?", changed)
    return len(changed)


def reset(conn, artist: str) -> None:
    """Rend aux releases de cet artiste l'artiste de leur nom et de leurs tags, avant un nouveau regroupement
    (rattachement manuel retiré)."""
    from app.naming import parse_release_name  # import tardif : naming n'a pas besoin de ce module
    for r in conn.execute("SELECT id, name FROM releases WHERE COALESCE(tag_artist, artist)=?", (artist,)).fetchall():
        conn.execute(
            "UPDATE releases SET artist=:a, tag_artist=(SELECT CASE WHEN count(DISTINCT artist)=1 AND count(artist)=count(*)"
            " THEN max(artist) END FROM tracks WHERE release_id=:r) WHERE id=:r",
            {"r": r["id"], "a": parse_release_name(r["name"])["artist"]})


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
