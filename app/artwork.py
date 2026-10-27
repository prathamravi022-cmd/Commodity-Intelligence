"""Domain artwork for the dashboard — bullion, MCX futures and vault motifs.

The SVG files in ``app/assets`` are the source of truth: plain, hand-editable
vector art drawn for this project (gold bars, settlement candles, futures
curve, expiry coin). Small icons stay crisp at any DPI and cost ~1 KB each.

Photography lives in ``app/static/photos`` and is described by ``PHOTOS``. Those
are licensed third-party photographs, so every entry carries its author,
licence and Commons file page, and every use carries a credit line. The files
are built by ``tools/build_photos.py``; nothing is fetched at runtime.

Photographs are **background layers only** — the canvas behind the whole app,
the Overview band, the closing band, and one frame behind each contract card.
Nothing here returns an ``<img>`` for a photograph: a figure is never asked to
sit on top of one. The SVG motifs in ``app/assets`` are the only images the
markup places, and they are inlined as ``data:`` URIs because a markdown block
would resolve a file path against the browser URL rather than the app root.
``tools/make_artwork.py`` regenerates the PNG favicon from the same motif set.
"""
from __future__ import annotations

import base64
import colorsys
import re
from functools import lru_cache
from pathlib import Path

ASSETS = Path(__file__).resolve().parent / "assets"

# ``page_header(title)`` value -> icon file in app/assets. Keys must match the
# navigation registry in app.components.NAV_PAGES; a test enforces that.
PAGE_ART: dict[str, str] = {
    "Overview": "icon-overview.svg",
    "Gold Contracts": "icon-curve.svg",
    "Price Comparison": "icon-prices.svg",
    "Spread Analytics": "icon-spreads.svg",
    "Signal Explorer": "icon-alerts.svg",
    "Backtesting": "icon-backtest.svg",
    "Data Quality": "icon-quality.svg",
    "Methodology": "icon-methodology.svg",
    "Settings": "icon-settings.svg",
}

LOGO = "logo-bullion.svg"
HERO = "hero-bullion.svg"
EMPTY = "empty-vault.svg"
FAVICON = "favicon.png"

# Which bullion frame stands behind which contract card. Kept here, next to
# ``PHOTOS``, so a card cannot drift to another product's picture. The numbers
# always come from config/config.yaml; the picture is a lit background layer
# reduced to a texture, not an illustration of the specification.
CONTRACT_PHOTO: dict[str, str] = {
    "GOLDM": "contract-goldm",
    "GOLDTEN": "contract-goldten",
    "GOLDGUINEA": "contract-goldguinea",
    "GOLDPETAL": "contract-goldpetal",
}


def contract_photo(symbol: str) -> str:
    """Registered photograph stem for a contract symbol ("" when none)."""
    return CONTRACT_PHOTO.get(symbol, "")


def contract_background(symbol: str, width: int = 640) -> str:
    """``url()``-ready background for a contract card ("" when unregistered)."""
    return photo_url(contract_photo(symbol), width)


@lru_cache(maxsize=None)
def data_uri(name: str) -> str:
    """``app/assets/<name>`` as a base64 data URI (empty string if absent)."""
    path = ASSETS / name
    if not path.is_file():
        return ""
    mime = "image/png" if path.suffix.lower() == ".png" else "image/svg+xml"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


def img(name: str, alt: str = "", cls: str = "", width: int | None = None) -> str:
    """An ``<img>`` tag for an asset, or "" when the asset is missing.

    Missing artwork degrades to plain text rather than a broken image, so the
    dashboard still renders if someone strips the assets folder.
    """
    uri = data_uri(name)
    if not uri:
        return ""
    attrs = [f'src="{uri}"', f'alt="{alt}"']
    if cls:
        attrs.append(f'class="{cls}"')
    if width:
        attrs.append(f'width="{width}" height="{width}"')
    return f"<img {' '.join(attrs)}>"


def art_for(page_title: str) -> str:
    """Icon <img> tag for a page title ("" when the page has no artwork)."""
    name = PAGE_ART.get(page_title)
    return img(name, alt="", cls="ph-icon") if name else ""


def favicon_path() -> str:
    """Path to the PNG favicon, or "" when it has not been generated."""
    path = ASSETS / FAVICON
    return str(path) if path.is_file() else ""


# -------------------------------------------------------------------------
# Photography
# -------------------------------------------------------------------------
# Streamlit serves app/static/ at /app/static/ (server.enableStaticServing), so
# photographs cost one cacheable HTTP request instead of base64 bloat in every
# rerun. Registration is explicit: a file with no entry here is never shipped to
# the page, and a test fails if an entry has no file.
PHOTO_PREFIX = "/app/static/photos"


def background_url(stem: str, width: int | None = None) -> str:
    """``url()``-ready URL for a background asset (same files as ``photo_url``)."""
    return photo_url(stem, width)

