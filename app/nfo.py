"""Date de sortie, label et numéro de catalogue lus dans le NFO d'une release."""
import datetime
import re
import unicodedata
from pathlib import Path

from app import security

SUFFIXES = (".nfo", ".txt")


def read(folder, root, limit: int) -> str | None:
    """Texte du NFO du dossier : le premier .nfo, sinon le premier .txt (les mixes en ont souvent un à la place, avec
    la tracklist). None sans l'un ni l'autre. Un .nfo est en page de code 437 (art ASCII) ; un .txt en UTF-8, sinon
    en Windows-1252. Lève OSError si le fichier est illisible ; liens symboliques ignorés."""
    names = security.regular_names(Path(folder), SUFFIXES)
    name = next((n for n in names if n.lower().endswith(".nfo")), names[0] if names else None)
    if name is None:
        return None
    with security.open_regular(Path(folder, name), root) as fh:  # lecture seule
        data = fh.read(limit)
    if name.lower().endswith(".nfo"):
        return data.decode("cp437")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252", "replace")

# libellés par ordre de préférence : date de la release, du rip, de diffusion, puis de mise en vente, enfin une
# « Date » seule ; en anglais (NFO) ou en français (les .txt des mixes : « Diffusé le 12/03/2010 »)
_LABELS = (r"rel(?:ease|s)?[ ._]*date|rls[ ._]*date|\br[ ._]?date|date de sortie|sorti(?:e|e? le)\b", r"rip[ ._]*date",
           r"air[ ._]*date|date de diffusion|diffus[ée]+(?: le)?|enregistr[ée]+(?: le)?|recorded(?: on)?|broadcast(?: on)?",
           r"(?:store|street|retail|str)[ ._]*date|\bs[ ._]?date", r"\bdate\b")
_MONTHS = {m: i + 1 for i, m in enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split())}
_S = r"[-./ ]"
_DATE = re.compile(rf"(?:(?P<mon>[A-Za-z]{{3,9}}){_S}(?P<md>\d{{1,2}}){_S}(?P<my>\d{{4}})"   # Sep-11-2007
                   rf"|(?P<dd>\d{{1,2}}){_S}(?P<dmon>[A-Za-z]{{3,9}}){_S}(?P<dy>\d{{4}})"     # 07/July/2000
                   rf"|(?P<iy>\d{{4}}){_S}(?P<im>\d{{1,2}}){_S}(?P<id>\d{{1,2}})"             # 2011-09-25
                   rf"|(?P<a>\d{{1,2}}){_S}(?P<b>\d{{1,2}}){_S}(?P<y>\d{{4}}))(?!\d)")        # 17-06-2008, 06.24.2012


def release_date(text: str) -> float | None:
    """Heure Unix (midi UTC) de la date de sortie annoncée par le NFO, ou None (absente, « 00-00-0000 », illisible)."""
    found = []  # (rang du libellé, correspondance)
    for rank, label in enumerate(_LABELS):
        for m in re.finditer(rf"(?:{label})[^A-Za-z0-9\n]{{0,20}}", text, re.I):
            if d := _DATE.match(text, m.end()):
                found.append((rank, d))
    # « 05-06-2008 » : jour ou mois d'abord ? Une autre date du même NFO tranche (31-10 ou 10-31)
    # ponytail: sans indice, jour d'abord ; lire la convention du groupe dans ses autres NFO si trop d'erreurs
    nums = [(int(d["a"]), int(d["b"])) for _, d in found if d["a"]]
    month_first = not any(a > 12 for a, _ in nums) and any(b > 12 for _, b in nums)
    for _, d in sorted(found, key=lambda f: f[0]):
        if d["mon"] or d["dmon"]:
            ymd = d["my"] or d["dy"], _MONTHS.get((d["mon"] or d["dmon"])[:3].lower(), 0), d["md"] or d["dd"]
        elif d["iy"]:
            ymd = d["iy"], d["im"], d["id"]
        else:
            ymd = (d["y"], d["a"], d["b"]) if month_first else (d["y"], d["b"], d["a"])
        try:
            day = datetime.datetime(*map(int, ymd), 12, tzinfo=datetime.timezone.utc)
        except ValueError:  # 00-00-2008, 31 février
            continue
        if 1980 <= day.year and day <= datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=366):
            return day.timestamp()
    return None


