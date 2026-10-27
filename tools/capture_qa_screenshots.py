"""Capture and audit every page of the dashboard at three viewport widths.

The pack is evidence, not decoration: each capture records whether the page
threw a Streamlit exception, whether the layout overflows horizontally, whether
any colour falls outside the four-family palette, whether exactly one rail item
is marked current, and whether every photographic layer behind the glass
resolves to a real file.

The image contract is background-only: no page places a photograph in the flow,
so the audit reads the computed ``background-image`` stack of the canvas, the
hero band, the contract cards and the closing band instead of looking for
``<img>`` tags.

Usage
-----
    python tools/capture_qa_screenshots.py                     # http://127.0.0.1:8601
    python tools/capture_qa_screenshots.py --base-url http://127.0.0.1:8601
    python tools/capture_qa_screenshots.py --only spread-analytics

Output goes to ``qa/``: ``manifest.json``, ``index.html`` and
``screenshots/{mobile,tablet,desktop}-NN-<page>.png`` (viewport) plus
``…-full.png`` (whole page).
"""
from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
PACK_DIR = ROOT / "qa"
SHOT_DIR = PACK_DIR / "screenshots"

# (slug, display name) in rail order — must match app/components.NAV_PAGES.
PAGES = [
    ("", "Overview"),
    ("gold-contracts", "Gold Contracts"),
    ("price-comparison", "Price Comparison"),
    ("spread-analytics", "Spread Analytics"),
    ("signal-explorer", "Signal Explorer"),
    ("backtesting", "Backtesting"),
    ("data-quality", "Data Quality"),
    ("methodology", "Methodology"),
    ("settings", "Settings"),
]

VIEWPORTS = {
    "mobile": (390, 844),
    "tablet": (768, 1024),
    "desktop": (1440, 900),
}

RENDER_WAIT_MS = 2200
MAX_FULL_HEIGHT = 7000

# Streamlit's frontend probes these relative to the current page path, so on a
# sub-route (/backtesting) they 404. Known benign: the page still renders and
# the app falls back to its host config.
BENIGN_URL_PARTS = ("_stcore/health", "_stcore/host-config")

# The four surfaces that must carry a photographic layer (see app/theme.py).
BACKGROUND_SURFACES = (".stApp", ".hero-band", ".spec-card", ".disclaimer")

# The palette is four hue families and nothing else (see app/artwork.py).
HUE_BANDS = ((340, 360), (0, 15), (20, 58), (140, 178), (200, 250))
SAT_FLOOR = 0.12

PALETTE_JS = """
({bands, floor}) => {
  const parse = (raw) => {
    if (typeof raw !== 'string') return null;
    const m = raw.match(/^rgba?\\(([^)]+)\\)$/);
    if (!m) return null;
    const p = m[1].split(',').map(v => parseFloat(v.trim()));
    if (p.length < 3 || p.slice(0, 3).some(Number.isNaN)) return null;
    return {r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1};
  };
  const hueSat = (c) => {
    const r = c.r / 255, g = c.g / 255, b = c.b / 255;
    const max = Math.max(r, g, b), min = Math.min(r, g, b);
    const d = max - min;
    if (d === 0) return {h: 0, s: 0};
    const l = (max + min) / 2;
    const s = d / (1 - Math.abs(2 * l - 1));
    let h;
    if (max === r) h = 60 * (((g - b) / d) % 6);
    else if (max === g) h = 60 * ((b - r) / d + 2);
    else h = 60 * ((r - g) / d + 4);
    if (h < 0) h += 360;
    return {h, s};
  };
  const out = [], seen = new Set();
  const check = (raw, where) => {
    const c = parse(raw);
    if (!c || c.a <= 0.05) return;
    const hs = hueSat(c);
    if (hs.s < floor) return;                    // neutral
    if (bands.some(([lo, hi]) => hs.h >= lo && hs.h <= hi)) return;
    const key = where + '|' + raw;
    if (seen.has(key)) return;
    seen.add(key);
    out.push({where, color: raw, hue: Math.round(hs.h),
              sat: Math.round(hs.s * 100) / 100});
  };
  document.querySelectorAll('.js-plotly-plot').forEach((plot, i) => {
    (plot._fullData || []).forEach((tr, j) => {
      const tag = 'chart' + i + '.trace' + j;
      if (tr.line) check(tr.line.color, tag + '.line');
      if (tr.marker) {
        const mc = tr.marker.color;
        if (typeof mc === 'string') check(mc, tag + '.marker');
        else if (Array.isArray(mc)) mc.forEach(c => check(c, tag + '.marker'));
        if (tr.marker.line) check(tr.marker.line.color, tag + '.marker.line');
      }
      check(tr.fillcolor, tag + '.fill');
      (tr.colorscale || []).forEach(st => check(st && st[1], tag + '.colorscale'));
      if (tr.increasing && tr.increasing.marker) check(tr.increasing.marker.color, tag + '.increasing');
      if (tr.decreasing && tr.decreasing.marker) check(tr.decreasing.marker.color, tag + '.decreasing');
      if (tr.totals && tr.totals.marker) check(tr.totals.marker.color, tag + '.totals');
    });
    const layout = plot._fullLayout || {};
    (layout.colorway || []).forEach(c => check(c, 'chart' + i + '.colorway'));
    check(layout.paper_bgcolor, 'chart' + i + '.paper');
    ((layout.colorscale && layout.colorscale.sequential) || [])
      .forEach(st => check(st && st[1], 'chart' + i + '.colorscale'));
  });
  const sel = '.badge,.status-chip,.meta-item,.config-chip,.caveat,.stale-banner,'
            + '.empty-link,.rail-name,.rail-status,.spec-price,.sample-flag';
  document.querySelectorAll(sel).forEach((el) => {
    const cs = getComputedStyle(el);
    const tag = String(el.className || 'el').split(' ')[0];
    check(cs.color, 'css.' + tag + '.color');
    check(cs.backgroundColor, 'css.' + tag + '.bg');
    check(cs.borderTopColor, 'css.' + tag + '.border');
  });
  return out;
}
"""

