#!/usr/bin/env python
"""Render the dashboard's committed artifacts to a static site (``site/``).

The Streamlit app needs a long-lived server and a persistent WebSocket, which a
static host such as Vercel cannot provide. This tool reads exactly the same
artifacts the app reads (``data/analytics/*.parquet``, ``data/clean``,
``data/results``) and writes plain HTML plus Plotly JSON, so the numbers on the
hosted pages are the same numbers the app shows. Nothing is recomputed and the
network is never touched.

    python -X utf8 tools/build_static_site.py            # writes site/
    python -X utf8 tools/build_static_site.py --out docs  # another target

The Streamlit app stays the interactive original; this is its read-only export.
"""
from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from plotly.offline import get_plotlyjs

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
SCENES = ROOT / "app" / "static" / "backgrounds"
PHOTOS = ROOT / "app" / "static" / "photos"
TEXTURES = ROOT / "app" / "assets"

# The app's artwork module imports nothing but the standard library, so the
# export can read the same photograph registry (author, licence, Commons page)
# instead of keeping a second copy of the credits that could drift.
sys.path.insert(0, str(ROOT))
try:                                  # pragma: no cover - artwork is always present
    from app import artwork as _artwork
    _PHOTO_META = _artwork.PHOTOS
    _photo_credit = _artwork.photo_credit
except Exception:                     # a stripped checkout still renders the pages
    _PHOTO_META: dict = {}
    _photo_credit = lambda stem: ""    # noqa: E731

# ---- palette -------------------------------------------------------------
# Mirrors .streamlit/config.toml and app/theme.py so the export and the app
# read as one product.
CANVAS = "#070B14"
SURFACE = "#0C1422"
GOLD = "#E8CD8A"
GOLD_DEEP = "#C7A25C"
TEXT = "#F2F6FC"
MUTED = "#8FA3BF"
UP = "#35D08A"
DOWN = "#FF6B6B"
SERIES = ["#E8CD8A", "#6EA8FE", "#4FD1A5", "#C79BFF", "#FFB86B", "#FF9BC1"]

#: The rail, in the app's order and section grouping (``app.components.NAV_PAGES``):
#: ``(file, label, section, icon)``. Every page the Streamlit app serves has an
#: entry here, so the static site never has fewer screens than the app.
PAGES: list[tuple[str, str, str, str]] = [
    ("index.html", "Overview", "Workspace", "icon-overview.svg"),
    ("contracts.html", "Gold Contracts", "Workspace", "icon-curve.svg"),
    ("prices.html", "Price Comparison", "Workspace", "icon-prices.svg"),
    ("spreads.html", "Spread Analytics", "Workspace", "icon-spreads.svg"),
    ("signals.html", "Signal Explorer", "Workspace", "icon-alerts.svg"),
    ("backtest.html", "Backtesting", "Research", "icon-backtest.svg"),
    ("quality.html", "Data Quality", "Research", "icon-quality.svg"),
    ("methodology.html", "Methodology", "Research", "icon-methodology.svg"),
    ("settings.html", "Settings", "Preferences", "icon-settings.svg"),
]

#: Latest session in the data, stamped in the rail. Set once by ``main``.
AS_OF = ""

RUN_RECORDS = ("pipeline.json", "run.json")

#: One canvas per exported page: the same composition the Streamlit app paints
#: (``app/backgrounds.py``), re-keyed to the output file. ``scene`` is the vector
#: scene, ``photo`` a registered photograph underneath it, ``focal`` the crop the
#: picture is held at, ``glow`` the gold light source and ``scrim`` the navy wash
#: that keeps figures readable on top.
PAGE_CANVAS: dict[str, dict] = {
    "index.html": {
        "key": "overview", "scene": "bg-overview.svg", "photo": "backdrop-hero",
        "focal": "58% 30%", "position": "50% 46%",
        "glow": ("84%", "-10%"), "alpha": 0.16, "scrim": 0.88,
    },
    "contracts.html": {
        "key": "gold-contracts", "scene": "bg-contracts.svg", "photo": "contracts-banner",
        "focal": "center 28%", "position": "62% 42%",
        "glow": ("72%", "-14%"), "alpha": 0.20, "scrim": 0.90,
    },
    "prices.html": {
        "key": "price-comparison", "scene": "bg-prices.svg", "photo": "contracts-banner",
        "focal": "center 46%", "position": "30% 40%",
        "glow": ("12%", "-8%"), "alpha": 0.13, "scrim": 0.87,
    },
    "spreads.html": {
        "key": "spread-analytics", "scene": "bg-spreads.svg", "photo": "backdrop-hero",
        "focal": "72% 62%", "position": "50% 50%",
        "glow": ("88%", "6%"), "alpha": 0.14, "scrim": 0.86,
    },
    "signals.html": {
        "key": "signal-explorer", "scene": "bg-signals.svg", "photo": "backdrop-hero",
        "focal": "24% 34%", "position": "50% 46%",
        "glow": ("76%", "4%"), "alpha": 0.15, "scrim": 0.86,
    },
    "backtest.html": {
        "key": "backtesting", "scene": "bg-backtest.svg", "photo": "contracts-banner",
        "focal": "72% 70%", "position": "50% 54%",
        "glow": ("18%", "-6%"), "alpha": 0.12, "scrim": 0.87,
    },
    "quality.html": {
        "key": "data-quality", "scene": "bg-quality.svg", "photo": "quality-assay",
        "focal": "center 24%", "position": "50% 52%",
        "glow": ("66%", "-12%"), "alpha": 0.16, "scrim": 0.88,
    },
    "methodology.html": {
        "key": "methodology", "scene": "bg-methodology.svg", "photo": "method-museum",
        "focal": "center 22%", "position": "58% 44%",
        "glow": ("80%", "-8%"), "alpha": 0.15, "scrim": 0.88,
    },
    "settings.html": {
        # The calmest canvas stays a texture rather than a picture: a gold bar
        # crop repeated at tile size, far under the plane of the content.
        "key": "settings", "scene": "bg-settings.svg", "photo": "tile-gold",
        "focal": "50% 50%", "position": "50% 50%",
        "photo_size": "420px 420px", "photo_repeat": "repeat",
        "glow": ("30%", "-10%"), "alpha": 0.10, "scrim": 0.90,
    },
}


def photo_file(stem: str) -> Path | None:
    """Largest published file for a registered photograph (or ``None``)."""
    if not stem:
        return None
    meta = _PHOTO_META.get(stem)
    if meta:
        path = PHOTOS / f"{stem}-{meta['widths'][0]}.webp"
        if path.is_file():
            return path
    candidates = sorted(PHOTOS.glob(f"{stem}-*.webp"))
    return candidates[-1] if candidates else None


def contract_specs() -> dict[str, dict]:
    """``config/config.yaml`` contract geometry, so a table can show size/purity."""
    try:
        import yaml  # noqa: PLC0415 - optional: only the comparison table needs it
        raw = yaml.safe_load((ROOT / "config" / "config.yaml").read_text(encoding="utf-8"))
        return (raw or {}).get("contracts", {}) or {}
    except Exception:
        return {}


def _scrim(alpha: float) -> str:
    """Navy wash that holds the picture down to atmosphere at this page's depth."""
    top = min(alpha, 0.99)
    middle = min(alpha + 0.04, 0.995)
    bottom = min(alpha + 0.07, 0.998)
    return (f"linear-gradient(180deg, rgba(7,11,20,{top:.2f}) 0%, "
            f"rgba(7,11,20,{middle:.2f}) 45%, "
            f"rgba(5,8,15,{bottom:.2f}) 100%)")


def canvas_rules() -> str:
    """One ``body[data-bg]`` rule per page, layer for layer the app's canvas.

    Order matches ``app.backgrounds.layers`` — gold light, cool counter-light,
    vector scene, navy scrim, photograph — so the export is lit the same way.
    """
    blocks = []
    for cfg in PAGE_CANVAS.values():
        glow_x, glow_y = cfg["glow"]
        # (image, size, position, repeat) - first layer is topmost, as in CSS.
        layers: list[tuple[str, str, str, str]] = [
            (f"radial-gradient(120% 80% at {glow_x} {glow_y}, "
             f"rgba(232,205,138,{cfg['alpha']:.2f}), rgba(232,205,138,0) 60%)",
             "cover", f"{glow_x} {glow_y}", "no-repeat"),
            ("radial-gradient(90% 64% at 2% 106%, rgba(143,184,236,0.09), "
             "rgba(143,184,236,0) 62%)", "cover", "2% 106%", "no-repeat"),
            # relative to site.css itself (which lives in assets/), not the page
            (f"url(backgrounds/{cfg['scene']})", "cover", cfg["position"], "no-repeat"),
            (_scrim(cfg["scrim"]), "cover", "center top", "no-repeat"),
        ]
        photo = photo_file(cfg["photo"])
        if photo is not None:
            layers.append((f"url(photos/{photo.name})", cfg.get("photo_size", "cover"),
                           cfg["focal"], cfg.get("photo_repeat", "no-repeat")))
        blocks.append(
            f'body[data-bg="{cfg["key"]}"] {{\n'
            f"  background-image: {', '.join(layer[0] for layer in layers)};\n"
            f"  background-size: {', '.join(layer[1] for layer in layers)};\n"
            f"  background-position: {', '.join(layer[2] for layer in layers)};\n"
            f"  background-repeat: {', '.join(layer[3] for layer in layers)};\n"
            f"  background-attachment: {', '.join(['fixed'] * len(layers))};\n"
            f"}}"
        )
    return "\n".join(blocks)


# ---- formatting ----------------------------------------------------------
def num(value, dp: int = 0, dash: str = "—") -> str:
    try:
        if value is None or pd.isna(value):
            return dash
        return f"{float(value):,.{dp}f}"
    except (TypeError, ValueError):
        return dash


def pct(value, dp: int = 1) -> str:
    try:
        if value is None or pd.isna(value):
            return "—"
        return f"{float(value) * 100:.{dp}f}%"
    except (TypeError, ValueError):
        return "—"


def signed(value, dp: int = 0) -> str:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "—"
    if pd.isna(v):
        return "—"
    cls = "up" if v > 0 else ("down" if v < 0 else "")
    return f'<span class="{cls}">{v:+,.{dp}f}</span>'


def day(value) -> str:
    try:
        ts = pd.Timestamp(value)
    except (TypeError, ValueError):
        return "—"
    return "—" if pd.isna(ts) else f"{ts:%d %b %Y}"


# ---- data ----------------------------------------------------------------
def read_parquet(name: str) -> pd.DataFrame:
    path = DATA / "analytics" / name
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_parquet(path)
    if "trade_date" in df.columns:
        df["trade_date"] = pd.to_datetime(df["trade_date"])
    return df


