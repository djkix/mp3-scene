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


_P2P = re.compile(r"(19\d\d|20\d\d)\)?|320")  # une année ou le débit à la place du groupe : pas une release de la scène


def group(raw: str | None) -> tuple[str | None, int | None]:
    """(groupe, année lue à sa place) du dernier segment d'un nom de release.

    Le suffixe de release interne est retiré : « AOV_INT », « XTC_iNT », « CBR_INT_INT » -> AOV, XTC, CBR.
    Une année ou « 320 » n'est pas un groupe : la release est rangée dans P2P."""
    grp = re.sub(r"(\s*_\s*int)+$", "", raw or "", flags=re.I).strip() or None
    if grp and (m := _P2P.fullmatch(grp)):
        return "P2P", int(m[1]) if m[1] else None
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