RAIL_JS = """
() => {
  const links = [...document.querySelectorAll('section[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"]')];
  const active = links.filter(a => a.closest('[class*="st-key-rail-active"]'));
  return {
    items: links.length,
    active: active.map(a => a.innerText.trim()),
    sidebar_visible: (() => {
      const s = document.querySelector('section[data-testid="stSidebar"]');
      if (!s) return false;
      const r = s.getBoundingClientRect();
      return r.width > 120 && r.right > 0;
    })(),
  };
}
"""


def wait_for_run(page) -> None:
    try:
        page.wait_for_selector('[data-testid="stAppViewContainer"]', timeout=30_000)
    except Exception:
        pass
    try:
        page.wait_for_function(
            """() => {
                const w = document.querySelector('[data-testid="stStatusWidget"]');
                return !w || !w.offsetParent;
            }""",
            timeout=30_000,
        )
    except Exception:
        pass
    # The status widget disappears before the page body is finished: on a cold
    # server the header and the rail can still be empty a second later. Wait for
    # the two landmarks every capture asserts on rather than hoping a fixed sleep
    # covers it.
    try:
        page.wait_for_function(
            """() => {
                const h1 = document.querySelector('h1');
                const rail = document.querySelectorAll(
                    'section[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"]');
                return !!(h1 && h1.innerText.trim()) && rail.length > 0;
            }""",
            timeout=30_000,
        )
    except Exception:
        pass
    page.wait_for_timeout(RENDER_WAIT_MS)
    # Charts, dataframes and the metric tiles mount as skeleton blocks before
    # Plotly sizes them. Shooting then records a grey placeholder and a chart
    # count of zero on a page that does have charts, so wait for the last
    # skeleton to be replaced (bounded — a page may legitimately keep one).
    try:
        page.wait_for_function(
            """() => document.querySelectorAll('[data-testid="stSkeleton"]').length === 0""",
            timeout=20_000,
        )
    except Exception:
        pass


BACKGROUNDS_JS = """
({surfaces}) => {
  const seen = [];
  surfaces.forEach((sel) => {
    document.querySelectorAll(sel).forEach((el, i) => {
      const layers = getComputedStyle(el).backgroundImage || '';
      const urls = [...layers.matchAll(/url\\((['"]?)([^'")]+)\\1\\)/g)]
        .map(m => m[2])
        .filter(u => !u.startsWith('data:'))
        .map(u => new URL(u, location.href).href);
      if (urls.length) seen.push({surface: sel + (i ? ':nth' + i : ''), urls});
    });
  });
  const inline = [...document.querySelectorAll('img')]
    .map(i => i.currentSrc || i.src)
    .filter(src => src.includes('/app/static/photos'));
  const fixed = getComputedStyle(document.querySelector('.stApp')).backgroundAttachment;
  return {layers: seen, inline_photos: inline, attachment: fixed};
}
"""


