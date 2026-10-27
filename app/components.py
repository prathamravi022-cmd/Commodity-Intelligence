"""Shared UI components and the single navigation registry.

Everything visual that more than one page needs lives here: the rail brand and
navigation, the page header (breadcrumb → title → data status), KPI tiles,
badges, empty states and the disclaimer.

Pages call ``page_header(...)`` once at the top. Nothing here reads the network;
the only data it touches is the as-of date and the last pipeline run, both from
``app.dataio``.
"""
from __future__ import annotations

import html

import streamlit as st

from app import artwork
from app.backgrounds import apply_page_background
from app.dataio import Freshness, data_status
from app.theme import TEXT_MUTED

# -------------------------------------------------------------------------
# Navigation registry — the one place page order, labels and icons are set.
# ``title`` is the page heading (and the key into artwork.PAGE_ART);
# ``path`` is the script, relative to app/Home.py; ``slug`` is the URL path.
# -------------------------------------------------------------------------
NAV_PAGES: list[dict] = [
    # The default page is served at "/"; Streamlit ignores its url_path, so its
    # slug is empty and every link to it must use "/" rather than "/overview".
    {"section": "Workspace", "title": "Overview", "label": "Overview",
     "path": "pages/1_Overview.py", "slug": "",
     "icon": ":material/insights:", "art": "icon-overview.svg"},
    {"section": "Workspace", "title": "Gold Contracts", "label": "Gold Contracts",
     "path": "pages/2_Gold_Contracts.py", "slug": "gold-contracts",
     "icon": ":material/workspaces:", "art": "icon-curve.svg"},
    {"section": "Workspace", "title": "Price Comparison", "label": "Price Comparison",
     "path": "pages/3_Price_Comparison.py", "slug": "price-comparison",
     "icon": ":material/candlestick_chart:", "art": "icon-prices.svg"},
    {"section": "Workspace", "title": "Spread Analytics", "label": "Spread Analytics",
     "path": "pages/4_Spread_Analytics.py", "slug": "spread-analytics",
     "icon": ":material/swap_horiz:", "art": "icon-spreads.svg"},
    {"section": "Workspace", "title": "Signal Explorer", "label": "Signal Explorer",
     "path": "pages/5_Signal_Explorer.py", "slug": "signal-explorer",
     "icon": ":material/notifications_active:", "art": "icon-alerts.svg"},
    {"section": "Research", "title": "Backtesting", "label": "Backtesting",
     "path": "pages/6_Backtesting.py", "slug": "backtesting",
     "icon": ":material/calculate:", "art": "icon-backtest.svg"},
    {"section": "Research", "title": "Data Quality", "label": "Data Quality",
     "path": "pages/7_Data_Quality.py", "slug": "data-quality",
     "icon": ":material/verified:", "art": "icon-quality.svg"},
    {"section": "Research", "title": "Methodology", "label": "Methodology",
     "path": "pages/8_Methodology.py", "slug": "methodology",
     "icon": ":material/menu_book:", "art": "icon-methodology.svg"},
    {"section": "Preferences", "title": "Settings", "label": "Settings",
     "path": "pages/9_Settings.py", "slug": "settings",
     "icon": ":material/tune:", "art": "icon-settings.svg"},
]

SECTIONS: list[str] = ["Workspace", "Research", "Preferences"]


def nav_entry(title: str) -> dict:
    for page in NAV_PAGES:
        if page["title"] == title:
            return page
    raise KeyError(title)


# -------------------------------------------------------------------------
# Rail (sidebar)
# -------------------------------------------------------------------------
def brand_block() -> None:
    """Rail brand: bullion mark, product name, team line."""
    mark = artwork.img(artwork.LOGO, alt="", cls="")
    st.markdown(f"""
<div class="rail-brand">
  <div class="rail-mark">{mark}</div>
  <div>
    <div class="rail-name">Commodity Intelligence</div>
    <div class="rail-sub">Team Starway</div>
  </div>
</div>
""", unsafe_allow_html=True)


