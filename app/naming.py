"""Extraction des champs (artiste, titre, source, année, groupe) depuis un nom de release."""
import datetime
import re
import unicodedata
from collections import Counter

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


def unwrap(s: str | None) -> str | None:
    """Artiste d'un tag sans le symbole décoratif qui l'encadre : « ✖ Tristan Garner ✖ » -> « Tristan Garner ».

    Seul un même symbole aux deux bouts est retiré : « A+ », « 200° » ou « Life+ » sont de vrais noms."""
    while s and len(s) > 2 and s[0] == s[-1] and unicodedata.category(s[0]) == "So" and s[1:-1].strip():
        s = s[1:-1].strip()
    return s


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
    if grp.startswith("_"):  # « …-_Ballroom_Tunes_6 » : la fin d'un titre, pas un groupe
        return "P2P", None
    if m := _YEAR.fullmatch(grp):
        return "P2P", int(m[1])
    if not re.fullmatch(r"[A-Za-z0-9_]+", grp) or grp.lstrip("_").upper() in _NOT_GROUPS or _NOT_GROUP.fullmatch(grp):
        return "P2P", None
    return grp, None


_CD = re.compile(r"(?:^|[-_ (])\d*x?CD[A-Z]?\d*(?:[-_ )]|$)", re.I)  # CD, 2CD, CDM, CD1…


# tag qui dit « single » : format court, promo, ou série de remixes
_SINGLE_TAG = re.compile(r"(?:^|[-_ (])(?:CDM|CDS|CDR|MCD|SINGLE|VINYL|VLS|EP|(?:\d+x)?12|BOOTLEG|PROMO|SAMPLER|REMIX|REMIXES"
                         r"|REMIXED|MIXES|RMX|TOOLS|ACAPELLAS?)(?:[-_ ).]|$)", re.I)
ALBUM_TRACKS = 10  # en dessous, trop de singles à remixes sans tag passeraient pour des albums


def album_like(name: str, track_count: int) -> bool:
    """Vrai si une release rangée avec les singles a tout d'un album : beaucoup de pistes, aucun tag de single."""
    return track_count >= ALBUM_TRACKS and not _SINGLE_TAG.search(name)


def one_song(titles: list[str]) -> bool:
    """Vrai si la plupart des pistes sont des versions d'un même morceau : un single, quel que soit leur nombre."""
    def base(t):  # « Crazy (Electro Radio Edit) » et « Crazy feat. X [Club Mix] » -> « crazy »
        return re.sub(r"\s+(feat|ft)\.?\s.*$", "", re.sub(r"\s*[(\[].*$", "", t).strip().lower())
    return bool(titles) and Counter(map(base, titles)).most_common(1)[0][1] >= 0.6 * len(titles)


# « Live » verbe dans un titre de morceau : « How_Can_I_Live_Without_You », « Live_And_Learn », « Live_More »
_LIVE_VERB = re.compile(r"(?:^|[-_ ])(?:(?:I|we|you|to|gonna|wanna|let|lets)[_ ]live|live[_ ](?:and|without|more|for|your|my|it"
                        r"|forever|again|is|life))(?:[-_ ]|$)", re.I)


# date complète dans le nom : une émission ou un set daté (« Hotmix_12-31-1999 », « -25-07-2009- », « 04.06.2006 »)
_FULL_DATE = re.compile(r"(?:^|[-_ (])(?:(\d{1,2})([-.])(\d{1,2})\2(?:19|20)\d\d|(?:19|20)\d\d([-.])(\d{1,2})\4(\d{1,2}))"
                        r"(?:[-_ )]|$)")


def _full_date(name):
    """Correspondance de la date complète du nom, ou None ; « Singles_97-07-2007 » n'en est pas une."""
    m = _FULL_DATE.search(name)
    if m:
        a, b = sorted(int(x) for x in (m[1] and (m[1], m[3]) or (m[5], m[6])))
        if not (1 <= a <= 12 and b <= 31):
            return None
    return m


