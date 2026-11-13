"""Extraction des champs (artiste, titre, source, année, groupe) depuis un nom de release."""
import datetime

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


def _clean(s):
    return s.replace("_", " ").strip() or None


def parse_release_name(name: str) -> dict:
    segs = name.split("-")
    skip = {i for i, s in enumerate(segs) if s.startswith("(") and s.endswith(")")}
    grp = None
    if len(segs) >= 3:
        grp = segs[-1] or None
        skip.add(len(segs) - 1)

    year = None
    for i in range(len(segs) - 1, -1, -1):
        s = segs[i]
        if i not in skip and len(s) == 4 and s.isascii() and s.isdigit() \
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
