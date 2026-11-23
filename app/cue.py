"""Chapitres d'un long mix, lus dans le fichier .cue qui l'accompagne."""
import os
import re
from pathlib import Path

from app.security import open_regular

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


def for_tracks(folder: Path, tracks: list[tuple[int, str]]) -> dict[int, list[dict]]:
    """Chapitres des pistes [(identifiant, chemin relatif)] d'une release, lus dans les .cue de son dossier et de ses
    sous-dossiers de disque. Seules les pistes découpées en au moins deux chapitres y figurent. Lève OSError si le
    dossier est illisible."""
    found = {}
    # os.walk sans suivre les dossiers liés, et aucun fichier .cue qui soit un lien symbolique (hors de la bibliothèque)
    cues = []
    for dirpath, dirnames, filenames in os.walk(folder):
        dirnames.sort()
        for n in sorted(filenames):
            p = Path(dirpath, n)
            if p.suffix.lower() == ".cue" and not p.is_symlink() and p.is_file() and p.stat().st_size < 512 * 1024:
                cues.append(p)
    for path in cues[:20]:
        with open_regular(path, folder) as fh:  # lecture seule
            for name, parts in parse(fh.read().decode("cp437")).items():
                found.setdefault(name, parts)
    out = {}
    for tid, relpath in tracks:
        name = relpath.rsplit("/", 1)[-1].lower()
        # le .cue nomme parfois un .wav d'origine : rapprochement sur le nom sans extension, puis piste unique
        parts = found.get(name) or next((v for k, v in found.items() if k.rsplit(".", 1)[0] == name.rsplit(".", 1)[0]), None)
        if parts is None and len(tracks) == 1 and len(found) == 1:
            parts = next(iter(found.values()))
        if parts and len(parts) > 1:
            out[tid] = parts
    return out
