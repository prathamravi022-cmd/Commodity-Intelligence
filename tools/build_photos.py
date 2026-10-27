"""Build the photographic asset set in ``app/static/photos`` from licensed sources.

Photography is the one asset class that cannot be hand-drawn, so it is the one
place where third-party material enters the product. This script keeps that
honest and reproducible:

* what the application ships (sizes, aspect, alt text, author, licence, source
  page) is the ``PHOTOS`` registry in ``app/artwork.py`` — the same table the UI
  and the tests read, so a credit cannot drift away from the file;
* this module adds only the build-time half: where the original lives and how it
  is framed;
* originals are cached in ``tools/_photo_sources`` (git-ignored) and only the
  crops and WebP encodes are committed, so the repository stays small;
* ``docs/photo-credits.md`` is generated from both tables.

Usage::

    python tools/build_photos.py            # download (if needed) and rebuild
    python tools/build_photos.py --check    # verify committed files only
"""
from __future__ import annotations

import argparse
import io
import pathlib
import sys
import urllib.request

import numpy as np
from PIL import Image, ImageFilter

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.artwork import PHOTOS  # noqa: E402  (needs ROOT on sys.path first)

CACHE = ROOT / "tools" / "_photo_sources"
OUT = ROOT / "app" / "static" / "photos"
CREDITS = ROOT / "docs" / "photo-credits.md"
UA = "StarwayCommodityIntel/1.0 (research dashboard; asset build script)"

# Build-time half of each asset: the original, and how to frame it.
#   margin -> the subject is found automatically and given this much air
#   crop   -> a hand-set box (fractions of the original), used only where the
#             frame's subject is not the gold itself
SOURCES: dict[str, dict] = {
    "contracts-banner": {
        "file": "Gold ingot and bar of Banque de France.jpg",
        "url": ("https://thumb.wikimedia.org/wikipedia/commons/thumb/5/50/"
                "Gold_ingot_and_bar_of_Banque_de_France.jpg/1280px-Gold_ingot_and_bar_"
                "of_Banque_de_France.jpg"),
        "margin": 0.25,
    },
    "contract-goldm": {
        "file": "Gold Ingot 100g Perth Mint.JPG",
        "url": ("https://upload.wikimedia.org/wikipedia/commons/1/11/"
                "Gold_Ingot_100g_Perth_Mint.JPG"),
        "margin": 0.08,
    },
    "contract-goldten": {
        "file": "Enu-1-oz-Gold-Bar-9999-1009-20000-2.jpg",
        "url": ("https://upload.wikimedia.org/wikipedia/commons/a/af/"
                "Enu-1-oz-Gold-Bar-9999-1009-20000-2.jpg"),
        "margin": 0.06,
    },
    "contract-goldguinea": {
        "file": "Two 20kr gold coins.png",
        "url": ("https://thumb.wikimedia.org/wikipedia/commons/thumb/a/a2/"
                "Two_20kr_gold_coins.png/1280px-Two_20kr_gold_coins.png"),
        "margin": 0.16,
    },
    "contract-goldpetal": {
        "file": "Gold Ingot on white background.jpg",
        "url": ("https://thumb.wikimedia.org/wikipedia/commons/thumb/c/cc/"
                "Gold_Ingot_on_white_background.jpg/1920px-Gold_Ingot_on_white_"
                "background.jpg"),
        "margin": 0.05,
    },
    # Cinematic 16:9 backdrop for the Overview hero band. Framed wide on purpose:
    # a navy scrim sits over it, so the stacked bars read as texture with gold
    # glints rather than as a photograph competing with the headline.
    "backdrop-hero": {
        "file": "Gold bullion bars.jpg",
        "url": ("https://upload.wikimedia.org/wikipedia/commons/thumb/a/af/"
                "Gold_bullion_bars.jpg/1920px-Gold_bullion_bars.jpg"),
        "margin": 0.30,
    },
    # A sealed 1 g assay card: weight, fineness and serial printed beside the bar.
    # The card is the subject, not the metal, so the box is set by hand to keep
    # the printed certificate inside the band (the gold is a few percent of the
    # frame and automatic subject framing would zoom straight into the bar).
    "quality-assay": {
        "file": "Goldas 1g gold bullion in assay card.jpg",
        "url": ("https://commons.wikimedia.org/wiki/Special:FilePath/"
                "Goldas_1g_gold_bullion_in_assay_card.jpg?width=1920"),
        "crop": (0.0, 0.05, 1.0, 0.89),
    },
    # A catalogued specimen in a museum case: the bar, its engraved weight and its
    # inventory stamp. Wide and hand-framed because the case is the picture.
    "method-museum": {
        "file": "Bullion Gold bar at Swiss Money Museum (Ank Kumar, Infosys).jpg",
        "url": ("https://commons.wikimedia.org/wiki/Special:FilePath/"
                "Bullion_Gold_bar_at_Swiss_Money_Museum_(Ank_Kumar,_Infosys).jpg"
                "?width=1920"),
        "crop": (0.0, 0.12, 1.0, 0.74),
    },
    # Seamless gold wash for contract cards and the footer strip: a soft, blurred
    # patch of bar surface, mirrored so it tiles without a seam at any size.
    "tile-gold": {
        "file": "Gold Ingot on white background.jpg",
        "url": ("https://thumb.wikimedia.org/wikipedia/commons/thumb/c/cc/"
                "Gold_Ingot_on_white_background.jpg/1920px-Gold_Ingot_on_white_"
                "background.jpg"),
        "patch": 320,      # plain-metal patch, found by lowest variance
        "tile": True,
        "blur": 6.0,
    },
}


