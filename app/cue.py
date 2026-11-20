"""Chapitres d'un long mix, lus dans le fichier .cue qui l'accompagne."""
import re

_LINE = re.compile(r'^\s*(FILE|TRACK|TITLE|PERFORMER|INDEX)\s+(.*?)\s*$', re.I)
_QUOTED = re.compile(r'"(.*)"')


def _text(value: str) -> str:
    m = _QUOTED.search(value)
    return (m.group(1) if m else value).strip()


def parse(text: str) -> dict[str, list[dict]]:
    """{nom du fichier audio en minuscules: [{title, artist, start (secondes)}]}, dans l'ordre du fichier.

    Seul INDEX 01 (début du morceau) compte ; un TRACK sans INDEX 01 est ignoré. Les TITLE et PERFORMER d'avant le
    premier TRACK décrivent le disque entier, pas un chapitre."""
    out, file, cur = {}, "", None
    for line in text.splitlines():
        m = _LINE.match(line)
        if not m:
            continue
        key, value = m.group(1).upper(), m.group(2)
        if key == "FILE":
            # FILE "nom.mp3" MP3 : le nom entre guillemets, sinon tout sauf le dernier mot (le type)
            file = (_QUOTED.search(value).group(1) if _QUOTED.search(value) else value.rsplit(" ", 1)[0]).strip()
            file = file.replace("\\", "/").rsplit("/", 1)[-1].lower()
            cur = None
        elif key == "TRACK":
            cur = {"title": "", "artist": "", "start": None}
        elif cur is not None and key == "TITLE":
            cur["title"] = _text(value)
        elif cur is not None and key == "PERFORMER":
            cur["artist"] = _text(value)
        elif cur is not None and key == "INDEX":
            m2 = re.match(r"0*1\s+(\d+):(\d{1,2}):(\d{1,2})$", value)
            if m2 and cur["start"] is None:
                cur["start"] = int(m2.group(1)) * 60 + int(m2.group(2)) + int(m2.group(3)) / 75  # 75 images par seconde
                out.setdefault(file, []).append(cur)
    return out