def kind(name: str) -> str | None:
    """Catégorie que les tags du nom indiquent : 'live', 'comp', 'single', ou None (le dossier décide alors)."""
    f = parse_release_name(name)
    # tag de diffusion : un segment entier (« -SAT- »), pas un mot du titre (« Slam_FM_Presents »)
    tags = {s.upper() for s in name.split("-")}
    if tags & {"SAT", "CABLE", "DAB", "FM", "LINE", "RADIO"}:
        return "live"
    if re.match(r"(VA|Various(_Artists)?)(_?-|$)", name, re.I):
        return "comp"
    if tags & {"DVB", "DVBC", "DVBS", "DVBT", "SBD"}:  # après VA : un « VA-…Yearmix-DVB » reste une compilation
        return "live"
    # nom daté au jour près, sans CD ni tag de single ailleurs que dans la date (« 12-31 » n'est pas un maxi 12 pouces)
    if (m := _full_date(name)) and not _CD.search(name) and not _SINGLE_TAG.search(name[:m.start()] + "-" + name[m.end():]):
        return "live"
    # « Live » ou « Concert » seul : pas un live si le nom parle aussi de CD
    if (f["source"] == "LIVE" or re.search(r"(?:^|[-_ (])concerts?(?:[-_ )]|$)", name, re.I)) \
            and not _CD.search(name) and not _LIVE_VERB.search(name):
        return "live"
    return "single" if f["source"] in ("CDS", "CDM", "SINGLE") else None


def _clean(s):
    return s.replace("_", " ").strip() or None


_ORNAMENT = re.compile(r"^[-_ ]*=+[-_ ]*|[-_ ]*=+[-_ ]*$")


def parse_release_name(name: str, legacy: bool = False) -> dict:
    """`legacy` : l'analyse d'avant la 1.58.0 (fin de titre prise pour un groupe, « _-_ » coupant après VA, compilation
    mixée rangée sous son titre, ornement « -=_ … _=- » gardé dans le titre), pour reconnaître en base les valeurs
    qu'elle a laissées (db.classify)."""
    # nom encadré de « -=_ … _=- » (« -=_Tomorrowland_2013_=- ») : un dossier d'événement ; le nom entier, sans
    # l'ornement, est le titre
    adorned = not legacy and _ORNAMENT.search(name) and _ORNAMENT.sub("", name)
    if adorned:
        name = adorned
    segs = name.split("-")
    skip = {i for i, s in enumerate(segs) if s.startswith("(") and s.endswith(")")}
    grp = year = None
    if len(segs) >= 3:
        grp, year = group(segs[-1])
        # un dernier segment qui n'a pas la forme d'un groupe (« _Ballroom_Tunes_6 », « 06) ») est la fin du titre
        last = _TAIL.sub("", segs[-1]).strip()
        if legacy or not (grp == "P2P" and year is None and (last.startswith("_") or not re.fullmatch(r"[A-Za-z0-9_]+", last))):
            skip.add(len(segs) - 1)

    for i in range(len(segs) - 1, -1, -1):
        s = segs[i]
        if year is None and i not in skip and len(s) == 4 and s.isascii() and s.isdigit() \
                and 1950 <= int(s) <= datetime.date.today().year:
            year = int(s)
            skip.add(i)
            break

    skip |= {i for i, s in enumerate(segs) if i and s.upper() in ("FLAC", "LOSSLESS")}  # format, pas un bout de titre
    source, si = _source(segs, skip)
    # le segment de la source quitte le titre, sauf un long bout de titre où le mot n'est qu'un mot parmi d'autres
    # (« Live_Royal_Summer_Party_at_Contact_Fm ») : la source compte pour la catégorie, le titre reste entier
    if si is not None and (legacy or len([w for w in segs[si].split("_") if w]) <= 3):
        skip.add(si)

    rest = "-".join(s for i, s in enumerate(segs) if i not in skip)
    # « VA-La_Rocca_-_Ballroom_Tunes_6 » : après VA, le premier tiret sépare, « _-_ » fait partie du titre
    for sep in ("-",) if not legacy and re.match(r"(VA|Various(_Artists)?)-", rest, re.I) else ("--", "_-_", "-"):
        if sep in rest:
            artist, title = rest.split(sep, 1)
            break
    else:
        artist = title = ""
    # « ultra dance 03 - mixed by johnny vicious » : une compilation mixée, dont le début du nom est le titre
    if not legacy and artist.strip(" _") and re.match(r"[ _]*mixed[ _]by[ _]", title, re.I):
        artist, title = "VA", f"{artist.strip(' _')} - {title.strip(' _')}"
    if adorned:
        artist, title = "", name
    return dict(artist=_clean(artist), title=_clean(title), source=source, year=year, grp=grp)


