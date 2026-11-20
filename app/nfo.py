"""Date de sortie, label et numéro de catalogue lus dans le NFO d'une release."""
import datetime
import re
import unicodedata

# libellés par ordre de préférence : date de la release, du rip, de diffusion, puis de mise en vente
_LABELS = (r"rel(?:ease|s)?[ ._]*date|rls[ ._]*date|\br[ ._]?date", r"rip[ ._]*date", r"air[ ._]*date",
           r"(?:store|street|retail|str)[ ._]*date|\bs[ ._]?date")
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