def audit_backgrounds(page, context) -> dict:
    """Read every photographic layer and confirm the file behind it exists."""
    found = page.evaluate(BACKGROUNDS_JS, {"surfaces": list(BACKGROUND_SURFACES)})
    statuses: dict[str, int | str] = {}
    for layer in found["layers"]:
        for url in layer["urls"]:
            if url in statuses:
                continue
            try:
                statuses[url] = context.request.get(url).status
            except Exception as exc:                     # network hiccup
                statuses[url] = f"{type(exc).__name__}: {exc}"
    found["statuses"] = statuses
    return found


# Streamlit keeps the page inside its own scroll container (section[data-testid
# ="stMain"]), so the document itself never grows and `full_page=True` only
# ever returns one screen. Lifting the fixed height and the overflow off that
# chain of wrappers lets the document take the full content height. Nothing is
# resized, so Plotly and the metric tiles keep the layout they already drew —
# resizing a rendered page blanks both, which is why the earlier whole-page
# shots were empty below the fold.
FULL_PAGE_CSS = """
html, body, [data-testid="stApp"], [data-testid="stAppViewContainer"],
[data-testid="stMain"], [data-testid="stMain"] > div {
  height: auto !important;
  max-height: none !important;
  overflow: visible !important;
}
"""


def expand_for_full_page(page) -> int:
    """Lift Streamlit's internal scroll clip so the whole page can be shot."""
    page.add_style_tag(content=FULL_PAGE_CSS)
    page.evaluate("() => window.scrollTo(0, 0)")
    page.wait_for_timeout(900)
    previous = -1
    for _ in range(6):
        height = page.evaluate("() => document.documentElement.scrollHeight")
        if height == previous:
            break
        previous = height
        page.wait_for_timeout(500)
    return max(previous, 0)


def content_height(page) -> int:
    return page.evaluate(
        """() => {
            const main = document.querySelector('[data-testid="stMain"]');
            const block = document.querySelector('.block-container');
            return Math.max(main ? main.scrollHeight : 0,
                            block ? block.scrollHeight : 0,
                            document.body.scrollHeight);
        }"""
    )