_FIELD = r"[^A-Za-z0-9\n]*[:=][ \t]*(\S[^\n]*)"
_LABEL = re.compile(r"^[^A-Za-z0-9\n]*(?:record[ ._]*)?label\b" + _FIELD, re.I | re.M)
_CAT = re.compile(r"\bcat(?:alog(?:ue)?)?(?:[ ._-]*(?:nr|no|num(?:ber)?|#|id))?(?![A-Za-z])" + _FIELD, re.I)
_NONE = {"na", "none", "unknown", "various", "va", "nolabel", "notonlabel", "selfreleased", "tba", "whitelabel"}


def _value(m, size):
    """Valeur d'un champ, sans le cadre du NFO à droite ; None si vide, trop longue, une adresse ou « n/a »."""
    if m is None:
        return None
    # « Foo Records      ║ », « Foo  Releasedate: … », « Foo / Cat.Nr: X » : la valeur s'arrête au cadre ou au champ suivant
    v = re.split(r"\s{2,}|\s+[/|]\s+(?=[^/|]*:)", m.group(1).strip())[0]
    v = clean_label(v)
    if not v or len(v) > size or "://" in v or "www." in v.lower() or re.sub(r"[\W_]", "", v).lower() in _NONE:
        return None
    return v


def label(text: str) -> tuple[str | None, str | None]:
    """(label, numéro de catalogue) annoncés par le NFO : « Label....: Ministry of Sound », « Cat.Nr: MOS123 »."""
    # ponytail: lignes « libellé : valeur » seulement ; les NFO en prose ou en tableau ne sont pas lus
    cat = _value(_CAT.search(text), 30)
    return _value(_LABEL.search(text), 60), cat if cat and any(c.isdigit() for c in cat) else None


def clean_label(v: str) -> str:
    """Label sans les restes de mise en forme du NFO : « ..... Defected », « ] Deep State », « █ PIAS », « (Warner) »,
    « (P) 2014 Protocol Recordings », « ((JOLLY ROGER) SOUND OF PIRATES)) ». Vide s'il ne reste rien (« ? », « ..... »)."""
    start = re.search(r"!?[^\W_]", v)  # premier caractère utile ; « !K7 » garde son point d'exclamation
    if start is None:
        return ""
    v = v[start.start():].replace("_", " ")
    v = re.sub(r"^[pc]\)\s*(?:(?:19|20)\d\d\s+)?", "", v, flags=re.I)              # « (P) 2014 … » : mention de copyright
    out, depth = [], 0
    for ch in v:  # parenthèses sans vis-à-vis retirées
        if ch == "(":
            depth += 1
        elif ch == ")":
            if depth == 0:
                continue
            depth -= 1
        out.append(ch)
    v = "".join(out)
    for _ in range(depth):
        i = v.rindex("(")
        v = v[:i] + v[i + 1:]
    # « ZYX Music û ZYX 20590-2 », « ZYX Music / Noise Traxx » : le premier label nommé (û : tiret mal décodé)
    v = re.split(r"\s+[/|û\u2013\u2014]\s+", v)[0]
    # numéro de catalogue pris pour le label ou collé à lui : « ZYX (ZYX-9168-8) », « ZYX 55786-2 », « ZYX82273-2 »
    v = re.sub(r"\s*\([^()]*\d{3}[^()]*\)", "", v)
    v = re.sub(r"(?<=[^\W\d_]{2})[\s-]*(?:\d{5,}|\d{3,}[\s-]\d+)(?:[\s-]\d+)*$", "", v)
    # « Zyx Music (ZYX) » : la parenthèse répète le début du nom
    if (m := re.fullmatch(r"(.+?)\s*\(([^()]+)\)", v)) and m[1].casefold().startswith(m[2].casefold()):
        v = m[1]
    v = " ".join(re.sub(r"[^\w)\]!?.'\"]+$", "", v).split())
    return v if sum(c.isalnum() for c in v) >= 2 else ""  # une lettre seule n'est pas un label


def label_key(v: str) -> str:
    """Clé de rapprochement des labels : sans casse, accents, espaces ni ponctuation, et sans « Records » ni « Music »
    final (« Defected », « DEFECTED », « Defected Records », « De-fected », « ZYX », « ZYX Music » ne font qu'un)."""
    k = "".join(c for c in unicodedata.normalize("NFKD", v).casefold() if c.isalnum())
    return re.sub(r"(?<=..)(?:records?|recordings?|recs?|music)$", "", k) or k