def rail_nav(groups: list[tuple[str, list]], current_title: str) -> None:
    """Custom rail navigation over ``st.page_link``.

    ``groups`` is ``[(section, [(st.Page, registry_entry), ...]), ...]``. The
    current page's wrapper carries a marker key, which the stylesheet uses for
    the gold active state (``st.page_link`` exposes no stable active attribute).
    """
    for section, entries in groups:
        st.markdown(f'<div class="rail-section">{section}</div>',
                    unsafe_allow_html=True)
        for page_obj, meta in entries:
            key = ("rail-active" if meta["title"] == current_title
                   else "railitem-" + meta["title"].lower().replace(" ", "-"))
            with st.container(key=key):
                st.page_link(page_obj, label=meta["label"], icon=meta["icon"])


def rail_search(pages: list[tuple[str, object]], current_title: str) -> None:
    """Quick navigation: one searchable control over every page.

    ``st.selectbox`` filters as you type, so it doubles as search and jump-to.
    It opens empty (placeholder, no selection) instead of echoing the page the
    reader is already on, which would have read as a stray duplicate of the
    rail item below. The key carries the current page, so each page gets a fresh
    control and the switch happens in ``on_change`` — a rerun can never bounce
    between two pages.
    """
    lookup = dict(pages)
    labels = list(lookup)
    key = "rail-jump:" + current_title

    def _jump() -> None:
        target = st.session_state.get(key)
        if target and target != current_title:
            st.switch_page(lookup[target])

    st.markdown('<div class="rail-section jump-label">Jump to</div>',
                unsafe_allow_html=True)
    st.selectbox("Jump to a page", labels,
                 index=None, placeholder="Search pages…",
                 key=key, label_visibility="collapsed",
                 help="Filter by typing, then press Enter to open a page."
                      "  Shortcut for the full rail below.", on_change=_jump)


def rail_status() -> None:
    """Data status card at the foot of the rail: as-of, last run, staleness.

    A failed attempt is its own row, not a silent gap: the pipeline writes a
    record before it re-raises, so "no new run since Tuesday" and "today's run
    died at validation" read differently here instead of looking identical.
    """
    status = data_status()
    asof = status.data_date.strftime("%d %b %Y") if status.data_date is not None else "no data"
    ran = status.last_run.strftime("%d %b %Y %H:%M") if status.last_run is not None else "never"
    chip = f'<span class="rail-status {status.tone}">{status.state}</span>'
    failed_row = ""
    if status.failure is not None:
        stage = html.escape(str(status.failure.get("stage") or "unknown stage"))
        when = html.escape(str(status.failure.get("failed_utc") or ""))
        failed_row = (
            '  <div class="rc-row"><span class="rc-k">Last attempt</span>'
            f'<span class="rc-v">Failed at {stage}</span>'
            f'<span class="rc-note">{when}</span></div>\n'
        )
    # the sentence, not just the chip: a reader should not have to know what
    # RECENT means, and the state must never be carried by colour alone
    note = (f'\n  <span class="rc-note rc-headline">{html.escape(status.headline)}</span>'
            if status.warns else "")
    st.markdown(f"""
<div class="rail-card">
  <div class="rc-row"><span class="rc-k">Data as of</span>
    <span class="rc-v">{asof}</span></div>
  <div class="rc-row"><span class="rc-k">Last pipeline run</span>
    <span class="rc-v">{ran}</span></div>
  <div class="rc-row">{chip}</div>
{failed_row}{note}
</div>
""", unsafe_allow_html=True)


def flash_reload_notice() -> None:
    """One-shot toast after a cache clear, raised by either reload button.

    The flag is set immediately before ``st.rerun()``, so it survives exactly one
    rerun: popped here, it can never produce a second toast or linger in session
    state. Called by the router *before* the page body runs, which is why the
    notice appears on the page the reader lands on rather than one rerun late.
    """
    if st.session_state.pop("data_reloaded", False):
        st.toast("Data reloaded — cached parquet reads cleared", icon="✅")


def rail_user() -> None:
    """Signed-in identity and sign-out, at the foot of the rail.

    Renders nothing on a public instance, so the rail is unchanged until a
    provider is configured. Imported inside the function to keep ``app.auth``
    free of any dependency on the chrome layer.
    """
    from app.auth import auth_enabled, auth_warning, sign_out, user

    # A half-configured or malformed [auth] block is not the same thing as "this
    # deployment chose to be public". Say so, name only the keys (never their
    # values), and keep the rest of the rail working.
    warning = auth_warning()
    if warning:
        st.markdown(f"""
<div class="rail-card rail-warn" role="status">
  <div class="rc-row"><span class="rc-k">Sign-in</span>
    <span class="rc-v">Not running</span></div>
  <span class="rail-warn-body">{warning}</span>
</div>
""", unsafe_allow_html=True)

    if not auth_enabled():
        return
    who = user()
    if not who:
        return

    st.markdown(f"""
<div class="rail-card">
  <div class="rc-row"><span class="rc-k">Signed in</span>
    <span class="rc-v">{who['name']}</span></div>
  <div class="rc-row"><span class="rc-k">Email</span>
    <span class="rc-v">{who['email'] or 'unknown'}</span></div>
</div>
""", unsafe_allow_html=True)
    if st.button("Sign out", width="stretch", key="rail_signout",
                 help="Clear this browser's session cookie."):
        sign_out()


