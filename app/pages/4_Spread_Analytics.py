"""Spread Analytics — pairwise spreads, carry residual and rolling z-score.

Parameters recompute in memory from normalized parquet (no pipeline rerun), so a
window or threshold change updates the charts immediately.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.components import (caveat_box, chart_table, contract_key,
                            disclaimer_footer, empty_state, kpi_row, page_header,
                            section_head, signal_badge)
from app.dataio import load_signals
from app.theme import (CONTRACT_COLORS, CONTRACT_DASH, DOWN, GOLD_BRIGHT,
                       LINE_STRONG, PLOTLY_CONFIG, SURFACE, TEXT_MUTED, UP,
                       contract_style)
from src.utils.config import load_config

page_header("Spread Analytics",
            "One pair at a time — spread, rolling z-score and the entries they imply",
            actions=[("Signal explorer", "signal-explorer"),
                     ("Price comparison", "price-comparison")])

sig = load_signals()
if sig.empty:
    empty_state("No spreads yet", "Run python -m src.pipeline, then reload this page.",
                link_slug="data-quality", link_label="Open Data Quality")
    disclaimer_footer()
    st.stop()

cfg_sig = load_config()["signal"]
exit_z = float(cfg_sig["exit_z"])

# ---- Controls ------------------------------------------------------------
with st.container(border=True):
    c1, c2 = st.columns([1.2, 1])
    spread_kind = c1.radio("Spread basis", ["Carry-adjusted residual", "Raw spread"],
                           horizontal=True, key="sa_kind",
                           help="Raw spread is A − B. The residual also subtracts the "
                                "carry implied by the difference in days to expiry.")
    pairs = (sig["leg_a"] + " vs " + sig["leg_b"]).unique().tolist()
    pair = c2.selectbox("Contract pair", pairs, key="sa_pair")

    c3, c4 = st.columns(2)
    window = c3.slider("Rolling window (trading days)", 20, 120,
                       int(st.session_state.get("default_window", 60)), 5,
                       key="sa_window",
                       help="Window used for the rolling mean and standard deviation.")
    entry = c4.slider("Entry threshold (|z|)", 1.5, 3.0,
                      float(st.session_state.get("default_entry", 2.0)), 0.1,
                      key="sa_entry")

col = "residual_after_carry" if spread_kind.startswith("Carry") else "spread_inr_g"
leg_a, leg_b = pair.split(" vs ")
sub = sig[(sig["leg_a"] == leg_a) & (sig["leg_b"] == leg_b)].sort_values("trade_date")

spread = sub.set_index("trade_date")[col]
past = spread.shift(1)                     # window excludes day t: no look-ahead
mu = past.rolling(window, min_periods=window).mean()
sd = past.rolling(window, min_periods=window).std(ddof=1)
z = (spread - mu) / sd
cur_z = z.iloc[-1] if len(z) else np.nan
az = abs(cur_z) if pd.notna(cur_z) else 0.0
state = ("Signal" if az >= entry else
         "Watch" if az >= float(cfg_sig["watch_z"]) else "Neutral")

# ---- The two legs of the trade ------------------------------------------
# The same colour-and-dash key the price chart uses, so a leg read here can be
# found on the other charts without a second legend to learn.
def _leg(symbol_leg: str, price: float) -> dict:
    sym = symbol_leg.split("@")[0]
    c = load_config()["contracts"].get(sym, {})
    unit = c.get("trading_unit_g")
    purity = c.get("purity")
    spec = " · ".join(part for part in (
        f"{unit} g" if unit is not None else "",
        f"{purity}" if purity else "") if part)
    return {"symbol": sym, "spec": spec or "contract size in config",
            "price": f"{price:,.2f} INR/g",
            "color": CONTRACT_COLORS.get(sym, GOLD_BRIGHT),
            "dash": CONTRACT_DASH.get(sym, "solid")}


last = sub.iloc[-1]
contract_key([_leg(leg_a, float(last["price_a"])),
              _leg(leg_b, float(last["price_b"]))])

# ---- Current state -------------------------------------------------------
kpi_row([
    {"label": "Current spread", "value": f"{spread.iloc[-1]:,.2f}",
     "help": "INR per gram (fine)."},
    {"label": "Rolling mean", "value": f"{mu.iloc[-1]:,.2f}" if pd.notna(mu.iloc[-1]) else "—",
     "help": f"Mean of the previous {window} sessions, excluding today."},
    {"label": "Rolling std", "value": f"{sd.iloc[-1]:,.3f}" if pd.notna(sd.iloc[-1]) else "—",
     "help": "Sample standard deviation (ddof=1) over the same window."},
    {"label": "Current z", "value": f"{cur_z:+.3f}" if pd.notna(cur_z) else "—",
     "delta": state, "delta_color": "off",
     "help": "How many rolling standard deviations today sits from "
             "the rolling mean."},
])

if pd.notna(cur_z):
    sym_a, sym_b = leg_a.split("@")[0], leg_b.split("@")[0]
    direction = (f"Short {sym_a} / long {sym_b}" if cur_z >= 0
                 else f"Long {sym_a} / short {sym_b}")
    st.markdown(
        f'{signal_badge(state)} <span style="color:{TEXT_MUTED};font-size:.82rem">'
        f'&nbsp;z = {cur_z:+.3f} · spread {sym_a} − {sym_b} · {direction}'
        f'</span>', unsafe_allow_html=True)

# ---- Spread chart --------------------------------------------------------
section_head("Spread over time", f"{pair} · {spread_kind.lower()}")

# A few sessions can sit far outside the rest of the series — near a roll, the
# carry that is subtracted collapses and the raw difference jumps. Left alone
# those days flatten the other 98% of the series into a line on zero. The
# default view frames the typical band and *pins* the excursions to its edge
# with their true values in the hover, so the shape of the spread is readable
# and nothing is quietly dropped.
typical = float(spread.abs().quantile(0.98)) * 1.5
worst = float(spread.abs().max())
off_scale = [v for v in spread if abs(v) > typical] if typical else []
zoom = False
if typical and worst > typical * 2:
    view = st.radio(
        "Y-axis", [f"Typical band (±{typical:,.2f})", f"Full range (±{worst:,.2f})"],
        horizontal=True, key="sa_yaxis",
        help="Six sessions in a year can sit many times outside the rest of the "
             "series. The typical band keeps the shape readable; the excursions "
             "are marked at the edge, not removed.")
    zoom = view.startswith("Typical")

fig = go.Figure()
fig.add_trace(go.Scatter(x=spread.index, y=spread.values, name=spread_kind,
                         line=contract_style("GOLDM", width=1.9)))
fig.add_hline(y=0, line=dict(color=LINE_STRONG, width=1, dash="dot"))
if zoom:
    fig.update_yaxes(range=[-typical * 1.12, typical * 1.12])
    high = spread[spread > typical]
    low = spread[spread < -typical]
    for side, marker, pinned in ((high, "triangle-up", typical),
                                 (low, "triangle-down", -typical)):
        if len(side):
            fig.add_trace(go.Scatter(
                x=side.index, y=[pinned] * len(side), mode="markers",
                marker=dict(color=TEXT_MUTED, size=8, symbol=marker),
                customdata=side.values,
                name=f"Off scale · {len(side)} sessions",
                hovertemplate=("%{x|%d %b %Y}<br>off scale: %{customdata:,.2f} "
                               "INR / g<extra></extra>")))
fig.update_layout(height=300, yaxis_title="INR / g", hovermode="x unified",
                  showlegend=False)
st.plotly_chart(fig, width="stretch", config=PLOTLY_CONFIG)
if zoom and off_scale:
    st.caption(f"{len(off_scale)} of {len(spread)} sessions sit outside ±{typical:,.2f} "
               f"INR/g and are pinned to the edge of the plot — switch to the full "
               f"range above, or read the exact values in the table below. They are "
               f"included in the rolling mean, the standard deviation and the "
               f"z-score.")

# ---- Z-score chart with entries and exits -------------------------------
section_head("Rolling z-score", f"Window {window} · entry ±{entry:g} · exit ±{exit_z:g}")


def crossings(zs: pd.Series, entry_z: float, exit_z: float):
    """Entry/exit points read off the *same* live z series the chart draws."""
    entries, exits, open_at = [], [], None
    for day, value in zs.items():
        if pd.isna(value):
            continue
        if open_at is None:
            if abs(value) >= entry_z:
                open_at = day
                entries.append((day, float(value)))
        elif abs(value) <= exit_z:
            open_at = None
            exits.append((day, float(value)))
    return entries, exits


entries, exits = crossings(z, entry, exit_z)
states = sub.set_index("trade_date")["signal_state"].reindex(z.index).fillna("—")

zf = go.Figure()
zf.add_trace(go.Scatter(
    x=z.index, y=z.values, name="z-score", line=dict(color=GOLD_BRIGHT, width=1.9),
    customdata=states.astype(str),
    hovertemplate="%{x|%d %b %Y}<br>z %{y:+.3f}<br>state %{customdata}<extra></extra>"))
zf.add_hline(y=entry, line=dict(color=DOWN, width=1, dash="dash"),
             annotation_text=f"+{entry}", annotation_position="top right")
zf.add_hline(y=-entry, line=dict(color=DOWN, width=1, dash="dash"),
             annotation_text=f"−{entry}", annotation_position="bottom right")
for level in (cfg_sig["watch_z"], -cfg_sig["watch_z"]):
    zf.add_hline(y=level, line=dict(color=LINE_STRONG, width=1, dash="dot"))
if entries:
    zf.add_trace(go.Scatter(
        x=[d for d, _ in entries], y=[v for _, v in entries], mode="markers",
        name=f"Entry (|z| ≥ {entry:g})",
        marker=dict(color=DOWN, size=9, symbol="diamond",
                    line=dict(color=SURFACE, width=1)),
        hovertemplate="%{x|%d %b %Y}<br>entry at z %{y:+.3f}<extra></extra>"))
if exits:
    zf.add_trace(go.Scatter(
        x=[d for d, _ in exits], y=[v for _, v in exits], mode="markers",
        name=f"Exit (|z| ≤ {exit_z:g})",
        marker=dict(color=UP, size=9, symbol="circle-open",
                    line=dict(width=2)),
        hovertemplate="%{x|%d %b %Y}<br>exit at z %{y:+.3f}<extra></extra>"))
zf.update_layout(height=320, hovermode="x unified", yaxis_title="z")
st.plotly_chart(zf, width="stretch", config=PLOTLY_CONFIG)
series_table = pd.DataFrame({
    "date": z.index, "spread": spread.values, "rolling_mean": mu.values,
    "rolling_std": sd.values, "z_score": z.values, "signal_state": states.values,
})
# round the numbers only: DataFrame.round() warns on the date column
num_cols = ["spread", "rolling_mean", "rolling_std", "z_score"]
series_table[num_cols] = series_table[num_cols].round(4)
chart_table(series_table, "Table view — spread and z-score")

caveat_box(f"Z-scores recompute in memory from normalized.parquet; changing the window "
           f"or threshold does <strong>not</strong> rerun the pipeline or the backtest. "
           f"Entry requires |z| ≥ {entry:g}, exit at |z| ≤ {exit_z:g} (config), watch at "
           f"±{cfg_sig['watch_z']}. The rolling window excludes the current day.")

disclaimer_footer()
