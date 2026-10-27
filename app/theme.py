"""Design system — Team Starway, Commodity Intelligence.

One material for the whole product: frosted glass over a deep midnight navy
canvas, lit by a single champagne-gold source. Gold is the brand accent and the
first contract series only; green and red stay reserved for signed movement
(up / down, long / short), so a colour never means two things at once.

Photography is atmosphere, never content: the bullion frame sits in a fixed
layer behind the whole application, a second frame lights the Overview band, and
a per-contract texture sits *under* each contract card. No photograph is placed
inline as an image, and every data surface keeps a translucent-but-opaque-enough
glass ground so a figure is never read off a photograph.

Every surface token lives here. Pages import tokens and helpers rather than
writing hex literals, which is what keeps the ten screens visually identical.

Charts use one registered Plotly template (``mcx_glass``) set as the default, so
a chart that forgets to specify colours still lands on-palette. Contract series
carry a dash pattern as well as a colour: the four series stay separable in
greyscale and for colour-blind readers.
"""
from string import Template

import plotly.io as pio
import streamlit as st

from app import artwork

# ---- Canvas --------------------------------------------------------------
CANVAS = "#070B14"        # page background, before the photograph layer
CANVAS_DEEP = "#050810"   # the floor beneath vignettes and shadows

# ---- Glass surfaces ------------------------------------------------------
# Translucency is a token, not a per-component decision: every panel uses the
# same three stops so stacked surfaces never double up into mud.
SURFACE = "rgba(255,255,255,0.05)"
SURFACE_ALT = "rgba(255,255,255,0.03)"
SURFACE_SOLID = "#0C1422"          # the fallback when backdrop-filter is absent
GLASS = "rgba(15,24,40,0.58)"
GLASS_STRONG = "rgba(11,18,30,0.80)"
# The pane under every raised surface: a navy base *plus* the white sheen. A
# sheen on its own leaves the scene strokes showing through a panel, which is
# exactly where a control's label has to stay readable — over the brightest
# curve in bg-spreads.svg, a 6%-white panel was not a surface at all.
GLASS_PANE = "linear-gradient(160deg, rgba(22,33,51,0.84), rgba(9,15,26,0.78))"
GLASS_LINE = "rgba(255,255,255,0.10)"
GLASS_LINE_HI = "rgba(255,255,255,0.18)"
GLASS_HIGHLIGHT = "rgba(255,255,255,0.14)"   # inset top edge: the lit lip
GLASS_SHADE = "rgba(0,0,0,0.55)"             # the shadow that lifts a panel
BLUR = "blur(22px) saturate(140%)"
BLUR_SOFT = "blur(14px) saturate(125%)"

LINE = "rgba(255,255,255,0.08)"       # hairlines inside a surface
LINE_STRONG = "rgba(255,255,255,0.17)"  # control borders

# ---- Navigation rail ------------------------------------------------------
RAIL = "rgba(8,13,23,0.62)"
RAIL_ELEV = "rgba(255,255,255,0.07)"
RAIL_LINE = "rgba(255,255,255,0.08)"
RAIL_TEXT = "#C6D1E2"
RAIL_MUTED = "#8494AC"

# ---- Text -----------------------------------------------------------------
TEXT = "#F2F6FC"
TEXT_MUTED = "#AAB7C9"
TEXT_FAINT = "#7E8DA3"
TEXT_INVERT = "#08101C"

# ---- Brand accent: champagne gold ----------------------------------------
GOLD = "#E8CD8A"          # accent text on navy (≈10:1 on the glass ground)
GOLD_BRIGHT = "#F4DFA8"   # hover, active marks, chart series
GOLD_DEEP = "#C9A227"     # rules and gradients, never small text
GOLD_SOFT = "rgba(232,205,138,0.14)"
GOLD_LINE = "rgba(232,205,138,0.34)"

# ---- Semantic: signed movement only --------------------------------------
UP = "#5BE3A6"            # positive / long
DOWN = "#FF8078"          # negative / short
UP_SOFT = "rgba(91,227,166,0.14)"
DOWN_SOFT = "rgba(255,128,120,0.14)"
WARN = "#F3B27C"          # stale / caution, never a P&L colour
WARN_SOFT = "rgba(243,178,124,0.14)"

# ---- Contract identity ----------------------------------------------------
# Gold, bronze, steel blue, slate — four lightness-separated hues from the same
# family set, each with its own dash so the series survive greyscale printing.
CONTRACT_COLORS = {
    "GOLDM": "#F2D89B",
    "GOLDTEN": "#8FB8EC",
    "GOLDGUINEA": "#C98F4A",
    "GOLDPETAL": "#93A2B8",
}
CONTRACT_DASH = {
    "GOLDM": "solid",
    "GOLDTEN": "dash",
    "GOLDGUINEA": "dashdot",
    "GOLDPETAL": "dot",
}

SIGNAL_COLORS = {
    "Neutral": TEXT_MUTED,
    "Watch": WARN,
    "Signal": DOWN,
    "Unvalidated": TEXT_FAINT,
    "Long": UP,
    "Short": DOWN,
}

FONT = "'Inter','Segoe UI',system-ui,-apple-system,sans-serif"
MONO = "'JetBrains Mono','SFMono-Regular',Consolas,monospace"


def contract_style(sym: str, width: float = 1.9) -> dict:
    """Line style for a contract: colour *and* dash pattern."""
    return dict(color=CONTRACT_COLORS.get(sym, GOLD),
                dash=CONTRACT_DASH.get(sym, "solid"), width=width)


def signed_color(value: float) -> str:
    """Green for positive, red for negative, muted for zero/NaN."""
    try:
        if value > 0:
            return UP
        if value < 0:
            return DOWN
    except TypeError:
        pass
    return TEXT_MUTED