def latest_run() -> tuple[dict, pd.DataFrame, dict, Path] | tuple[None, None, None, None]:
    """Newest run directory, its record, trades and metrics."""
    results = DATA / "results"
    if not results.exists():
        return None, None, None, None
    ranked = []
    for path in results.iterdir():
        if not path.is_dir():
            continue
        record = {}
        for name in RUN_RECORDS:
            candidate = path / name
            if candidate.exists():
                try:
                    record = json.loads(candidate.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    record = {}
                break
        started = pd.to_datetime(record.get("started_utc"), utc=True, errors="coerce")
        ranked.append((started, path.name, path, record))
    if not ranked:
        return None, None, None, None
    ranked.sort(key=lambda r: (pd.isna(r[0]), str(r[0]), r[1]))
    started, _, path, record = ranked[-1]
    trades = pd.DataFrame()
    trades_p = path / "trades.csv"
    if trades_p.exists():
        trades = pd.read_csv(trades_p)
        for column in ("entry_date", "exit_date"):
            if column in trades.columns:
                trades[column] = pd.to_datetime(trades[column])
    metrics = {}
    metrics_p = path / "metrics.json"
    if metrics_p.exists():
        try:
            metrics = json.loads(metrics_p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            metrics = {}
    return record, trades, metrics, path


# ---- html fragments ------------------------------------------------------
def table(headers, rows, empty: str = "No rows to show.") -> str:
    if not rows:
        return f'<p class="empty">{empty}</p>'
    head = "".join(f"<th>{h}</th>" for h in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows
    )
    return (
        f'<div class="scroll"><table><thead><tr>{head}</tr></thead>'
        f"<tbody>{body}</tbody></table></div>"
    )


def cards(items) -> str:
    cells = "".join(
        f'<div class="card"><p class="label">{i["label"]}</p>'
        f'<p class="value">{i["value"]}</p>'
        f'<p class="sub">{i.get("sub", "")}</p></div>'
        for i in items
    )
    return f'<div class="cards">{cells}</div>'


def panel(title: str, body: str, note: str = "") -> str:
    note_html = f'<p class="note">{note}</p>' if note else ""
    return (
        f'<section class="panel"><h2>{title}</h2>{body}{note_html}</section>'
    )


class ChartSink:
    """Collects figures per page; each becomes a Plotly div + JSON payload."""

    def __init__(self) -> None:
        self.items: list[tuple[str, str]] = []

    def add(self, fig: go.Figure, height: int = 360, lazy: bool = False) -> str:
        """Register a figure; ``lazy`` lets the page plot it when its tab opens."""
        cid = f"chart-{len(self.items)}"
        fig.update_layout(
            height=height,
            margin=dict(l=52, r=18, t=16, b=40),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(family="Inter, system-ui, sans-serif", size=12, color=MUTED),
            title=None,
            hoverlabel=dict(bgcolor=SURFACE, font_color=TEXT, bordercolor=GOLD_DEEP),
            showlegend=True,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, font=dict(size=11)),
        )
        fig.update_xaxes(gridcolor="rgba(143,163,191,0.14)", zeroline=False, linecolor="rgba(143,163,191,0.2)")
        fig.update_yaxes(gridcolor="rgba(143,163,191,0.14)", zeroline=False, linecolor="rgba(143,163,191,0.2)")
        self.items.append((cid, fig.to_json(), lazy))
        return f'<div class="chart" id="{cid}"></div>'

    def scripts(self) -> str:
        payload = "".join(
            f'<script type="application/json" id="spec-{cid}"'
            f'{" data-lazy=\"1\"" if lazy else ""}>{spec}</script>'
            for cid, spec, lazy in self.items
        )
        if not self.items:
            return ""
        init = """
<script>
/* Lazy specs are plotted by whichever control owns them (the scenario tabs),
   so a hidden pane never draws at zero width. */
document.querySelectorAll('script[type="application/json"][id^="spec-"]').forEach(function (node) {
  if (node.dataset.lazy === '1') return;
  var spec = JSON.parse(node.textContent);
  var id = node.id.replace('spec-', '');
  Plotly.newPlot(id, spec.data, spec.layout, {
    responsive: true, displayModeBar: false, scrollZoom: false
  });
});
</script>"""
        return payload + init


# ---- page shell ----------------------------------------------------------
def _head(slug: str, title: str, subtitle: str) -> str:
    """Cinematic hero band on the Overview, frosted strip on every other page."""
    eyebrow = "MCX gold · relative value research"
    if slug == "index.html":
        credit = _photo_credit("backdrop-hero")
        return f"""<section class="hero-band" aria-label="{title}">
  <div class="hero-glass">
    <p class="eyebrow">{eyebrow}</p>
    <h1>{title}</h1>
    <p class="hero-sub">{subtitle}</p>
  </div>
  {f'<div class="hero-credit">{credit}</div>' if credit else ''}
</section>"""
    return f"""<div class="page-head">
  <p class="eyebrow">{eyebrow}</p>
  <h1>{title}</h1>
  <p class="lede">{subtitle}</p>
</div>"""


def _rail(slug: str) -> str:
    """The app's sidebar rail: brand, sectioned page links, data stamp.

    Every page carries the full rail, so navigation is always one click and the
    export has the same nine screens in the same order as the Streamlit app.
    """
    groups: dict[str, list[tuple[str, str, str]]] = {}
    for href, label, section, icon in PAGES:
        groups.setdefault(section, []).append((href, label, icon))

    blocks = []
    for section, items in groups.items():
        links = "".join(
            f'<a href="{href}"'
            f'{" class=\"active\" aria-current=\"page\"" if href == slug else ""}>'
            f'<img src="assets/icons/{icon}" alt="" width="16" height="16">{label}</a>'
            for href, label, icon in items
        )
        blocks.append(f'<p class="rail-section">{section}</p>{links}')

    stamp = f'<span class="rail-stamp">Data as of <b>{AS_OF}</b></span>' if AS_OF else ""
    return f"""<aside class="rail">
  <a class="rail-brand" href="index.html">
    <img class="rail-logo" src="assets/icons/logo-bullion.svg" alt="" width="34" height="34">
    <span><strong>Commodity Intelligence</strong><em>Team Starway</em></span>
  </a>
  <nav class="rail-nav" aria-label="Pages">{''.join(blocks)}</nav>
  <div class="rail-foot">{stamp}<span class="rail-note">Static export · research prototype</span></div>
</aside>
<script>
/* On narrow screens the rail is a horizontal strip: bring the current page's
   link into view so the reader can see where they are without hunting. */
(function () {{
  var rail = document.querySelector('.rail'), link = rail && rail.querySelector('a.active');
  if (!rail || !link || rail.scrollWidth <= rail.clientWidth) return;
  var box = link.getBoundingClientRect(), edge = rail.getBoundingClientRect();
  rail.scrollLeft += box.left - edge.left - (rail.clientWidth - box.width) / 2;
}})();
</script>"""


def shell(slug: str, title: str, subtitle: str, body: str, charts: ChartSink, footer: str) -> str:
    key = PAGE_CANVAS.get(slug, {}).get("key", "")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} · Commodity Intelligence</title>
<link rel="icon" type="image/png" href="assets/favicon.png">
<link rel="stylesheet" href="assets/site.css">
{PREFS_JS}
<script src="assets/plotly.min.js" charset="utf-8"></script>
</head>
<body data-bg="{key}" data-page="{slug}">
{_rail(slug)}
<div class="shell">
  <main>
    {_head(slug, title, subtitle)}
    {body}
    {footer}
  </main>
  <footer class="site-foot">
    <p><strong>Research prototype — not investment advice.</strong> Settlement prices are
    not executable fills; past backtest results do not predict future performance.
    Signals are research outputs, not trade recommendations.</p>
    <p class="fine">Static export of the Streamlit dashboard, rendered from the committed
    pipeline artifacts.</p>
  </footer>
</div>
<div class="palette" id="palette" role="dialog" aria-label="Keyboard shortcuts">
  <div class="palette-scrim"></div>
  <div class="palette-card">
    <h2>Keyboard shortcuts</h2>
    <dl>
      <dt><kbd>←</kbd> <kbd>→</kbd></dt><dd>Previous / next page</dd>
      <dt><kbd>?</kbd></dt><dd>Toggle this panel</dd>
      <dt><kbd>Esc</kbd></dt><dd>Close</dd>
      <dt><kbd>P</kbd></dt><dd>Print or save as PDF</dd>
    </dl>
    <p class="note">Each page is a static file: the rail, the arrows and every
    chart work without a server.</p>
  </div>