# -------------------------------------------------------------------------
# Page header — breadcrumb, title, context and data status
# -------------------------------------------------------------------------
def _freshbar(asof: str, ran: str, status: Freshness) -> str:
    """Markup for the data stamp every page carries above its header.

    Three facts: what the figures are as of, when they were built, and which of
    the six freshness states applies. The wrapper is the live region — the link
    inside keeps its link semantics, which is why the status role sits on the
    container instead of on the anchor. The state is never colour alone: the
    word is always present, and anything short of CURRENT carries a sentence
    saying *why*, so the reader does not have to guess what RECENT means.

    The explanation can quote a pipeline stage name, which comes from a JSON
    file on disk — treated as untrusted text and escaped.
    """
    note = (f'\n  <p class="fb-note">{html.escape(status.headline)}</p>'
            if status.warns else "")
    return f"""
<div class="freshbar-wrap" role="status" aria-live="polite">
  <a class="freshbar {status.tone}" href="/methodology"
     title="Data provenance and the validation rules in force — Methodology">
    <span class="fb-k">Data as of</span><span class="fb-v">{asof}</span>
    <span class="fb-sep">·</span>
    <span class="fb-k">Last pipeline run</span><span class="fb-v">{ran}</span>
    <span class="fb-sep">·</span>
    <span class="fb-state">{status.state}</span>
  </a>{note}
</div>"""


def freshness_banner() -> None:
    """The data stamp on its own, for a page that does not open on a header."""
    status = data_status()
    asof = status.data_date.strftime("%d %b %Y") if status.data_date is not None else "no data"
    ran = status.last_run.strftime("%d %b %Y %H:%M") if status.last_run is not None else "never"
    st.markdown(_freshbar(asof, ran, status), unsafe_allow_html=True)