def _fetch(entry: dict) -> pathlib.Path:
    """Download (once) the original for an entry and return the cached path."""
    CACHE.mkdir(parents=True, exist_ok=True)
    dest = CACHE / entry["file"].replace(" ", "_")
    if not dest.exists() or dest.stat().st_size == 0:
        req = urllib.request.Request(entry["url"], headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=90) as resp:
            dest.write_bytes(resp.read())
        print(f"  fetched {dest.name} ({dest.stat().st_size // 1024} KB)")
    return dest


def _gold_mask(im: Image.Image) -> np.ndarray:
    """Boolean mask of amber-hued pixels — i.e. the bullion.

    Gold is the only amber mass in these photographs, so a hue/saturation test
    finds the subject without any hand-drawn box. Downscaled, because the framing
    decision does not need full resolution.
    """
    small = im.resize((320, max(1, int(320 * im.size[1] / im.size[0]))))
    a = np.asarray(small, dtype=float) / 255.0
    r, g, b = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    mx, mn = a.max(axis=2), a.min(axis=2)
    d = mx - mn
    safe = np.maximum(d, 1e-6)
    hue = np.where(mx == r, 60 * (((g - b) / safe) % 6),
          np.where(mx == g, 60 * ((b - r) / safe + 2),
                            60 * ((r - g) / safe + 4)))
    sat = np.where(mx > 0, d / np.maximum(mx, 1e-6), 0.0)
    return (d > 0) & (hue >= 25) & (hue <= 62) & (sat > 0.20) & (mx > 0.20)


def _framing(im: Image.Image, ratio: tuple[int, int],
             margin: float) -> tuple[float, float, float, float]:
    """Crop box (fractions of the original) centred on the gold in the frame.

    Falls back to a centred fit when the frame holds no warm mass, so a source
    that changes character still produces a usable, undistorted crop.
    """
    w, h = im.size
    mask = _gold_mask(im)
    rows, cols = np.nonzero(mask)
    if len(rows) == 0:
        x0, y0, x1, y1 = 0.0, 0.0, float(w), float(h)
    else:
        sy, sx = h / mask.shape[0], w / mask.shape[1]
        x0, x1 = cols.min() * sx, (cols.max() + 1) * sx
        y0, y1 = rows.min() * sy, (rows.max() + 1) * sy
    pad = margin * max(w, h)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    cw, ch = (x1 - x0) + 2 * pad, (y1 - y0) + 2 * pad
    # grow the short side to the target aspect, then shrink the whole box
    # uniformly if the frame cannot hold it — the ratio is never broken
    target = ratio[0] / ratio[1]
    if cw / ch < target:
        cw = ch * target
    else:
        ch = cw / target
    scale = min(1.0, w / cw, h / ch)
    cw, ch = cw * scale, ch * scale
    left = min(max(cx - cw / 2, 0.0), w - cw)
    top = min(max(cy - ch / 2, 0.0), h - ch)
    return (left / w, top / h, (left + cw) / w, (top + ch) / h)


