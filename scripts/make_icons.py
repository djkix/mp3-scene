"""Génère les icônes PWA (stdlib seule) : python scripts/make_icons.py"""
import struct
import zlib
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "static" / "icons"
GREEN, WHITE = (0x1D, 0xB9, 0x54), (255, 255, 255)


def png(path, size, scale):
    """`scale` : part du côté occupée par le pictogramme (maskable : zone sûre = disque central de 80 %)."""
    ss = 3  # suréchantillonnage pour lisser les bords
    n = size * ss
    unit = n * scale  # pictogramme dans un carré de côté `unit`, centré
    ox = oy = (n - unit) / 2

    def inside(x, y):
        u, v = (x - ox) / unit, (y - oy) / unit  # 0..1
        if (u - .36) ** 2 / .17 ** 2 + (v - .76) ** 2 / .12 ** 2 <= 1 and u < .56:  # tête de la note (ellipse)
            return True
        if .50 <= u <= .58 and .10 <= v <= .76:  # hampe
            return True
        return .50 <= u <= .84 and .10 + (u - .50) * .9 <= v <= .30 + (u - .50) * .9  # fanion incliné

    raw = bytearray()
    for y in range(size):
        raw.append(0)
        for x in range(size):
            hits = sum(inside(x * ss + i, y * ss + j) for i in range(ss) for j in range(ss)) / ss ** 2
            raw += bytes(round(g + (w - g) * hits) for g, w in zip(GREEN, WHITE))

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))

    data = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b""))
    path.write_bytes(data)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    # fond uni sur tout le carré : valable tel quel en « maskable » ; pictogramme à 62 % pour rester dans la zone sûre
    png(OUT / "icon-192.png", 192, .62)
    png(OUT / "icon-512.png", 512, .62)
    png(OUT / "apple-touch-icon.png", 180, .62)
    png(OUT / "favicon-32.png", 32, .8)
    # favicon.ico : en-tête ICO + une entrée 32x32 contenant le PNG tel quel
    data = (OUT / "favicon-32.png").read_bytes()
    (OUT / "favicon-32.png").unlink()
    (OUT.parent / "favicon.ico").write_bytes(struct.pack("<HHH", 0, 1, 1) + struct.pack("<BBBBHHII", 32, 32, 0, 0, 1, 32, len(data), 22) + data)
