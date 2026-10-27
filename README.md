# Commodity Intelligence — Team Starway

A research dashboard for MCX gold relative value. It ingests exchange bhavcopy
CSVs, validates them, restates four gold contracts (GOLDM, GOLDTEN, GOLDGUINEA,
GOLDPETAL) to a single fine-gold INR/gram basis, computes pairwise spreads with
rolling z-scores, runs a walk-forward backtest with explicit transaction costs,
and surfaces the results as a focused analytics product.

> **Research prototype — not investment advice.**
> It uses exchange settlement prices, which are not executable fill prices.
> Past backtest results do not predict future performance. Signals are research
> outputs, not trade recommendations.

## Quick start

```bash
cd commodity-intel
python -m pip install -r requirements.txt

# 1) Generate synthetic sample data (no network required)
python -X utf8 tests/fixtures.py

# 2) Run the full pipeline (~20 s)
python -X utf8 -m src.pipeline

# 3) Launch the dashboard
python -m streamlit run app/Home.py --server.port 8601
```

Open <http://localhost:8601>. All pipeline assumptions live in
[config/config.yaml](config/config.yaml). Copy [.env.example](.env.example) to
`.env` only if you intend to download files; the dashboard itself never calls a
market API.

## Deploying

The Streamlit app is a long-running server with a persistent WebSocket, so it
needs a host that keeps a process alive (Streamlit Community Cloud, a VM, a
container). A serverless host such as Vercel cannot run it — there is no setting
that turns a function into an always-on Streamlit server.

For those hosts the repo also ships a **static export**: the same artifacts
rendered to plain HTML and Plotly JSON, committed in `site/` and served as
static files.

```bash
python -X utf8 tools/build_static_site.py     # regenerate site/ after a pipeline run
```

| Page | File |
|---|---|
| Overview — coverage, validation, prices, strongest pairs | `site/index.html` |
| Contracts — summary, quoted prices, volume | `site/contracts.html` |
| Spreads & Z-score — top pair histories, latest spreads | `site/spreads.html` |
| Signals — state counts, z-score bands, latest state | `site/signals.html` |
| Backtesting — KPIs, equity curve, per-pair, trade log | `site/backtest.html` |
| Data quality — coverage, presence ribbon, rejections | `site/quality.html` |
| Methodology — formulas, design, limitations | `site/methodology.html` |

The export keeps the app's artwork: each page carries its own vector scene and
(where the app has one) its registered photograph, copied into
`site/assets/backgrounds` and `site/assets/photos`, with the Overview opening on
the same photographic band. The layer order — gold light, cool counter-light,
scene, navy scrim, photograph — is the one in [app/backgrounds.py](app/backgrounds.py),
so the hosted pages are lit like the running app. Credits travel with the
pictures: the band prints its author and licence, and no scene or photograph is
fetched from the network.

**Vercel.** [vercel.json](vercel.json) sets `outputDirectory` to `site`, blanks
the install and build steps, and disables framework auto-detection — so a
deployment serves the committed static pages instead of trying to compile them.
Push, or set the project's *Framework Preset* to **Other** with empty build
settings, and the export goes live. Regenerate `site/` and commit it whenever
the data changes; the deploy never rebuilds it.

**Streamlit Community Cloud** runs the real app: repository
`prathamravi022-cmd/Commodity-Intelligence`, branch `main`, main file
`app/Home.py`, Python 3.12, no secrets.

## Pipeline

```
data/raw/*.csv  (one file per requested date, MCX bhavcopy layout)
   │
   ▼  src.ingest       download or manual CSV import + manifest (sha256, row counts)
   ▼  src.validate     schema-strict parse, reason-tagged rejection rows
   │                   MISSING_FIELD, PRICE_RANGE, DATE_MISMATCH,
   │                   BAD_DATE_FORMAT, BAD_EXPIRY, DUPLICATE
   ▼  data/clean/*.parquet + rejections tracked per file
   ▼  src.normalize    INR/gram fine: price × (trading_unit/quoted_unit) / purity
   ▼  src.analytics    pairwise spreads, carry adjustment, rolling z-score,
   │                   signal state machine (Neutral → Watch → Entered → Exited)
   ▼  src.backtest     walk-forward, chronological split, explicit costs
   ▼  data/results/<run_id>/  trades.csv, metrics.json, run.json
   ▼  app/             Streamlit dashboard (read-only over data/analytics + data/results)
```