_DISC = re.compile(r"^\W*(?:cd|disc|disk)\s*0*(\d+)\b", re.I)
_TIME = r"\[?\(?(?:(\d{1,2}):)?(\d{1,3}):(\d{2})\)?\]?"
_AFTER = re.compile(rf"^\s*\d{{1,3}}\s*[.)\-]?\s+(.+?)\s+{_TIME}\s*$")          # « 1. Artiste - Titre    4:00 »
# « [00:00] 01. Artiste - Titre », « 01. [00:00] Artiste - Titre », « 00:00 - Artiste - Titre »
_BEFORE = re.compile(rf"^\s*(?:\d{{1,3}}\s*[.)]\s*)?{_TIME}\s*(?:[-\u2013|]\s+|\s)(?:\d{{1,3}}\s*[.)\-]?\s+)?(.+?)\s*$")


def tracklist(text: str) -> list[list[dict]]:
    """Tracklist minutée du NFO, un tableau par disque : [{artist, title, start (secondes)}].

    Les temps sont des durées (« 4:00 » en fin de ligne) ou des débuts (« [00:00] » en tête de ligne, ou une suite
    croissante qui part de zéro) ; les débuts sont recalculés depuis les durées. Une ligne qui ne commence que par une
    parenthèse prolonge le titre précédent (« (Tommyboy Remix) »). Un disque de moins de deux morceaux est ignoré."""
    discs, cur = [], []
    for line in text.splitlines():
        if (d := _DISC.match(line)) and not _AFTER.match(line):
            if cur:
                discs.append(cur)
            cur = []
            continue
        m, before = _AFTER.match(line), False
        if not m and (m := _BEFORE.match(line)):
            before = True
        if m:
            h, mi, se = (m.group(1), m.group(2), m.group(3)) if before else (m.group(2), m.group(3), m.group(4))
            name = m.group(4) if before else m.group(1)
            secs = int(h or 0) * 3600 + int(mi) * 60 + int(se)
            artist, sep, title = re.split(r"\s+[-\u2013]\s+", name.strip(), maxsplit=1)[0], " - ", ""
            parts = re.split(r"\s+[-\u2013]\s+", name.strip(), maxsplit=1)
            artist, title = (parts[0], parts[1]) if len(parts) == 2 else ("", parts[0])
            cur.append({"artist": artist.strip()[:200], "title": title.strip()[:300], "t": secs, "before": before})
        elif cur and line.strip().startswith("("):
            cur[-1]["title"] = (cur[-1]["title"] + " " + line.strip())[:300]
    if cur:
        discs.append(cur)
    out = []
    for parts in discs:
        if len(parts) < 2:
            continue
        times = [p["t"] for p in parts]
        starts = parts[0]["before"] or (times[0] == 0 and all(a < b for a, b in zip(times, times[1:])))
        if not starts:  # durées : chaque morceau commence où le précédent finit
            acc, times = 0, []
            for p in parts:
                times.append(acc)
                acc += p["t"]
        out.append([{"artist": p["artist"], "title": p["title"], "start": t, "length": None if starts else p["t"]}
                    for p, t in zip(parts, times)])
    return out


_NUMBERED = re.compile(r"^\s*(\d{1,3})\s*[.)\-]\s+(.+?)(?:\s+\[?\(?(?:\d{1,2}:)?\d{1,3}:\d{2}\)?\]?)?\s*$")


def track_names(text: str) -> list[dict]:
    """Morceaux numérotés de la tracklist du NFO, dans l'ordre, minutés ou non : [{artist, title}]. La numérotation
    doit repartir de 1 à chaque disque et se suivre ; une ligne qui ne commence que par une parenthèse prolonge le
    titre précédent."""
    out, expect = [], 1
    for line in text.splitlines():
        m = _NUMBERED.match(line)
        if m:
            n = int(m[1])
            if n == 1 and out:
                expect = 1  # disque suivant
            if n != expect:
                continue
            expect += 1
            parts = re.split(r"\s+[-\u2013]\s+", m[2].strip(), maxsplit=1)
            artist, title = (parts[0], parts[1]) if len(parts) == 2 else ("", parts[0])
            out.append({"artist": artist.strip()[:200], "title": title.strip()[:300]})
        elif out and line.strip().startswith("("):
            out[-1]["title"] = (out[-1]["title"] + " " + line.strip())[:300]
    return out