def page_header(title: str, subtitle: str = "", band: str = "",
                actions: list[tuple[str, str]] | None = None) -> None:
    """Breadcrumb + page title + market context + data-status chips.

    Every screen gets the same header, so an analyst always knows which page
    they are on and how old the numbers are before reading a figure.

    ``band`` turns the header into the cinematic band: a registered background
    photograph (see ``artwork.BACKGROUNDS``) under a navy wash and a gold light,
    with the headline on a frosted glass panel. ``actions`` is
    ``[(label, slug), ...]`` and renders real links, so the buttons navigate
    rather than decorate. Without a band the header is the compact glass strip
    every research page opens with.
    """
    meta = nav_entry(title)
    # Select this page's canvas before anything is painted on it (app/backgrounds.py).
    apply_page_background(title)
    status = data_status()
    asof = status.data_date.strftime("%d %b %Y") if status.data_date is not None else "no data"
    ran = status.last_run.strftime("%d %b %Y %H:%M") if status.last_run is not None else "never"
    # CURRENT is the resting state; every other state is named on the chip so a
    # reader sees the difference between one session behind and historical data
    chip = (f'<span class="status-chip {status.tone}"><span class="dot"></span>'
            f'{status.state.title().replace("_", " ")}</span>')

    # the stamp renders on every page, band or no band, exactly once: a reader
    # should never have to open the rail card to learn how old a number is
    st.markdown(_freshbar(asof, ran, status), unsafe_allow_html=True)

    if band:
        state = (f'<span class="hero-chip {status.tone}"><span class="dot"></span>'
                 f'<span class="v">{status.state.title()}</span></span>')
        links = ""
        for index, (label, slug) in enumerate(actions or []):
            href = f"/{slug}" if slug else "/"
            css = "hero-cta" if index == 0 else "hero-cta ghost"
            links += f'<a class="{css}" href="{href}">{label}</a>'
        st.markdown(f"""
<section class="hero-band" aria-label="{title}">
  <div class="hero-glass">
    <div class="hero-inner">
      <nav class="crumb" aria-label="Breadcrumb"><span>{meta['section']}</span>
        <span class="sep">/</span><span class="cur">{title}</span></nav>
      <h1>{title}</h1>
      {f'<p class="hero-sub">{subtitle}</p>' if subtitle else ''}
      <div class="hero-meta">
        <span class="hero-chip"><span class="k">Market</span><span class="v">MCX · Gold</span></span>
        <span class="hero-chip"><span class="k">Data as of</span><span class="v">{asof}</span></span>
        <span class="hero-chip"><span class="k">Last run</span><span class="v">{ran}</span></span>
        {state}
      </div>
      {f'<div class="hero-actions">{links}</div>' if links else ''}
    </div>
  </div>
  <div class="hero-credit">{artwork.photo_credit(band)}</div>
</section>
""", unsafe_allow_html=True)
        return

    mark = artwork.art_for(title)
    links = "".join(f'<a class="ph-cta" href="{"/" + slug if slug else "/"}">{label}</a>'
                    for label, slug in actions or [])
    st.markdown(f"""
<nav class="crumb" aria-label="Breadcrumb"><span>{meta['section']}</span>
  <span class="sep">/</span><span class="cur">{title}</span></nav>
<div class="pagehead">
  <div class="ph-text">
    <div class="ph-title">
      {f'<div class="ph-mark">{mark}</div>' if mark else ''}
      <h1>{title}</h1>
    </div>
    {f'<p class="ph-sub">{subtitle}</p>' if subtitle else ''}
    {f'<div class="ph-actions">{links}</div>' if links else ''}
  </div>
  <div class="ph-meta">
    <span class="meta-item"><span class="k">Market</span><span class="v">MCX · Gold</span></span>
    <span class="meta-item"><span class="k">Data as of</span><span class="v">{asof}</span></span>
    <span class="meta-item"><span class="k">Last run</span><span class="v">{ran}</span></span>
    {chip}
  </div>
</div>
""", unsafe_allow_html=True)


# -------------------------------------------------------------------------
# Small pieces
# -------------------------------------------------------------------------
def section_head(title: str, hint: str = "") -> None:
    st.markdown(
        f'<div class="section-head"><h2>{title}</h2>'
        f'{f"<span class=hint>{hint}</span>" if hint else ""}</div>',
        unsafe_allow_html=True)


def signal_badge(state: str) -> str:
    """Signal state badge. Text label always present — never colour alone."""
    icon = {"Neutral": "○", "Watch": "◐", "Signal": "●",
            "Unvalidated": "◌"}.get(state, "○")
    return f'<span class="badge badge-{state}">{icon} {state}</span>'


def expiry_label(days_to_expiry: float) -> str:
    """Plain-language contract state — a negative day count is never shown as one."""
    try:
        dte = int(days_to_expiry)
    except (TypeError, ValueError):
        return "unknown"
    if dte < 0:
        return "Expired (fixture expiry)"
    if dte <= 5:
        return f"Expiring in {dte}d"
    if dte <= 30:
        return f"Near expiry · {dte}d"
    return f"Active · {dte}d"


def direction_badge(direction: str) -> str:
    """Long/short badge, green/red with the word spelled out."""
    return f'<span class="badge badge-{direction}">{direction}</span>'


def kpi_row(cards: list[dict]) -> None:
    """KPI tiles; ``delta`` is optional and coloured by sign.

    ``delta_color="off"`` is for a delta that is a *word* rather than a move —
    a green "Neutral" reads as a gain when nothing has moved. ``icon`` is a
    ``:material/...:`` name; the stylesheet renders it as a small gold glass chip
    beside the label, so the tile still reads as one object.
    """
    cols = st.columns(len(cards))
    for col, card in zip(cols, cards):
        with col:
            st.metric(label=card["label"], value=card["value"],
                      delta=card.get("delta"),
                      delta_color=card.get("delta_color", "normal"),
                      help=card.get("help"), icon=card.get("icon"))


def metric_row(cards: list[dict]) -> None:  # backwards-compatible alias
    kpi_row(cards)