def complete_title(title: str | None, filename: str, artist: bool = False) -> str | None:
    """Titre coupé à 30 caractères par un tag ID3v1, complété par la suite lue dans le nom du fichier :
    « Everyday My Life (Cevi » + « 01-dajae-everyday_my_life_(cevin_fisher_mix).mp3 » -> « Everyday My Life (Cevin fisher mix) ».

    Inchangé si le titre ne fait pas exactement 30 caractères ou si le nom du fichier ne le contient pas.
    `artist` : la valeur est un artiste, dont la suite s'arrête au tiret qui le sépare du titre dans le nom du fichier
    (« Bob Sinclar Feat Gary Nesta Pi » + « 01-bob_sinclar_feat_gary_nesta_pine-love_generation.mp3 »)."""
    if not title or len(title) != 30:
        return title
    if title.endswith(")") and title.count("(") == title.count(")"):  # parenthèses refermées : titre entier
        return title
    stem = filename.rsplit(".", 1)[0]
    letters = [(i, c.casefold()) for i, c in enumerate(stem) if c.isalnum()]  # lettres et chiffres seuls, avec leur place
    key = "".join(c.casefold() for c in title if c.isalnum())
    at = "".join(c for _, c in letters).rfind(key) if key else -1
    if at < 0:
        return title
    tail = stem[letters[at + len(key) - 1][0] + 1:]
    tail = tail.split("-", 1)[0] if artist else re.sub(r"-[^-\s()\[\]]+$", "", tail)  # sans le groupe final (« -etlmp3 »)
    tail = " ".join(tail.replace("_", " ").split(" ")) if tail else ""
    # ponytail: la suite garde la casse du nom du fichier (souvent en minuscules) ; relire un tag ID3v2 si elle existe
    # sans lettre dans la suite, le titre faisait 30 caractères sans être coupé
    return re.sub(r" {2,}", " ", title + tail).strip() if any(c.isalnum() for c in tail) else title


# --- Festivals (Live & Radio) -------------------------------------------------------------------------------------
# Grands rendez-vous dont le nom ne contient pas « Festival » ; les autres sont reconnus à ce mot.
_BRANDS = re.compile(r"^(tomorrowland|mysteryland|defqon\.?1|qlimax|awakenings|mayday|nature one|time warp|creamfields"
                     r"|electric daisy carnival|sensation|dance valley|global gathering|untold|parookaville|extrema outdoor"
                     r"|electric love|world club dome|airbeat one|medusa|dreambeach|love parade|street parade|coachella"
                     r"|glastonbury|lollapalooza)\b", re.I)
_LIVE_AT = re.compile(r"^(?:.*?\b)?(?:live|set|dj set)\s+(?:at|au|@|from|a|à)\s+", re.I)
_FEST_YEAR = re.compile(r"\b(19[89]\d|20\d\d)\b")
# mots qui ne distinguent pas deux festivals : « INOX Electronique Festival » = « INOX Electronic Festival »
_FEST_NOISE = {"music", "festival", "electronic", "electronique", "electronica", "open", "air", "the", "de", "des", "du"}


def festival(name: str) -> tuple[str, int | None] | None:
    """(festival, année) d'un set : « Tomorrowland_2013-… », « Artiste-Live_at_Ultra_Music_Festival_2015_(Miami)-… »,
    « Festival_Des_Vieilles_Charrues-DVBS-2009 ». Année lue après le nom du festival, sinon None (celle de la release
    sert alors). None si le nom ne cite aucun festival."""
    for seg in re.split(r"-", name):
        s = re.sub(r"\s+", " ", seg.replace("_", " ")).strip()
        s = _LIVE_AT.sub("", s)
        s = re.sub(r"^live\s+", "", s, flags=re.I)
        if re.match(r"festival (?!mix|edit|version|anthem)", s, re.I):  # « Festival Des Vieilles Charrues (…) 2009 »
            m = re.match(r"^(festival [^\d(]+?)(?= *[\d(]|$)", s, re.I)
        else:
            m = _BRANDS.match(s) or re.match(r"^((?:\S+ ){1,4}?festival)\b(?! (?:mix|edit|version|anthem))", s, re.I)
        if m:
            y = _FEST_YEAR.search(s[m.end():])
            return m[1].strip(), int(y[1]) if y else None
    return None