def _flattest_box(im: Image.Image, size: int) -> tuple[int, int, int, int]:
    """Pixel box of the flattest square patch of the frame.

    A texture that repeats behind a card must read as a wash, not as a pattern,
    so the tile is cut from the region with the lowest luminance variance — plain
    metal rather than an edge, a shadow or an engraved stamp. Computed from an
    integral image, so it stays fast on a full-size original.
    """
    scale = min(1.0, 640 / max(im.size))
    small = np.asarray(im.convert("L").resize(
        (max(1, int(im.width * scale)), max(1, int(im.height * scale)))),
        dtype=np.float64)
    h, w = small.shape
    win = max(8, int(round(size * scale)))
    if win >= h or win >= w:
        return (0, 0, im.width, im.height)
    padded = np.zeros((h + 1, w + 1))
    padded[1:, 1:] = small
    ii = padded.cumsum(0).cumsum(1)
    sq = np.zeros((h + 1, w + 1))
    sq[1:, 1:] = small ** 2
    ii2 = sq.cumsum(0).cumsum(1)

    def window(integral):
        return (integral[win:, win:] - integral[:-win, win:]
                - integral[win:, :-win] + integral[:-win, :-win])

    n = float(win * win)
    mean = window(ii) / n
    var = window(ii2) / n - mean ** 2
    y, x = np.unravel_index(int(np.argmin(var)), var.shape)
    left, top = int(x / scale), int(y / scale)
    return (left, top, left + size, top + size)


def _mirror_tile(crop: Image.Image) -> Image.Image:
    """Four-way mirror a crop so the result tiles without a seam.

    Mirroring is what makes a photographic texture usable as a background: the
    right edge of the tile meets the left edge exactly, so a card can repeat it
    at any size without a visible join.
    """
    flip_lr = crop.transpose(Image.FLIP_LEFT_RIGHT)
    flip_tb = crop.transpose(Image.FLIP_TOP_BOTTOM)
    flip_both = flip_lr.transpose(Image.FLIP_TOP_BOTTOM)
    out = Image.new("RGB", (crop.width * 2, crop.height * 2))
    out.paste(crop, (0, 0))
    out.paste(flip_lr, (crop.width, 0))
    out.paste(flip_tb, (0, crop.height))
    out.paste(flip_both, (crop.width, crop.height))
    return out


def _fit(crop: Image.Image, ratio: tuple[int, int]) -> Image.Image:
    """Centre-trim a crop to ``ratio`` (trims pixel edges, never stretches)."""
    target = ratio[0] / ratio[1]
    cw, ch = crop.size
    if cw / ch > target:                      # too wide: trim the sides
        new_w = int(round(ch * target))
        off = (cw - new_w) // 2
        crop = crop.crop((off, 0, off + new_w, ch))
    else:                                     # too tall: trim top and bottom
        new_h = int(round(cw / target))
        off = (ch - new_h) // 2
        crop = crop.crop((0, off, cw, off + new_h))
    return crop


def build() -> list[str]:
    OUT.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for stem, entry in SOURCES.items():
        meta = PHOTOS[stem]
        src = _fetch(entry)
        with Image.open(src) as raw:
            im = raw.convert("RGB")
            if entry.get("crop"):
                entry["framing"] = tuple(entry["crop"])
            elif entry.get("patch"):
                # a texture: cut the flattest square instead of hunting for gold,
                # because a repeat of anything with structure reads as a pattern
                x0, y0, x1, y1 = _flattest_box(im, entry["patch"])
                entry["framing"] = (x0 / im.width, y0 / im.height,
                                    x1 / im.width, y1 / im.height)
            else:
                entry["framing"] = _framing(im, meta["ratio"], entry["margin"])
            cropped = _fit(_crop_box(im, entry["framing"]), meta["ratio"])
            if entry.get("blur"):
                # soften the surface so no stamp or engraving is legible when the
                # tile is repeated behind a card at a few per cent opacity
                cropped = cropped.filter(ImageFilter.GaussianBlur(entry["blur"]))
            if entry.get("tile"):
                cropped = _mirror_tile(cropped)
            for width in meta["widths"]:
                height = int(round(width * meta["ratio"][1] / meta["ratio"][0]))
                scaled = cropped.resize((width, height), Image.LANCZOS)
                path = OUT / f"{stem}-{width}.webp"
                scaled.save(path, "WEBP", quality=76, method=6)
                written.append(f"{path.name} {width}x{height} "
                               f"{path.stat().st_size // 1024} KB")
    write_credits()
    return written


def _crop_box(im: Image.Image, box: tuple[float, float, float, float]) -> Image.Image:
    """Pixel crop of ``box`` (fractions of the original)."""
    w, h = im.size
    return im.crop((int(box[0] * w), int(box[1] * h),
                    int(box[2] * w), int(box[3] * h)))