# -------------------------------------------------------------------------
# Stylesheet — string.Template, so CSS braces need no escaping.
# -------------------------------------------------------------------------
CSS = Template(r"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');

:root {
    --canvas: $CANVAS; --glass: $GLASS; --glass-strong: $GLASS_STRONG;
    --line: $LINE; --line-strong: $LINE_STRONG;
    --text: $TEXT; --muted: $TEXT_MUTED; --faint: $TEXT_FAINT;
    --gold: $GOLD; --gold-bright: $GOLD_BRIGHT; --gold-line: $GOLD_LINE;
    --up: $UP; --down: $DOWN; --warn: $WARN;
    --radius: 18px; --radius-sm: 12px; --radius-xs: 8px;
    /* one curve and two clocks for every hover, press and focus in the
       product: a control that eases differently from its neighbour reads as a
       different component even when the fills match */
    --ease: cubic-bezier(0.4,0,0.2,1);
    --t-fast: 150ms; --t-med: 200ms;
    --lift: 0 2px 6px rgba(0,0,0,0.15);
    --ring: 0 0 0 3px rgba(232,205,138,0.4);
    --blur: $BLUR; --blur-soft: $BLUR_SOFT;
    --shadow: 0 24px 48px -28px $GLASS_SHADE, 0 2px 8px -4px $GLASS_SHADE;
    --lip: inset 0 1px 0 $GLASS_HIGHLIGHT;
}

/* ---------------- App canvas ----------------
   One fixed photographic layer under the whole application: a stacked-bullion
   frame, a gold light source top-right, a cool counter-light bottom-left, and a
   navy wash that holds the photograph down to atmosphere. Because the layer is
   fixed, panels glide over a still image instead of dragging a pattern along.
   Everything readable sits on glass above it. */
.stApp {
    background-color: $CANVAS_DEEP;
    background-image:
        radial-gradient(120% 78% at 84% -12%, $GOLD_LINE, rgba(232,205,138,0) 58%),
        radial-gradient(90% 62% at 4% 108%, rgba(143,184,236,0.10), rgba(143,184,236,0) 62%),
        url($TERMINAL_TEX),
        linear-gradient(180deg, rgba(7,11,20,0.90) 0%, rgba(7,11,20,0.94) 42%,
                        rgba(5,8,15,0.97) 100%),
        url($HERO_BG);
    background-size: cover, cover, 520px 520px, cover, cover;
    background-position: center top, center bottom, 0 0, center top, center top;
    background-attachment: fixed, fixed, fixed, fixed, fixed;
    background-repeat: no-repeat, no-repeat, repeat, no-repeat, no-repeat;
    color: $TEXT;
    font-family: $FONT;
    -webkit-font-smoothing: antialiased;
}
/* ---------------- Page canvases ----------------
   Every page replaces the default canvas above with its own composition (scene,
   optional photograph, light source, wash). The rules are scoped with :has() to
   the marker div the page renders (app/backgrounds.py), so navigation changes
   the picture without re-injecting the stylesheet. A browser without :has()
   keeps the default canvas — readable, just less specifically lit. */
$PAGE_BG
.${MARKER_CLASS} { display: none; }
header[data-testid="stHeader"] {
    background: transparent; backdrop-filter: none;
}
section.main > div { padding-top: .35rem; }
.block-container { padding: 1.15rem 2rem 3rem; max-width: 1560px; }

h1, h2, h3, h4 { font-family: $FONT; color: $TEXT !important; letter-spacing: -.022em; }
/* !important: Streamlit's own h1 rule is class-scoped and would otherwise win */
h1 { font-size: 1.72rem !important; font-weight: 650 !important; margin: 0 !important; }
h2 { font-size: 1.06rem; font-weight: 600; margin: 2rem 0 .5rem; }
h3 { font-size: .95rem; font-weight: 600; margin: 1.6rem 0 .4rem; }

p, li, label, .stMarkdown { font-size: .875rem; line-height: 1.58; }
[data-testid="stCaptionContainer"], .stCaption, small {
    color: $TEXT_FAINT !important; font-size: .78rem !important;
}

/* ---------------- Navigation rail ----------------
   Frosted rather than solid: the canvas photograph and its gold light source
   stay faintly visible through the rail, which is what ties the chrome to the
   page instead of framing it in a separate material. */
section[data-testid="stSidebar"] {
    background-color: $RAIL;
    background-image:
        linear-gradient(180deg, rgba(255,255,255,0.055) 0%, rgba(255,255,255,0.01) 32%,
                        rgba(255,255,255,0) 100%),
        radial-gradient(130% 46% at 0% 0%, $GOLD_LINE, rgba(8,13,23,0) 62%);
    backdrop-filter: $BLUR;
    -webkit-backdrop-filter: $BLUR;
    border-right: 1px solid $GLASS_LINE;
    box-shadow: 24px 0 60px -40px $GLASS_SHADE;
    width: 262px !important;
}
section[data-testid="stSidebar"] > div { padding-top: .9rem; }
/* the native page list is replaced by the custom rail nav in components.py */
section[data-testid="stSidebar"] [data-testid="stSidebarNav"] { display: none; }
section[data-testid="stSidebar"] * { color: $RAIL_TEXT; }
section[data-testid="stSidebar"] a, section[data-testid="stSidebar"] a:visited {
    color: $RAIL_TEXT !important; text-decoration: none !important;
}
section[data-testid="stSidebar"] hr { border-color: $RAIL_LINE; margin: 1rem 0; }
/* rail button: glass on glass, not a white block */
section[data-testid="stSidebar"] .stButton button,
section[data-testid="stSidebar"] button[kind] {
    background: rgba(255,255,255,0.06) !important;
    border: 1px solid $GLASS_LINE !important;
    color: #E9EFF8 !important; font-size: .78rem; font-weight: 500;
    /* the same 8px as every other widget button, so the rail and the page do
       not show two different button corners side by side */
    border-radius: var(--radius-xs); backdrop-filter: $BLUR_SOFT;
}
section[data-testid="stSidebar"] .stButton button:hover,
section[data-testid="stSidebar"] button[kind]:hover {
    background: rgba(255,255,255,0.11) !important;
    border-color: $GOLD_LINE !important;
    color: #FFFFFF !important;
}
section[data-testid="stSidebar"] button[kind] p { color: inherit !important; }

.rail-brand { display: flex; align-items: center; gap: .7rem; padding: .2rem .25rem 1rem; }
.rail-mark {
    width: 38px; height: 38px; border-radius: 12px; flex: 0 0 auto;
    display: grid; place-items: center;
    background: linear-gradient(150deg, $GOLD_SOFT, rgba(255,255,255,0.04));
    border: 1px solid $GOLD_LINE;
    box-shadow: var(--lip), 0 8px 18px -12px $GOLD_DEEP;
}
.rail-mark img { width: 24px; height: 24px; display: block; }
.rail-name {
    font-size: .95rem; font-weight: 600; color: #FFFFFF; line-height: 1.2;
    letter-spacing: -.01em;
}
.rail-sub {
    font-size: .66rem; color: $RAIL_MUTED; letter-spacing: .12em;
    text-transform: uppercase; margin-top: .16rem;
}

.rail-section {
    font-size: .62rem; font-weight: 600; letter-spacing: .16em;
    text-transform: uppercase; color: $RAIL_MUTED;
    padding: 1rem .55rem .35rem;
}
/* st.page_link inside a keyed container: the container carries the active mark */
div[class*="st-key-railitem"] { margin: 0 !important; padding: 0 !important; }
section[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"] {
    border-radius: 11px; padding: .5rem .6rem; min-height: 40px;
    font-size: .85rem; font-weight: 500; color: $RAIL_TEXT !important;
    border: 1px solid transparent;
    transition: background var(--t-fast) var(--ease),
                border-color var(--t-fast) var(--ease),
                color var(--t-fast) var(--ease),
                transform var(--t-fast) var(--ease);
}
/* press: the rail item sinks a pixel, so navigation has the same physical
   feedback as a button rather than a silent page swap */
section[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"]:active {
    transform: translateY(1px);
}
section[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"]:hover {
    background: rgba(255,255,255,0.055);
    border-color: $GLASS_LINE;
    color: #FFFFFF !important;
}
section[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"] p {
    font-size: .85rem !important; font-weight: 500;
}
div[class*="st-key-rail-active"] [data-testid="stPageLink-NavLink"] {
    background: linear-gradient(100deg, $GOLD_SOFT, rgba(255,255,255,0.045) 62%) !important;
    border-color: $GOLD_LINE !important;
    color: #FFFFFF !important;
    box-shadow: var(--lip), 0 10px 22px -18px $GOLD_DEEP;
}
div[class*="st-key-rail-active"] [data-testid="stPageLink-NavLink"] p {
    color: #FFFFFF !important; font-weight: 600;
}
div[class*="st-key-rail-active"] [data-testid="stPageLink-NavLink"] svg {
    color: $GOLD_BRIGHT !important; fill: $GOLD_BRIGHT !important;
}
section[data-testid="stSidebar"] [data-testid="stIconMaterial"] { color: inherit !important; }

/* quick navigation: a real search field, styled to disappear into the rail */
section[data-testid="stSidebar"] div[data-baseweb="select"] > div {
    background: rgba(255,255,255,0.05) !important;
    border-color: $GLASS_LINE !important;
    border-radius: 11px !important;
    min-height: 38px;
}
section[data-testid="stSidebar"] div[data-baseweb="select"] > div:hover {
    border-color: $GOLD_LINE !important;
}

.rail-card {
    margin-top: .35rem; padding: .85rem .9rem; border-radius: 14px;
    background: linear-gradient(160deg, rgba(255,255,255,0.06), rgba(255,255,255,0.02));
    border: 1px solid $GLASS_LINE;
    box-shadow: var(--lip);
}
.rail-card .rc-k {
    font-size: .59rem; letter-spacing: .14em; text-transform: uppercase;
    color: $RAIL_MUTED; display: block;
}
.rail-card .rc-v {
    font-size: .8rem; color: #EDF2FA; font-family: $MONO;
    display: block; margin-top: .12rem;
}
.rail-card .rc-row + .rc-row { margin-top: .6rem; }
.rail-status {
    display: inline-flex; align-items: center; gap: .35rem;
    font-size: .66rem; font-weight: 600; letter-spacing: .07em;
    text-transform: uppercase; padding: .2em .6em; border-radius: 999px;
    border: 1px solid;
}
.rail-status.fresh { color: $UP; background: $UP_SOFT; border-color: rgba(91,227,166,.28); }
.rail-status.current { color: $GOLD; background: $GOLD_SOFT; border-color: $GOLD_LINE; }
.rail-status.recent { color: $WARN; background: $WARN_SOFT; border-color: rgba(243,178,124,.28); }
/* STALE, NO_DATA and ERROR are incidents, not lateness notes: red, and the word
   is always present so the state survives greyscale */
.rail-status.stale,
.rail-status.error,
.rail-status.no-data { color: $DOWN; background: $DOWN_SOFT; border-color: rgba(255,107,114,.30); }

/* rail card that reports a broken configuration (see app.auth.auth_warning) */
.rail-card.rail-warn {
    border-color: rgba(243,178,124,.30);
    background: linear-gradient(160deg, $WARN_SOFT, rgba(255,255,255,0.02));
}
.rail-card.rail-warn .rc-v { color: $WARN; }
.rail-warn-body {
    display: block; margin-top: .35rem; font-size: .72rem; line-height: 1.45;
    color: $RAIL_TEXT;
}
.rail-card .rc-note {
    display: block; margin-top: .18rem; font-size: .66rem; color: $RAIL_MUTED;
    font-family: $MONO;
}

/* ---------------- Top bar / page header ----------------
   The compact glass header every research page opens with: breadcrumb, title,
   one line of context, and the data-status chips on the right. */
.crumb {
    display: flex; align-items: center; gap: .4rem;
    font-size: .68rem; color: $TEXT_FAINT; text-transform: uppercase;
    letter-spacing: .12em; font-weight: 600; margin-bottom: .5rem;
}
.crumb .sep { color: rgba(255,255,255,0.22); }
.crumb .cur { color: $TEXT_MUTED; }

.pagehead {
    display: flex; align-items: flex-start; justify-content: space-between;
    gap: 1.2rem; flex-wrap: wrap;
    padding: 1.15rem 1.35rem 1.2rem; margin-bottom: 1.35rem;
    border-radius: var(--radius);
    background: linear-gradient(160deg, rgba(255,255,255,0.065), rgba(255,255,255,0.022)),
                $GLASS_PANE;
    border: 1px solid $GLASS_LINE;
    backdrop-filter: $BLUR_SOFT; -webkit-backdrop-filter: $BLUR_SOFT;
    box-shadow: var(--shadow), var(--lip);
}
.ph-text { min-width: 0; }
.ph-title { display: flex; align-items: center; gap: .65rem; }
.ph-title h1 { line-height: 1.15; }
.ph-sub {
    color: $TEXT_MUTED; font-size: .855rem; margin: .45rem 0 0;
    max-width: 70ch;
}
/* quiet glass links to the pages that follow on from this one */
.ph-actions { display: flex; flex-wrap: wrap; gap: .5rem; margin-top: .85rem; }
.ph-cta {
    display: inline-flex; align-items: center; gap: .35rem;
    padding: .36rem .78rem; border-radius: 10px;
    font-size: .78rem; font-weight: 550;
    background: rgba(255,255,255,0.055); border: 1px solid $GLASS_LINE;
    color: $TEXT !important; text-decoration: none !important;
    transition: border-color .16s ease, background .16s ease, color .16s ease;
}
.ph-cta:hover {
    border-color: $GOLD_LINE !important; color: $GOLD_BRIGHT !important;
    background: $GOLD_SOFT;
}
.ph-mark { width: 26px; height: 26px; flex: 0 0 auto; opacity: .95; }
.ph-mark img { width: 100%; height: 100%; display: block; }
.ph-meta { display: flex; align-items: center; gap: .45rem; flex-wrap: wrap; }
.meta-item {
    display: inline-flex; align-items: baseline; gap: .35rem;
    background: rgba(255,255,255,0.045); border: 1px solid $LINE;
    border-radius: 9px; padding: .34rem .62rem; font-size: .74rem;
}
.meta-item .k { color: $TEXT_FAINT; font-size: .61rem; text-transform: uppercase; letter-spacing: .09em; }
.meta-item .v { color: $TEXT; font-family: $MONO; font-size: .74rem; }
.status-chip {
    display: inline-flex; align-items: center; gap: .4rem;
    border-radius: 9px; padding: .34rem .64rem; font-size: .68rem;
    font-weight: 650; letter-spacing: .07em; text-transform: uppercase;
    border: 1px solid;
}
.status-chip.fresh { color: $UP; border-color: rgba(91,227,166,.32); background: $UP_SOFT; }
.status-chip.stale { color: $WARN; border-color: rgba(243,178,124,.32); background: $WARN_SOFT; }
.status-chip .dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }

/* ---------------- Hero band ----------------
   The cinematic header: a bullion photograph under a navy wash and a gold
   light, with a frosted glass panel carrying the headline. Layer order (first =
   topmost): navy wash, vertical vignette, grid, photograph. */
.hero-band {
    position: relative; overflow: hidden;
    border-radius: 24px; border: 1px solid $GLASS_LINE;
    padding: 1.15rem; margin-bottom: 1.5rem;
    background-color: $CANVAS_DEEP;
    background-image:
        linear-gradient(112deg, rgba(6,10,18,0.92) 0%, rgba(6,10,18,0.74) 42%,
                        rgba(6,10,18,0.38) 72%, rgba(6,10,18,0.30) 100%),
        linear-gradient(180deg, rgba(6,10,18,0.55) 0%, rgba(6,10,18,0.08) 46%,
                        rgba(6,10,18,0.72) 100%),
        radial-gradient(60% 80% at 88% 0%, $GOLD_LINE, rgba(232,205,138,0) 62%),
        url($TERMINAL_TEX),
        url($HERO_BG);
    background-size: 100% 100%, 100% 100%, 100% 100%, 520px 520px, cover;
    background-position: 0 0, 0 0, 0 0, 0 0, 64% 38%;
    background-repeat: no-repeat, no-repeat, no-repeat, repeat, no-repeat;
    box-shadow: 0 40px 80px -48px #000, var(--lip);
}
.hero-band::after {
    content: ''; position: absolute; left: 0; right: 0; bottom: 0; height: 2px;
    background: linear-gradient(90deg, $GOLD_BRIGHT, rgba(232,205,138,.12) 68%, transparent);
}
.hero-glass {
    position: relative; z-index: 1;
    background: rgba(9,15,26,0.56);
    border: 1px solid $GLASS_LINE_HI;
    border-radius: 18px;
    padding: 1.35rem 1.5rem 1.4rem;
    backdrop-filter: $BLUR; -webkit-backdrop-filter: $BLUR;
    box-shadow: inset 0 1px 0 $GLASS_HIGHLIGHT, 0 26px 50px -40px #000;
}
.hero-inner { position: relative; z-index: 1; max-width: 64ch; }
.hero-band .crumb { color: rgba(255,255,255,.58); margin-bottom: .55rem; }
.hero-band .crumb .sep { color: rgba(255,255,255,.28); }
.hero-band .crumb .cur { color: rgba(255,255,255,.82); }
.hero-band h1 { color: #FFFFFF !important; font-size: 2.08rem !important; }
.hero-sub {
    color: #CFD9E8; font-size: .9rem; line-height: 1.6;
    margin: .5rem 0 0; max-width: 60ch;
}
.hero-meta { display: flex; flex-wrap: wrap; gap: .45rem; margin-top: 1.1rem; }
.hero-chip {
    display: inline-flex; align-items: baseline; gap: .4rem;
    background: rgba(255,255,255,0.06); border: 1px solid $GLASS_LINE;
    border-radius: 9px; padding: .32rem .62rem; font-size: .74rem;
    backdrop-filter: $BLUR_SOFT;
}
.hero-chip .k {
    color: rgba(255,255,255,.55); font-size: .6rem; letter-spacing: .1em;
    text-transform: uppercase;
}
.hero-chip .v { color: #FFFFFF; font-family: $MONO; font-size: .74rem; }
.hero-chip.fresh { color: $UP; border-color: rgba(91,227,166,.32); background: $UP_SOFT; }
.hero-chip.fresh .v { color: $UP; text-transform: uppercase; letter-spacing: .05em; }
.hero-chip.stale { color: $WARN; border-color: rgba(243,178,124,.32); background: $WARN_SOFT; }
.hero-chip.stale .v { color: $WARN; text-transform: uppercase; letter-spacing: .05em; }
.hero-chip .dot {
    width: 6px; height: 6px; border-radius: 50%; background: currentColor;
    display: inline-block;
}
.hero-actions { display: flex; flex-wrap: wrap; gap: .55rem; margin-top: 1.15rem; }
.hero-cta {
    display: inline-flex; align-items: center; gap: .4rem;
    background: linear-gradient(160deg, $GOLD_BRIGHT, $GOLD_DEEP);
    color: $TEXT_INVERT !important;
    border: 1px solid rgba(244,223,168,.55); border-radius: 10px;
    padding: .5rem .92rem; font-size: .82rem; font-weight: 650;
    text-decoration: none !important;
    box-shadow: 0 10px 24px -14px $GOLD_DEEP, inset 0 1px 0 rgba(255,255,255,.35);
    transition: filter .16s ease, transform .16s ease;
}
.hero-cta:hover { filter: brightness(1.06); transform: translateY(-1px); }
.hero-cta.ghost {
    background: rgba(255,255,255,0.06); border-color: $GLASS_LINE_HI;
    color: #EDF2FA !important; box-shadow: var(--lip);
}
.hero-cta.ghost:hover {
    background: rgba(255,255,255,0.11); border-color: $GOLD_LINE;
    color: #FFFFFF !important;
}
.hero-credit {
    position: relative; z-index: 1; margin: .8rem .35rem 0;
    font-size: .67rem; color: rgba(255,255,255,.48);
}
.hero-credit a {
    color: rgba(255,255,255,.7) !important; text-decoration: none;
    border-bottom: 1px dotted rgba(255,255,255,.26);
}

/* ---------------- Cards & metrics ----------------
   One glass recipe for every raised surface: translucent gradient, hairline
   border, lit top lip, and a shadow deep enough to lift the panel off the
   canvas. Blur is applied once per surface, never nested. */
div[data-testid="stMetric"] {
    background: linear-gradient(160deg, rgba(255,255,255,0.07), rgba(255,255,255,0.022)),
                $GLASS_PANE;
    border: 1px solid $GLASS_LINE;
    border-radius: var(--radius); padding: 1rem 1.1rem 1.05rem;
    min-height: 108px;
    backdrop-filter: $BLUR_SOFT; -webkit-backdrop-filter: $BLUR_SOFT;
    box-shadow: var(--shadow), var(--lip);
    transition: border-color var(--t-med) var(--ease),
                transform var(--t-med) var(--ease),
                box-shadow var(--t-med) var(--ease);
}
div[data-testid="stMetric"]:hover {
    border-color: $GOLD_LINE;
    transform: translateY(-2px);
    box-shadow: 0 28px 54px -30px #000, var(--lip);
}
div[data-testid="stMetricLabel"] p {
    color: $TEXT_FAINT !important; font-size: .68rem !important;
    letter-spacing: .1em; text-transform: uppercase; font-weight: 600;
    white-space: normal; line-height: 1.35;
}
div[data-testid="stMetricValue"] {
    font-family: $MONO; color: $TEXT !important;
    font-size: 1.5rem !important; font-variant-numeric: tabular-nums;
    letter-spacing: -.025em;
}
div[data-testid="stMetricDelta"] { font-size: .76rem !important; font-weight: 500; }
/* signed movement keeps its semantic colours; nothing here is gold */
div[data-testid="stMetricDelta"] svg { display: none; }
/* the metric's optional icon: a small gold glass chip beside the label */
div[data-testid="stMetric"] [data-testid="stMetricIcon"],
div[data-testid="stMetric"] [data-testid="stIconMaterial"] {
    color: $GOLD !important;
    background: $GOLD_SOFT; border: 1px solid $GOLD_LINE;
    border-radius: 9px; padding: 3px;
}

div[data-testid="stVerticalBlockBorderWrapper"] {
    background: linear-gradient(160deg, rgba(255,255,255,0.058), rgba(255,255,255,0.018)),
                $GLASS_PANE;
    border: 1px solid $GLASS_LINE !important;
    border-radius: var(--radius);
    backdrop-filter: $BLUR_SOFT; -webkit-backdrop-filter: $BLUR_SOFT;
    box-shadow: var(--shadow), var(--lip);
}
div[data-testid="stVerticalBlockBorderWrapper"] > div { padding: .2rem .25rem; }

.panel {
    background: linear-gradient(160deg, rgba(255,255,255,0.06), rgba(255,255,255,0.02));
    border: 1px solid $GLASS_LINE; border-radius: var(--radius);
    padding: 1rem 1.1rem; box-shadow: var(--shadow), var(--lip);
}
.section-head {
    display: flex; align-items: baseline; justify-content: space-between;
    gap: 1rem; margin: 2.1rem 0 .7rem;
}
.section-head h2 { margin: 0; font-size: 1.02rem; font-weight: 600; letter-spacing: -.01em; }
.section-head .hint { font-size: .75rem; color: $TEXT_FAINT; }

/* ---------------- Badges ---------------- */
.badge {
    display: inline-flex; align-items: center; gap: .38em;
    padding: .2em .6em; border-radius: 7px;
    font-size: .72rem; font-weight: 600; letter-spacing: .02em;
    border: 1px solid; white-space: nowrap;
}
.badge-Neutral { color: $TEXT_MUTED; border-color: $LINE_STRONG; background: rgba(255,255,255,0.05); }
.badge-Watch { color: $WARN; border-color: rgba(243,178,124,.32); background: $WARN_SOFT; }
.badge-Signal { color: $DOWN; border-color: rgba(255,128,120,.32); background: $DOWN_SOFT; }
.badge-Unvalidated { color: $TEXT_FAINT; border-color: $LINE; background: rgba(255,255,255,0.03); }
.badge-Long { color: $UP; border-color: rgba(91,227,166,.32); background: $UP_SOFT; }
.badge-Short { color: $DOWN; border-color: rgba(255,128,120,.32); background: $DOWN_SOFT; }
.badge-Dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }

/* ---------------- Tables ----------------
   The frame is glass; the grid itself stays on a near-solid pane so figures are
   never read through the photograph behind the page. */
div[data-testid="stDataFrame"], div[data-testid="stDataFrameResizable"] {
    border: 1px solid $GLASS_LINE; border-radius: var(--radius); overflow: hidden;
    background: rgba(12,20,34,0.90);
    box-shadow: var(--shadow), var(--lip);
}
div[data-testid="stDataFrame"] > div { overflow-x: auto; }
div[data-testid="stDataFrame"] [data-testid="stElementToolbar"] { background: transparent; }

/* ---------------- Inputs ---------------- */
div[data-baseweb="select"] > div, div[data-baseweb="input"] > div,
.stTextInput input, .stNumberInput input, .stDateInput input {
    background: rgba(255,255,255,0.05) !important;
    border-color: $GLASS_LINE !important;
    color: $TEXT !important;
    border-radius: 11px !important;
}
div[data-baseweb="select"] > div:hover,
div[data-baseweb="input"] > div:hover { border-color: $GOLD_LINE !important; }
div[data-baseweb="select"] svg { fill: $TEXT_MUTED !important; }
/* the open menu is a solid pane: a list read through a chart is unreadable */
div[data-baseweb="popover"] ul,
div[data-baseweb="popover"] div[role="listbox"] {
    background: $SURFACE_SOLID !important;
    border: 1px solid $GLASS_LINE !important;
    border-radius: 12px !important;
    box-shadow: 0 30px 60px -30px #000;
}
div[data-baseweb="popover"] li { color: $TEXT !important; }
div[data-baseweb="popover"] li:hover { background: rgba(255,255,255,0.06) !important; }
div[data-baseweb="calendar"] { background: $SURFACE_SOLID !important; color: $TEXT !important; }
/* multiselect tags: gold glass.
   Streamlit renders the selected values as `[data-tag]` spans (BaseWeb's
   `[data-baseweb="tag"]` is still matched for older versions); left unstyled
   they inherit primaryColor as a solid fill with white text, which is the one
   place in the product where text would drop to roughly 1.4:1. */
div[data-baseweb="tag"], [data-tag] {
    background: $GOLD_SOFT !important; border: 1px solid $GOLD_LINE !important;
    border-radius: 7px !important;
}
div[data-baseweb="tag"], div[data-baseweb="tag"] span,
[data-tag], [data-tag] span {
    color: $GOLD_BRIGHT !important; font-weight: 500;
}
div[data-baseweb="tag"] svg, [data-tag] svg { fill: $GOLD_BRIGHT !important; }
[data-tag] button { background: transparent !important; }

/* alerts (st.success/info/warning/error): a glass pane with a coloured edge.
   The stock component is a saturated fill; here the state is carried by the
   left rule and the icon, and the sentence stays body-coloured and readable. */
div[data-testid="stAlertContainer"] {
    background: rgba(15,24,40,0.78) !important;
    border: 1px solid $GLASS_LINE !important;
    border-left: 2px solid $GOLD_LINE !important;
    border-radius: 12px !important;
    backdrop-filter: $BLUR_SOFT; -webkit-backdrop-filter: $BLUR_SOFT;
    box-shadow: var(--lip);
}
div[data-testid="stAlertContainer"]:has([data-testid="stAlertContentSuccess"]) {
    border-left-color: $UP !important;
}
div[data-testid="stAlertContainer"]:has([data-testid="stAlertContentError"]) {
    border-left-color: $DOWN !important;
}
div[data-testid="stAlertContainer"]:has([data-testid="stAlertContentWarning"]) {
    border-left-color: $WARN !important;
}
div[data-testid^="stAlertContent"] { color: $TEXT_MUTED !important; }
div[data-testid="stAlertContentSuccess"] svg { fill: $UP !important; color: $UP !important; }
div[data-testid="stAlertContentError"] svg { fill: $DOWN !important; color: $DOWN !important; }
div[data-testid="stAlertContentWarning"] svg { fill: $WARN !important; color: $WARN !important; }
div[data-testid="stAlertContentInfo"] svg { fill: $GOLD !important; color: $GOLD !important; }
div[data-testid^="stAlertContent"] p { color: $TEXT_MUTED !important; }
[data-testid="stWidgetLabel"] p {
    font-size: .75rem !important; font-weight: 600; color: $TEXT_MUTED !important;
    letter-spacing: .01em;
}

/* ---------------- Buttons: one tiered glass system ----------------
   Three native widget tiers (primary / secondary / tertiary) plus markup
   classes for the two cases Streamlit has no kind for — danger and ghost.
   Every tier shares one radius, one easing curve, one clock, one press
   behaviour and one focus ring, so a control's *weight* is the only thing that
   changes between them. Gold stays reserved for the deliberate action; the
   quiet tiers are glass and text only. */
.stButton button, .stDownloadButton button, .stFormSubmitButton button {
    position: relative; overflow: hidden;          /* clips the press ripple */
    border-radius: var(--radius-xs); font-size: .82rem; font-weight: 550;
    border: 1px solid $GLASS_LINE; background: rgba(255,255,255,0.055);
    color: $TEXT; backdrop-filter: $BLUR_SOFT;
    transition: background var(--t-fast) var(--ease),
                border-color var(--t-fast) var(--ease),
                color var(--t-fast) var(--ease),
                transform var(--t-fast) var(--ease),
                box-shadow var(--t-fast) var(--ease);
}
/* secondary — the default kind: glass, gold edge on hover, 2px lift */
.stButton button:hover, .stDownloadButton button:hover,
.stFormSubmitButton button:hover {
    border-color: $GOLD_LINE; color: $GOLD_BRIGHT; background: $GOLD_SOFT;
    transform: translateY(-2px); box-shadow: var(--lift);
}
/* press: the surface sinks 1px and drops its shadow, so the button reads as
   physically pushed rather than merely recoloured */
.stButton button:active, .stDownloadButton button:active,
.stFormSubmitButton button:active {
    transform: translateY(1px); box-shadow: none;
}
/* the ripple: a gold ring expanding out of the button on press. Pure CSS and
   purely decorative — no state depends on it, so the reduced-motion guard can
   strip it without changing behaviour. */
.stButton button::after, .stDownloadButton button::after,
.stFormSubmitButton button::after {
    content: ''; position: absolute; inset: 50% 50%; border-radius: 50%;
    background: rgba(232,205,138,0.30); opacity: 0; pointer-events: none;
}
.stButton button:active::after, .stDownloadButton button:active::after,
.stFormSubmitButton button:active::after {
    animation: btn-ripple 120ms var(--ease);
}
@keyframes btn-ripple {
    from { inset: 50% 50%; opacity: .55; }
    to   { inset: -40%;  opacity: 0; }
}
/* primary — the one gold control on a screen: the deliberate action */
button[data-testid="stBaseButton-primary"],
button[data-testid="stBaseButton-primaryFormSubmit"],
.stButton button[kind="primary"],
.stDownloadButton button[kind="primary"] {
    background: linear-gradient(160deg, $GOLD_BRIGHT, $GOLD_DEEP) !important;
    border-color: rgba(244,223,168,.55) !important;
    color: $TEXT_INVERT !important;
    box-shadow: 0 12px 26px -16px $GOLD_DEEP, inset 0 1px 0 rgba(255,255,255,.35);
}
button[data-testid="stBaseButton-primary"]:hover,
button[data-testid="stBaseButton-primaryFormSubmit"]:hover,
.stButton button[kind="primary"]:hover,
.stDownloadButton button[kind="primary"]:hover {
    filter: brightness(1.07); transform: translateY(-2px);
    color: $TEXT_INVERT !important;
}
button[data-testid="stBaseButton-primary"]:active,
button[data-testid="stBaseButton-primaryFormSubmit"]:active,
.stButton button[kind="primary"]:active {
    transform: translateY(1px); filter: brightness(.99);
}
button[data-testid="stBaseButton-primary"] p,
button[data-testid="stBaseButton-primaryFormSubmit"] p,
.stButton button[kind="primary"] p {
    color: $TEXT_INVERT !important; font-weight: 650;
}
/* tertiary — a text action: no border, no fill, gold type. It underlines only
   on keyboard focus, so a pointer user never sees a link impersonating a rule. */
button[data-testid="stBaseButton-tertiary"],
.stButton button[kind="tertiary"],
.stDownloadButton button[kind="tertiary"] {
    background: transparent !important; border-color: transparent !important;
    color: $GOLD !important; box-shadow: none !important;
}
button[data-testid="stBaseButton-tertiary"]:hover,
.stButton button[kind="tertiary"]:hover,
.stDownloadButton button[kind="tertiary"]:hover {
    background: rgba(255,255,255,0.05) !important;
    border-color: transparent !important; color: $GOLD_BRIGHT !important;
    transform: none; box-shadow: none;
}
button[data-testid="stBaseButton-tertiary"] p,
.stButton button[kind="tertiary"] p,
.stDownloadButton button[kind="tertiary"] p { color: inherit !important; }
/* one focus ring for every tier: 3px gold, never the browser default */
.stButton button:focus-visible, .stDownloadButton button:focus-visible,
.stFormSubmitButton button:focus-visible {
    outline: none; box-shadow: var(--ring) !important;
}
/* disabled: the control stays legible but stops inviting a click */
.stButton button:disabled, .stDownloadButton button:disabled,
.stFormSubmitButton button:disabled {
    opacity: .45; transform: none !important; box-shadow: none !important;
    cursor: not-allowed;
}

/* markup tiers — for the cases a Streamlit widget cannot express */
.gbtn {
    display: inline-flex; align-items: center; gap: .4rem;
    padding: .42rem .8rem; border-radius: var(--radius-xs);
    font-size: .8rem; font-weight: 550; line-height: 1.2;
    border: 1px solid $GLASS_LINE; background: rgba(255,255,255,0.055);
    color: $TEXT !important; text-decoration: none !important;
    transition: background var(--t-fast) var(--ease),
                border-color var(--t-fast) var(--ease),
                color var(--t-fast) var(--ease),
                transform var(--t-fast) var(--ease),
                box-shadow var(--t-fast) var(--ease);
}
.gbtn:hover {
    border-color: $GOLD_LINE; color: $GOLD_BRIGHT !important;
    background: $GOLD_SOFT; transform: translateY(-2px);
    box-shadow: var(--lift);
}
.gbtn:active { transform: translateY(1px); box-shadow: none; }
.gbtn:focus-visible { outline: none; box-shadow: var(--ring); }
.gbtn-primary {
    background: linear-gradient(160deg, $GOLD_BRIGHT, $GOLD_DEEP);
    border-color: rgba(244,223,168,.55); color: $TEXT_INVERT !important;
    font-weight: 650;
    box-shadow: 0 12px 26px -16px $GOLD_DEEP, inset 0 1px 0 rgba(255,255,255,.35);
}
.gbtn-primary:hover {
    filter: brightness(1.07); color: $TEXT_INVERT !important;
    border-color: rgba(244,223,168,.7);
}
.gbtn-tertiary {
    background: transparent; border-color: transparent; color: $GOLD !important;
}
.gbtn-tertiary:hover {
    background: rgba(255,255,255,0.05); border-color: transparent;
    color: $GOLD_BRIGHT !important; transform: none; box-shadow: none;
}
.gbtn-ghost {
    background: transparent; border-color: $GLASS_LINE; color: $GOLD !important;
}
.gbtn-ghost:hover {
    background: $GOLD_SOFT; border-color: $GOLD_LINE;
    color: $GOLD_BRIGHT !important;
}
.gbtn-danger {
    background: rgba(180,35,24,0.16); border-color: rgba(180,35,24,0.55);
    color: #FF9A93 !important; font-weight: 600;
}
.gbtn-danger:hover {
    background: rgba(180,35,24,0.30); border-color: #B42318;
    color: #FFFFFF !important;
}

/* tabs: gold underline on glass */
div[data-testid="stTabs"] [data-baseweb="tab-list"] {
    gap: .25rem; border-bottom: 1px solid $LINE;
}
div[data-testid="stTabs"] button[data-baseweb="tab"] {
    font-size: .84rem; font-weight: 500; color: $TEXT_MUTED;
    padding: .55rem .7rem;
}
div[data-testid="stTabs"] button[aria-selected="true"] { color: $TEXT; font-weight: 600; }
div[data-testid="stTabs"] [data-baseweb="tab-highlight"] { background: $GOLD_BRIGHT; height: 2px; }
div[data-testid="stTabs"] [data-baseweb="tab-border"] { display: none; }

/* sliders: gold thumb and track on a quiet groove */
div[data-testid="stSlider"] [data-baseweb="slider"] div[role="slider"] {
    background: $GOLD_BRIGHT !important; border-color: $GOLD_BRIGHT !important;
    box-shadow: 0 0 0 4px $GOLD_SOFT;
}
div[data-testid="stSlider"] [data-baseweb="slider"] > div > div {
    background: $GOLD_DEEP !important;
}

/* expanders */
details[data-testid="stExpander"] {
    border: 1px solid $GLASS_LINE !important; border-radius: 14px !important;
    background: rgba(255,255,255,0.035);
    backdrop-filter: $BLUR_SOFT;
}
details[data-testid="stExpander"] summary { font-size: .82rem; color: $TEXT_MUTED; }

/* radio and checkbox controls */
div[data-testid="stRadio"] label[data-baseweb="radio"] > div:first-child,
div[data-testid="stCheckbox"] label span[aria-checked="true"] {
    border-color: $GOLD_BRIGHT !important;
}

/* ---------------- Empty, caveat, footer ---------------- */
.empty-state {
    text-align: center; padding: 2.8rem 1.2rem;
    border: 1px dashed $GLASS_LINE_HI; border-radius: 20px;
    background: linear-gradient(160deg, rgba(255,255,255,0.05), rgba(255,255,255,0.015)),
                $GLASS_PANE;
    backdrop-filter: $BLUR_SOFT;
}
.empty-art { width: 54px; height: 54px; opacity: .7; margin-bottom: .6rem; }
.empty-title { font-weight: 600; color: $TEXT; margin-bottom: .3rem; font-size: .95rem; }
.empty-body { color: $TEXT_MUTED; font-size: .84rem; max-width: 46ch; margin: 0 auto; }
.empty-link {
    display: inline-block; margin-top: .9rem; color: $GOLD_BRIGHT !important;
    font-size: .82rem; font-weight: 600; text-decoration: none;
    border-bottom: 1px solid $GOLD_LINE;
}
.stale-banner {
    padding: .7rem .95rem; border-radius: 12px; margin-bottom: 1.05rem;
    background: $WARN_SOFT; border: 1px solid rgba(243,178,124,.28);
    color: $WARN; font-size: .82rem;
}
.caveat {
    padding: .65rem .9rem; border-radius: 12px; margin: .6rem 0;
    background: $GLASS_PANE; border: 1px solid $LINE;
    color: $TEXT_MUTED; font-size: .8rem; line-height: 1.55;
}
/* closing band: the same navy and gold as the hero, so the page opens and closes
   on the same material instead of ending on a grey box */
.disclaimer {
    margin-top: 2.8rem; padding: 1.15rem 1.3rem 1.25rem;
    border: 1px solid $GLASS_LINE; border-top: 2px solid $GOLD_BRIGHT;
    border-radius: 16px;
    background-color: rgba(9,15,26,0.86);
    background-image: linear-gradient(100deg, rgba(9,15,26,0.94), rgba(9,15,26,0.72)),
                      url($GOLD_TILE);
    background-size: 100% 100%, 340px 340px;
    backdrop-filter: $BLUR_SOFT;
    color: #C3CEE0; font-size: .76rem; line-height: 1.65;
    box-shadow: var(--lip);
}
.disclaimer strong { color: #FFFFFF; }
.disclaimer a { color: $GOLD_BRIGHT !important; }
.config-chip {
    font-family: $MONO; font-size: .7rem; color: $TEXT_MUTED;
    background: rgba(255,255,255,0.05); border: 1px solid $LINE;
    border-radius: 6px; padding: .15em .5em;
}
.divider {
    height: 1px; margin: 1.8rem 0;
    background: linear-gradient(90deg, $GOLD_LINE, $LINE 45%, transparent);
}

/* demo / sample data notice — never mixed silently with real data */
.sample-flag {
    display: inline-flex; align-items: center; gap: .4rem;
    font-size: .69rem; font-weight: 600; letter-spacing: .06em;
    text-transform: uppercase; color: $WARN;
    background: $WARN_SOFT; border: 1px solid rgba(243,178,124,.28);
    border-radius: 7px; padding: .2em .55em;
}

/* ---------------- Contract spec cards ----------------
   Each card is a pane of glass over its own bullion frame: the photograph is a
   background layer at low opacity under a navy gradient, so the specification
   rows and the price still sit on a surface dark enough for AA contrast. The
   accent rule at the top repeats the contract's chart colour. */
.spec-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: .85rem; }
.spec-card {
    position: relative; overflow: hidden;
    background-color: rgba(11,18,30,0.72);
    background-image:
        linear-gradient(165deg, rgba(10,16,28,0.80) 0%, rgba(10,16,28,0.90) 48%,
                        rgba(8,13,23,0.96) 100%),
        var(--shot, none);
    background-size: cover, cover;
    background-position: center, center;
    border: 1px solid $GLASS_LINE; border-radius: var(--radius);
    padding: 1rem 1.05rem 1.05rem;
    box-shadow: var(--shadow), var(--lip);
    transition: border-color .18s ease, transform .18s ease;
}
.spec-card:hover { border-color: var(--accent, $GOLD_LINE); transform: translateY(-2px); }
.spec-card::before {
    content: ''; position: absolute; left: 0; right: 0; top: 0; height: 2px;
    background: linear-gradient(90deg, var(--accent, $GOLD), transparent 85%);
}
.spec-sym { font-family: $MONO; font-size: .98rem; font-weight: 600; color: $TEXT; letter-spacing: .01em; }
.spec-price {
    font-family: $MONO; font-size: 1.4rem; color: $TEXT;
    margin: .4rem 0 .12rem; font-variant-numeric: tabular-nums; letter-spacing: -.02em;
}
.spec-unit { font-size: .68rem; color: $TEXT_FAINT; text-transform: uppercase; letter-spacing: .08em; }
.spec-rows { margin-top: .8rem; border-top: 1px solid $LINE; padding-top: .6rem; }
.spec-row {
    display: flex; justify-content: space-between; gap: .5rem;
    font-size: .76rem; padding: .14rem 0;
}
.spec-row .k { color: $TEXT_FAINT; }
.spec-row .v { color: $TEXT; font-family: $MONO; }

/* ---------------- Signal ladder ---------------- */
.ladder { display: grid; grid-template-columns: repeat(3, 1fr); gap: .85rem; }
.ladder-step {
    background: linear-gradient(160deg, rgba(255,255,255,0.06), rgba(255,255,255,0.02));
    border: 1px solid $GLASS_LINE; border-radius: var(--radius);
    padding: .95rem 1.05rem; position: relative; overflow: hidden;
    box-shadow: var(--shadow), var(--lip);
}
.ladder-step::before {
    content: ''; position: absolute; left: 0; top: 0; bottom: 0; width: 3px;
    background: var(--tone, $GOLD);
    box-shadow: 0 0 18px var(--tone, $GOLD);
}
.ladder-zone { font-size: .66rem; letter-spacing: .13em; text-transform: uppercase; color: $TEXT_FAINT; font-weight: 650; }
.ladder-rule { font-family: $MONO; font-size: 1rem; color: $TEXT; margin-top: .3rem; }
.ladder-note { font-size: .75rem; color: $TEXT_MUTED; margin-top: .3rem; }

/* ---------------- Chart series key ----------------
   A legend that ties a line colour to a contract without an image: the dot
   repeats the plotted colour, the dash sample repeats the dash, and the price
   is the same normalized figure the chart draws. */
.contract-key {
    display: flex; flex-wrap: wrap; align-items: center; gap: .5rem .9rem;
    border: 1px solid $GLASS_LINE; border-radius: 14px;
    background: rgba(255,255,255,0.04);
    padding: .6rem .85rem; margin: 0 0 1rem;
    backdrop-filter: $BLUR_SOFT;
}
.key-item {
    display: flex; align-items: center; gap: .55rem; margin: 0;
    padding-right: .9rem; border-right: 1px solid $LINE;
}
.key-item:last-of-type { border-right: 0; padding-right: 0; }
.key-item figcaption { display: flex; flex-direction: column; gap: .02rem; line-height: 1.3; }
.key-name {
    display: flex; align-items: center; gap: .4rem;
    font-family: $MONO; font-size: .8rem; font-weight: 600; color: $TEXT;
}
.key-dash { display: inline-block; width: 22px; height: 0; border-top: 2px solid var(--dot); }
.key-spec { font-size: .7rem; color: $TEXT_FAINT; }
.key-price { font-family: $MONO; font-size: .73rem; color: $TEXT; }
.key-credit { margin-left: auto; font-size: .66rem; color: $TEXT_FAINT; }
.key-credit a {
    color: $TEXT_FAINT !important; text-decoration: none;
    border-bottom: 1px dotted $LINE_STRONG;
}
@media (max-width: 760px) {
    .key-item { border-right: 0; padding-right: 0; }
    .key-credit { flex-basis: 100%; margin-left: 0; }
}

/* ---------------- Methodology pipeline ----------------
   The pipeline is drawn in markup rather than shipped as a picture: six glass
   stages on one rail, readable at every width. */
.pipe {
    display: grid; grid-template-columns: repeat(6, 1fr);
    gap: .5rem; padding: .35rem .1rem .2rem;
}
.pipe-step {
    /* grid items size to min-content by default, and the monospace output path
       is wider than a phone column — let the cell shrink and the path wrap */
    min-width: 0;
    position: relative; padding: .8rem .7rem .85rem;
    border: 1px solid $GLASS_LINE; border-radius: 14px;
    background: rgba(255,255,255,0.04);
    box-shadow: var(--lip);
}
.pipe-step::after {
    content: ''; position: absolute; right: -.42rem; top: 50%; width: .34rem;
    height: 1px; background: $GOLD_LINE;
}
.pipe-step:last-child::after { display: none; }
.pipe-n {
    font-family: $MONO; font-size: .64rem; color: $GOLD_BRIGHT;
    letter-spacing: .1em;
}
.pipe-name { font-size: .82rem; font-weight: 600; color: $TEXT; margin-top: .15rem; }
.pipe-note { font-size: .7rem; color: $TEXT_MUTED; line-height: 1.45; margin-top: .25rem; }
.pipe-io {
    font-family: $MONO; font-size: .64rem; color: $TEXT_FAINT; margin-top: .4rem;
    padding-top: .35rem; border-top: 1px solid $LINE;
    overflow-wrap: anywhere;
}
.pipe-note-wide {
    display: flex; flex-wrap: wrap; justify-content: space-between; gap: .4rem;
    margin-top: .55rem; font-size: .72rem; color: $TEXT_FAINT;
}

/* ---------------- Selection --------------
   The accent at low alpha: a highlighted figure keeps its own colour and stays
   readable, instead of turning into white-on-gold. */
::selection { background: rgba(232,205,138,0.18); color: $TEXT; }
::selection:window-inactive { background: rgba(232,205,138,0.12); }

/* ---------------- Cursors ----------------
   Everything interactive says so on hover; the chart's drag layer is a
   crosshair because that is the gesture — reading a value off two axes. Text
   stays a text cursor, and a disabled control never invites a click. */
button, [role="button"], a, summary, select,
div[data-baseweb="select"], label[data-baseweb="radio"],
label[data-baseweb="checkbox"], .stCheckbox label { cursor: pointer; }
button:disabled, [aria-disabled="true"], .stButton button:disabled {
    cursor: not-allowed;
}
.js-plotly-plot .nsewdrag, .js-plotly-plot .draglayer { cursor: crosshair; }
[data-testid="stStatusWidget"], .stSpinner { cursor: progress; }

/* ---------------- Running indicator ----------------
   While a page reruns, the app's own top decoration becomes the progress
   cursor: one gold hairline, no spinner of our own to keep in sync. */
div[data-testid="stDecoration"] {
    height: 2px;
    background-image: linear-gradient(90deg, $GOLD_DEEP, $GOLD_BRIGHT, $GOLD_DEEP);
}

/* ---------------- Data freshness strip ----------------
   The permanent stamp above every page header: what the numbers are as of, and
   when they were last built. It is the page's only live region, so a rerun
   that flips Current to Stale is announced rather than only recoloured. Stale
   keeps the product's amber warning tone — red is reserved for signed
   movement, and a state colour must never mean two things. */
.freshbar {
    display: flex; align-items: center; gap: .45rem; flex-wrap: wrap;
    margin: 0 0 .9rem; padding: .42rem .75rem;
    border-radius: var(--radius-xs);
    background: rgba(255,255,255,0.045); border: 1px solid $LINE;
    font-size: .72rem; text-decoration: none !important;
    transition: border-color var(--t-fast) var(--ease),
                background var(--t-fast) var(--ease);
}
.freshbar:hover { border-color: $GOLD_LINE; background: $GOLD_SOFT; }
.freshbar:focus-visible { outline: none; box-shadow: var(--ring); }
.freshbar .fb-k {
    color: $TEXT_FAINT; text-transform: uppercase; letter-spacing: .09em;
    font-size: .61rem; font-weight: 600;
}
.freshbar .fb-v { color: $TEXT; font-family: $MONO; font-size: .72rem; }
.freshbar .fb-sep { color: rgba(255,255,255,.22); }
.freshbar .fb-state {
    margin-left: auto; font-weight: 700; letter-spacing: .09em; font-size: .66rem;
}
/* One colour per freshness state, and the sentence that explains it.
   CURRENT is the resting state (the normal "one session behind"); RECENT is a
   warning that the file is behind; STALE and the two error states are red
   because the figures are historical or unverified, not merely late. */
.freshbar.fresh .fb-state { color: $UP; }
.freshbar.current .fb-state { color: $GOLD; }
.freshbar.recent .fb-state { color: $WARN; }
.freshbar.stale .fb-state,
.freshbar.error .fb-state,
.freshbar.no-data .fb-state { color: $DOWN; }
.freshbar.recent { border-color: rgba(243,178,124,.30); }
.freshbar.stale, .freshbar.error, .freshbar.no-data {
    border-color: rgba(255,107,114,.30);
}
.freshbar-wrap .fb-note {
    margin: .35rem 0 0 .15rem; font-size: .72rem; line-height: 1.45;
    color: $TEXT_MUTED;
}
.rail-card .rc-headline { font-family: $FONT; font-size: .7rem; line-height: 1.4; }
@media (max-width: 640px) {
    .freshbar { font-size: .68rem; gap: .3rem .4rem; padding: .4rem .6rem; }
    .freshbar .fb-state { margin-left: 0; flex-basis: 100%; }
    .freshbar-wrap .fb-note { font-size: .68rem; }
}

/* ---------------- Links ----------------
   A link in body copy is gold and unmarked; the underline appears only when
   the keyboard is driving, so a pointer user is never handed decoration. */
[data-testid="stMarkdownContainer"] a:hover { text-decoration: none; }
[data-testid="stMarkdownContainer"] a:focus-visible {
    text-decoration: underline; text-underline-offset: 2px;
    outline: none; box-shadow: var(--ring); border-radius: 4px;
}

/* ---------------- Focus, scrollbars, motion ---------------- */
:focus-visible { outline: 2px solid $GOLD_BRIGHT; outline-offset: 2px; border-radius: 6px; }
*::-webkit-scrollbar { width: 9px; height: 9px; }
*::-webkit-scrollbar-track { background: transparent; }
*::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.14); border-radius: 6px; }
*::-webkit-scrollbar-thumb:hover { background: rgba(255,255,255,0.24); }
a, a:visited { color: $GOLD_BRIGHT; }
[data-testid="stMarkdownContainer"] a:hover { color: #FFFFFF; }

/* charts: the surface is glass, the plotting area is not. Blur would soften
   axes and gridlines, so the canvas stays crisp on a darkened pane — the same
   navy pane as the cards, because a chart is where a figure is *read* and the
   photograph behind it must not print through the grid. */
.js-plotly-plot, .js-plotly-plot .svg-container { width: 100% !important; }
div[data-testid="stPlotlyChart"] {
    background: linear-gradient(160deg, rgba(18,28,45,0.66), rgba(10,17,29,0.62)),
                $GLASS_PANE;
    border: 1px solid $GLASS_LINE; border-radius: var(--radius);
    /* No padding here: Plotly sizes the canvas to an exact pixel height and
       paints the date labels inside that height. Padding on the panel subtracts
       from the canvas box, so the tick labels land outside the element and get
       clipped — the chart's own margins provide the inset instead. */
    padding: 0;
    box-shadow: var(--shadow), var(--lip);
}
.modebar { background: transparent !important; }
.modebar-btn path { fill: $TEXT_FAINT !important; }
.modebar-btn:hover path { fill: $GOLD_BRIGHT !important; }

/* toasts and the running-spinner surface follow the glass material */
div[data-testid="stToast"] {
    background: $GLASS_STRONG !important;
    border: 1px solid $GLASS_LINE !important;
    border-radius: 14px !important;
    backdrop-filter: $BLUR;
    color: $TEXT !important;
}

/* ---------------- Responsive ----------------
   The rail collapses natively at every width. Two real controls, always
   visible: the chevron inside the rail closes it, the pill floating over the
   canvas reopens it — so Streamlit's remembered "collapsed" state can never
   strand a wide screen with no navigation. Below 1025px the same pill opens
   the mobile drawer. */
[data-testid="stSidebarCollapseButton"] button {
    background: rgba(255,255,255,0.06) !important;
    border: 1px solid $GLASS_LINE !important;
    color: #E9EFF8 !important; border-radius: 10px;
    transition: background .16s ease, border-color .16s ease;
}
[data-testid="stSidebarCollapseButton"] button:hover {
    background: rgba(255,255,255,0.12) !important;
    border-color: $GOLD_LINE !important;
}
button[data-testid="stExpandSidebarButton"] {
    background: rgba(14,22,36,0.82) !important;
    border: 1px solid $GLASS_LINE !important;
    color: $TEXT !important; border-radius: 10px;
    backdrop-filter: $BLUR_SOFT;
    box-shadow: 0 12px 26px -18px #000;
    transition: border-color .16s ease, color .16s ease;
}
button[data-testid="stExpandSidebarButton"]:hover {
    border-color: $GOLD_LINE !important; color: $GOLD_BRIGHT !important;
}

@media (max-width: 1100px) {
    .block-container { padding: 1rem 1.1rem 2.4rem; }
    .spec-grid { grid-template-columns: repeat(2, 1fr); }
    .ladder { grid-template-columns: 1fr; }
    .pipe { grid-template-columns: repeat(3, 1fr); }
    .pipe-step:nth-child(3)::after { display: none; }
    .hero-band { background-position: 0 0, 0 0, 0 0, 0 0, 58% 36%; }
}
@media (max-width: 820px) {
    /* the collapsed-rail chevron floats over the canvas; clear it so it never
       sits on top of the breadcrumb on a compact header */
    .block-container { padding-top: 2.6rem; }
    div[data-testid="stHorizontalBlock"] { flex-wrap: wrap; gap: .6rem !important; }
    div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] { min-width: 46% !important; }
    .pagehead { flex-direction: column; gap: .8rem; padding: 1rem 1.1rem 1.05rem; }
    /* the band keeps its headline first; the photograph is only ever a layer */
    .hero-band { padding: .8rem; }
    .hero-glass { padding: 1.1rem 1.15rem 1.2rem; }
    .hero-band h1 { font-size: 1.7rem !important; }
    .hero-sub { font-size: .86rem; }
    h1 { font-size: 1.45rem !important; }
    .ph-mark { width: 22px; height: 22px; }
    /* one blur per screenful on weaker GPUs; the border and lip still read */
    div[data-testid="stMetric"], .pagehead, div[data-testid="stVerticalBlockBorderWrapper"] {
        backdrop-filter: none; -webkit-backdrop-filter: none;
        background: rgba(15,24,40,0.82);
    }
}
@media (max-width: 640px) {
    .block-container { padding: 2.4rem .7rem 2rem; }
    div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] { min-width: 100% !important; }
    .spec-grid { grid-template-columns: 1fr; }
    .pipe { grid-template-columns: repeat(2, 1fr); }
    .pipe-step:nth-child(2n)::after { display: none; }
    h1 { font-size: 1.3rem !important; }
    div[data-testid="stMetric"] { min-height: 92px; padding: .85rem .9rem; }
    div[data-testid="stMetricValue"] { font-size: 1.2rem !important; }
    .ph-sub { font-size: .8rem; }
    .meta-item, .status-chip { font-size: .68rem; }
    .disclaimer, .caveat { font-size: .74rem; }
    .section-head { flex-direction: column; align-items: flex-start; gap: .15rem; }
    .section-head .hint { font-size: .72rem; }
    section[data-testid="stSidebar"] { width: 17rem !important; }
    .hero-band {
        padding: .55rem;
        background-image:
            linear-gradient(100deg, rgba(6,10,18,0.94) 0%, rgba(6,10,18,0.78) 58%,
                            rgba(6,10,18,0.52) 100%),
            linear-gradient(180deg, rgba(6,10,18,0.55) 0%, rgba(6,10,18,0.14) 48%,
                            rgba(6,10,18,0.78) 100%),
            radial-gradient(70% 90% at 92% 0%, $GOLD_LINE, rgba(232,205,138,0) 66%),
            url($TERMINAL_TEX),
            url($HERO_BG_SM);
        background-size: 100% 100%, 100% 100%, 100% 100%, 380px 380px, cover;
        background-position: 0 0, 0 0, 0 0, 0 0, 66% 34%;
    }
    .hero-glass { padding: .95rem .9rem 1rem; border-radius: 15px; }
    .hero-band h1 { font-size: 1.5rem !important; }
    .hero-sub { font-size: .82rem; }
    .hero-chip { font-size: .7rem; padding: .3rem .55rem; }
    .hero-cta { flex: 1 1 auto; justify-content: center; }
    .hero-credit { margin-top: .7rem; font-size: .65rem; }
    .ladder-step { padding: .85rem .9rem; }
}
@media (prefers-reduced-motion: reduce) {
    /* Every transition, animation and smooth scroll becomes instant. Nothing
       here carries meaning that only motion conveys — hover and focus states
       still change colour, the ripple simply never plays, and the app stays
       fully usable. */
    *, *::before, *::after {
        transition: none !important; animation: none !important;
        scroll-behavior: auto !important;
    }
    /* the lift is motion, so it is removed; the colour change is kept */
    .stButton button:hover, .stDownloadButton button:hover,
    .stFormSubmitButton button:hover, .gbtn:hover,
    div[data-testid="stMetric"]:hover, .spec-card:hover {
        transform: none !important;
    }
}