def capture(base_url: str, pack_dir: Path, color_scheme: str = "dark",
            only: str | None = None) -> dict:
    shot_dir = pack_dir / "screenshots"
    shot_dir.mkdir(parents=True, exist_ok=True)
    # Windows/OneDrive can hold a lock on the directory itself; pruning the files
    # is enough and never blocks the run.
    for stale in shot_dir.glob("*.png"):
        try:
            stale.unlink()
        except OSError:
            pass

    records: list[dict] = []
    with sync_playwright() as pw:
        try:
            browser = pw.chromium.launch()
        except Exception:
            # A Playwright upgrade can leave its bundled browser uninstalled;
            # fall back to the system Chrome/Chromium instead of failing.
            browser = pw.chromium.launch(channel="chrome")
        for view, (width, height) in VIEWPORTS.items():
            for idx, (slug, name) in enumerate(PAGES, start=1):
                if only and only not in (slug or "overview"):
                    continue
                context = browser.new_context(
                    viewport={"width": width, "height": height},
                    color_scheme=color_scheme,
                    device_scale_factor=1,
                )
                page = context.new_page()
                console_errors: list[str] = []
                page_errors: list[str] = []
                bad_responses: list[dict] = []
                page.on("console", lambda m: console_errors.append(m.text)
                        if m.type == "error" else None)
                page.on("pageerror", lambda e: page_errors.append(str(e)))
                page.on("response", lambda r: bad_responses.append(
                    {"url": r.url, "status": r.status}) if r.status >= 400 else None)

                url = f"{base_url}/{slug}" if slug else f"{base_url}/"
                key = slug or "overview"
                record: dict = {"view": view, "page": name, "slug": slug or "/",
                                "url": url, "width": width, "height": height}
                file_name = f"{view}-{idx:02d}-{key}.png"
                target = shot_dir / file_name
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=45_000)
                    wait_for_run(page)

                    record["heading"] = page.evaluate(
                        "() => document.querySelector('h1')?.innerText || ''")
                    record["exceptions"] = page.evaluate(
                        """() => [...document.querySelectorAll('[data-testid="stException"]')]
                                 .map(e => e.innerText.slice(0, 400))""")
                    record["rail"] = page.evaluate(RAIL_JS)
                    record["charts"] = page.evaluate(
                        "() => document.querySelectorAll('.js-plotly-plot').length")
                    # Every visible chart must keep its axis labels inside the
                    # glass panel. Plotly paints them within a fixed canvas
                    # height, so panel padding or a small margin clips them to
                    # unreadable slivers — text that exists but cannot be read.
                    record["chart_labels"] = page.evaluate(
                        """() => {
                            const plots = [...document.querySelectorAll('.js-plotly-plot')];
                            if (!plots.length) return null;
                            for (const plot of plots) {
                                const cont = plot.closest('[data-testid="stPlotlyChart"]');
                                if (!cont) continue;
                                const box = cont.getBoundingClientRect();
                                const sel = '.xtick text, .ytick text';
                                for (const t of plot.querySelectorAll(sel)) {
                                    const s = getComputedStyle(t);
                                    const r = t.getBoundingClientRect();
                                    // Plotly leaves zero-sized labels in the DOM for
                                    // ticks it chose not to draw; those are not
                                    // clipped text and must not fail the check.
                                    if (s.visibility === 'hidden' || s.display === 'none'
                                            || !t.textContent.trim()
                                            || r.width === 0 || r.height === 0) continue;
                                    if (r.bottom > box.bottom + 1 || r.top < box.top - 1
                                            || r.left < box.left - 1) return false;
                                }
                            }
                            return true;
                        }""")
                    record["overflow_px"] = page.evaluate(
                        """() => {
                            const main = document.querySelector('[data-testid="stMain"]');
                            const a = main ? main.scrollWidth - main.clientWidth : 0;
                            const b = document.documentElement.scrollWidth
                                      - document.documentElement.clientWidth;
                            return Math.max(a, b);
                        }""")
                    record["palette"] = page.evaluate(
                        PALETTE_JS,
                        {"bands": [list(b) for b in HUE_BANDS], "floor": SAT_FLOOR})
                    record["artwork_loaded"] = page.evaluate(
                        """() => Document.prototype.querySelectorAll.call(document, '.ph-mark img')
                                 .length ? [...document.querySelectorAll('.ph-mark img')]
                                 .every(i => i.complete && i.naturalWidth > 0) : null""")
                    # Photographs are a background fetch, not markup: record
                    # every layer and the status of the file behind it. A wrong
                    # static path (or a build that never ran) shows up here.
                    record["backgrounds"] = audit_backgrounds(page, context)

                    page.screenshot(path=str(target), full_page=True, timeout=90_000,
                                    animations="disabled")
                    record["file"] = file_name

                    full_name = f"{view}-{idx:02d}-{key}-full.png"
                    full_target = shot_dir / full_name
                    measured = content_height(page)
                    target_h = expand_for_full_page(page)
                    tall_clip = target_h > MAX_FULL_HEIGHT
                    page.screenshot(path=str(full_target), full_page=True,
                                    timeout=90_000, animations="disabled",
                                    clip={"x": 0, "y": 0, "width": width,
                                          "height": min(target_h, MAX_FULL_HEIGHT)}
                                    if tall_clip else None)
                    record["full_file"] = full_name
                    record["full_height"] = target_h
                    record["full_clipped"] = tall_clip
                    record["content_height"] = measured

                    record["console_errors"] = sorted(set(console_errors))
                    record["page_errors"] = page_errors
                    record["bad_responses"] = bad_responses
                    rail = record["rail"]
                    # page_link renders the Material icon inside the link text, so
                    # the label is contained in (not equal to) the active text.
                    active_ok = (len(rail["active"]) == 1
                                 and name.lower() in rail["active"][0].lower())
                    overflow_ok = record["overflow_px"] <= 0
                    palette_ok = not record["palette"]
                    real_bad = [r for r in bad_responses
                                if not any(part in r["url"] for part in BENIGN_URL_PARTS)]
                    record["checks"] = {
                        "heading": record["heading"].strip().lower() == name.lower(),
                        "no_exception": not record["exceptions"],
                        "no_page_error": not page_errors,
                        "no_http_error": not real_bad,
                        "no_overflow": overflow_ok,
                        "palette": palette_ok,
                        "rail_active": active_ok,
                        "artwork": record["artwork_loaded"] in (True, None),
                        "chart_labels": record["chart_labels"] in (True, None),
                        "backgrounds": bool(record["backgrounds"]["layers"])
                                       and not record["backgrounds"]["inline_photos"]
                                       and all(s == 200 for s
                                               in record["backgrounds"]["statuses"].values()),
                    }
                    record["ok"] = all(record["checks"].values())
                except Exception as exc:
                    record["error"] = f"{type(exc).__name__}: {exc}"
                    record["ok"] = False
                print(f"[{'ok  ' if record.get('ok') else 'FAIL'}] "
                      f"{view:7s} {name:20s} -> {file_name}", flush=True)
                records.append(record)
                context.close()
        browser.close()

    manifest = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "base_url": base_url,
        "color_scheme": color_scheme,
        "pages": [{"slug": s or "/", "name": n} for s, n in PAGES],
        "viewports": VIEWPORTS,
        "results": records,
        "summary": {
            "captures": len(records),
            "ok": sum(1 for r in records if r.get("ok")),
            "failed": [f"{r['view']} · {r['page']}" for r in records if not r.get("ok")],
        },
    }
    (pack_dir / "manifest.json").write_text(json.dumps(manifest, indent=2),
                                            encoding="utf-8")
    (pack_dir / "index.html").write_text(gallery_html(manifest), encoding="utf-8")
    return manifest