</div>
<script type="application/json" id="page-order">{"[" + ", ".join(chr(34) + href + chr(34) for href, _, _, _ in PAGES) + "]"}</script>
<script>{SHORTCUTS_JS}</script>
{charts.scripts()}
</body>
</html>
"""


CSS = f""":root {{
  --canvas: {CANVAS}; --surface: {SURFACE}; --gold: {GOLD}; --gold-deep: {GOLD_DEEP};
  --text: {TEXT}; --muted: {MUTED}; --up: {UP}; --down: {DOWN};
  --line: rgba(143,163,191,.16);
}}
* {{ box-sizing: border-box; }}
html, body {{ margin: 0; background: var(--canvas); color: var(--text); }}
body {{
  font: 15px/1.6 Inter, "Segoe UI", system-ui, -apple-system, sans-serif;
  background-image:
    radial-gradient(1100px 520px at 12% -10%, rgba(232,205,138,.10), transparent 65%),
    radial-gradient(900px 480px at 92% 0%, rgba(110,168,254,.08), transparent 60%);
  background-repeat: no-repeat;
  /* Rail + content: the app's sidebar on the left, pages to its right. */
  display: grid; grid-template-columns: 268px minmax(0, 1fr);
  min-height: 100vh; align-items: start;
}}
a {{ color: var(--gold); text-decoration: none; }}
a:hover {{ color: #fff; }}
/* ---------------- Rail ---------------- */
.rail {{
  position: sticky; top: 0; z-index: 20; height: 100vh; overflow-y: auto;
  display: flex; flex-direction: column; gap: 18px;
  padding: 18px 14px 16px; border-right: 1px solid var(--line);
  background: rgba(7,11,20,.78); backdrop-filter: blur(16px);
}}
.rail-brand {{
  display: flex; align-items: center; gap: 10px; padding: 6px 8px 14px;
  border-bottom: 1px solid var(--line); color: var(--text);
}}
.rail-brand strong {{ display: block; font-size: 14px; font-weight: 650; letter-spacing: .01em; }}
.rail-brand em {{ display: block; font-style: normal; color: var(--muted); font-size: 11px;
                  letter-spacing: .10em; text-transform: uppercase; margin-top: 2px; }}
.rail-logo {{ flex: 0 0 auto; }}
.rail-nav {{ display: flex; flex-direction: column; gap: 2px; }}
.rail-section {{
  margin: 14px 8px 4px; color: var(--muted); font-size: 10px; letter-spacing: .16em;
  text-transform: uppercase; opacity: .75;
}}
.rail-section:first-child {{ margin-top: 0; }}
.rail-nav a {{
  display: flex; align-items: center; gap: 9px; padding: 8px 10px; border-radius: 10px;
  color: var(--muted); font-size: 13.5px; border: 1px solid transparent;
}}
.rail-nav a img {{ opacity: .78; flex: 0 0 auto; }}
.rail-nav a:hover {{ color: var(--text); background: rgba(255,255,255,.05); }}
.rail-nav a:hover img {{ opacity: 1; }}
.rail-nav a.active {{
  color: var(--gold); font-weight: 600;
  background: rgba(232,205,138,.10); border-color: rgba(232,205,138,.38);
}}
.rail-nav a.active img {{ opacity: 1; }}
.rail-foot {{
  margin-top: auto; padding: 12px 8px 0; border-top: 1px solid var(--line);
  display: flex; flex-direction: column; gap: 5px; color: var(--muted); font-size: 11px;
}}
.rail-stamp b {{ color: var(--gold); font-weight: 600; }}
.rail-note {{ opacity: .7; }}
.shell {{ min-width: 0; }}
main {{ max-width: 1120px; margin: 0 auto; padding: 28px 26px 56px; }}
/* Frosted strip: the scene moves behind it, the headline never sits on raw art. */
.page-head {{
  margin: 0 0 26px; padding: 20px 24px 22px; border-radius: 18px;
  border: 1px solid rgba(255,255,255,.10);
  background: rgba(9,15,26,.56); backdrop-filter: blur(14px);
  box-shadow: inset 0 1px 0 rgba(255,255,255,.06), 0 26px 50px -40px #000;
}}
/* Cinematic hero band — the app's Overview header: bullion photograph, navy
   wash, gold light and a tiled terminal texture, headline on frosted glass. */
.hero-band {{
  position: relative; overflow: hidden; margin: 0 0 24px; padding: 14px;
  border-radius: 22px; border: 1px solid rgba(255,255,255,.10);
  background-color: #05080F;
  background-image:
    linear-gradient(112deg, rgba(6,10,18,.92) 0%, rgba(6,10,18,.74) 42%,
                    rgba(6,10,18,.38) 72%, rgba(6,10,18,.30) 100%),
    linear-gradient(180deg, rgba(6,10,18,.55) 0%, rgba(6,10,18,.08) 46%,
                    rgba(6,10,18,.72) 100%),
    radial-gradient(60% 80% at 88% 0%, rgba(232,205,138,.22), rgba(232,205,138,0) 62%),
    url(textures/texture-terminal.svg),
    url(photos/backdrop-hero-1600.webp);
  background-size: 100% 100%, 100% 100%, 100% 100%, 520px 520px, cover;
  background-position: 0 0, 0 0, 0 0, 0 0, 58% 30%;
  background-repeat: no-repeat, no-repeat, no-repeat, repeat, no-repeat;
  box-shadow: 0 40px 80px -48px #000;
}}
.hero-band::after {{
  content: ''; position: absolute; left: 0; right: 0; bottom: 0; height: 2px;
  background: linear-gradient(90deg, #F4DFA5, rgba(232,205,138,.12) 68%, transparent);
}}
.hero-glass {{
  position: relative; z-index: 1; padding: 20px 22px 22px; border-radius: 16px;
  background: rgba(9,15,26,.56); border: 1px solid rgba(255,255,255,.12);
  backdrop-filter: blur(14px);
  box-shadow: inset 0 1px 0 rgba(255,255,255,.08), 0 26px 50px -40px #000;
}}
.hero-band h1 {{ color: #fff; }}
.hero-sub {{ margin: 8px 0 0; max-width: 62ch; color: #CFD9E8; font-size: 14px; line-height: 1.6; }}
.hero-credit {{ position: relative; z-index: 1; margin: 8px 6px 0; font-size: 10px; color: rgba(255,255,255,.42); }}
.hero-credit a {{ color: rgba(255,255,255,.52); }}
.eyebrow {{ margin: 0 0 6px; color: var(--gold-deep); font-size: 11px; letter-spacing: .16em; text-transform: uppercase; }}
h1 {{ margin: 0 0 8px; font-size: clamp(26px, 4vw, 38px); line-height: 1.15; letter-spacing: -.01em; }}
.lede {{ margin: 0; max-width: 74ch; color: var(--muted); }}
.cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(168px, 1fr)); gap: 12px; margin: 0 0 22px; }}
.card {{
  border: 1px solid var(--line); border-radius: 14px; padding: 14px 16px;
  background: linear-gradient(180deg, rgba(255,255,255,.045), rgba(255,255,255,.015));
}}
.card .label {{ margin: 0; color: var(--muted); font-size: 11px; letter-spacing: .12em; text-transform: uppercase; }}
.card .value {{ margin: 6px 0 2px; font-size: 26px; font-weight: 600; letter-spacing: -.02em; }}
.card .sub {{ margin: 0; color: var(--muted); font-size: 12px; }}
.panel {{
  margin: 0 0 20px; padding: 18px 20px 20px; border-radius: 16px;
  border: 1px solid var(--line); background: rgba(12,20,34,.62);
}}
.panel h2 {{ margin: 0 0 12px; font-size: 15px; letter-spacing: .02em; font-weight: 600; color: var(--text); }}
.note {{ margin: 10px 0 0; color: var(--muted); font-size: 12px; }}
.empty {{ margin: 0; color: var(--muted); font-size: 13px; }}
.chart {{ width: 100%; }}
.scroll {{ overflow-x: auto; }}
table {{ width: 100%; border-collapse: collapse; font-size: 13px; font-variant-numeric: tabular-nums; }}
th {{ text-align: left; padding: 8px 10px; color: var(--muted); font-weight: 500; font-size: 11px;
      letter-spacing: .08em; text-transform: uppercase; border-bottom: 1px solid var(--line); white-space: nowrap; }}
td {{ padding: 8px 10px; border-bottom: 1px solid rgba(143,163,191,.09); white-space: nowrap; }}
tbody tr:hover td {{ background: rgba(255,255,255,.03); }}
.up {{ color: var(--up); }}
.down {{ color: var(--down); }}
.badge {{ display: inline-block; padding: 1px 9px; border-radius: 999px; font-size: 11px;
          border: 1px solid rgba(232,205,138,.45); color: var(--gold); }}
.keys {{ display: flex; flex-wrap: wrap; gap: 10px; margin: 0 0 16px; }}
.key {{
  display: inline-flex; align-items: baseline; gap: 8px; padding: 8px 12px;
  border: 1px solid var(--line); border-radius: 12px;
  background: rgba(12,20,34,.60); font-size: 12px;
}}
.key i {{ width: 9px; height: 9px; border-radius: 3px; display: inline-block; }}
.key b {{ font-weight: 600; color: var(--text); }}
.key em {{ font-style: normal; color: var(--muted); }}
.key .val {{ color: var(--gold); font-variant-numeric: tabular-nums; }}
pre.code {{
  margin: 0; padding: 14px 16px; border-radius: 12px; overflow-x: auto;
  border: 1px solid var(--line); background: rgba(5,8,15,.72);
  font-family: ui-monospace, "Cascadia Mono", monospace; font-size: 12px;
  line-height: 1.55; color: #D8E3F2;
}}
ul.plain {{ margin: 0; padding-left: 18px; color: var(--muted); }}
ul.plain li {{ margin: 4px 0; }}
code {{ font-family: ui-monospace, "Cascadia Mono", monospace; font-size: 12px;
        background: rgba(255,255,255,.06); padding: 1px 6px; border-radius: 5px; }}
.site-foot {{ max-width: 1180px; margin: 0 auto; padding: 22px 24px 48px; border-top: 1px solid var(--line);
              color: var(--muted); font-size: 12px; }}
.site-foot strong {{ color: var(--gold); font-weight: 600; }}
.site-foot .fine {{ margin-top: 8px; opacity: .75; }}
/* ---------------- Surface detail ----------------
   A faint film grain over the canvas: it keeps large navy areas from reading as
   flat fill on wide screens, and it is a data URI so nothing is fetched. */
body::after {{
  content: ''; position: fixed; inset: 0; z-index: 2; pointer-events: none;
  opacity: .05; mix-blend-mode: overlay;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='180' height='180'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='180' height='180' filter='url(%23n)' opacity='0.55'/%3E%3C/svg%3E");
}}
.card, .panel, .key, .tabpane {{ transition: transform .18s ease, border-color .18s ease, box-shadow .18s ease; }}
.card:hover {{
  transform: translateY(-2px); border-color: rgba(232,205,138,.34);
  box-shadow: 0 18px 40px -30px #000, inset 0 1px 0 rgba(255,255,255,.08);
}}
.panel:hover {{ border-color: rgba(143,163,191,.28); }}
.key:hover {{ border-color: rgba(232,205,138,.30); }}
.scroll {{ max-height: 620px; overflow: auto; border-radius: 10px; }}
.scroll thead th {{
  position: sticky; top: 0; z-index: 1;
  background: #0B1320; box-shadow: inset 0 -1px 0 var(--line);
}}
.scroll tbody tr:nth-child(even) td {{ background: rgba(255,255,255,.018); }}
.eyebrow::after {{
  content: ''; display: block; width: 34px; height: 2px; margin-top: 8px;
  background: linear-gradient(90deg, var(--gold), rgba(232,205,138,0));
}}
::selection {{ background: rgba(232,205,138,.28); color: #fff; }}
a:focus-visible, button:focus-visible, input:focus-visible, summary:focus-visible {{
  outline: 2px solid var(--gold); outline-offset: 2px; border-radius: 8px;
}}
.rail::-webkit-scrollbar {{ width: 8px; }}
.rail::-webkit-scrollbar-thumb {{ background: rgba(143,163,191,.22); border-radius: 8px; }}
.sr-only {{
  position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px;
  overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; border: 0;
}}

/* ---------------- Controls ----------------
   Client-side filters for the pages that can be filtered without a server. */
.controls {{
  display: flex; flex-wrap: wrap; gap: 10px 18px; align-items: center;
  margin: 0 0 18px; padding: 12px 14px; border-radius: 14px;
  border: 1px solid var(--line); background: rgba(12,20,34,.62);
}}
.controls .group {{ display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }}
.controls .label {{
  color: var(--muted); font-size: 10px; letter-spacing: .14em; text-transform: uppercase;
  margin-right: 2px;
}}
.chip {{
  font: inherit; font-size: 12px; cursor: pointer; padding: 6px 11px; border-radius: 999px;
  color: var(--muted); background: rgba(255,255,255,.03);
  border: 1px solid var(--line); display: inline-flex; align-items: center; gap: 7px;
}}
.chip:hover {{ color: var(--text); border-color: rgba(232,205,138,.34); }}
.chip[aria-pressed="true"] {{
  color: var(--gold); border-color: rgba(232,205,138,.46); background: rgba(232,205,138,.10);
}}
.chip .dot {{
  width: 8px; height: 8px; border-radius: 50%; background: currentColor; opacity: .85;
}}
.chip.sq .dot {{ border-radius: 2px; }}
.btn {{
  font: inherit; font-size: 12px; cursor: pointer; padding: 7px 13px; border-radius: 10px;
  color: var(--canvas); background: var(--gold); border: 1px solid var(--gold); font-weight: 600;
}}
.btn.ghost {{ color: var(--gold); background: transparent; border-color: rgba(232,205,138,.42); }}
.btn:hover {{ filter: brightness(1.06); }}
.controls .readout {{ margin-left: auto; color: var(--muted); font-size: 12px; }}

/* ---------------- Tabs ----------------
   Scenario switcher: one panel visible at a time, no reload, no server. */
.tabs {{ display: flex; flex-wrap: wrap; gap: 6px; margin: 0 0 16px; }}
.tabs button {{
  font: inherit; font-size: 12.5px; cursor: pointer; padding: 7px 14px; border-radius: 10px;
  color: var(--muted); background: rgba(12,20,34,.66); border: 1px solid var(--line);
}}
.tabs button:hover {{ color: var(--text); border-color: rgba(232,205,138,.34); }}
.tabs button[aria-selected="true"] {{
  color: var(--canvas); background: var(--gold); border-color: var(--gold); font-weight: 600;
}}
.tabpane[hidden] {{ display: none; }}

/* ---------------- Shortcuts overlay ---------------- */
.palette {{ position: fixed; inset: 0; z-index: 60; display: none; }}
.palette[open] {{ display: grid; place-items: center; }}
.palette-scrim {{ position: absolute; inset: 0; background: rgba(3,6,12,.72); backdrop-filter: blur(4px); }}
.palette-card {{
  position: relative; width: min(520px, calc(100vw - 32px)); padding: 20px 22px;
  border-radius: 16px; border: 1px solid rgba(255,255,255,.14);
  background: #0B1320; box-shadow: 0 40px 80px -40px #000;
}}
.palette-card h2 {{ margin: 0 0 12px; font-size: 14px; letter-spacing: .02em; }}
.palette-card dl {{ margin: 0; display: grid; grid-template-columns: 108px 1fr; gap: 8px 12px; font-size: 13px; }}
.palette-card dt {{ color: var(--gold); font-family: ui-monospace, monospace; font-size: 12px; }}
.palette-card dd {{ margin: 0; color: var(--muted); }}
kbd {{
  font-family: ui-monospace, monospace; font-size: 11px; padding: 2px 6px; border-radius: 6px;
  border: 1px solid var(--line); background: rgba(255,255,255,.05); color: var(--text);
}}

/* ---------------- Preferences ----------------
   Density and motion are attributes on <html>, set by the head bootstrap, so a
   saved preference never flashes from its default while the page loads. */
:root[data-density="compact"] td,
:root[data-density="compact"] th {{ padding: 5px 9px; }}
:root[data-density="compact"] .panel {{ padding: 14px 16px 16px; margin-bottom: 14px; }}
:root[data-density="compact"] .card {{ padding: 10px 12px; }}
:root[data-density="compact"] .card .value {{ font-size: 22px; }}
:root[data-density="compact"] .cards {{ gap: 9px; margin-bottom: 16px; }}
:root[data-motion="reduced"] *,
:root[data-motion="reduced"] *::before,
:root[data-motion="reduced"] *::after {{
  transition: none !important; animation: none !important;
}}
:root[data-motion="reduced"] .card:hover {{ transform: none; }}

/* Preference rows on Settings: one control per row, label left, value right. */
.pref {{ display: flex; flex-wrap: wrap; align-items: center; gap: 10px 14px;
         padding: 13px 0; border-bottom: 1px solid rgba(143,163,191,.10); }}
.pref:last-of-type {{ border-bottom: 0; }}
.pref .pref-label {{ flex: 1 1 300px; }}
.pref .pref-label b {{ display: block; font-size: 13.5px; font-weight: 600; }}
.pref .pref-label span {{ display: block; margin-top: 2px; color: var(--muted); font-size: 12px; }}
.seg {{ display: inline-flex; gap: 3px; padding: 3px; border-radius: 10px;
        border: 1px solid var(--line); background: rgba(5,8,15,.55); }}
.seg button {{ font: inherit; font-size: 12px; cursor: pointer; padding: 5px 12px;
               border-radius: 7px; color: var(--muted); background: transparent;
               border: 1px solid transparent; }}
.seg button:hover {{ color: var(--text); }}
.seg button[aria-pressed="true"] {{ color: var(--canvas); background: var(--gold); font-weight: 600; }}
.pref select {{ font: inherit; font-size: 12.5px; color: var(--text); padding: 6px 10px;
                border-radius: 9px; border: 1px solid var(--line); background: rgba(5,8,15,.7); }}
.pref-actions {{ display: flex; flex-wrap: wrap; gap: 8px; margin: 16px 0 0; }}
.pref-status {{ margin: 12px 0 0; font-size: 12px; color: var(--muted); min-height: 18px; }}
.pref-status.ok {{ color: var(--up); }}
.pref-status.warn {{ color: var(--down); }}
.shortcut-list {{ margin: 0; display: grid; grid-template-columns: 130px 1fr; gap: 7px 14px; font-size: 12.5px; }}
.shortcut-list dt {{ color: var(--gold); font-family: ui-monospace, "Cascadia Mono", monospace; font-size: 11.5px; }}
.shortcut-list dd {{ margin: 0; color: var(--muted); }}

@media (prefers-reduced-motion: reduce) {{
  *, *::before, *::after {{ transition: none !important; animation: none !important; }}
}}
@media print {{
  .rail, .palette, body::after, .site-foot {{ display: none !important; }}
  body {{ grid-template-columns: 1fr; background: #fff; color: #111; }}
  .panel, .card {{ border-color: #ccc; background: #fff; break-inside: avoid; }}
  .panel h2, h1, .eyebrow {{ color: #111; }}
}}

/* Below this width the rail becomes a strip on top; every page stays one click
   away by scrolling it horizontally. */
@media (max-width: 940px) {{
  body {{ grid-template-columns: 1fr; }}
  .rail {{
    height: auto; flex-direction: row; align-items: center; gap: 10px;
    padding: 8px 12px; overflow-x: auto; overflow-y: hidden;
    border-right: 0; border-bottom: 1px solid var(--line);
  }}
  .rail-brand {{ flex: 0 0 auto; padding: 0 8px 0 0; border-bottom: 0; }}
  .rail-brand strong {{ font-size: 12px; white-space: nowrap; }}
  .rail-brand em {{ display: none; }}
  .rail-nav {{ flex-direction: row; gap: 4px; }}
  .rail-section, .rail-foot {{ display: none; }}
  .rail-nav a {{ white-space: nowrap; padding: 7px 10px; }}
}}
@media (max-width: 620px) {{
  main {{ padding: 20px 14px 48px; }}
  /* Filters stay on one scrolling row instead of stacking into a wall. */
  .controls {{ gap: 8px; padding: 10px 12px; }}
  .controls .group {{ flex-wrap: nowrap; overflow-x: auto; width: 100%; padding-bottom: 2px; }}
  .controls .label {{ flex: 0 0 auto; }}
  .controls .readout {{ margin-left: 0; width: 100%; }}
  .chip {{ white-space: nowrap; }}
  .keys {{ flex-wrap: nowrap; overflow-x: auto; }}
  .card .value {{ font-size: 22px; }}
  .page-head {{ padding: 16px 16px 18px; }}
  .hero-band {{ padding: 10px; }}
  .hero-glass {{ padding: 16px 15px 17px; }}
}}
/* The canvas is fixed on desktop so the scene holds still while figures scroll.
   On touch devices fixed backgrounds repaint on every scroll, so it scrolls. */
@media (max-width: 820px), (hover: none) {{
  body {{ background-attachment: scroll !important; }}
}}

/* ---- per-page canvases (app/backgrounds.py) ---- */
{canvas_rules()}
"""


#: Presentation preferences, read in the head before the page paints.
#: They live in this browser only (localStorage), so the export needs no server
#: and no account: density and motion are attributes on <html>, the start page
#: retargets the rail brand, and the research defaults are read by the pages
#: that own tabs. Nothing here changes an artefact or a calculation.
PREFS_JS = """<script>
(function () {
  var KEY = 'ci.prefs.v1';
  var DEFAULTS = { density: 'comfortable', motion: 'full', start: 'index.html',
                   scenario: 'base', range: 'all' };
  var saved = {};
  try { saved = JSON.parse(localStorage.getItem(KEY) || '{}'); } catch (e) { saved = {}; }
  var prefs = {};
  Object.keys(DEFAULTS).forEach(function (k) {
    prefs[k] = Object.prototype.hasOwnProperty.call(saved, k) && saved[k] !== null
      ? saved[k] : DEFAULTS[k];
  });

  function apply() {
    var root = document.documentElement;
    root.setAttribute('data-density', prefs.density);
    root.setAttribute('data-motion', prefs.motion);
    var brand = document.querySelector('.rail-brand');
    if (brand) brand.setAttribute('href', prefs.start);
  }

  window.CI_PREFS = {
    key: KEY,
    defaults: DEFAULTS,
    all: function () { return JSON.parse(JSON.stringify(prefs)); },
    get: function (k) { return prefs[k]; },
    set: function (k, v) { prefs[k] = v; this.save(); apply(); },
    save: function () {
      try { localStorage.setItem(KEY, JSON.stringify(prefs)); } catch (e) {}
    },
    replace: function (obj) {
      if (!obj || typeof obj !== 'object') return;
      Object.keys(DEFAULTS).forEach(function (k) {
        if (Object.prototype.hasOwnProperty.call(obj, k)) prefs[k] = obj[k];
      });
      this.save(); apply();
    },
    reset: function () { prefs = JSON.parse(JSON.stringify(DEFAULTS)); this.save(); apply(); }
  };

  apply();
  document.addEventListener('DOMContentLoaded', apply);
})();
</script>"""


#: Filters, a range window and a CSV download for the Price Comparison page.
#: Runs against the embedded series, so the hosted page needs no server.
PRICE_COMPARISON_JS = """(function () {
  var node = document.getElementById('pc-series');
  var chart = document.getElementById('pc-chart');
  if (!node || !chart || !window.Plotly) return;
  var series = JSON.parse(node.textContent);
  var controls = document.getElementById('pc-controls');
  var readout = document.getElementById('pc-readout');
  var on = {};
  series.forEach(function (s) { on[s.symbol] = true; });

  /* The window follows the Settings default (1m / 3m / 6m / all) until the
     reader picks another chip on this page. */
  var RANGE_DAYS = { '1m': 30, '3m': 90, '6m': 180, 'all': 0 };
  var prefs = window.CI_PREFS;
  var windowKey = (prefs && RANGE_DAYS.hasOwnProperty(prefs.get('range'))) ? prefs.get('range') : 'all';
  var windowDays = RANGE_DAYS[windowKey];
  Array.prototype.forEach.call(controls.querySelectorAll('[data-range]'), function (b) {
    b.setAttribute('aria-pressed', String(Number(b.dataset.range) === windowDays));
  });

  var layout = {
    paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)',
    height: 460, margin: { l: 58, r: 20, t: 14, b: 42 }, hovermode: 'x unified',
    showlegend: true,
    legend: { orientation: 'h', yanchor: 'bottom', y: 1.02, x: 0, font: { size: 11 } },
    font: { family: 'Inter, system-ui, sans-serif', size: 12, color: '#8FA3BF' },
    xaxis: { gridcolor: 'rgba(143,163,191,.14)', zeroline: false },
    yaxis: { gridcolor: 'rgba(143,163,191,.14)', zeroline: false,
             title: { text: 'INR / g (fine)' } },
    hoverlabel: { bgcolor: '#0C1422', font: { color: '#F2F6FC' }, bordercolor: '#C7A25C' }
  };
  var config = { responsive: true, displayModeBar: false, scrollZoom: false };
  var fmt = new Intl.DateTimeFormat('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });

  function indices(s) {
    if (!windowDays) return s.dates.map(function (_, i) { return i; });
    var end = Date.parse(s.dates[s.dates.length - 1]);
    var floor = end - windowDays * 864e5;
    var out = [];
    for (var i = 0; i < s.dates.length; i++) {
      if (Date.parse(s.dates[i]) >= floor) out.push(i);
    }
    return out;
  }

  function visible() {
    var rows = [], lo = null, hi = null;
    series.forEach(function (s) {
      if (!on[s.symbol]) return;
      var idx = indices(s);
      if (!idx.length) return;
      var x = idx.map(function (i) { return s.dates[i]; });
      var y = idx.map(function (i) { return s.fine[i]; });
      var raw = idx.map(function (i) { return s.raw[i]; });
      lo = lo === null || x[0] < lo ? x[0] : lo;
      hi = hi === null || x[x.length - 1] > hi ? x[x.length - 1] : hi;
      rows.push({ symbol: s.symbol, x: x, y: y, raw: raw, color: s.color, n: x.length });
    });
    return { rows: rows, lo: lo, hi: hi };
  }

  function render() {
    var v = visible();
    var traces = v.rows.map(function (r) {
      return {
        type: 'scatter', mode: 'lines', name: r.symbol, x: r.x, y: r.y, customdata: r.raw,
        line: { width: 1.9, color: r.color },
        hovertemplate: '%{x|%d %b %Y}<br>raw ₹%{customdata:,.2f}<br>' +
                       '₹%{y:,.2f}/g fine<extra>' + r.symbol + '</extra>'
      };
    });
    if (!traces.length) {
      readout.textContent = 'No contracts selected';
    } else {
      var n = v.rows.reduce(function (a, r) { return a + r.n; }, 0);
      readout.textContent = n + ' points · ' + fmt.format(new Date(v.lo)) +
                            ' → ' + fmt.format(new Date(v.hi));
    }
    Plotly.react(chart, traces, layout, config);
  }

  controls.addEventListener('click', function (event) {
    var chip = event.target.closest('.chip');
    if (chip && chip.dataset.sym) {
      var sym = chip.dataset.sym;
      on[sym] = !on[sym];
      chip.setAttribute('aria-pressed', on[sym] ? 'true' : 'false');
      render();
      return;
    }
    if (chip && chip.dataset.range) {
      windowDays = parseInt(chip.dataset.range, 10) || 0;
      Array.prototype.forEach.call(controls.querySelectorAll('[data-range]'), function (b) {
        b.setAttribute('aria-pressed', b === chip ? 'true' : 'false');
      });
      render();
      return;
    }
    if (event.target.id === 'pc-csv') {
      var v = visible();
      var lines = ['date,symbol,raw_close,inr_per_g_fine'];
      v.rows.forEach(function (r) {
        r.x.forEach(function (d, i) {
          lines.push(d + ',' + r.symbol + ',' + r.raw[i] + ',' + r.y[i]);
        });
      });
      var blob = new Blob([lines.join('\\n')], { type: 'text/csv;charset=utf-8' });
      var a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = 'normalized-prices.csv';
      a.click();
      setTimeout(function () { URL.revokeObjectURL(a.href); }, 1000);
    }
  });

  render();
})();"""

#: Cost-scenario tabs on Backtesting. Charts inside a pane are lazy, so only the
#: visible scenario is ever drawn at full width.
SCENARIO_TABS_JS = """(function () {
  var bar = document.querySelector('[data-tabs]');
  if (!bar) return;
  var buttons = Array.prototype.slice.call(bar.querySelectorAll('button[data-pane]'));

  function plot(pane) {
    if (!window.Plotly) return;
    document.querySelectorAll('script[type="application/json"][id^="spec-"]').forEach(function (node) {
      if (node.dataset.plotted === '1') return;
      var id = node.id.replace('spec-', '');
      var host = document.getElementById(id);
      if (!host || !pane.contains(host)) return;
      var spec = JSON.parse(node.textContent);
      Plotly.newPlot(id, spec.data, spec.layout,
                     { responsive: true, displayModeBar: false, scrollZoom: false });
      node.dataset.plotted = '1';
    });
    pane.querySelectorAll('.js-plotly-plot').forEach(function (p) { Plotly.Plots.resize(p); });
  }

  function show(id) {
    buttons.forEach(function (b) {
      b.setAttribute('aria-selected', b.dataset.pane === id ? 'true' : 'false');
    });
    document.querySelectorAll('.tabpane').forEach(function (p) { p.hidden = p.id !== id; });
    var pane = document.getElementById(id);
    /* Plot synchronously: the pane is already visible, and a frame callback is
       throttled or never delivered in background tabs and offscreen views. */
    if (pane) plot(pane);
  }

  bar.addEventListener('click', function (e) {
    var b = e.target.closest('button[data-pane]');
    if (b) show(b.dataset.pane);
  });
  bar.addEventListener('keydown', function (e) {
    if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
    e.preventDefault();
    var i = buttons.findIndex(function (b) { return b.getAttribute('aria-selected') === 'true'; });
    var next = buttons[(i + (e.key === 'ArrowRight' ? 1 : -1) + buttons.length) % buttons.length];
    next.focus();
    show(next.dataset.pane);
  });

  /* The chart specs are emitted after the page body, so the first pane is drawn
     once parsing has finished rather than mid-parse. */
  function start() {
    /* The Settings default opens the page on the reader's cost scenario; the
       panes still switch freely from there. */
    var pref = window.CI_PREFS && window.CI_PREFS.get('scenario');
    var chosen = pref && buttons.filter(function (b) {
      return b.dataset.pane === 'pane-' + pref;
    })[0];
    var initial = chosen || bar.querySelector('button[aria-selected="true"]') || buttons[0];
    if (initial) show(initial.dataset.pane);
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }
})();"""

#: Settings controls. Each one writes the shared preference store and repaints
#: the site immediately; the export has no server, so "saved" means saved in
#: this browser, and the panel says so rather than implying an account.
SETTINGS_JS = """(function () {
  var P = window.CI_PREFS;
  if (!P) return;
  var status = document.getElementById('pref-status');
  var NAMES = { density: 'Density', motion: 'Motion', scenario: 'Default cost scenario',
                range: 'Default price window', start: 'Opening page' };

  function say(message, kind) {
    if (!status) return;
    status.textContent = message;
    status.className = 'pref-status ' + (kind || 'ok');
  }

  function paint() {
    var p = P.all();
    var start = document.getElementById('pref-start');
    if (start) start.value = p.start;
    Array.prototype.forEach.call(
      document.querySelectorAll('[data-pref][data-value]'), function (b) {
        b.setAttribute('aria-pressed', String(String(p[b.dataset.pref]) === b.dataset.value));
      });
  }

  document.addEventListener('click', function (event) {
    var b = event.target.closest('[data-pref][data-value]');
    if (!b) return;
    P.set(b.dataset.pref, b.dataset.value);
    paint();
    say((NAMES[b.dataset.pref] || 'Preference') + ' set to ' + b.textContent.trim() +
        ' — applied to every page in this browser.');
  });

  var start = document.getElementById('pref-start');
  if (start) {
    start.addEventListener('change', function () {
      P.set('start', start.value);
      paint();
      say('Opening page set to ' + start.options[start.selectedIndex].text +
          ' — the rail brand now links there.');
    });
  }

  var download = document.getElementById('pref-download');
  if (download) {
    download.addEventListener('click', function () {
      var payload = JSON.stringify(
        { app: 'commodity-intelligence', version: 1, prefs: P.all() }, null, 2);
      var blob = new Blob([payload], { type: 'application/json' });
      var a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = 'commodity-intelligence-preferences.json';
      a.click();
      setTimeout(function () { URL.revokeObjectURL(a.href); }, 1000);
      say('Downloaded — settings only, no market data.');
    });
  }

  var imp = document.getElementById('pref-import');
  if (imp) {
    imp.addEventListener('change', function () {
      var file = imp.files && imp.files[0];
      if (!file) return;
      var reader = new FileReader();
      reader.onload = function () {
        try {
          var parsed = JSON.parse(String(reader.result));
          P.replace(parsed.prefs || parsed);
          paint();
          say('Preferences imported from ' + file.name + '.');
        } catch (err) {
          say('That file is not a preferences export — nothing changed.', 'warn');
        }
        imp.value = '';
      };
      reader.readAsText(file);
    });
  }

  var reset = document.getElementById('pref-reset');
  if (reset) {
    reset.addEventListener('click', function () {
      P.reset();
      paint();
      say('Back to the shipped defaults.');
    });
  }

  paint();
})();"""


#: Arrow-key page navigation, a shortcuts panel and print. Progressive: with
#: JavaScript off the rail still navigates and every page still renders.
SHORTCUTS_JS = """(function () {
  var holder = document.getElementById('page-order');
  var order = holder ? JSON.parse(holder.textContent) : [];
  var here = document.body.getAttribute('data-page') || '';
  var index = order.indexOf(here);
  var palette = document.getElementById('palette');

  function go(delta) {
    if (index < 0 || !order.length) return;
    window.location.href = order[(index + delta + order.length) % order.length];
  }
  function toggle(show) {
    if (!palette) return;
    var open = show === undefined ? !palette.hasAttribute('open') : show;
    if (open) { palette.setAttribute('open', ''); } else { palette.removeAttribute('open'); }
  }
  document.addEventListener('keydown', function (e) {
    var tag = (document.activeElement && document.activeElement.tagName) || '';
    if (/^(INPUT|TEXTAREA|SELECT)$/.test(tag)) return;
    if (e.key === 'ArrowRight') { e.preventDefault(); go(1); }
    else if (e.key === 'ArrowLeft') { e.preventDefault(); go(-1); }
    else if (e.key === '?') { e.preventDefault(); toggle(); }
    else if (e.key === 'Escape') { toggle(false); }
    else if (e.key === 'p' || e.key === 'P') { e.preventDefault(); window.print(); }
  });
  if (palette) {
    palette.addEventListener('click', function (e) {
      if (!e.target.closest('.palette-card')) toggle(false);
    });
  }
})();"""


# ---- pages ---------------------------------------------------------------
def build(norm: pd.DataFrame, spreads: pd.DataFrame, signals: pd.DataFrame,
          rejections: pd.DataFrame, clean: pd.DataFrame, record: dict,
          trades: pd.DataFrame, metrics: dict, run_dir: Path | None) -> dict[str, str]:
    out: dict[str, str] = {}
    symbols = sorted(norm["symbol"].unique()) if not norm.empty else []
    total_dates = norm["trade_date"].nunique() if not norm.empty else 0

    # ---------------- Overview ----------------
    charts = ChartSink()
    latest_date = norm["trade_date"].max() if not norm.empty else None
    body = ""
    body += cards([
        {"label": "Contracts", "value": len(symbols), "sub": "restated to INR/g fine"},
        {"label": "Trading days", "value": num(total_dates), "sub": f"to {day(latest_date)}"},
        {"label": "Validation", "value": "All rows pass" if rejections.empty else f"{len(rejections)} rejected",
         "sub": f"{num(len(clean))} clean rows"},
        {"label": "Pairs tracked", "value": num(spreads[["leg_a", "leg_b"]].drop_duplicates().shape[0] if not spreads.empty else 0),
         "sub": "pairwise spreads"},
    ])

    if not norm.empty:
        fig = go.Figure()
        for i, symbol in enumerate(symbols):
            rows = norm[norm["symbol"] == symbol].sort_values("trade_date")
            fig.add_trace(go.Scatter(
                x=rows["trade_date"], y=rows["inr_per_g_fine"], mode="lines", name=symbol,
                line=dict(width=1.8, color=SERIES[i % len(SERIES)]),
                hovertemplate="%{x|%d %b %Y}<br>₹%{y:,.2f}/g<extra>" + symbol + "</extra>",
            ))
        body += panel("Fine-gold price history — INR per gram",
                      charts.add(fig),
                      "Every contract restated to one basis: price × (trading unit ÷ quoted unit) ÷ purity.")
    else:
        body += panel("Fine-gold price history", '<p class="empty">No normalized data committed.</p>')

    if not norm.empty:
        last = norm.sort_values("trade_date").groupby("symbol").tail(1).sort_values("inr_per_g_fine", ascending=False)
        rows = [
            [r.symbol, day(r.expiry_date), f"₹{num(r.close_raw, 2)}", f"₹{num(r.inr_per_g_fine, 2)}",
             num(r.volume), num(r.open_interest), num(r.days_to_expiry)]
            for r in last.itertuples()
        ]
        body += panel("Latest settlement per contract",
                      table(["Contract", "Expiry", "Quoted close", "INR/g fine", "Volume", "Open interest", "Days to expiry"], rows))

    if not signals.empty:
        last_sig = signals.sort_values("trade_date").groupby(["leg_a", "leg_b"]).tail(1)
        last_sig = last_sig.assign(abs_z=last_sig["z_score"].abs()).sort_values("abs_z", ascending=False)
        rows = [
            [f"{r.symbol_a} / {r.symbol_b}", signed(r.spread_inr_g, 2), pct(r.spread_pct, 3),
             signed(r.z_score, 2) if pd.notna(r.z_score) else "—", f'<span class="badge">{r.signal_state}</span>']
            for r in last_sig.itertuples()
        ]
        body += panel("Strongest pairs on the last session",
                      table(["Pair", "Spread ₹/g", "Spread %", "Z-score", "State"], rows),
                      "Z-scores are blank until the rolling window has enough history.")
    out["index.html"] = shell("index.html", "Overview",
                              "Current state of the research pipeline: coverage, validation, spreads and the last backtest.",
                              body, charts, "")

    # ---------------- Contracts ----------------
    charts = ChartSink()
    body = ""
    if norm.empty:
        body = panel("Contracts", '<p class="empty">No normalized data committed.</p>')
    else:
        rows = []
        for symbol in symbols:
            rows.append([symbol, day(norm.loc[norm.symbol == symbol, "expiry_date"].max())])
        summary = []
        for symbol in symbols:
            block = norm[norm.symbol == symbol].sort_values("trade_date")
            last = block.iloc[-1]
            summary.append([
                symbol, day(last["expiry_date"]), num(len(block)), f"₹{num(last['close_raw'], 2)}",
                f"₹{num(last['inr_per_g_fine'], 2)}", num(last["volume"]), num(last["open_interest"]),
                num(last["days_to_expiry"]), block["expiry_window"].iloc[-1] if "expiry_window" in block else "—",
            ])
        body += panel("Contract summary", table(
            ["Contract", "Expiry", "Sessions", "Quoted close", "INR/g fine", "Volume", "Open interest",
             "Days to expiry", "Expiry window"], summary))

        fig = go.Figure()
        for i, symbol in enumerate(symbols):
            block = norm[norm["symbol"] == symbol].sort_values("trade_date")
            fig.add_trace(go.Scatter(
                x=block["trade_date"], y=block["close_raw"], mode="lines", name=symbol,
                line=dict(width=1.7, color=SERIES[i % len(SERIES)]),
                hovertemplate="%{x|%d %b %Y}<br>₹%{y:,.2f}<extra>" + symbol + "</extra>",
            ))
        body += panel("Quoted settlement prices", charts.add(fig, 420),
                      "GOLDPETAL and GOLDGUINEA quote small units, so their levels are not comparable — "
                      "use the INR/g fine view on Overview for that.")

        volume = norm.pivot_table(index="trade_date", columns="symbol", values="volume", aggfunc="sum")
        if not volume.empty:
            fig = go.Figure()
            for i, symbol in enumerate(volume.columns):
                fig.add_trace(go.Bar(x=volume.index, y=volume[symbol], name=str(symbol),
                                     marker_color=SERIES[i % len(SERIES)], opacity=.85))
            fig.update_layout(barmode="stack")
            body += panel("Daily volume by contract", charts.add(fig, 320))
    out["contracts.html"] = shell("contracts.html", "Gold Contracts",
                                  "Four gold contracts, one basis — settlement prices, volume and open interest.",
                                  body, charts, "")

    # ---------------- Price comparison ----------------
    charts = ChartSink()
    body = ""
    specs = contract_specs()
    if norm.empty:
        body = panel("Price comparison", '<p class="empty">No normalized data committed.</p>')
    else:
        last_day = norm["trade_date"].max()
        # A real control surface, not a picture of one: the chips filter the series
        # and the range buttons window it, both client-side against the embedded
        # data, so the hosted page behaves like the app's selectors without a
        # server. The last price rides on each chip, so the key and the legend are
        # the same object.
        chips = []
        series = []
        for i, symbol in enumerate(symbols):
            block = norm[norm.symbol == symbol].sort_values("trade_date")
            last = block[block.trade_date == last_day]
            spec = specs.get(symbol, {}) or {}
            bits = []
            if spec.get("trading_unit_g") is not None:
                bits.append(f"{float(spec['trading_unit_g']):g} g")
            if spec.get("purity") is not None:
                bits.append(f"{float(spec['purity']):g} fine")
            spec_txt = " · ".join(bits) or "contract size in config"
            price = num(last["inr_per_g_fine"].iloc[0], 2) if len(last) else "—"
            color = SERIES[i % len(SERIES)]
            chips.append(
                f'<button class="chip sq" data-sym="{symbol}" aria-pressed="true" '
                f'title="{symbol} · {spec_txt}">'
                f'<span class="dot" style="background:{color}"></span>{symbol}'
                f'<span style="opacity:.62">₹{price}</span></button>')
            series.append({
                "symbol": symbol, "color": color,
                "dates": [d.strftime("%Y-%m-%d") for d in block["trade_date"]],
                "fine": [round(float(v), 4) for v in block["inr_per_g_fine"]],
                "raw": [round(float(v), 2) for v in block["close_raw"]],
            })

        controls = (
            '<div class="controls" id="pc-controls">'
            '<div class="group" role="group" aria-label="Contracts">'
            f'<span class="label">Contracts</span>{"".join(chips)}</div>'
            '<div class="group" role="group" aria-label="Window">'
            '<span class="label">Window</span>'
            '<button class="chip" data-range="30" aria-pressed="false">1M</button>'
            '<button class="chip" data-range="90" aria-pressed="false">3M</button>'
            '<button class="chip" data-range="180" aria-pressed="false">6M</button>'
            '<button class="chip" data-range="0" aria-pressed="true">All</button></div>'
            '<div class="group"><button class="btn ghost" id="pc-csv">Download CSV</button></div>'
            '<span class="readout" id="pc-readout"></span>'
            '</div>'
        )
        payload = json.dumps(series, separators=(",", ":"))
        body += (
            '<section class="panel"><h2>Normalized settlement price</h2>'
            f'{controls}<div class="chart" id="pc-chart" style="height:460px"></div>'
            '<p class="note">Every contract restated to one basis before comparison; hover '
            'shows the quoted price the normalized line was derived from. Filters and the '
            'CSV run in the browser against the committed series.</p>'
            f'<script type="application/json" id="pc-series">{payload}</script>'
            f'<script>{PRICE_COMPARISON_JS}</script>'
            '</section>'
        )

        # Latest comparison against the previous session. Two sessions is enough
        # for a change figure; a longer window belongs on Spread Analytics.
        days = sorted(norm["trade_date"].unique())
        latest = norm[norm.trade_date == days[-1]]
        prev = norm[norm.trade_date == days[-2]] if len(days) > 1 else norm.iloc[0:0]
        rows = []
        for symbol in symbols:
            row = latest[latest.symbol == symbol]
            if row.empty:
                continue
            price = float(row["inr_per_g_fine"].iloc[0])
            before = prev[prev.symbol == symbol]
            change = (price / float(before["inr_per_g_fine"].iloc[0]) - 1) if not before.empty else None
            spec = specs.get(symbol, {}) or {}
            rows.append([
                symbol, f"₹{num(price, 2)}",
                signed(change * 100, 3) if change is not None else "—",
                num(spec.get("trading_unit_g")), num(spec.get("purity"), 3),
                day(row["expiry_date"].iloc[0]), num(row["days_to_expiry"].iloc[0]),
            ])
        body += panel("Latest comparison — versus the previous session", table(
            ["Contract", "INR/g fine", "Change %", "Contract size (g)", "Purity", "Expiry",
             "Days to expiry"], rows),
            "Contract size and purity come from config/config.yaml, the same file the pipeline reads.")

        body += panel("Row data",
                      '<p class="note">Every settlement in the series is committed as parquet: '
                      '<code>data/analytics/normalized.parquet</code> '
                      '(<code>symbol</code>, <code>trade_date</code>, <code>close_raw</code>, '
                      '<code>inr_per_g_fine</code>, volume, open interest, days to expiry). '
                      'The interactive app on Streamlit Cloud serves it as a CSV download; '
                      'this export is read-only.</p>')
    out["prices.html"] = shell("prices.html", "Price Comparison",
                               "Settlement prices restated to fine-gold INR per gram — the only comparable basis.",
                               body, charts, "")

    # ---------------- Spreads ----------------
    charts = ChartSink()
    body = ""
    if spreads.empty:
        body = panel("Spreads", '<p class="empty">No spread analytics committed.</p>')
    else:
        pairs = (spreads[["leg_a", "leg_b"]].drop_duplicates()
                 .merge(spreads.groupby(["leg_a", "leg_b"]).size().rename("n").reset_index(),
                        on=["leg_a", "leg_b"]).sort_values("n", ascending=False))
        top = pairs.head(3)
        for i, r in enumerate(top.itertuples()):
            block = spreads[(spreads.leg_a == r.leg_a) & (spreads.leg_b == r.leg_b)].sort_values("trade_date")
            label = f"{block['symbol_a'].iloc[0]} / {block['symbol_b'].iloc[0]}"
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=block["trade_date"], y=block["spread_inr_g"], mode="lines",
                                     name=label, line=dict(width=1.9, color=SERIES[i % len(SERIES)]),
                                     hovertemplate="%{x|%d %b %Y}<br>₹%{y:,.2f}/g<extra></extra>"))
            fig.add_hline(y=0, line=dict(color="rgba(143,163,191,.45)", width=1, dash="dot"))
            mean = block["spread_inr_g"].mean()
            fig.add_hline(y=mean, line=dict(color=GOLD_DEEP, width=1, dash="dash"),
                          annotation_text="mean", annotation_position="top right",
                          annotation_font=dict(size=10, color=GOLD_DEEP))
            body += panel(f"{label} — spread, ₹/g", charts.add(fig, 300))

        last = spreads.sort_values("trade_date").groupby(["leg_a", "leg_b"]).tail(1)
        rows = [
            [f"{r.symbol_a} / {r.symbol_b}", signed(r.spread_inr_g, 2), pct(r.spread_pct, 3),
             f"₹{num(r.price_a, 2)}", f"₹{num(r.price_b, 2)}", num(r.dte_a), num(r.dte_b)]
            for r in last.sort_values("spread_inr_g", key=abs, ascending=False).itertuples()
        ]
        body = panel("Latest spread per pair",
                     table(["Pair", "Spread ₹/g", "Spread %", "Leg A ₹/g", "Leg B ₹/g", "DTE A", "DTE B"], rows)) + body
    out["spreads.html"] = shell("spreads.html", "Spread Analytics",
                                "Pairwise spreads after restating each leg to fine gold, with the carry adjustment applied.",
                                body, charts, "")

    # ---------------- Signals ----------------
    charts = ChartSink()
    body = ""
    if signals.empty:
        body = panel("Signals", '<p class="empty">No signal analytics committed.</p>')
    else:
        counts = signals.groupby("signal_state").size().sort_values(ascending=False)
        body += cards([{"label": str(state), "value": num(count), "sub": "rows"}
                       for state, count in counts.items()])
        pairs = (signals[["leg_a", "leg_b"]].drop_duplicates()
                 .merge(signals.groupby(["leg_a", "leg_b"]).size().rename("n").reset_index(),
                        on=["leg_a", "leg_b"]).sort_values("n", ascending=False))
        for i, r in enumerate(pairs.head(3).itertuples()):
            block = signals[(signals.leg_a == r.leg_a) & (signals.leg_b == r.leg_b)].sort_values("trade_date")
            label = f"{block['symbol_a'].iloc[0]} / {block['symbol_b'].iloc[0]}"
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=block["trade_date"], y=block["z_score"], mode="lines", name=label,
                                     line=dict(width=1.9, color=SERIES[i % len(SERIES)]),
                                     hovertemplate="%{x|%d %b %Y}<br>z = %{y:.2f}<extra></extra>"))
            for level in (2.0, -2.0):
                fig.add_hline(y=level, line=dict(color="rgba(232,205,138,.5)", width=1, dash="dash"),
                              annotation_text=f"{level:+.0f}", annotation_position="right",
                              annotation_font=dict(size=10, color=GOLD_DEEP))
            fig.update_yaxes(range=[-4, 4])
            body += panel(f"{label} — rolling z-score", charts.add(fig, 280),
                          "Entry band at ±2σ; the window is 60 sessions (config/config.yaml).")

        last = signals.sort_values("trade_date").groupby(["leg_a", "leg_b"]).tail(1)
        rows = [
            [day(r.trade_date), f"{r.symbol_a} / {r.symbol_b}", signed(r.spread_inr_g, 2),
             signed(r.residual_after_carry, 2), signed(r.z_score, 2) if pd.notna(r.z_score) else "—",
             f'<span class="badge">{r.signal_state}</span>']
            for r in last.sort_values("trade_date", ascending=False).itertuples()
        ]
        body += panel("Latest state per pair",
                      table(["Session", "Pair", "Spread ₹/g", "Residual after carry", "Z-score", "State"], rows))
    out["signals.html"] = shell("signals.html", "Signal Explorer",
                                "The signal state machine over each pair: Neutral → Watch → Entered → Exited.",
                                body, charts, "")

    # ---------------- Backtesting ----------------
    charts = ChartSink()
    body = ""
    footer = ""
    if trades.empty:
        body = panel("Backtest", '<p class="empty">No backtest run committed.</p>')
    else:
        # Three cost scenarios ship in the same run, so the page offers all three
        # as tabs instead of hard-coding ``base``. Each pane carries its own KPIs,
        # equity curve and log; charts plot when their tab opens.
        scenarios = [s for s in ("low", "base", "high") if s in set(trades["scenario"])]
        scenarios = scenarios or sorted(set(trades["scenario"]))
        active = "base" if "base" in scenarios else scenarios[0]
        min_trades = metrics.get("min_trades_required")
        panes: list[tuple[str, str]] = []

        for scenario in scenarios:
            t = trades[trades["scenario"] == scenario].sort_values("entry_date")
            net = t["net_pnl"].to_numpy()
            eq = net.cumsum()
            mdd = float((eq - pd.Series(eq).cummax()).min()) if len(eq) else 0.0
            oos = t[t["split"] == "test"]

            pane = cards([
                {"label": "Gross P&L", "value": num(t.gross_pnl.sum()), "sub": f"{scenario} cost scenario"},
                {"label": "Net P&L", "value": num(net.sum()), "sub": "after all costs"},
                {"label": "Trades", "value": num(len(t)), "sub": f"{len(oos)} out-of-sample"},
                {"label": "Win rate", "value": pct((net > 0).mean() if len(net) else float("nan"), 0),
                 "sub": "positive net P&L"},
                {"label": "Max drawdown", "value": num(mdd), "sub": "on net equity"},
            ])
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=t["exit_date"], y=eq, mode="lines", name="Net equity",
                                     line=dict(width=2.1, color=GOLD),
                                     fill="tozeroy", fillcolor="rgba(232,205,138,.10)",
                                     hovertemplate="%{x|%d %b %Y}<br>%{y:,.1f}<extra></extra>"))
            fig.add_hline(y=0, line=dict(color="rgba(143,163,191,.45)", width=1, dash="dot"))
            pane += panel("Net equity curve — cumulative trade P&L", charts.add(fig, 340, lazy=True),
                          f"Chronological walk-forward; the out-of-sample block starts at "
                          f"{day(oos['entry_date'].min()) if len(oos) else '—'}.")

            per_pair = []
            for value in (metrics.get("pairs") or {}).values():
                if value.get("scenario") not in (None, scenario):
                    continue
                per_pair.append([
                    str(value.get("pair", "—")), num(value.get("trade_count")),
                    pct(value.get("win_rate")), num(value.get("avg_net_per_trade"), 1),
                    signed(value.get("total_net_pnl"), 1), num(value.get("max_drawdown"), 1),
                    signed(value.get("out_of_sample_net"), 1),
                ])
            if per_pair:
                pane += panel("Per-pair outcome", table(
                    ["Pair", "Trades", "Win rate", "Avg net / trade", "Total net", "Max DD",
                     "Out-of-sample net"], per_pair))

            rows = [[str(r.pair), day(r.entry_date), day(r.exit_date), str(r.direction).replace("_", " "),
                     signed(r.gross_pnl, 2), num(r.cost_total, 2), signed(r.net_pnl, 2), str(r.split)]
                    for r in t.itertuples()]
            pane += panel("Trade log", table(
                ["Pair", "Entry", "Exit", "Direction", "Gross ₹/g", "Costs", "Net ₹/g", "Split"], rows),
                f"{scenario} cost scenario · {len(t)} closed trades from run "
                f"{record.get('run_id', run_dir.name if run_dir else '—')}.")
            if min_trades and len(oos) < int(min_trades):
                pane += panel("Evidence note",
                              f'<p class="empty">{len(oos)} out-of-sample trades against a '
                              f'{int(min_trades)}-trade minimum. Treat every number on this pane '
                              f'as underpowered, not as validation.</p>')
            panes.append((scenario, pane))

        tabs = "".join(
            f'<button role="tab" aria-selected="{"true" if s == active else "false"}"'
            f' aria-controls="pane-{s}" data-pane="pane-{s}">{s.title()} cost</button>'
            for s in scenarios)
        body = (f'<div class="tabs" role="tablist" aria-label="Cost scenario" data-tabs>{tabs}</div>'
                + "".join(
                    f'<section class="tabpane" id="pane-{s}" role="tabpanel"'
                    f'{" hidden" if s != active else ""}>{pane}</section>'
                    for s, pane in panes)
                + f'<script>{SCENARIO_TABS_JS}</script>')
        footer = ""
    out["backtest.html"] = shell("backtest.html", "Backtesting",
                                 "Walk-forward research on settlement prices with explicit transaction costs.",
                                 body, charts, footer)

    # ---------------- Data quality ----------------
    charts = ChartSink()
    body = ""
    raw_files = len(list((DATA / "raw").glob("*.csv"))) if (DATA / "raw").exists() else 0
    body += cards([
        {"label": "Raw files", "value": num(raw_files), "sub": "one per requested date"},
        {"label": "Clean rows", "value": num(len(clean)), "sub": "parsed and accepted"},
        {"label": "Rejected rows", "value": num(len(rejections)), "sub": "reason-tagged"},
        {"label": "Sessions", "value": num(total_dates), "sub": f"to {day(norm['trade_date'].max()) if not norm.empty else '—'}"},
    ])
    if not norm.empty:
        rows = []
        for symbol in symbols:
            block = norm[norm.symbol == symbol]
            rows.append([symbol, num(block["trade_date"].nunique()), day(block["trade_date"].min()),
                         day(block["trade_date"].max()),
                         pct(block["trade_date"].nunique() / total_dates if total_dates else float("nan"))])
        body += panel("Coverage per contract", table(
            ["Contract", "Sessions present", "First", "Last", "Share of window"], rows))

        presence = norm.pivot_table(index="symbol", columns="trade_date", values="close_raw", aggfunc="size").fillna(0)
        fig = go.Figure(go.Heatmap(
            z=presence.values, x=presence.columns, y=presence.index.astype(str),
            colorscale=[[0, "rgba(143,163,191,0.10)"], [0.5, "rgba(232,205,138,0.45)"], [1, GOLD]],
            showscale=False, xgap=0, ygap=2,
            hovertemplate="%{y}<br>%{x|%d %b %Y}<extra></extra>",
        ))
        body += panel("Settlement presence", charts.add(fig, 240),
                      "A break in the ribbon is a missing settlement, not a flat price.")
    if rejections.empty:
        body += panel("Rejections", '<p class="empty">No rejected rows — every parsed row passed schema, '
                                    "range, date and duplicate checks.</p>")
    else:
        rows = [[str(v) for v in row] for row in rejections.head(60).itertuples(index=False)]
        body += panel("Rejected rows", table(list(rejections.columns), rows))
    body += panel("How imports are treated",
                  '<ul class="plain"><li>An uploaded CSV faces the same validation as a downloaded one — '
                  "nothing reaches <code>data/raw</code> that has not already passed.</li>"
                  "<li>Re-running <code>python -m src.pipeline</code> rebuilds analytics; an import alone "
                  "never rewrites results.</li></ul>")
    out["quality.html"] = shell("quality.html", "Data Quality",
                                "What the pipeline accepted, what it rejected, and where the record has holes.",
                                body, charts, "")

    # ---------------- Methodology ----------------
    body = f"""
{panel("Normalisation", '''<p>Every contract is restated to one basis before any comparison:</p>
<p><code>INR per gram fine = price × (trading unit ÷ quoted unit) ÷ purity</code></p>
<p>GOLDM (10 g, 0.995), GOLDTEN (100 g, 0.995), GOLDGUINEA (10 g, 0.916) and GOLDPETAL (1 g, 0.995)
therefore become directly comparable, and a spread is a real relative-value number rather than a
unit mismatch.</p>''')}
{panel("Spread and z-score", '''<ul class="plain">
<li><strong>Spread</strong> = leg A − leg B, both in INR per gram fine.</li>
<li><strong>Carry adjustment</strong> removes the financing implied by the expiry gap; the rate lives
in <code>config/config.yaml</code> and is currently <code>0.0</code>, so the residual equals the raw spread.</li>
<li><strong>Z-score</strong> = (residual − rolling mean) ÷ rolling standard deviation over a 60-session window.</li>
<li><strong>Signal state machine</strong>: Neutral → Watch (inside the entry band) → Entered (|z| ≥ 2) →
Exited (|z| ≤ 0.5). States are research labels, not orders.</li>
</ul>''')}
{panel("Backtest design", '''<ul class="plain">
<li>Chronological split: 60% train, 40% out-of-sample — never shuffled, never re-fit on the test block.</li>
<li>Walk-forward re-estimation every 20 sessions.</li>
<li>Explicit per-leg, per-side costs: exchange fee, brokerage, statutory charges and slippage, in three
scenarios (low / base / high).</li>
<li>Metrics are per pair; a pair below the minimum out-of-sample trade count is reported as underpowered
rather than ranked.</li>
</ul>''')}
{panel("Known limitations", '''<ul class="plain">
<li>Daily settlement prices only — not executable fill prices.</li>
<li>The carry rate is a documented input, not a sourced market rate.</li>
<li>Cost assumptions are illustrative until tied to a real fee schedule.</li>
<li>GOLDTEN's exchange history starts in 2025, so it contributes fewer sessions.</li>
<li>The bundled fixture expiries are fixed, so late sessions show settled contracts.</li>
<li>No theme toggle: Streamlit themes are fixed per deployment, and the dark workspace is the tested one.</li>
</ul>''')}
{panel("Rebuilding this export", '''<p>The Streamlit app is the interactive original and still runs from the repo root:</p>
<p><code>python -m streamlit run app/Home.py --server.port 8601</code></p>
<p>This static site is generated from the same committed artifacts and is what a static host serves:</p>
<p><code>python -X utf8 tools/build_static_site.py</code></p>''')}
"""
    out["methodology.html"] = shell("methodology.html", "Methodology",
                                    "Assumptions, formulas and limitations behind every number in this dashboard.",
                                    body, ChartSink(), "")

    # ---------------- Settings ----------------
    # Preferences here are real controls: they persist in localStorage and change
    # the export itself (density, motion, opening page, and the defaults that the
    # Prices and Backtesting tabs open with). The data facts below stay read-only,
    # because no browser can rewrite a committed artefact or config.yaml.
    body = ""
    cfg_path = ROOT / "config" / "config.yaml"
    cfg_text = cfg_path.read_text(encoding="utf-8") if cfg_path.is_file() else ""
    run_id = record.get("run_id") or (run_dir.name if run_dir else "—")

    def coverage(frame: pd.DataFrame) -> str:
        if frame.empty or "trade_date" not in frame.columns:
            return "—"
        dates = pd.to_datetime(frame["trade_date"])
        return f"{day(dates.min())} → {day(dates.max())}"

    started = record.get("started_utc")
    run_label = "—"
    if started:
        try:
            run_label = day(pd.Timestamp(started))
        except (TypeError, ValueError):
            run_label = "—"
    body += cards([
        {"label": "Contracts", "value": num(len(symbols)) if not norm.empty else "—", "sub": "in configuration"},
        {"label": "Sessions", "value": num(total_dates), "sub": "trading days loaded"},
        {"label": "Last pipeline run", "value": run_label, "sub": "results directory in data/results"},
        {"label": "Config", "value": "Read-only", "sub": "config/config.yaml"},
    ])

    # ---- Preferences ----------------------------------------------------
    # Counters, not a menu: a segmentation control is one click away from the
    # page it changes, and every value is written to localStorage immediately.
    def seg(pref: str, options: list[tuple[str, str]]) -> str:
        buttons = "".join(
            f'<button type="button" data-pref="{pref}" data-value="{value}"'
            f' aria-pressed="false">{label}</button>'
            for value, label in options)
        return f'<div class="seg" role="group" aria-label="{pref}">{buttons}</div>'

    start_options = "".join(
        f'<option value="{href}">{label}</option>' for href, label, _, _ in PAGES)

    body += panel("Workspace", (
        '<div class="pref">'
        '<span class="pref-label"><b>Opening page</b>'
        '<span>Where the rail brand takes you. The arrow keys still walk the full page order.</span></span>'
        f'<select id="pref-start" aria-label="Opening page">{start_options}</select>'
        '</div>'
        '<div class="pref">'
        '<span class="pref-label"><b>Density</b>'
        '<span>Compact tightens table rows and panel padding for screens with more rows than room.</span></span>'
        + seg("density", [("comfortable", "Comfortable"), ("compact", "Compact")]) +
        '</div>'
        '<div class="pref">'
        '<span class="pref-label"><b>Motion</b>'
        '<span>Reduced drops hover lifts and transitions. The OS reduce-motion setting is '
        'respected either way.</span></span>'
        + seg("motion", [("full", "Full"), ("reduced", "Reduced")]) +
        '</div>'
        '<p class="pref-status" id="pref-status" role="status" aria-live="polite">'
        'Preferences are saved in this browser only — no account, and nothing is sent to a server.</p>'
    ), "Changes apply to every page the moment you click them.")

    body += panel("Research defaults", (
        '<div class="pref">'
        '<span class="pref-label"><b>Default cost scenario</b>'
        '<span>Which pane Backtesting opens on. The tabs stay switchable, and every pane '
        'still reflects the same pipeline run.</span></span>'
        + seg("scenario", [("low", "Low"), ("base", "Base"), ("high", "High")]) +
        '</div>'
        '<div class="pref">'
        '<span class="pref-label"><b>Default price window</b>'
        '<span>The span Price Comparison opens on. The chips on that page override it for '
        'the rest of the session.</span></span>'
        + seg("range", [("1m", "1M"), ("3m", "3M"), ("6m", "6M"), ("all", "All")]) +
        '</div>'
    ), "These choose what you <em>see</em> first — they do not change a threshold, a "
       "cost assumption or any computed figure. Those live in config/config.yaml and "
       "the run recorded below.")

    body += panel("This browser", (
        '<div class="pref-actions">'
        '<button type="button" class="btn ghost" id="pref-download">Download preferences</button>'
        '<label class="btn ghost" for="pref-import" style="cursor:pointer">Import preferences</label>'
        '<input id="pref-import" type="file" accept="application/json,.json" style="display:none">'
        '<button type="button" class="btn ghost" id="pref-reset">Reset to defaults</button>'
        '</div>'
        '<p class="note">The exported JSON holds these five settings and nothing else — no '
        'market data and no credentials. Importing one replaces what this browser has saved, '
        'which is the quickest way to move a setup to another machine.</p>'
    ))

    body += panel("Keyboard", (
        '<dl class="shortcut-list">'
        '<dt>← / →</dt><dd>Previous / next page, in rail order</dd>'
        '<dt>?</dt><dd>Open the shortcut panel</dd>'
        '<dt>Esc</dt><dd>Close the panel</dd>'
        '<dt>P</dt><dd>Print, or save the page as PDF</dd>'
        '<dt>Tab</dt><dd>Reach the rail, scenario tabs and contract chips without a mouse</dd>'
        '</dl>'
    ), "The same shortcuts are listed in the overlay, so you can find them from any page.")

    body += f'<script>{SETTINGS_JS}</script>'

    body += panel("Loaded datasets", table(
        ["Dataset", "Rows", "Coverage"], [
            ["Normalized prices", num(len(norm)), coverage(norm)],
            ["Spread / z-score history", num(len(signals)), coverage(signals)],
            ["Clean bhavcopy", num(len(clean)), coverage(clean)],
            ["Rejected rows", num(len(rejections)), "reason-tagged"],
        ]),
        "The export reads these files directly; nothing is downloaded at page load.")
    body += panel("Configuration in force",
                  f'<pre class="code">{html.escape(cfg_text)}</pre>',
                  f"Read-only here — edits belong in config/config.yaml, which both the "
                  f"pipeline and this export read. The figures on every other page come "
                  f"from run <code>{html.escape(str(run_id))}</code>.")
    body += panel("Regenerate",
                  '<pre class="code">python -X utf8 tests/fixtures.py\n'
                  'python -X utf8 -m src.pipeline\n'
                  'python -X utf8 tools/build_static_site.py</pre>',
                  "The first writes sample data only when none is present; the last rebuilds "
                  "these pages from the committed artifacts.")
    out["settings.html"] = shell("settings.html", "Settings",
                                 "Preferences for this browser, plus the data and configuration this "
                                 "export was rendered from.",
                                 body, ChartSink(), "")
    return out


def publish_artwork(target: Path) -> int:
    """Copy the app's scenes, photographs and texture next to the pages.

    The pages reference these by relative path, so the export needs no network
    and no Streamlit static server: ``assets/backgrounds/`` for the vector
    scenes, ``assets/photos/`` for the registered photographs, and
    ``assets/textures/`` for the tiled hero texture.
    """
    copied = 0
    for folder in ("backgrounds", "photos", "textures"):
        (target / "assets" / folder).mkdir(parents=True, exist_ok=True)

    for cfg in PAGE_CANVAS.values():
        scene = SCENES / cfg["scene"]
        if scene.is_file():
            (target / "assets" / "backgrounds" / scene.name).write_bytes(scene.read_bytes())
            copied += 1

    for stem in sorted({cfg["photo"] for cfg in PAGE_CANVAS.values() if cfg["photo"]}):
        photo = photo_file(stem)
        if photo is not None:
            (target / "assets" / "photos" / photo.name).write_bytes(photo.read_bytes())
            copied += 1

    texture = TEXTURES / "texture-terminal.svg"
    if texture.is_file():
        (target / "assets" / "textures" / texture.name).write_bytes(texture.read_bytes())
        copied += 1

    # Rail artwork: the page icons the app shows beside each link, plus the brand
    # mark. Same files, so the export's rail reads like the app's rail.
    (target / "assets" / "icons").mkdir(parents=True, exist_ok=True)
    icons = [icon for _, _, _, icon in PAGES] + ["logo-bullion.svg"]
    for name in icons:
        source = TEXTURES / name
        if source.is_file():
            (target / "assets" / "icons" / name).write_bytes(source.read_bytes())
            copied += 1
    return copied


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="site", help="output directory (default: site)")
    args = parser.parse_args()

    target = (ROOT / args.out).resolve()
    # Files are overwritten in place rather than the directory being rebuilt:
    # on Windows a running preview server holds the folder open, and nothing
    # here needs a fresh tree.
    (target / "assets").mkdir(parents=True, exist_ok=True)

    global AS_OF
    norm = read_parquet("normalized.parquet")
    # The rail stamps the session the numbers are from, like the app's freshness bar.
    if not norm.empty and "trade_date" in norm.columns:
        AS_OF = day(pd.to_datetime(norm["trade_date"]).max())
    spreads = read_parquet("spreads.parquet")
    signals = read_parquet("signals.parquet")

    rejections = pd.DataFrame()
    rejections_p = DATA / "clean" / "rejections.csv"
    if rejections_p.exists():
        try:
            rejections = pd.read_csv(rejections_p)
        except pd.errors.EmptyDataError:
            rejections = pd.DataFrame()

    clean = pd.DataFrame()
    clean_p = DATA / "clean" / "bhavcopy.parquet"
    if clean_p.exists():
        clean = pd.read_parquet(clean_p)

    record, trades, metrics, run_dir = latest_run()

    pages = build(norm, spreads, signals, rejections, clean,
                  record or {}, trades if trades is not None else pd.DataFrame(),
                  metrics or {}, run_dir)

    (target / "assets" / "site.css").write_text(CSS, encoding="utf-8")
    (target / "assets" / "plotly.min.js").write_text(get_plotlyjs(), encoding="utf-8")
    favicon = ROOT / "app" / "assets" / "favicon.png"
    if favicon.exists():
        (target / "assets" / "favicon.png").write_bytes(favicon.read_bytes())
    published = publish_artwork(target)
    for name, html in pages.items():
        (target / name).write_text(html, encoding="utf-8")
    for stale in target.glob("*.html"):
        if stale.name not in pages:
            stale.unlink()

    size = sum(f.stat().st_size for f in target.rglob("*") if f.is_file())
    print(f"wrote {len(pages)} pages to {target} ({size / 1024 / 1024:.1f} MB), "
          f"{published} artwork files")
    for name in sorted(pages):
        print(f"  {name:<18} {(target / name).stat().st_size / 1024:>6.0f} KB")
    if norm.empty:
        print("warning: no normalized.parquet — pages rendered their empty states", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
