"""Regroupe les genres des étiquettes qui ne diffèrent que par l'orthographe, la casse ou la mise en forme."""
import re
import unicodedata

# formes retenues (la plus répandue dans la bibliothèque) ; les variantes de casse, tiret, souligné, accent s'y rangent
CANON = ("House", "Electronic", "Dance", "Trance", "Techno", "Pop", "Hardcore", "R&B", "Club-House", "Rock",
         "Hip-Hop", "Lo-Fi", "Drum & Bass", "Soundtrack", "Reggae", "Soul", "A Cappella", "Tech House", "Chillout",
         "Electro House", "Downtempo", "Alt. Rock", "Electronica & Dance", "Mashup", "Electro", "Variété française",
         "Trip-Hop", "Deep House", "Progressive House", "Dance Hall", "Classical", "Children's Music",
         "Singer/Songwriter", "Jazz+Funk")
# fautes et libellés équivalents -> forme retenue
ALIASES = {"hosue": "House", "housе": "House", "electornic": "Electronic", "tech houhousese": "Tech House",
           "downtemppo": "Downtempo", "alternrock": "Alt. Rock", "a capella": "A Cappella", "acapella": "A Cappella",
           "chill out": "Chillout", "chill": "Chillout", "mash up": "Mashup",
           "electronica/dance": "Electronica & Dance", "electronica dance": "Electronica & Dance",
           "general trance": "Trance", "general hip hop": "Hip-Hop", "house [progressive]": "Progressive House",
           "house [electro]": "Electro House", "reggae [other]": "Reggae", "original soundtrack": "Soundtrack",
           "classique": "Classical", "children": "Children's Music", "танцевальная/электронная музыка": "Dance",
           "alternatif": "Alternative", "chanson francaise": "Chanson", "chansons pour enfants": "Children's Music",
           "film soundtracks": "Soundtrack", "rap & hip hop": "Hip-Hop", "chillout ambient": "Chillout",
           "house mix": "House", "world music world music": "World Music", "dj tools and acapellas": "DJ Tools"}
JUNK = {"unknown", "unknown genre", "genre", "other", "misc", "various artists", "compilation", "bootleg"}
_SITE = re.compile(r"://|^www\.|\.(com|net|org|ru)$", re.I)
_LIST = re.compile(r"\s*[,;/]\s*|\s+[-:]\s+")  # « House, Tech House », « Dance / Disco », « Club - House »


def _fold(g: str) -> str:
    g = "".join(c for c in unicodedata.normalize("NFKD", g) if not unicodedata.combining(c))
    return " ".join(re.sub(r"[_-]", " ", g.casefold()).split()).strip(" :()")


_KNOWN = {**{_fold(c): c for c in CANON}, **ALIASES}


def normalize(genre: str | None) -> str | None:
    """Genre regroupé, ou None s'il n'y en a pas (vide, « Unknown », adresse de site…).

    Une liste de genres est réduite à son premier élément."""
    g = (genre or "").strip()
    if g.startswith("￾"):  # UTF-16 lu dans le mauvais sens : « ￾䠀椀瀀 » pour « Hip »
        g = g[1:].encode("utf-16-be", "ignore").decode("utf-16-le", "ignore").strip()
    if not any(c.isalnum() for c in g) or _SITE.search(g):
        return None
    for part in (g, next(filter(None, _LIST.split(g)), g)):  # le libellé entier d'abord, puis son premier genre
        key = _fold(part)
        if key in JUNK:
            return None
        if key in _KNOWN:
            return _KNOWN[key]
    # ponytail: genre hors liste gardé tel quel, capitalisé s'il est tout en minuscules ou capitales ; l'ajouter à CANON
    # si deux graphies d'un même genre réapparaissent
    return part.title() if part.islower() or part.isupper() else part


def apply(conn) -> int:
    """Regroupe les genres déjà en base ; renvoie le nombre de valeurs réécrites. Sans effet au second passage."""
    n = 0
    for table in ("tracks", "releases"):
        # ponytail: un parcours de la table par démarrage, et un par valeur à réécrire la première fois (tracks.genre
        # n'a pas d'index) ; quelques secondes sur 500 000 pistes
        for (g,) in conn.execute(f"SELECT DISTINCT genre FROM {table} WHERE genre IS NOT NULL").fetchall():
            if (new := normalize(g)) != g:
                conn.execute(f"UPDATE {table} SET genre=? WHERE genre=?", (new, g))
                n += 1
    return n
