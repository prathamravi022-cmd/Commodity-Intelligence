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

PAGES = [
    ("index.html", "Overview"),
    ("contracts.html", "Contracts"),
    ("spreads.html", "Spreads & Z-score"),
    ("signals.html", "Signals"),
    ("backtest.html", "Backtesting"),
    ("quality.html", "Data quality"),
    ("methodology.html", "Methodology"),
]

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
    "spreads.html": {
        "key": "spread-analytics", "scene": "bg-spreads.svg", "photo": "",
        "focal": "center", "position": "50% 50%",
        "glow": ("88%", "6%"), "alpha": 0.14, "scrim": 0.58,
    },
    "signals.html": {
        "key": "signal-explorer", "scene": "bg-signals.svg", "photo": "",
        "focal": "center", "position": "50% 46%",
        "glow": ("76%", "4%"), "alpha": 0.15, "scrim": 0.60,
    },
    "backtest.html": {
        "key": "backtesting", "scene": "bg-backtest.svg", "photo": "",
        "focal": "center", "position": "50% 54%",
        "glow": ("18%", "-6%"), "alpha": 0.12, "scrim": 0.58,
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
        images = [
            (f"radial-gradient(120% 80% at {glow_x} {glow_y}, "
             f"rgba(232,205,138,{cfg['alpha']:.2f}), rgba(232,205,138,0) 60%)"),
            "radial-gradient(90% 64% at 2% 106%, rgba(143,184,236,0.09), "
            "rgba(143,184,236,0) 62%)",
            # relative to site.css itself (which lives in assets/), not the page
            f"url(backgrounds/{cfg['scene']})",
            _scrim(cfg["scrim"]),
        ]
        positions = [f"{glow_x} {glow_y}", "2% 106%", cfg["position"], "center top"]
        photo = photo_file(cfg["photo"])
        if photo is not None:
            images.append(f"url(photos/{photo.name})")
            positions.append(cfg["focal"])
        blocks.append(
            f'body[data-bg="{cfg["key"]}"] {{\n'
            f"  background-image: {', '.join(images)};\n"
            f"  background-size: {', '.join(['cover'] * len(images))};\n"
            f"  background-position: {', '.join(positions)};\n"
            f"  background-repeat: {', '.join(['no-repeat'] * len(images))};\n"
            f"  background-attachment: {', '.join(['fixed'] * len(images))};\n"
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

    def add(self, fig: go.Figure, height: int = 360) -> str:
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
        self.items.append((cid, fig.to_json()))
        return f'<div class="chart" id="{cid}"></div>'

    def scripts(self) -> str:
        payload = "".join(
            f'<script type="application/json" id="spec-{cid}">{spec}</script>' for cid, spec in self.items
        )
        if not self.items:
            return ""
        init = """
<script>
document.querySelectorAll('script[type="application/json"][id^="spec-"]').forEach(function (node) {
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


def shell(slug: str, title: str, subtitle: str, body: str, charts: ChartSink, footer: str) -> str:
    nav = "".join(
        f'<a href="{href}"{" class=\"active\"" if href == slug else ""}>{label}</a>'
        for href, label in PAGES
    )
    key = PAGE_CANVAS.get(slug, {}).get("key", "")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} · Commodity Intelligence</title>
<link rel="icon" type="image/png" href="assets/favicon.png">
<link rel="stylesheet" href="assets/site.css">
<script src="assets/plotly.min.js" charset="utf-8"></script>
</head>
<body data-bg="{key}">
<header class="topbar">
  <a class="brand" href="index.html"><span class="mark">CI</span> Commodity Intelligence</a>
  <nav>{nav}</nav>
</header>
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
}}
a {{ color: var(--gold); text-decoration: none; }}
a:hover {{ color: #fff; }}
.topbar {{
  position: sticky; top: 0; z-index: 10; display: flex; flex-wrap: wrap; gap: 14px;
  align-items: center; justify-content: space-between; padding: 14px 26px;
  border-bottom: 1px solid var(--line);
  background: rgba(7,11,20,.82); backdrop-filter: blur(14px);
}}
.brand {{ display: inline-flex; align-items: center; gap: 10px; color: var(--text); font-weight: 600; letter-spacing: .01em; }}
.mark {{
  display: inline-grid; place-items: center; width: 26px; height: 26px; border-radius: 8px;
  border: 1px solid rgba(232,205,138,.5); color: var(--gold); font-size: 11px; font-weight: 700;
  background: rgba(232,205,138,.10);
}}
nav {{ display: flex; flex-wrap: wrap; gap: 4px; }}
nav a {{
  padding: 6px 11px; border-radius: 999px; color: var(--muted); font-size: 13px;
  border: 1px solid transparent;
}}
nav a:hover {{ color: var(--text); background: rgba(255,255,255,.05); }}
nav a.active {{ color: var(--canvas); background: var(--gold); font-weight: 600; }}
main {{ max-width: 1180px; margin: 0 auto; padding: 34px 24px 64px; }}
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
ul.plain {{ margin: 0; padding-left: 18px; color: var(--muted); }}
ul.plain li {{ margin: 4px 0; }}
code {{ font-family: ui-monospace, "Cascadia Mono", monospace; font-size: 12px;
        background: rgba(255,255,255,.06); padding: 1px 6px; border-radius: 5px; }}
.site-foot {{ max-width: 1180px; margin: 0 auto; padding: 22px 24px 48px; border-top: 1px solid var(--line);
              color: var(--muted); font-size: 12px; }}
.site-foot strong {{ color: var(--gold); font-weight: 600; }}
.site-foot .fine {{ margin-top: 8px; opacity: .75; }}
@media (max-width: 620px) {{
  main {{ padding: 24px 14px 48px; }}
  .topbar {{ padding: 12px 14px; }}
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
    out["contracts.html"] = shell("contracts.html", "Contracts",
                                  "Four gold contracts, one basis — settlement prices, volume and open interest.",
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
    out["spreads.html"] = shell("spreads.html", "Spreads & Z-score",
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
    out["signals.html"] = shell("signals.html", "Signals",
                                "The signal state machine over each pair: Neutral → Watch → Entered → Exited.",
                                body, charts, "")

    # ---------------- Backtesting ----------------
    charts = ChartSink()
    body = ""
    footer = ""
    if trades.empty:
        body = panel("Backtest", '<p class="empty">No backtest run committed.</p>')
    else:
        scenario = "base" if "base" in set(trades["scenario"]) else sorted(trades["scenario"])[0]
        t = trades[trades["scenario"] == scenario].sort_values("entry_date")
        net = t["net_pnl"].to_numpy()
        eq = net.cumsum()
        peak = eq.max() if len(eq) else 0.0
        mdd = float((eq - pd.Series(eq).cummax()).min()) if len(eq) else 0.0
        oos = t[t["split"] == "test"]
        body += cards([
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
        body += panel("Net equity curve — cumulative trade P&L", charts.add(fig, 340),
                      f"Chronological walk-forward; the out-of-sample block starts at "
                      f"{day(oos['entry_date'].min()) if len(oos) else '—'}.")

        per_pair = []
        for value in (metrics.get("pairs") or {}).values():
            per_pair.append([
                str(value.get("pair", "—")), num(value.get("trade_count")),
                pct(value.get("win_rate")), num(value.get("avg_net_per_trade"), 1),
                signed(value.get("total_net_pnl"), 1), num(value.get("max_drawdown"), 1),
                signed(value.get("out_of_sample_net"), 1),
            ])
        if per_pair:
            body += panel("Per-pair outcome", table(
                ["Pair", "Trades", "Win rate", "Avg net / trade", "Total net", "Max DD", "Out-of-sample net"],
                per_pair))

        rows = [[str(r.pair), day(r.entry_date), day(r.exit_date), str(r.direction).replace("_", " "),
                 signed(r.gross_pnl, 2), num(r.cost_total, 2), signed(r.net_pnl, 2), str(r.split)]
                for r in t.itertuples()]
        body += panel("Trade log", table(
            ["Pair", "Entry", "Exit", "Direction", "Gross ₹/g", "Costs", "Net ₹/g", "Split"], rows),
            f"{scenario} cost scenario · {len(t)} closed trades from run "
            f"{record.get('run_id', run_dir.name if run_dir else '—')}.")
        min_trades = metrics.get("min_trades_required")
        if min_trades and len(oos) < int(min_trades):
            footer = panel("Evidence note",
                           f'<p class="empty">{len(oos)} out-of-sample trades against a '
                           f'{int(min_trades)}-trade minimum. Treat every number on this page as '
                           f'underpowered, not as validation.</p>')
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
    out["quality.html"] = shell("quality.html", "Data quality",
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

    norm = read_parquet("normalized.parquet")
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
