"""Date de sortie lue dans le NFO d'une release."""
import datetime
import re

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
