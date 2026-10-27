"""Generate the per-page canvas scenes in ``app/static/backgrounds/``.

Each page of the workspace gets its own vector scene, drawn here rather than
photographed: the artwork is deterministic, a few kilobytes, palette-locked
(navy, gold, neutrals — no other hue family), and shipped as a file, so nothing
is fetched at runtime and no licence is involved.

The scenes are *atmosphere*: they sit under a navy wash at low contrast behind
the glass panels. They never encode a number, a price or a result — a wave, a
grid of nodes and a set of folds are shapes, not data. Where a page wants
photographic realism it gets one of the licensed bullion frames from
``app.artwork.PHOTOS`` underneath its scene, chosen in ``app/backgrounds.py``.

The files are served by Streamlit's static server (``server.enableStaticServing``,
see ``.streamlit/config.toml``), so the stylesheet can point at a cacheable URL
instead of inlining a base64 copy of every scene into every page. Only the scene
of the page being read is ever downloaded.

Run: ``python tools/make_backgrounds.py``
Check: ``python tools/make_backgrounds.py --check``
"""
from __future__ import annotations

import math
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "app" / "static" / "backgrounds"

W, H = 1600, 900

# Palette (kept inside app.artwork.ALLOWED_HUES: gold 20–58°, navy 200–250°).
GOLD = "#E8CD8A"
GOLD_BRIGHT = "#F4DFA5"
GOLD_DEEP = "#8A6E3A"
NAVY_DEEP = "#070B14"
NAVY = "#101A2C"
STEEL = "#8FA9C9"


def _svg(defs: str, body: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
        f'width="{W}" height="{H}" preserveAspectRatio="xMidYMid slice" '
        f'role="img" aria-hidden="true">\n'
        f"  <defs>\n{defs}  </defs>\n{body}</svg>\n"
    )


def _smooth_path(points: list[tuple[float, float]]) -> str:
    """Catmull-Rom → cubic bezier path through every point."""
    if not points:
        return ""
    d = [f"M {points[0][0]:.1f} {points[0][1]:.1f}"]
    for i in range(len(points) - 1):
        p0 = points[i - 1] if i > 0 else points[i]
        p1, p2 = points[i], points[i + 1]
        p3 = points[i + 2] if i + 2 < len(points) else p2
        c1 = (p1[0] + (p2[0] - p0[0]) / 6.0, p1[1] + (p2[1] - p0[1]) / 6.0)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6.0, p2[1] - (p3[1] - p1[1]) / 6.0)
        d.append(f"C {c1[0]:.1f} {c1[1]:.1f} {c2[0]:.1f} {c2[1]:.1f} "
                 f"{p2[0]:.1f} {p2[1]:.1f}")
    return " ".join(d)


# -------------------------------------------------------------------------
# Scenes
# -------------------------------------------------------------------------
def overview() -> str:
    """Ridgelines: the shape of a market read as landscape, not a price."""
    rng = random.Random(11)
    defs = (
        f'<linearGradient id="ridge" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{GOLD}" stop-opacity="0.20"/>'
        f'<stop offset="0.55" stop-color="{NAVY}" stop-opacity="0.55"/>'
        f'<stop offset="1" stop-color="{NAVY_DEEP}" stop-opacity="0.85"/>'
        f"</linearGradient>"
        f'<linearGradient id="rim" x1="0" y1="0" x2="1" y2="0">'
        f'<stop offset="0" stop-color="{GOLD}" stop-opacity="0.05"/>'
        f'<stop offset="0.6" stop-color="{GOLD_BRIGHT}" stop-opacity="0.55"/>'
        f'<stop offset="1" stop-color="{GOLD}" stop-opacity="0.10"/>'
        f"</linearGradient>"
    )
    body = []
    # faint vertical rules: a chart's worth of structure, no labels
    for x in range(0, W, 100):
        body.append(f'<line x1="{x}" y1="0" x2="{x}" y2="{H}" '
                    f'stroke="{STEEL}" stroke-opacity="0.035" stroke-width="1"/>')
    for layer in range(6):
        base = 430 + layer * 78
        pts = []
        for step in range(21):
            x = step * W / 20
            y = (base
                 - 120 * math.sin(step / 3.1 + layer * 0.7)
                 - 46 * math.sin(step / 1.3 + layer)
                 + rng.uniform(-10, 10))
            pts.append((x, y))
        d = _smooth_path(pts)
        body.append(f'<path d="{d} L {W} {H} L 0 {H} Z" fill="url(#ridge)" '
                    f'fill-opacity="{0.55 - layer * 0.06:.2f}"/>')
        body.append(f'<path d="{d}" fill="none" stroke="url(#rim)" '
                    f'stroke-width="{1.6 if layer == 0 else 1}" '
                    f'stroke-opacity="{0.9 - layer * 0.13:.2f}"/>')
    return _svg(defs, "".join(body))