def festival_key(name: str) -> str:
    """Clé de regroupement : sans accents, casse ni mots génériques (« Ultra Music Festival » = « Ultra Festival »)."""
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().casefold()
    words = [w for w in re.findall(r"[a-z0-9]+", s) if w not in _FEST_NOISE]
    return " ".join(words) or s


# --- Émissions de radio (Live & Radio) ----------------------------------------------------------------------------
# Émissions connues (abréviation -> nom affiché) ; une release de source radio (SAT, FM…) sans émission connue prend
# le titre lu dans son nom, sans numéro d'épisode ni date.
_SHOWS = {"essential mix": "Essential Mix", "a state of trance": "A State of Trance", "asot": "A State of Trance",
          "global dj broadcast": "Global DJ Broadcast", "group therapy": "Group Therapy", "club ?life": "Club Life",
          "hardwell on air": "Hardwell On Air", "corsten'?s countdown": "Corsten's Countdown",
          "trance around the world": "Trance Around The World", "tatw": "Trance Around The World",
          "future sound of egypt": "Future Sound of Egypt", "fsoe": "Future Sound of Egypt",
          "anjunabeats worldwide": "Anjunabeats Worldwide", "anjunadeep edition": "Anjunadeep Edition",
          "protocol radio": "Protocol Radio", "revealed radio": "Revealed Radio", "heldeep radio": "Heldeep Radio",
          "spinnin'? sessions": "Spinnin' Sessions", "musical freedom radio": "Musical Freedom Radio",
          "drumcode radio": "Drumcode Radio", "vonyc sessions": "Vonyc Sessions", "tranceition": "Tranceition",
          "fun radio": "Fun Radio", "radio fg": "Radio FG", "kiss fm": "Kiss FM", "bbc radio ?1": "BBC Radio 1"}
_SHOW = re.compile(r"\b(" + "|".join(_SHOWS) + r")\b", re.I)
_RADIO_SRC = re.compile(r"^(SAT|CABLE|DVB[CST]?|FM|DAB|RADIO|STREAM)$", re.I)
_RADIO_WORDS = re.compile(r"\b(radio ?show|podcast|broadcast|radio)\b", re.I)
_EPISODE = re.compile(r"(\s*\((?:[^)]*)\)|\s+(?:episode|ep|#|vol\.?|part)?\s*\d[\d.\s-]*$)", re.I)


def radio(name: str) -> tuple[str, int | None, bool] | None:
    """(émission, année) d'une release de radio : émission connue citée dans le nom (« Armin_van_Buuren-A_State_of_
    Trance_1100-SAT-… »), sinon titre d'une release de source radio ou qui se dit « radio show », « podcast »…
    None sinon (set de club ou autre). Le booléen dit si l'émission est sûre (connue, ou « radio show »…) ; sinon elle
    n'est tirée que de la source et ne vaut qu'avec plusieurs épisodes."""
    segs = [re.sub(r"\s+", " ", s.replace("_", " ")).strip() for s in name.split("-")]
    segs = [s for s in segs if s]
    y = _FEST_YEAR.search(name.replace("_", " "))
    year = int(y[1]) if y else None
    m = _SHOW.search(name.replace("_", " "))
    if m:
        key = next(k for k in _SHOWS if re.fullmatch(k, m[1], re.I))
        return _SHOWS[key], year, True
    radio_src = any(_RADIO_SRC.match(s) for s in segs[1:])
    for s in segs[1:2] if len(segs) > 1 else segs[:1]:
        if radio_src or _RADIO_WORDS.search(s):
            show, sure = s, bool(_RADIO_WORDS.search(s))
            while (t := _EPISODE.sub("", show).strip()) != show:
                show = t
            show = re.sub(r"\s+(?:\d{1,2}[.\s]\d{1,2}[.\s]\d{2,4}|live)$", "", show, flags=re.I).strip()
            if _RADIO_WORDS.fullmatch(show) and len(segs) > 1:  # « Podcast 045 » seul : « Dubfire Podcast »
                show = f"{segs[0]} {show}"
            if re.search(r"[^\W\d_]", show) and not _LIVE_AT.match(show + " "):
                return show, year, sure
    return None