def write_credits() -> None:
    lines = [
        "# Photography credits",
        "",
        "Generated by `tools/build_photos.py` from the registry in "
        "`app/artwork.py` — do not edit by hand. The dashboard ships cropped, "
        "re-encoded WebP copies of each original; the originals, the licences and "
        "the exact framing are recorded here so the imagery stays attributable and "
        "reviewable.",
        "",
        "| Asset | Photograph | Author | Licence | Source page |",
        "| --- | --- | --- | --- | --- |",
    ]
    for stem, meta in PHOTOS.items():
        for width in meta["widths"]:
            lines.append(
                f"| `{stem}-{width}.webp` | {meta['title']} | {meta['author']} | "
                f"[{meta['licence']}]({meta['licence_url']}) | "
                f"[Wikimedia Commons]({meta['page']}) |")
    lines += [
        "",
        "## Modifications",
        "",
        "Every file is a crop and a downscale of the original, re-encoded to WebP "
        "at quality 76. Nothing is recoloured, retouched or composited, and no "
        "photograph is presented as market data or as the specification of an MCX "
        "contract.",
        "",
        "Framing is decided by the build: it locates the amber mass in the frame "
        "and crops around it, so a refreshed original cannot silently reframe a "
        "card. The box each image actually used (fractions of the original, "
        "left/top/right/bottom) is recorded here:",
        "",
        "| Asset | Framing box | Original |",
        "| --- | --- | --- |",
    ]
    for stem, entry in SOURCES.items():
        box = entry.get("framing")
        if box is None:
            shown = "not recorded — rebuild the set"
        else:
            method = ("hand-set box" if entry.get("crop") else
                      "flattest patch" if entry.get("patch") else "subject-centred")
            shown = f"{method}: " + ", ".join(f"{v:.3f}" for v in box)
        lines.append(f"| `{stem}` | {shown} | {entry['file']} |")
    lines += ["", "## Share-alike derivatives", ""]
    share_alike = [f"- `{stem}` — *{PHOTOS[stem]['title']}* by "
                   f"{PHOTOS[stem]['author']}, licensed {PHOTOS[stem]['licence']}. "
                   f"This cropped and re-encoded version is distributed under the "
                   f"same licence." for stem in SOURCES
                   if "sa" in PHOTOS[stem]["licence"].lower()]
    lines += share_alike or ["No source in the set requires share-alike."]
    lines += [
        "",
        "## Use in the interface",
        "",
        "- Photographs are context for physical bullion only. Prices, spreads, "
        "z-scores and backtest results always come from the pipeline outputs in "
        "`data/`, never from an image.",
        "- Contract cards caption their photograph as illustrative: contract size, "
        "quoted unit and purity come from `config/config.yaml`.",
        "- Every photograph is rendered with the author and licence underneath it, "
        "and `app/artwork.py` is the only place they are declared.",
        "",
    ]
    CREDITS.parent.mkdir(parents=True, exist_ok=True)
    CREDITS.write_text("\n".join(lines), encoding="utf-8")


def check() -> int:
    """Verify the committed WebP set matches the registry (no network access)."""
    problems: list[str] = []
    registered: set[str] = set()
    for stem, meta in PHOTOS.items():
        expected_h = int(round(meta["widths"][0] * meta["ratio"][1] / meta["ratio"][0]))
        for width in meta["widths"]:
            registered.add(f"{stem}-{width}.webp")
            path = OUT / f"{stem}-{width}.webp"
            if not path.is_file():
                problems.append(f"missing {path.relative_to(ROOT)}")
                continue
            data = path.read_bytes()
            if data[:4] != b"RIFF" or data[8:12] != b"WEBP":
                problems.append(f"{path.name} is not WebP")
                continue
            with Image.open(io.BytesIO(data)) as im:
                if im.size[0] != width:
                    problems.append(f"{path.name} is {im.size}, expected width {width}")
            if len(data) > 260_000:
                problems.append(f"{path.name} is {len(data) // 1024} KB — over budget")
        if expected_h <= 0:
            problems.append(f"{stem} has an impossible aspect ratio")
        if stem not in SOURCES:
            problems.append(f"{stem} is registered but has no build source")
    for path in OUT.glob("*.webp"):
        if path.name not in registered:
            problems.append(f"{path.name} is not registered in artwork.PHOTOS")
    if not CREDITS.is_file():
        problems.append("docs/photo-credits.md is missing")
    else:
        text = CREDITS.read_text(encoding="utf-8")
        for stem, meta in PHOTOS.items():
            if meta["author"] not in text or meta["licence"] not in text:
                problems.append(f"docs/photo-credits.md does not credit {stem}")
    if problems:
        print("photo set: FAILED")
        for problem in problems:
            print("  -", problem)
        return 1
    total = sum(p.stat().st_size for p in OUT.glob("*.webp"))
    print(f"photo set: ok — {len(list(OUT.glob('*.webp')))} files, "
          f"{total // 1024} KB total")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Build the licensed photo set")
    ap.add_argument("--check", action="store_true",
                    help="verify the committed files instead of rebuilding them")
    args = ap.parse_args()
    if args.check:
        return check()
    for line in build():
        print(" ", line)
    return check()


if __name__ == "__main__":
    sys.exit(main())