PHOTOS: dict[str, dict] = {
    "contracts-banner": {
        "widths": (1600, 800),
        "ratio": (24, 10),
        "alt": ("A cast gold ingot and a minted gold bar photographed on a dark "
                "surface."),
        "title": "Gold ingot and bar of the Banque de France",
        "author": "Ibex73",
        "licence": "CC BY 4.0",
        "licence_url": "https://creativecommons.org/licenses/by/4.0/",
        "page": ("https://commons.wikimedia.org/wiki/File:Gold_ingot_and_bar_of_"
                 "Banque_de_France.jpg"),
        "role": "Gold Contracts header background — the metal the four contracts price",
    },
    "contract-goldm": {
        "widths": (640, 320),
        "ratio": (4, 3),
        "alt": ("A minted 100 gram gold bar sealed in a numbered assay card, the "
                "contract the 100 g specification describes."),
        "title": "100 g gold ingot, Perth Mint",
        "author": "B7khSy",
        "licence": "CC BY 3.0",
        "licence_url": "https://creativecommons.org/licenses/by/3.0/",
        "page": "https://commons.wikimedia.org/wiki/File:Gold_Ingot_100g_Perth_Mint.JPG",
        "role": "GOLDM (100 g) card background — minted bar in an assay card",
    },
    "contract-goldten": {
        "widths": (640, 320),
        "ratio": (4, 3),
        "alt": ("Five small minted gold bars from different refiners laid side by side "
                "on a white surface."),
        "title": "1 oz fine-gold bars from five refiners",
        "author": "Rohkroh",
        "licence": "CC BY-SA 4.0",
        "licence_url": "https://creativecommons.org/licenses/by-sa/4.0/",
        "page": ("https://commons.wikimedia.org/wiki/File:Enu-1-oz-Gold-Bar-9999-"
                 "1009-20000-2.jpg"),
        "role": "GOLDTEN (10 g) card background — small minted bars, one per refiner",
    },
    "contract-goldguinea": {
        "widths": (640, 320),
        "ratio": (4, 3),
        "alt": "A struck gold coin shown on a black background.",
        "title": "Two 20 krone gold coins",
        "author": "Anonimski",
        "licence": "CC0 1.0",
        "licence_url": "https://creativecommons.org/publicdomain/zero/1.0/",
        "page": "https://commons.wikimedia.org/wiki/File:Two_20kr_gold_coins.png",
        "role": "GOLDGUINEA (8 g) card background — struck coin, the oldest contract form",
    },
    "contract-goldpetal": {
        "widths": (640, 320),
        "ratio": (4, 3),
        "alt": ("A close macro of a single gold bar filling the frame, the smallest "
                "tradable unit in the set."),
        "title": "Gold ingot on white background",
        "author": "Szaaman",
        "licence": "Public domain",
        "licence_url": "https://commons.wikimedia.org/wiki/Commons:Copyright_tags",
        "page": ("https://commons.wikimedia.org/wiki/File:Gold_Ingot_on_white_"
                 "background.jpg"),
        "role": "GOLDPETAL (1 g) card background — a bar at full frame, the smallest contract",
    },
    "quality-assay": {
        "widths": (1280, 800),
        "ratio": (16, 9),
        "alt": ("A one gram gold bar sealed inside a printed assay card, the "
                "hallmark and serial number visible on the card."),
        "title": "1 g gold bullion in an assay card",
        "author": "Kjmonkey",
        "licence": "CC0 1.0",
        "licence_url": "https://creativecommons.org/publicdomain/zero/1.0/",
        "page": ("https://commons.wikimedia.org/wiki/File:Goldas_1g_gold_bullion_"
                 "in_assay_card.jpg"),
        "role": ("Data Quality header background — a sealed assay card stands for "
                 "the hallmark-and-checksum discipline the page applies to every row"),
    },
    "method-museum": {
        "widths": (1600, 800),
        "ratio": (24, 10),
        "alt": ("A large cast gold bar displayed behind glass at a money museum, "
                "with its museum label card beside it."),
        "title": "Bullion gold bar at the Swiss Money Museum",
        "author": "Ank Kumar",
        "licence": "CC BY-SA 4.0",
        "licence_url": "https://creativecommons.org/licenses/by-sa/4.0/",
        "page": ("https://commons.wikimedia.org/wiki/File:Bullion_Gold_bar_at_Swiss_"
                 "Money_Museum_(Ank_Kumar,_Infosys).jpg"),
        "role": ("Methodology header background — a catalogued specimen with its "
                 "label: the documented, attributable version of the number"),
    },
    # The two background assets. They are registered here like any other image so
    # their licences appear in the same credit list, but they are applied as CSS
    # backgrounds (see app/theme.py) and never as content: no data sits on top of
    # a photograph without a solid or near-solid surface between them.
    "backdrop-hero": {
        "widths": (1600, 960),
        "ratio": (16, 9),
        "alt": ("A stacked pile of minted gold bars against a pale surface, used as "
                "the Overview band backdrop under a navy scrim."),
        "title": "Gold bullion bars",
        "author": "Stevebidmead",
        "licence": "CC0 1.0",
        "licence_url": "https://creativecommons.org/publicdomain/zero/1.0/",
        "page": "https://commons.wikimedia.org/wiki/File:Gold_bullion_bars.jpg",
        "role": "Overview hero band background, under a navy gradient",
    },
    "tile-gold": {
        "widths": (512, 256),
        "ratio": (1, 1),
        "alt": ("A seamless mirror-tiled crop of a gold bar surface, used as a faint "
                "texture behind contract cards and the footer strip."),
        "title": "Gold ingot on white background",
        "author": "Szaaman",
        "licence": "Public domain",
        "licence_url": "https://commons.wikimedia.org/wiki/Commons:Copyright_tags",
        "page": ("https://commons.wikimedia.org/wiki/File:Gold_Ingot_on_white_"
                 "background.jpg"),
        "role": "Seamless gold texture behind contract cards and the footer",
    },
}