/* ---------------- Fallbacks ----------------
   No backdrop-filter (older browsers, some Linux builds): the same layout on a
   near-opaque pane, which keeps every figure as readable as the glass version. */
@supports not ((backdrop-filter: blur(6px)) or (-webkit-backdrop-filter: blur(6px))) {
    section[data-testid="stSidebar"] { background-color: rgba(8,13,23,0.96); }
    .pagehead, .hero-glass, div[data-testid="stMetric"],
    div[data-testid="stVerticalBlockBorderWrapper"], .empty-state {
        background: rgba(14,22,36,0.94);
    }
}
</style>
""")


def rendered_css() -> str:
    """The stylesheet with every token substituted.

    Background URLs come from ``app.artwork`` rather than being typed here, so a
    renamed or rebuilt asset cannot leave the stylesheet pointing at a 404. The
    SVG textures are inlined as data URIs: a few hundred bytes, no extra request,
    and no flash of unstyled texture on first paint.

    Exposed separately from ``apply_theme`` so the tests can assert on the exact
    string the app ships.
    """
    from app.backgrounds import MARKER_CLASS, scoped_css

    return CSS.substitute(
        PAGE_BG=scoped_css(), MARKER_CLASS=MARKER_CLASS,
        HERO_BG=artwork.background_url("backdrop-hero", 1600),
        HERO_BG_SM=artwork.background_url("backdrop-hero", 960),
        GOLD_TILE=artwork.background_url("tile-gold", 512),
        TERMINAL_TEX=artwork.data_uri("texture-terminal.svg"),
        CANVAS=CANVAS, CANVAS_DEEP=CANVAS_DEEP,
        SURFACE=SURFACE, SURFACE_ALT=SURFACE_ALT, SURFACE_SOLID=SURFACE_SOLID,
        GLASS=GLASS, GLASS_STRONG=GLASS_STRONG, GLASS_LINE=GLASS_LINE,
        GLASS_LINE_HI=GLASS_LINE_HI, GLASS_HIGHLIGHT=GLASS_HIGHLIGHT,
        GLASS_SHADE=GLASS_SHADE, BLUR=BLUR, BLUR_SOFT=BLUR_SOFT,
        LINE=LINE, LINE_STRONG=LINE_STRONG,
        RAIL=RAIL, RAIL_ELEV=RAIL_ELEV, RAIL_LINE=RAIL_LINE,
        RAIL_TEXT=RAIL_TEXT, RAIL_MUTED=RAIL_MUTED,
        TEXT=TEXT, TEXT_MUTED=TEXT_MUTED, TEXT_FAINT=TEXT_FAINT,
        TEXT_INVERT=TEXT_INVERT,
        GLASS_PANE=GLASS_PANE,
        GOLD=GOLD, GOLD_BRIGHT=GOLD_BRIGHT, GOLD_DEEP=GOLD_DEEP,
        GOLD_SOFT=GOLD_SOFT, GOLD_LINE=GOLD_LINE,
        UP=UP, DOWN=DOWN, WARN=WARN, UP_SOFT=UP_SOFT, DOWN_SOFT=DOWN_SOFT,
        WARN_SOFT=WARN_SOFT, FONT=FONT, MONO=MONO,
    )


def apply_theme() -> None:
    """Inject the stylesheet (called once per run by the router)."""
    st.markdown(rendered_css(), unsafe_allow_html=True)


# ---- Plotly template -----------------------------------------------------
# A single registered template, set as the default, keeps every chart on the
# same dark pane: no chart can drift onto Plotly's stock blue or a white card.
GRID = "rgba(240,245,255,0.07)"
AXIS = "#93A2B8"
HOVER_BG = "#0E1728"
# The crosshair: a gold rule at 20% alpha tracking the cursor across the whole
# plot. Strong enough to line a date up between two axes, quiet enough that it
# never competes with the series. Set on the template so every chart gets it,
# including the ones that only pass their own margins.
SPIKE = "rgba(232,205,138,0.20)"
SPIKE_AXES = dict(showspikes=True, spikemode="across", spikesnap="cursor",
                  spikecolor=SPIKE, spikethickness=1, spikedash="solid")

pio.templates["mcx_glass"] = dict(layout=dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Inter, sans-serif", color=TEXT_MUTED, size=12),
    colorway=[CONTRACT_COLORS["GOLDM"], CONTRACT_COLORS["GOLDTEN"],
              CONTRACT_COLORS["GOLDGUINEA"], CONTRACT_COLORS["GOLDPETAL"],
              GOLD_BRIGHT, DOWN, UP],
    hoverlabel=dict(bgcolor=HOVER_BG, bordercolor=GLASS_LINE_HI,
                    font=dict(family="Inter", color=TEXT, size=12)),
    # automargin lets Plotly grow the margins to fit tick labels and axis
    # titles. Without it the fixed margin below clips date labels to slivers
    # on every chart, so a reader cannot tell one month from another.
    xaxis=dict(gridcolor=GRID, zeroline=False, linecolor=GLASS_LINE,
               tickcolor=GLASS_LINE, ticks="outside", ticklen=4,
               automargin=True, tickfont=dict(color=AXIS, size=11),
               **SPIKE_AXES),
    yaxis=dict(gridcolor=GRID, zeroline=False, linecolor=GLASS_LINE,
               tickcolor=GLASS_LINE, ticks="outside", ticklen=4,
               automargin=True, tickfont=dict(color=AXIS, size=11),
               **SPIKE_AXES),
    legend=dict(orientation="h", y=1.1, x=0, bgcolor="rgba(0,0,0,0)",
                font=dict(size=11, color=TEXT_MUTED)),
    title=dict(font=dict(size=13, color=TEXT), x=0, xanchor="left"),
    # Room for the axis titles and date labels. Plotly measures a fixed pixel
    # height for the whole canvas, so a margin that is too small steals the
    # space from the tick labels and they get cut off at the panel edge.
    margin=dict(l=62, r=16, t=48, b=36),
    colorscale=dict(
        sequential=[[0.0, "#0B1526"], [0.5, GOLD_DEEP], [1.0, GOLD_BRIGHT]],
        diverging=[[0.0, DOWN], [0.5, "#16233A"], [1.0, UP]],
    ),
    scene=dict(bgcolor="rgba(0,0,0,0)",
               xaxis=dict(gridcolor=GRID, color=AXIS),
               yaxis=dict(gridcolor=GRID, color=AXIS),
               zaxis=dict(gridcolor=GRID, color=AXIS)),
    waterfallgap=0.35,
))
pio.templates.default = "mcx_glass"

PLOTLY_CONFIG = {"responsive": True, "displaylogo": False,
                 "modeBarButtonsToRemove": ["lasso2d", "select2d"]}