def contracts() -> str:
    """Vault bars: three ingots in isometric profile, seen from above."""
    defs = (
        f'<linearGradient id="top" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset="0" stop-color="{GOLD_BRIGHT}" stop-opacity="0.42"/>'
        f'<stop offset="0.55" stop-color="{GOLD}" stop-opacity="0.20"/>'
        f'<stop offset="1" stop-color="{GOLD_DEEP}" stop-opacity="0.10"/>'
        f"</linearGradient>"
        f'<linearGradient id="face" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{GOLD_DEEP}" stop-opacity="0.30"/>'
        f'<stop offset="1" stop-color="{NAVY_DEEP}" stop-opacity="0.55"/>'
        f"</linearGradient>"
    )
    body = []
    bar_w, bar_h, skew = 430, 120, 96
    for i, (x, y) in enumerate(((180, 650), (520, 470), (860, 290))):
        x2 = x + bar_w
        body.append(
            f'<path d="M {x} {y} L {x + skew} {y - bar_h} L {x2 + skew} {y - bar_h} '
            f'L {x2} {y} Z" fill="url(#top)" stroke="{GOLD}" '
            f'stroke-opacity="0.22" stroke-width="1.2"/>'
        )
        body.append(
            f'<path d="M {x} {y} L {x2} {y} L {x2} {y + 62} L {x} {y + 62} Z" '
            f'fill="url(#face)" stroke="{GOLD_DEEP}" stroke-opacity="0.16" '
            f'stroke-width="1"/>'
        )
        body.append(
            f'<path d="M {x2} {y} L {x2 + skew} {y - bar_h} L {x2 + skew} {y - bar_h + 62} '
            f'L {x2} {y + 62} Z" fill="{NAVY}" fill-opacity="0.35" '
            f'stroke="{GOLD_DEEP}" stroke-opacity="0.12" stroke-width="1"/>'
        )
    # floor shadow: the bars sit on something
    body.append(
        f'<ellipse cx="740" cy="800" rx="640" ry="90" fill="{GOLD}" '
        f'fill-opacity="0.05"/>'
    )
    return _svg(defs, "".join(body))


def prices() -> str:
    """Two interleaved series over a dotted measure grid."""
    rng = random.Random(23)
    defs = (
        f'<linearGradient id="seriesA" x1="0" y1="0" x2="1" y2="0">'
        f'<stop offset="0" stop-color="{GOLD}" stop-opacity="0.06"/>'
        f'<stop offset="0.5" stop-color="{GOLD_BRIGHT}" stop-opacity="0.55"/>'
        f'<stop offset="1" stop-color="{GOLD}" stop-opacity="0.10"/>'
        f"</linearGradient>"
        f'<linearGradient id="seriesB" x1="0" y1="0" x2="1" y2="0">'
        f'<stop offset="0" stop-color="{STEEL}" stop-opacity="0.05"/>'
        f'<stop offset="0.55" stop-color="{STEEL}" stop-opacity="0.42"/>'
        f'<stop offset="1" stop-color="{STEEL}" stop-opacity="0.06"/>'
        f"</linearGradient>"
        # one tiled pattern instead of ~330 <circle> elements: same measure
        # grid on screen, a fraction of the bytes
        f'<pattern id="dots" width="64" height="64" patternUnits="userSpaceOnUse">'
        f'<circle cx="32" cy="32" r="1.4" fill="{STEEL}" fill-opacity="0.10"/>'
        f"</pattern>"
    )
    body = [f'<rect width="{W}" height="{H}" fill="url(#dots)"/>']
    for grad, amp, phase, width, op in (("seriesA", 150, 0.0, 2.2, 0.9),
                                        ("seriesB", 96, 1.9, 1.5, 0.7)):
        pts = []
        for step in range(25):
            x = step * W / 24
            y = (H * 0.52
                 - amp * math.sin(step / 2.6 + phase)
                 - rng.uniform(0, 40))
            pts.append((x, y))
        d = _smooth_path(pts)
        body.append(f'<path d="{d}" fill="none" stroke="url(#{grad})" '
                    f'stroke-width="{width}" stroke-opacity="{op}"/>')
        for x, y in pts[::4]:
            body.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" '
                        f'fill="{GOLD}" fill-opacity="0.35"/>')
    return _svg(defs, "".join(body))