## The dashboard

Nine pages, grouped in the navigation rail. Every page reads only the artifacts
above — nothing recomputes the pipeline on page load.

| Page | What it answers |
|---|---|
| **Overview** | Current state: contract count, latest data date, validation status, backtest status, full price history, strongest pair, contract comparison |
| **Gold Contracts** | Contract specifications, why raw prices are not comparable, expiry/liquidity state, and the settlement curve with carry residual and 3D surface |
| **Price Comparison** | All four contracts on one axis, contract/date selection, raw values on hover, row data and CSV export |
| **Spread Analytics** | One pair at a time: spread (raw or carry residual), rolling mean/std, z-score, entry and exit markers |
| **Signal Explorer** | Configurable window and watch/entry/exit thresholds, per-pair state and direction, entry/exit markers on the z-chart, episode timeline, episode detail, dwell and frequency statistics, a calculation audit trail, and the alert log |
| **Backtesting** | Gross/net P&L, trade count, win rate, drawdown, cost sensitivity, equity curve with the train/test split, trade log, attribution waterfall |
| **Data Quality** | Coverage per contract, rows per contract per date, rejections with reasons, **CSV import with column mapping**, import history, shareable data-quality report, source checksums, validation rules |
| **Methodology** | Normalization, spread/carry/z formulas, cost model, backtest design, limitations, sources |
| **Settings** | Session defaults, data reload, configuration in force, environment |

Analysis parameters (window, threshold, pair, contract selection, cost scenario)
are real controls: each one recomputes or refilters what is on screen. The
defaults on **Settings** seed the analysis pages for the session and never
rewrite `config/config.yaml` — a dashboard click cannot silently change a
backtest's assumptions.

## Design system

A light research workspace with a navy navigation rail: dense, quiet and
print-like where the numbers are, dark and fixed where navigation lives.

| Token | Value | Used for |
|---|---|---|
| `CANVAS` | `#F6F7F9` | page background |
| `SURFACE` | `#FFFFFF` | cards, charts, tables |
| `LINE` | `#E6E9EF` | hairline borders |
| `RAIL` | `#0C1626` | navigation rail |
| `TEXT` / `TEXT_MUTED` | `#101828` / `#5A6577` | primary and secondary copy |
| `GOLD` | `#A67C00` | brand accent, active nav marker, key rules |
| `UP` / `DOWN` | `#0E7C57` / `#B42318` | positive / negative movement, long / short |
| `WARN` | `#B54708` | stale data and caution states |

Rules the code enforces, not just guidelines:

- **Green and red mean direction, nothing else.** They are used for signed P&L,
  day change, long/short and the net equity line — a negative curve is red, even
  when it is the "good" series. Nothing decorative uses them.
- **Gold is brand, not status.** Active navigation, section rules, accents.
- **Four families only** — gold, red, green, navy. `palette_violations()` in
  [app/artwork.py](app/artwork.py) fails on any other hue, and the QA harness
  applies the same bands to every rendered chart and styled surface.
- **Contract identity never rests on colour alone**: GOLDM/GOLDTEN/GOLDGUINEA/
  GOLDPETAL each carry a distinct dash pattern as well as a colour, so the
  series stay separable in greyscale.
- **Charts share one Plotly template** (`mcx_glass`, registered and set as the
  default in [app/theme.py](app/theme.py)), so no chart can drift off-palette.

Typography is Inter for interface text and JetBrains Mono for every figure, so
columns of numbers align. Radii are 8–10px, shadows are single-pixel, and motion
is limited to 150–200ms hover transitions — all disabled under
`prefers-reduced-motion`.