def stale_banner(status: Freshness) -> None:
    """Freshness warning: the state, the reason, and the data date.

    Takes the status rather than a date so the sentence cannot drift from the
    state: "more than one trading day old" was true of the old boolean and is
    false for RECENT, which is exactly the sort of copy that goes stale silently.
    """
    when = (status.data_date.strftime("%d %b %Y")
            if status.data_date is not None else "no data")
    st.markdown(f"""
<div class="stale-banner"><strong>{status.state.title()}</strong> —
{html.escape(status.headline)} Latest data date {when}.</div>
""", unsafe_allow_html=True)
    st.markdown(
        '<style>div[data-testid="stMetricValue"],'
        f'div[data-testid="stMetricValue"] p{{color:{TEXT_MUTED} !important;}}</style>',
        unsafe_allow_html=True)


def caveat_box(text: str) -> None:
    st.markdown(f'<div class="caveat">{text}</div>', unsafe_allow_html=True)


def config_chip(cfg_hash: str) -> None:
    st.markdown(f'<span class="config-chip">config {cfg_hash}</span>',
                unsafe_allow_html=True)


def empty_state(title: str, body: str, link_slug: str | None = None,
                link_label: str = "") -> None:
    """Empty/error panel with the vault artwork and an optional route link."""
    art = artwork.img(artwork.EMPTY, alt="", cls="empty-art")
    link = ""
    if link_slug is not None:
        href = f"/{link_slug}" if link_slug else "/"
        link = (f'<a class="empty-link" href="{href}">'
                f'{link_label or link_slug or "Home"} →</a>')
    st.markdown(f"""
<div class="empty-state">
  {art}
  <div class="empty-title">{title}</div>
  <div class="empty-body">{body}</div>
  {link}
</div>
""", unsafe_allow_html=True)


def disclaimer_footer() -> None:
    st.markdown("""
<div class="disclaimer">
<strong>Research prototype — not investment advice.</strong>
Exchange settlement prices are not executable fill prices. Nothing here is
investment advice; past backtest results do not predict future performance.
Signals are research outputs, not trade recommendations.
</div>
""", unsafe_allow_html=True)


def contract_key(items: list[dict]) -> None:
    """The chart's series key, drawn rather than photographed.

    A dot and a dash sample repeat exactly what the chart plots (colour *and*
    dash), so a line can be walked back to a contract without an image — and the
    figure beside it is the same normalized price the chart draws. Each item is
    ``{"symbol", "spec", "price", "color", "dash"}``.
    """
    borders = {"solid": "solid", "dash": "dashed", "dashdot": "dashed",
               "dot": "dotted"}
    cells = []
    for item in items:
        style = borders.get(item.get("dash", "solid"), "solid")
        cells.append(f"""
<div class="key-item">
  <figcaption>
    <span class="key-name">
      <i class="key-dash" style="--dot:{item['color']};border-top-style:{style}"></i>
      {item['symbol']}
    </span>
    <span class="key-spec">{item['spec']}</span>
    <span class="key-price">{item['price']}</span>
  </figcaption>
</div>""")
    if not cells:
        return
    st.markdown(f'<div class="contract-key">{"".join(cells)}</div>',
                unsafe_allow_html=True)


def pipeline_steps(steps: list[dict]) -> None:
    """The pipeline as markup: numbered glass stages on one rail.

    Drawn in the page instead of shipped as a picture, so it stays sharp at any
    width, wraps on a phone, and its stage names are text a screen reader can
    read. Each step is ``{"name", "note", "io"}``.
    """
    cells = "".join(
        f'<div class="pipe-step"><div class="pipe-n">{i:02d}</div>'
        f'<div class="pipe-name">{step["name"]}</div>'
        f'<div class="pipe-note">{step["note"]}</div>'
        f'<div class="pipe-io">{step["io"]}</div></div>'
        for i, step in enumerate(steps, start=1))
    st.markdown(f'<div class="pipe">{cells}</div>', unsafe_allow_html=True)


def chart_table(df, label: str = "Table view") -> None:
    """Tabular alternative for a chart (accessibility: no chart-only content)."""
    with st.expander(label):
        if df is None or len(df) == 0:
            st.caption("Nothing to tabulate yet.")
        else:
            st.dataframe(df, width="stretch")


def sample_notice(kind: str = "Synthetic sample data") -> None:
    """Explicit flag for non-market data. Never silently mixed with real data."""
    st.markdown(f'<span class="sample-flag">Demo · {kind}</span>',
                unsafe_allow_html=True)