def gallery_html(manifest: dict) -> str:
    cards = []
    for rec in manifest["results"]:
        badge = "ok" if rec.get("ok") else "fail"
        issues = []
        for name, passed in (rec.get("checks") or {}).items():
            if not passed:
                issues.append(name)
        for exc in rec.get("exceptions") or []:
            issues.append(exc.splitlines()[0])
        cards.append(f"""
    <figure class="card {badge}">
      <a href="screenshots/{rec.get('file', '')}">
        <img loading="lazy" src="screenshots/{rec.get('file', '')}" alt="{rec['page']} {rec['view']}">
      </a>
      <figcaption>
        <strong>{rec['page']}</strong> · {rec['view']} ({rec['width']}px)
        <span class="tag {badge}">{badge}</span>
        {f'<div class="issues">{"; ".join(issues[:4])}</div>' if issues else ''}
      </figcaption>
    </figure>""")
    summary = manifest["summary"]
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Commodity Intelligence — QA pack</title>
<style>
  :root {{ --ink:#101828; --muted:#5A6577; --line:#E6E9EF; --gold:#A67C00;
           --ok:#0E7C57; --bad:#B42318; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; padding:28px; background:#F6F7F9; color:var(--ink);
          font-family:Inter,system-ui,-apple-system,sans-serif; }}
  h1 {{ font-size:22px; margin:0 0 4px; letter-spacing:-.02em; }}
  .meta {{ color:var(--muted); font-size:13px; margin-bottom:22px; }}
  .summary {{ display:flex; gap:10px; margin-bottom:22px; flex-wrap:wrap; }}
  .pill {{ background:#fff; border:1px solid var(--line); border-radius:8px;
           padding:7px 12px; font-size:13px; }}
  .pill b {{ color:var(--ok); }}
  .pill.bad b {{ color:var(--bad); }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(300px,1fr)); gap:18px; }}
  .card {{ margin:0; background:#fff; border:1px solid var(--line); border-radius:10px;
           overflow:hidden; }}
  .card.fail {{ border-color:#E7B4AF; }}
  .card img {{ width:100%; display:block; border-bottom:1px solid var(--line); }}
  figcaption {{ padding:10px 12px; font-size:13px; color:var(--muted); }}
  figcaption strong {{ color:var(--ink); }}
  .tag {{ float:right; font-size:11px; text-transform:uppercase; letter-spacing:.06em;
          padding:2px 7px; border-radius:5px; }}
  .tag.ok {{ color:var(--ok); background:rgba(14,124,87,.10); }}
  .tag.fail {{ color:var(--bad); background:rgba(180,35,24,.10); }}
  .issues {{ margin-top:6px; color:var(--bad); font-size:12px; }}
  code {{ background:#fff; border:1px solid var(--line); border-radius:4px; padding:1px 5px; }}
</style></head>
<body>
  <h1>Commodity Intelligence — QA pack</h1>
  <div class="meta">Generated {manifest['generated_at']} UTC · {manifest['base_url']} ·
    {len(manifest['pages'])} pages × {len(manifest['viewports'])} widths ·
    colour scheme emulated as <code>{manifest['color_scheme']}</code></div>
  <div class="summary">
    <span class="pill">Captures <b>{summary['captures']}</b></span>
    <span class="pill">Passing <b>{summary['ok']}</b></span>
    <span class="pill {'bad' if summary['failed'] else ''}">Failing
      <b>{len(summary['failed'])}</b></span>
  </div>
  <div class="grid">{''.join(cards)}</div>
</body></html>"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8601")
    ap.add_argument("--out", default=str(PACK_DIR))
    ap.add_argument("--color-scheme", default="dark",
                    choices=["light", "dark", "system"],
                    help="Emulate a visitor's OS colour scheme (the app is dark-only).")
    ap.add_argument("--only", default=None,
                    help="Capture a single page by slug, e.g. spread-analytics.")
    args = ap.parse_args()
    manifest = capture(args.base_url, Path(args.out), args.color_scheme, args.only)
    summary = manifest["summary"]
    print(f"\n{summary['ok']}/{summary['captures']} captures passed")
    for failure in summary["failed"]:
        print(f"  FAIL {failure}")
    return 0 if not summary["failed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
