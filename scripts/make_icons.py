"""Génère les icônes de l'application : un disque vinyle, « MP3Z / SCENE » en lettres de blocs.

    python scripts/make_icons.py      # réécrit static/icons/*.png, favicon.svg et static/favicon.ico
"""
from pathlib import Path

from PIL import Image, ImageDraw

STATIC = Path(__file__).resolve().parent.parent / "static"
BG, DISC, RING, GREEN, LABEL = "#0c0c0d", "#131314", "#2a2a2b", "#22c55e", "#0e0e0f"
GLYPHS = {"M": "10001 11011 10101 10001 10001", "P": "11110 10001 11110 10000 10000", "3": "11110 00001 01110 00001 11110",
          "Z": "11111 00010 00100 01000 11111", "S": "01111 10000 01110 00001 11110", "C": "01111 10000 10000 10000 01111",
          "E": "11111 10000 11110 10000 11111", "N": "10001 11001 10101 10011 10001"}
CELL = 9  # côté d'un bloc, sur une grille de 512


def draw(size: int, text: bool) -> Image.Image:
    """Icône carrée ; sans texte pour les petites tailles, où il serait illisible."""
    k = 4 * size / 512  # suréchantillonnage ×4, réduit ensuite
    img = Image.new("RGB", (4 * size, 4 * size), BG)
    d = ImageDraw.Draw(img)
    circle = lambda r, **kw: d.ellipse([k * (256 - r), k * (256 - r), k * (256 + r), k * (256 + r)], **kw)
    circle(226, fill=DISC, outline=RING, width=round(3 * k))
    for r in range(210, 165, -15):
        circle(r, outline=RING, width=max(1, round(k)))
    circle(158, fill=LABEL, outline=GREEN, width=round((4 if text else 14) * k))
    if not text:
        circle(46, fill=GREEN)
        return img.resize((size, size), Image.LANCZOS)
    for row, word in enumerate(("MP3Z", "SCENE")):
        x0 = 256 - CELL * (6 * len(word) - 1) / 2
        y0 = 256 - CELL * 6 + row * CELL * 7
        for i, ch in enumerate(word):
            for y, line in enumerate(GLYPHS[ch].split()):
                for x, on in enumerate(line):
                    if on == "1":
                        px, py = x0 + CELL * (6 * i + x), y0 + CELL * y
                        d.rectangle([k * px, k * py, k * (px + CELL) - 1, k * (py + CELL) - 1], fill=GREEN if row == 0 else "#e8e8e4")
    for sx, sy in ((1, 1), (-1, 1), (1, -1), (-1, -1)):  # équerres des coins
        cx, cy = 256 - sx * 226, 256 - sy * 226
        d.line([k * cx, k * (cy + sy * 34), k * cx, k * cy, k * (cx + sx * 34), k * cy], fill=GREEN, width=round(5 * k), joint="curve")
    return img.resize((size, size), Image.LANCZOS)


if __name__ == "__main__":
    for name, size in (("icon-512.png", 512), ("icon-192.png", 192), ("apple-touch-icon.png", 180)):
        draw(size, True).save(STATIC / "icons" / name, optimize=True)
    draw(48, False).save(STATIC / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])
    (STATIC / "icons" / "favicon.svg").write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="12" fill="{BG}"/>'
        f'<circle cx="32" cy="32" r="28" fill="{DISC}" stroke="{RING}"/><circle cx="32" cy="32" r="19" fill="{LABEL}" '
        f'stroke="{GREEN}" stroke-width="3"/><circle cx="32" cy="32" r="6" fill="{GREEN}"/></svg>\n')
