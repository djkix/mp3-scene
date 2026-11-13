"""Génère une fausse bibliothèque pour tester l'interface : python scripts/make_demo_library.py <dossier_cible>"""
import random
import sys
from pathlib import Path

from mutagen.id3 import ID3, TCON, TIT2, TPE1

ARTISTS = ["A-Trak", "Daft_Punk", "Justice", "Bonobo", "Kavinsky", "Moderat", "Caribou", "Four_Tet", "Jamie_xx",
           "Disclosure", "Fatboy_Slim", "Chemical_Brothers", "Mr_Oizo", "Cassius", "Air", "Etienne_de_Crecy"]
TITLES = ["Night_Drive", "Ibanez", "Midnight_City", "Slow_Burn", "Open_Eye", "Back_To_You", "Red_Light", "Kites",
          "Strobe", "Digital_Love", "Starlight", "Desert_Rose", "Echoes", "Afterglow", "Blue_Hour", "Static"]
GENRES = ["House", "Techno", "Electro", "Trance", "Ambient", "Hip-Hop", "Pop", "Rock"]
SOURCES = ["WEB", "CD", "VINYL", "SAT"]
GROUPS = ["WUS", "ALPHA", "YARD", "CMG", "TALION", "ESC"]
BOX = "┌──────────────────────────┐\n│  %s  │\n└──────────────────────────┘\n"


def write_mp3(path, title, artist, genre, frames=20):
    # trames MPEG-1 Layer III, 128 kbit/s, 44,1 kHz (cf. fixture make_mp3 de tests/conftest.py)
    path.write_bytes((b"\xff\xfb\x90\x64" + b"\x00" * 413) * frames)
    tags = ID3()
    for frame, value in ((TIT2, title), (TPE1, artist), (TCON, genre)):
        tags.add(frame(encoding=3, text=value))
    tags.save(path)


def make_release(folder, rng, cds=1):
    artist, genre = rng.choice(ARTISTS), rng.choice(GENRES)
    folder.mkdir(parents=True)
    names = []
    for cd in range(1, cds + 1):
        sub = folder / f"CD{cd}" if cds > 1 else folder
        sub.mkdir(exist_ok=True)
        for n in range(1, rng.randint(1, 4) + 1):
            title = rng.choice(TITLES)
            name = f"{n:02d}-{artist.lower()}-{title.lower()}.mp3"
            write_mp3(sub / name, title.replace("_", " "), artist.replace("_", " "), genre)
            names.append(name)
    (folder / "release.nfo").write_bytes((BOX % folder.name[:22].ljust(22)).encode("cp437", "replace"))
    (folder / "release.sfv").write_text("".join(f"{n} 00000000\n" for n in names))
    (folder / "release.m3u").write_text("".join(f"{n}\n" for n in names))


def main(target):
    root, rng = Path(target), random.Random(42)
    used = set()
    for i in range(110):
        artist, title = rng.choice(ARTISTS), rng.choice(TITLES)
        name = f"{artist}--{title}-({rng.choice('SP')}{rng.randint(100, 999)})-{rng.choice(SOURCES)}-{rng.randint(2008, 2024)}-{rng.choice(GROUPS)}"
        if name in used:
            continue
        used.add(name)
        make_release(root / "Singles" / artist[0].upper() / name, rng)
    for i in range(10):
        make_release(root / "Albums" / f"{rng.choice(ARTISTS)}-Album_{i}-2CD-WEB-{rng.randint(2010, 2024)}-{rng.choice(GROUPS)}",
                     rng, cds=2 if i == 0 else 1)
    print(f"{len(used) + 10} releases créées dans {root}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