# Every registered photograph is applied as a CSS background layer. The set is
# kept explicit so a future entry has to be classified rather than quietly
# becoming an inline image again.
BACKGROUNDS: frozenset[str] = frozenset(PHOTOS)


def photo_url(stem: str, width: int | None = None) -> str:
    """Public URL for a photo (largest variant when ``width`` is omitted)."""
    meta = PHOTOS.get(stem)
    if not meta:
        return ""
    return f"{PHOTO_PREFIX}/{stem}-{width or meta['widths'][0]}.webp"


def photo_credit(stem: str) -> str:
    """Visible attribution line: author, licence, and where it came from."""
    meta = PHOTOS.get(stem)
    if not meta:
        return ""
    return (f'Photo: {meta["author"]} · '
            f'<a href="{meta["licence_url"]}" target="_blank" '
            f'rel="noopener">{meta["licence"]}</a> · '
            f'<a href="{meta["page"]}" target="_blank" rel="noopener">Wikimedia '
            f'Commons</a>')


def credit_lines() -> list[str]:
    """Markdown credit list for the Methodology page, one line per photograph."""
    return [f"{meta['title']} — {meta['author']}, "
            f"[{meta['licence']}]({meta['licence_url']}), "
            f"[Wikimedia Commons]({meta['page']}) · {meta['role']}"
            for meta in PHOTOS.values()]


# ---- Palette lock --------------------------------------------------------
# The product palette has four hue families and nothing else: red and green are
# *semantic* (down/long, up/short), gold is the brand accent, navy is the
# navigation rail and the fourth contract series. Anything outside these bands
# — purple, teal, cyan, stock-Plotly blue — is a design leak, so it fails here.
# Colours below the saturation floor are neutrals and pass.
ALLOWED_HUES: tuple[tuple[float, float], ...] = (
    (340.0, 360.0), (0.0, 15.0),   # red: negative / short
    (20.0, 58.0),                  # gold, amber, bronze: brand + contracts
    (140.0, 178.0),                # green: positive / long
    (200.0, 250.0),                # navy / slate: rail + contracts
)
SATURATION_FLOOR = 0.12

_HEX_RE = re.compile(r"#([0-9A-Fa-f]{3}|[0-9A-Fa-f]{6})\b")
_RGBA_RE = re.compile(r"rgba?\(([^)]+)\)")


def _hue_sat(r: int, g: int, b: int) -> tuple[float, float]:
    hue, _, sat = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
    return hue * 360.0, sat


def _in_palette(hue: float, sat: float) -> bool:
    if sat < SATURATION_FLOOR:
        return True
    return any(lo <= hue <= hi for lo, hi in ALLOWED_HUES)


def palette_violations(text: str, allow_transparent: float = 0.05) -> list[str]:
    """Colour literals in ``text`` outside the four-family palette."""
    found: list[str] = []
    for match in _HEX_RE.finditer(text):
        raw = match.group(1)
        if len(raw) == 3:
            raw = "".join(c * 2 for c in raw)
        r, g, b = (int(raw[i:i + 2], 16) for i in (0, 2, 4))
        hue, sat = _hue_sat(r, g, b)
        if not _in_palette(hue, sat):
            found.append(f"#{raw} (hue {hue:.0f}°, sat {sat:.2f})")
    for match in _RGBA_RE.finditer(text):
        parts = [p.strip() for p in match.group(1).split(",")]
        if len(parts) < 3:
            continue
        try:
            r, g, b = (float(p) for p in parts[:3])
            alpha = float(parts[3]) if len(parts) > 3 else 1.0
        except ValueError:
            continue
        if alpha <= allow_transparent:
            continue
        hue, sat = _hue_sat(round(r), round(g), round(b))
        if not _in_palette(hue, sat):
            found.append(f"{match.group(0)} (hue {hue:.0f}°, sat {sat:.2f})")
    return found