def spreads() -> str:
    """A corridor between two bounds, with a distribution column at the right."""
    rng = random.Random(37)
    defs = (
        f'<linearGradient id="band" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{GOLD}" stop-opacity="0.16"/>'
        f'<stop offset="0.5" stop-color="{GOLD}" stop-opacity="0.05"/>'
        f'<stop offset="1" stop-color="{GOLD}" stop-opacity="0.16"/>'
        f"</linearGradient>"
    )
    body = [f'<rect x="0" y="330" width="{W}" height="240" fill="url(#band)"/>']
    for y in (330, 570):
        body.append(f'<line x1="0" y1="{y}" x2="{W}" y2="{y}" stroke="{GOLD}" '
                    f'stroke-opacity="0.30" stroke-width="1.4" '
                    f'stroke-dasharray="10 9"/>')
    pts = []
    for step in range(25):
        x = step * W / 24
        y = 450 + 90 * math.sin(step / 2.2) + rng.uniform(-14, 14)
        pts.append((x, y))
    body.append(f'<path d="{_smooth_path(pts)}" fill="none" '
                f'stroke="{GOLD_BRIGHT}" stroke-opacity="0.42" stroke-width="1.8"/>')
    # z-score style columns on the right edge: bars, not values
    for i in range(14):
        h = 30 + abs(math.sin(i / 1.7)) * 210
        x = W - 470 + i * 30
        body.append(f'<rect x="{x}" y="{620 - h}" width="13" height="{h:.0f}" '
                    f'rx="3" fill="{STEEL}" fill-opacity="0.16"/>')
    body.append(f'<line x1="{W - 470}" y1="622" x2="{W - 40}" y2="622" '
                f'stroke="{STEEL}" stroke-opacity="0.18"/>')
    return _svg(defs, "".join(body))


def signals() -> str:
    """A constellation of nodes: pattern-finding, drawn as a network."""
    rng = random.Random(53)
    defs = (
        f'<radialGradient id="halo">'
        f'<stop offset="0" stop-color="{GOLD_BRIGHT}" stop-opacity="0.40"/>'
        f'<stop offset="1" stop-color="{GOLD}" stop-opacity="0"/>'
        f"</radialGradient>"
    )
    nodes = []
    for row in range(5):
        for col in range(9):
            x = 110 + col * 172 + rng.uniform(-30, 30)
            y = 140 + row * 160 + rng.uniform(-26, 26)
            nodes.append((x, y))
    body = []
    for i, (x1, y1) in enumerate(nodes):
        for j in range(i + 1, len(nodes)):
            x2, y2 = nodes[j]
            dist = math.hypot(x2 - x1, y2 - y1)
            if dist < 200:
                body.append(
                    f'<line x1="{x1:.0f}" y1="{y1:.0f}" x2="{x2:.0f}" y2="{y2:.0f}" '
                    f'stroke="{STEEL}" stroke-opacity="0.085" stroke-width="1"/>'
                )
    lit = {2, 13, 21, 30, 38}
    for index, (x, y) in enumerate(nodes):
        if index in lit:
            body.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="46" fill="url(#halo)"/>')
            body.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4.6" '
                        f'fill="{GOLD_BRIGHT}" fill-opacity="0.85"/>')
        else:
            body.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.6" '
                        f'fill="{STEEL}" fill-opacity="0.30"/>')
    return _svg(defs, "".join(body))


