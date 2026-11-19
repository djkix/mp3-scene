"""Extraction des champs (artiste, titre, source, année, groupe) depuis un nom de release."""
import datetime
import re

SOURCES = frozenset(
    "WEB VINYL CDM CDS CD CDR CDA EP LP PROMO BOOTLEG SAT DAB CABLE TAPE DVD FM LINE LIVE MP3 SINGLE RETAIL".split()
)
_WEAK = frozenset({"PROMO", "EP", "LP", "LIVE", "SINGLE", "RETAIL"})


def _source(segs, skip):
    weak = None, None
    for i in range(len(segs) - 1, -1, -1):
        if i in skip:
            continue
        for w in segs[i].upper().split("_"):
            if w in SOURCES - _WEAK:
                return w, i
            if w in _WEAK and weak[0] is None:
                weak = w, i
    return weak


_YEAR = re.compile(r"(19\d\d|20\d\d)\)?")
# ce qui traîne après le groupe dans un nom abîmé : « WUS[rarbg] », « BPM.nz », « wWs.1 », « SOB_INT (1) »
_TAIL = re.compile(r"(\[rarbg\]|\.rar_Music|\.(1|nz)|\s*\(\d+\))$", re.I)
_REPAIRS = {"2008 MTC": "MTC", "2008_MTC": "MTC", "MonoPol": "MonoPoly", "EiTheL3P3": "EiTheLMP3", "MW3_iN": "MW3"}
# dernier segment qui n'est pas un groupe : source, débit, numéro de disque, bout de titre
_NOT_GROUPS = SOURCES | frozenset("VA INT HOUSE 320 200X THE_ULTIMATE_MILLENNIUM_MEGAMIX HOP_IN_60_MINUTES RECORDS ROCK"
                                  " CLASSIC BANGERS VOUS DJ_ PROMO_CDS".split())
_NOT_GROUP = re.compile(r"\d{1,2}|CD\d|\dCD", re.I)


def group(raw: str | None) -> tuple[str | None, int | None]:
    """(groupe, année lue à sa place) du dernier segment d'un nom de release.

    Le suffixe de release interne est retiré : « AOV_INT », « XTC_iNT », « CBR_INT_INT » -> AOV, XTC, CBR.
    Un segment qui n'a pas la forme d'un nom de groupe (espaces, crochets, parenthèses : un bout de titre), une
    année, une source ou un débit range la release dans P2P."""
    grp = (raw or "").strip()
    grp = _REPAIRS.get(grp) or re.sub(r"(\s*_\s*int)+$", "", _TAIL.sub("", grp), flags=re.I).strip()
    grp = _REPAIRS.get(grp, grp)
    if grp.startswith("_") and len(grp) < 8:  # « _XDS »
        grp = grp.lstrip("_")
    if not grp:
        return None, None
    if m := _YEAR.fullmatch(grp):
        return "P2P", int(m[1])
    if not re.fullmatch(r"[A-Za-z0-9_]+", grp) or grp.lstrip("_").upper() in _NOT_GROUPS or _NOT_GROUP.fullmatch(grp):
        return "P2P", None
    return grp, None


def _clean(s):
    return s.replace("_", " ").strip() or None


def parse_release_name(name: str) -> dict:
    segs = name.split("-")
    skip = {i for i, s in enumerate(segs) if s.startswith("(") and s.endswith(")")}
    grp = year = None
    if len(segs) >= 3:
        grp, year = group(segs[-1])
        skip.add(len(segs) - 1)

    for i in range(len(segs) - 1, -1, -1):
        s = segs[i]
        if year is None and i not in skip and len(s) == 4 and s.isascii() and s.isdigit() \
                and 1950 <= int(s) <= datetime.date.today().year:
            year = int(s)
            skip.add(i)
            break

    source, si = _source(segs, skip)
    if si is not None:
        skip.add(si)

    rest = "-".join(s for i, s in enumerate(segs) if i not in skip)
    for sep in ("--", "_-_", "-"):
        if sep in rest:
            artist, title = rest.split(sep, 1)
            break
    else:
        artist = title = ""
    return dict(artist=_clean(artist), title=_clean(title), source=source, year=year, grp=grp)