### Navigation and responsiveness

The rail is grouped **Workspace** (Overview, Gold Contracts, Price Comparison,
Spread Analytics, Signal Explorer), **Research** (Backtesting, Data Quality,
Methodology) and **Preferences** (Settings). It is rendered by
`rail_nav()` over `st.page_link`, with the current page marked gold; the native
page list is hidden. The registry in
[app/components.py](app/components.py) (`NAV_PAGES`) is the single source of
truth for order, labels, icons, routes and page artwork — a test fails if a
registered script is missing.

Every header also carries the same top bar: a semantic breadcrumb (`nav`
landmark), market/data-as-of/last-run chips derived from real state, and quiet
links to the related pages (the hero band shows them as its two calls to
action). No header invents a user, a notification or a live-market feed.

| Width | Behaviour |
|---|---|
| ≥1100px | rail open (collapsible), KPI tiles in one row, contract cards 4-up |
| 820–1100px | rail collapses to the drawer, tiles wrap, contract cards 2-up |
| ≤820px | columns stack, header actions and meta wrap below the title |
| ≤640px | one metric per row, contract cards 1-up, drawer closed on first visit, no horizontal overflow |

The rail is Streamlit's own sidebar, so its collapsed state is remembered by the
browser. It is never pinned open: the chevron inside the rail closes it and the
pill floating over the canvas reopens it at any width, so a remembered collapsed
can never strand a wide screen without navigation. `initial_sidebar_state="auto"`
opens the rail on a desktop's first visit and leaves a phone with the dashboard
rather than the drawer covering it; below 1025px it is the native overlay
drawer. A test fails if a rule that forces it open comes back.

Photographs follow the same rules: the hero band always renders its headline
first and treats the photograph only as a layer beneath the navy scrim (reframed
at ≤1100px, tighter type at ≤820px and ≤640px), contract thumbnails go 4-up →
2-up → 1-up, and the pipeline diagram scrolls inside its own panel instead of
the page.

### Authentication (optional)

The application ships **open**: with no `[auth]` block in
[.streamlit/secrets.toml](.streamlit/secrets.toml.example) every page renders and
[app/auth.py](app/auth.py) is inert, which is what keeps the test suite and the
QA harness working on a fresh checkout. Adding a complete block turns a sign-in
gate on for the whole product from one place — `require_auth()` in
[app/Home.py](app/Home.py) runs before the rail and before any page script, so a
new page cannot forget it.

Sign-in uses **Streamlit's native OIDC** (`st.login` / `st.user` / `st.logout`)
with Clerk as the identity provider. No Clerk package is installed and no
publishable key reaches the browser: Streamlit runs the authorisation-code flow
and keeps the tokens in a signed cookie, and Clerk only supplies the discovery
document. A clerk user's name and email in the rail come from the verified ID
token, never from a query parameter.

| Step | Where |
|---|---|
| Enable OIDC, copy the discovery URL | Clerk dashboard → Configure |
| Register `http://localhost:8601/oauth2callback` (dev) and `https://<domain>/oauth2callback` (prod) | Clerk → allowed redirect URIs |
| Fill `client_id`, `client_secret`, `server_metadata_url`, `redirect_uri`, `cookie_secret` | `.streamlit/secrets.toml` (copy the `.example` file; never commit it) |

`cookie_secret` is a string you generate — `python -c "import secrets; print(secrets.token_urlsafe(32))"`
— not a Clerk value. A half-filled block leaves the app open rather than locking
everyone out of a working prototype.

### Photography

The product carries nine licensed photographs and nothing more: the cinematic
**Overview** hero backdrop, a banner plus one thumbnail per contract on **Gold
Contracts**, a seamless gold texture used as a wash behind contract cards and
the closing band, an assay card on **Data Quality**, a catalogued specimen on
**Methodology**, and a drawn pipeline diagram beside it. The four contract
thumbnails are reused where a colour needs a physical meaning: as the key above
the line chart on **Price Comparison** (the dot repeats the line colour) and as
the two-leg strip on **Spread Analytics**. Every chart, table and figure is
generated from the pipeline outputs — no image is ever a stand-in for a number.