def backtest() -> str:
    """Walk-forward folds: a partition of history into test windows."""
    defs = (
        f'<linearGradient id="fold" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset="0" stop-color="{GOLD}" stop-opacity="0.18"/>'
        f'<stop offset="1" stop-color="{NAVY}" stop-opacity="0.30"/>'
        f"</linearGradient>"
    )
    body = []
    # partition rail: the timeline the folds are cut from
    body.append(f'<line x1="80" y1="770" x2="{W - 80}" y2="770" '
                f'stroke="{STEEL}" stroke-opacity="0.22"/>')
    for i in range(9):
        x = 80 + i * ((W - 160) / 8)
        body.append(f'<line x1="{x:.0f}" y1="764" x2="{x:.0f}" y2="776" '
                    f'stroke="{STEEL}" stroke-opacity="0.22"/>')
    for i in range(5):
        x = 150 + i * 250
        y = 620 - i * 96
        w = 250 + i * 26
        h = 74
        body.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" '
                    f'fill="url(#fold)" stroke="{GOLD}" stroke-opacity="0.24"/>')
        body.append(f'<rect x="{x + w * 0.56:.0f}" y="{y}" width="{w * 0.44:.0f}" '
                    f'height="{h}" rx="8" fill="{GOLD}" fill-opacity="0.10"/>')
        body.append(f'<line x1="{x + w * 0.56:.0f}" y1="{y}" '
                    f'x2="{x + w * 0.56:.0f}" y2="{y + h}" stroke="{GOLD}" '
                    f'stroke-opacity="0.35" stroke-dasharray="4 4"/>')
    return _svg(defs, "".join(body))


def quality() -> str:
    """A checksum lattice: every cell checked, a few flagged for attention."""
    defs = (
        f'<linearGradient id="scan" x1="0" y1="0" x2="1" y2="0">'
        f'<stop offset="0" stop-color="{GOLD}" stop-opacity="0"/>'
        f'<stop offset="0.5" stop-color="{GOLD_BRIGHT}" stop-opacity="0.30"/>'
        f'<stop offset="1" stop-color="{GOLD}" stop-opacity="0"/>'
        f"</linearGradient>"
    )
    rng = random.Random(71)
    body = []
    cols, rows, cw, ch = 16, 8, 78, 70
    ox, oy = 100, 170
    flagged = {(2, 3), (7, 5), (11, 2), (13, 6)}
    for r in range(rows):
        for c in range(cols):
            x = ox + c * cw
            y = oy + r * ch
            if (c, r) in flagged:
                body.append(f'<rect x="{x}" y="{y}" width="{cw - 12}" '
                            f'height="{ch - 12}" rx="5" fill="{GOLD}" '
                            f'fill-opacity="0.16" stroke="{GOLD}" '
                            f'stroke-opacity="0.42"/>')
            elif rng.random() < 0.14:
                body.append(f'<rect x="{x}" y="{y}" width="{cw - 12}" '
                            f'height="{ch - 12}" rx="5" fill="{STEEL}" '
                            f'fill-opacity="0.09"/>')
            else:
                body.append(f'<rect x="{x}" y="{y}" width="{cw - 12}" '
                            f'height="{ch - 12}" rx="5" fill="none" '
                            f'stroke="{STEEL}" stroke-opacity="0.07"/>')
    body.append(f'<rect x="0" y="404" width="{W}" height="3" fill="url(#scan)"/>')
    return _svg(defs, "".join(body))


