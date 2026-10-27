"""Generate the raster favicon and validate the SVG artwork set.

The favicon has to be a raster file for ``st.set_page_config(page_icon=...)``,
so it is rasterised here from the same motif set as the hand-drawn SVGs in
``app/assets``. Running this script also checks every asset: each SVG must
parse as XML, every ``app.artwork.PAGE_ART`` entry must exist on disk, and the
PNG must come out square.

Usage (project root):

    python tools/make_artwork.py            # regenerate + validate
    python tools/make_artwork.py --check    # validate only, no writes

The generated PNG is committed, so Pillow is a dev-only dependency and stays
out of requirements.txt.
"""
from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "app" / "assets"
FAVICON = ASSETS / "favicon.png"

SIZE = 64          # favicon edge in pixels
SUPER = 8          # supersample factor: draw big, downscale for clean edges

BG = (11, 14, 20, 255)         # app.theme.BG
GOLD = (201, 162, 54, 255)     # bullion bar body
GOLD_LIGHT = (235, 203, 110, 255)  # highlight
RING = (212, 175, 55, 90)      # app.theme.ACCENT at low alpha

# Bar geometry, in the same 64x64 coordinate space as the SVGs.
BASE_BAR = [(18, 38), (46, 38), (50, 47), (14, 47)]
TOP_BAR = [(22, 27), (42, 27), (46, 38), (18, 38)]
HIGHLIGHT = [(24, 43), (40, 43)]


def draw_favicon(out: Path) -> None:
    from PIL import Image, ImageDraw

    s = SIZE * SUPER
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, s - 1, s - 1], radius=int(s * 0.22), fill=BG)
    d.ellipse([s * 0.06, s * 0.06, s * 0.94, s * 0.94],
              outline=RING, width=max(1, int(s * 0.035)))

    def scale(points):
        return [(x / 64 * s, y / 64 * s) for x, y in points]

    d.polygon(scale(BASE_BAR), fill=GOLD)
    d.polygon(scale(TOP_BAR), fill=GOLD)
    d.line(scale(HIGHLIGHT), fill=GOLD_LIGHT, width=max(1, int(s * 0.03)))

    out.parent.mkdir(parents=True, exist_ok=True)
    img.resize((SIZE, SIZE), Image.LANCZOS).save(out, "PNG")


def validate() -> list[str]:
    """Return a list of problems found in the artwork set ([] when clean)."""
    sys.path.insert(0, str(ROOT))
    from app import artwork

    problems: list[str] = []
    svgs = sorted(ASSETS.glob("*.svg"))
    if not svgs:
        problems.append(f"no SVG assets found in {ASSETS}")
    for path in svgs:
        text = path.read_text(encoding="utf-8")
        try:
            ET.parse(path)
        except ET.ParseError as exc:
            problems.append(f"{path.name}: invalid SVG/XML ({exc})")
            continue
        if path.stat().st_size < 200:
            problems.append(f"{path.name}: suspiciously small ({path.stat().st_size} bytes)")
        for bad in artwork.palette_violations(text):
            problems.append(f"{path.name}: off-palette colour {bad} (gold and red only)")

    wanted = set(artwork.PAGE_ART.values()) | {artwork.LOGO, artwork.HERO, artwork.EMPTY}
    for name in sorted(wanted):
        if not (ASSETS / name).is_file():
            problems.append(f"{name}: referenced by app.artwork but missing")

    if FAVICON.is_file():
        from PIL import Image

        with Image.open(FAVICON) as im:
            if im.size != (SIZE, SIZE):
                problems.append(f"favicon.png: expected {SIZE}x{SIZE}, got {im.size}")
    else:
        problems.append("favicon.png: not generated yet")

    return problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="validate only, do not regenerate the favicon")
    args = ap.parse_args()

    if not args.check:
        draw_favicon(FAVICON)
        print(f"wrote {FAVICON.relative_to(ROOT)} ({FAVICON.stat().st_size} bytes)")

    problems = validate()
    for p in problems:
        print(f"[FAIL] {p}")
    if problems:
        return 1
    n = len(list(ASSETS.glob("*.svg")))
    print(f"[ok] {n} SVGs parse, all referenced artwork present, favicon {SIZE}x{SIZE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