| Concern | How it is handled |
|---|---|
| Licensing | `PHOTOS` in [app/artwork.py](app/artwork.py) records author, licence and Commons file page; a test fails if any entry is missing them |
| Attribution | The credit line is part of the component (`.hero-credit`, `figcaption`, `.key-credit`, `.pair-credit`), plus a full list on **Methodology → Image credits** and in [docs/photo-credits.md](docs/photo-credits.md) — including the two images applied as CSS backgrounds |
| Honesty | Contract cards caption their photo as illustrative; specifications come from `config/config.yaml`, never from the picture |
| Weight | WebP at two widths (320/640 for thumbnails, 800/1600 for the banner, 960/1600 for the hero backdrop, 256/512 for the tile), 14 files / 565 KB for the whole set, `srcset` + `sizes` so a small slot never downloads the large file |
| Accessibility | Descriptive `alt` text on every image, `width`/`height` to prevent layout shift, lazy loading except the above-the-fold hero |
| Serving | `[server] enableStaticServing` in [.streamlit/config.toml](.streamlit/config.toml) exposes `app/static/` at `/app/static/`, so photos are cacheable requests instead of base64 in every rerun |

```bash
python tools/build_photos.py            # fetch originals, crop, encode, write credits
python tools/build_photos.py --check    # verify the committed set (offline)
```

The build finds the amber mass in each frame and crops around it, writing the
box it used into the credits file: a refreshed original cannot silently reframe a
card. Originals are cached in `tools/_photo_sources/` (git-ignored).

### Backgrounds

Layered material instead of wallpaper: four surfaces carry imagery, and none of
them ever sits between a reader and a number.

| Surface | Layering (top → bottom) |
|---|---|
| App canvas | `texture-canvas.svg` as a data URI at 480px, single-digit opacity over `#F6F7F9` |
| **Overview** hero band | navy wash → vertical vignette → `texture-terminal.svg` grid → `backdrop-hero` photograph, `background-size: cover` with a per-breakpoint `background-position` |
| Contract cards | white gradient (opaque by the data rows) over `tile-gold` at ~14% at the top, under the full-bleed thumbnail |
| Closing disclaimer | the same navy and terminal grid as the hero, with the gold top rule that opens and closes every page |

Every background has a solid fallback colour beneath it (`#0B1220` for the navy
bands, `#FFFFFF` for the cards), so a failed request leaves a clean surface
rather than a hole. Charts, tables and metric tiles stay on solid `$SURFACE`:
`palette_violations()` and the QA harness would flag anything off-palette behind
a figure. There are no animated backgrounds, and `prefers-reduced-motion`
disables the remaining hover transitions.

### Data honesty

- A stale dataset (>1 trading day old) shows a banner **and** mutes metric
  values on every page.
- Empty states name the missing input and link to the page that explains it;
  no page fabricates a number or draws a chart of zeros.
- Fixture expiry dates are fixed and long-dated, so later sessions show settled
  contracts. The dashboard labels those "Expired (fixture expiry)" and says so
  inline rather than printing a negative day count as if it were live.
- The validation rules in force are printed on **Data Quality**, read from config.

## Manual import

**Data Quality → Import a bhavcopy CSV** accepts any CSV carrying the nine MCX
columns, whatever they are called. Header names are matched
case- and separator-insensitively against a synonym table (`scrip` → Symbol,
`Settlement Price` → Close, `qty` → Volume, …) and every mapping can be
overridden before anything happens. The order is deliberate:

1. **Validate** runs the *same* validators as the download path — schema, date,
expiry, price range, requested-date match — on a temporary copy. It writes
nothing and reports accepted rows, rejected rows and the reason for each.
2. **Save to data/raw** writes the mapped file in canonical column order, adds
its SHA-256 to `data/raw/manifest.json` and appends a record (rows, reasons,
config hash, timestamp) to `data/imports.json`. An existing raw file is never
replaced unless the overwrite box is ticked; raw files are evidence.
3. Re-run `python -X utf8 -m src.pipeline` to rebuild analytics. The page says so
in the success message — an import alone does not silently rewrite results.

Imports face the same bar as downloads: nothing reaches `data/raw` that has not
already passed validation, so an uploaded file cannot produce a different answer
from the same file fetched from the exchange.

## Tests

```bash
python -m pytest -q          # 231 tests: pipeline, analytics, signal research, page interaction, freshness, backgrounds, import, expiry, artwork, photos, palette, UI markup
python -X utf8 tools/make_artwork.py --check   # 19 SVGs parse; every registry entry resolves
python -X utf8 tools/build_photos.py --check   # 14 WebP files, 565 KB; sizes and credits all match the registry
```

## Visual QA pack

`qa/` holds a captured set of all nine pages at three widths, with the evidence
behind each verdict.

```bash
python tools/capture_qa_screenshots.py                        # http://127.0.0.1:8601
python tools/capture_qa_screenshots.py --only spread-analytics
```

| Artifact | Contents |
|---|---|
| [qa/index.html](qa/index.html) | Browsable gallery — nine pages × three widths, pass/fail badges, issues |
| [qa/manifest.json](qa/manifest.json) | Per-capture evidence: heading, exception text, rail active item, chart count, axis-label clipping, overflow px, palette offenders, console/page errors, HTTP failures |
| `qa/screenshots/*.png` | Viewport and full-content captures |

A capture passes only when the heading matches the page, no Streamlit exception
rendered, no page/console error or HTTP failure occurred, nothing overflows
horizontally, every colour is inside the four palettes, every chart's axis
labels sit inside its glass panel, and exactly one rail item is marked current.

## Layout

```
app/
  Home.py                 router + rail (st.navigation)
  theme.py                design tokens, stylesheet, Plotly template
  components.py           NAV_PAGES registry, rail, header, cards, badges, states
  dataio.py               cached readers over data/ (never the network)
  artwork.py              SVG + photo registries, palette guard, credits
  assets/                 project-drawn SVG artwork and favicon
  static/photos/          licensed photography shipped as WebP
  pages/                  1_Overview … 9_Settings
src/                      ingest → validate → normalize → analytics → backtest
config/config.yaml        every assumption: contracts, signals, costs, backtest
data/                     raw CSV, clean parquet, analytics parquet, results, alerts
tests/                    pytest suite + synthetic fixture generator
docs/ROADMAP.md           150-feature backlog with audit status and the milestone plan
tools/                    artwork + photo builders, QA screenshot harness,
                          build_static_site.py (HTML export in site/),
                          verify_import_flow.py (browser test of the import path),
                          verify_signal_page.py (renders + charts on Signal Explorer)
qa/                       screenshot pack (generated)
site/                     static export of the dashboard (generated, committed)
vercel.json               serves site/ as a static deployment
```

## Known assumptions and limitations

- Daily settlement prices only — not executable fill prices.
- The carry rate is set in config (`annual_carry_rate: 0.0`); with r = 0 the
  residual spread equals the raw spread. Document the real rate before drawing
  carry conclusions.
- Cost assumptions are illustrative placeholders until sourced from a fee
  schedule.
- GOLDTEN's exchange history begins in 2025; earlier points are drawn dotted and
  excluded from headline conclusions.
- The bundled fixture set uses fixed long-dated expiries, so late sessions show
  settled contracts (labelled as such). Regenerate with rolling expiries for a
  term-structure study.
- No theme toggle: Streamlit themes are fixed per deployment, and a toggle that
  flipped only the custom CSS would leave native widgets in the other mode.
  The light workspace is the single tested appearance.