def methodology() -> str:
    """Measurement rings and a ruler: the documented edge of the data."""
    defs = (
        f'<linearGradient id="ring" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset="0" stop-color="{GOLD}" stop-opacity="0.30"/>'
        f'<stop offset="1" stop-color="{STEEL}" stop-opacity="0.05"/>'
        f"</linearGradient>"
    )
    body = []
    cx, cy = 1180, 400
    for i, r in enumerate((150, 230, 310, 400)):
        body.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" '
                    f'stroke="url(#ring)" stroke-width="1.2" '
                    f'stroke-opacity="{0.65 - i * 0.12:.2f}" '
                    f'stroke-dasharray="{"2 10" if i % 2 else "none"}"/>')
    body.append(f'<line x1="{cx - 470}" y1="{cy}" x2="{cx + 470}" y2="{cy}" '
                f'stroke="{STEEL}" stroke-opacity="0.12"/>')
    body.append(f'<line x1="{cx}" y1="{cy - 470}" x2="{cx}" y2="{cy + 470}" '
                f'stroke="{STEEL}" stroke-opacity="0.12"/>')
    for i in range(41):
        x = 120 + i * 36
        tall = 18 if i % 5 == 0 else 9
        body.append(f'<line x1="{x}" y1="800" x2="{x}" y2="{800 - tall}" '
                    f'stroke="{GOLD}" stroke-opacity="0.22"/>')
    body.append(f'<line x1="120" y1="800" x2="{W - 120}" y2="800" '
                f'stroke="{GOLD}" stroke-opacity="0.16"/>')
    return _svg(defs, "".join(body))


def settings() -> str:
    """Quiet architectural planes: the calmest page in the workspace."""
    defs = (
        f'<linearGradient id="slat" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{STEEL}" stop-opacity="0.10"/>'
        f'<stop offset="0.5" stop-color="{NAVY}" stop-opacity="0.12"/>'
        f'<stop offset="1" stop-color="{STEEL}" stop-opacity="0.02"/>'
        f"</linearGradient>"
        f'<linearGradient id="edge" x1="0" y1="0" x2="1" y2="0">'
        f'<stop offset="0" stop-color="{GOLD}" stop-opacity="0.22"/>'
        f'<stop offset="1" stop-color="{GOLD}" stop-opacity="0"/>'
        f"</linearGradient>"
    )
    body = []
    for i in range(9):
        y = 90 + i * 88
        body.append(f'<rect x="0" y="{y}" width="{W}" height="60" '
                    f'fill="url(#slat)" fill-opacity="0.55"/>')
        body.append(f'<rect x="0" y="{y}" width="{W}" height="1" '
                    f'fill="url(#edge)"/>')
    body.append(f'<rect x="980" y="0" width="2" height="{H}" fill="{GOLD}" '
                f'fill-opacity="0.07"/>')
    body.append(f'<rect x="300" y="0" width="1" height="{H}" fill="{STEEL}" '
                f'fill-opacity="0.06"/>')
    return _svg(defs, "".join(body))


SCENES: dict[str, tuple[str, callable]] = {
    "bg-overview.svg": overview,
    "bg-contracts.svg": contracts,
    "bg-prices.svg": prices,
    "bg-spreads.svg": spreads,
    "bg-signals.svg": signals,
    "bg-backtest.svg": backtest,
    "bg-quality.svg": quality,
    "bg-methodology.svg": methodology,
    "bg-settings.svg": settings,
}


def build() -> list[Path]:
    OUT.mkdir(parents=True, exist_ok=True)
    written = []
    for name, scene in SCENES.items():
        path = OUT / name
        svg = scene()
        path.write_text(svg, encoding="utf-8")
        written.append(path)
    return written


def check() -> int:
    missing = [name for name in SCENES if not (OUT / name).is_file()]
    if missing:
        print("missing scenes:", ", ".join(missing))
    for name, scene in SCENES.items():
        path = OUT / name
        if path.is_file() and path.read_text(encoding="utf-8") != scene():
            print("stale scene:", name)
            missing.append(name)
    return 1 if missing else 0


if __name__ == "__main__":
    if "--check" in sys.argv:
        raise SystemExit(check())
    for path in build():
        print(f"wrote {path.relative_to(ROOT)} ({path.stat().st_size} bytes)")
