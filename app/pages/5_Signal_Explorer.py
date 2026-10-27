"""Signal Explorer — thresholds, states, episodes and the maths behind them.

Features 41-50: watch/entry/exit thresholds are page controls, episodes are
drawn as a timeline and marked on the z-chart, frequency and dwell are stated
in plain numbers, and every z-value can be traced to the window that produced
it. Feature 80: when there are too few episodes to describe a habit, the page
says so instead of letting the numbers imply one.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.components import (caveat_box, chart_table, config_chip, disclaimer_footer,
                            empty_state, kpi_row, page_header, section_head)
from app.dataio import cfg_hash_chip, latest_backtest_run, load_alerts, load_signals
from app.theme import (DOWN, DOWN_SOFT, GOLD_BRIGHT, GOLD_DEEP, PLOTLY_CONFIG,
                       UP, UP_SOFT, WARN)
from src.analytics.signal_research import (audit_trail, dwell_profile,
                                           entry_frequency, episodes,
                                           sample_warning)
from src.analytics.zscore import rolling_zscores, signal_state
from src.utils.config import load_config

page_header("Signal Explorer",
            "Research indicators, not trade calls — thresholds are controls, and each one is labelled",
            actions=[("Spread analytics", "spread-analytics"),
                     ("Backtesting", "backtesting")])

sig = load_signals()
if sig.empty:
    empty_state("No signal history yet", "Run python -m src.pipeline, then reload this page.",
                link_slug="data-quality", link_label="Open Data Quality")
    disclaimer_footer()
    st.stop()

cfg = load_config()
cfg_sig = cfg["signal"]
entry_cfg = float(cfg_sig["entry_z"])
watch_cfg = float(cfg_sig["watch_z"])
exit_cfg = float(cfg_sig["exit_z"])
min_episodes = int(cfg["backtest"]["min_out_of_sample_trades"])

pairs = (sig["leg_a"] + " vs " + sig["leg_b"]).unique().tolist()

# ---- Controls ------------------------------------------------------------
with st.container(border=True):
    c1, c2 = st.columns([1.2, 1])
    pair = c1.selectbox("Contract pair", pairs, key="se_pair")
    window = c2.slider("Rolling window (trading days)", 20, 120,
                       int(cfg_sig["window_days"]), 5, key="se_window",
                       help="Window for the rolling mean and standard deviation. "
                            "The window excludes the day being scored.")
    c3, c4, c5 = st.columns(3)
    watch = c3.slider("Watch threshold (|z|)", 1.0, 2.9, watch_cfg, 0.1,
                      key="se_watch")
    entry = c4.slider("Entry threshold (|z|)", 1.5, 3.5, entry_cfg, 0.1,
                      key="se_entry")
    exit_z = c5.slider("Exit threshold (|z|)", 0.0, 1.5, exit_cfg, 0.1,
                       key="se_exit",
                       help="An open episode closes when |z| falls to this level or "
                            "below. The stored backtest keeps its own config value; "
                            "these controls change what this page shows.")

if not watch < entry:
    st.error("The watch threshold must sit below the entry threshold — adjust the "
             "sliders so the zones do not overlap.")
    disclaimer_footer()
    st.stop()

leg_a, leg_b = pair.split(" vs ")
sub = (sig[(sig["leg_a"] == leg_a) & (sig["leg_b"] == leg_b)]
       .sort_values("trade_date"))
spread = sub.set_index("trade_date")["residual_after_carry"]
z = rolling_zscores(spread, window)

ep = episodes(z, entry, exit_z)
prof = dwell_profile(z, watch, entry, exit_z)
closed = int((~ep["open"]).sum()) if not ep.empty else 0
cur_z = float(z.iloc[-1]) if len(z) else np.nan
state = signal_state(cur_z, entry, watch)

# ---- Threshold ladder ----------------------------------------------------
section_head("Threshold ladder", "the values this page is using · absolute z-score")
st.markdown(f"""
<div class="ladder">
  <div class="ladder-step" style="--tone:{WARN}">
    <div class="ladder-zone">Watch</div>
    <div class="ladder-rule">|z| ≥ {watch:g}</div>
    <div class="ladder-note">Divergence is building but has not reached the entry threshold.</div>
  </div>
  <div class="ladder-step" style="--tone:{DOWN}">
    <div class="ladder-zone">Entry</div>
    <div class="ladder-rule">|z| ≥ {entry:g}</div>
    <div class="ladder-note">Spread is far enough from its rolling mean to register a signal.</div>
  </div>
  <div class="ladder-step" style="--tone:{UP}">
    <div class="ladder-zone">Exit</div>
    <div class="ladder-rule">|z| ≤ {exit_z:g}</div>
    <div class="ladder-note">Reversion complete — an open episode closes at this level.</div>
  </div>
</div>
""", unsafe_allow_html=True)

# ---- Current state -------------------------------------------------------
latest_day = sig["trade_date"].max()
latest = sig[sig["trade_date"] == latest_day].copy()
run = latest_backtest_run()
tested = set(run["trades"]["pair"].unique()) if run and "trades" in run else set()

rows = []
for _, r in latest.iterrows():
    zz = r["z_score"]
    pr = f"{r['leg_a']} vs {r['leg_b']}"
    rows.append({
        "Pair": pr,
        "z (stored)": None if pd.isna(zz) else round(float(zz), 3),
        "State": signal_state(zz, entry, watch),
        "Direction": ("Short A / long B" if (pd.notna(zz) and zz >= 0)
                      else "Long A / short B") if pd.notna(zz) else "—",
        "Backtest support": "Yes" if pr in tested else "No — unvalidated",
    })

section_head("Current state per pair",
             f"latest session {latest_day:%d %b %Y} · states use the thresholds above")
st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
st.caption("A pair with no out-of-sample support is shown as unvalidated rather than "
           "as a signal — the threshold is met, the evidence is not.")
config_chip(cfg_hash_chip())

# ---- The selected pair ---------------------------------------------------
section_head(f"{pair}", f"{len(sub):,} sessions · window {window} · "
                        f"entry {entry:g} / exit {exit_z:g} / watch {watch:g}")
kpi_row([
    {"label": "Current z", "value": f"{cur_z:+.2f}" if pd.notna(cur_z) else "—",
     "delta": state, "delta_color": "off",
     "help": "z from the residual spread, window above."},
    {"label": "Episodes", "value": f"{len(ep)}",
     "delta": f"{closed} closed", "help": "Entry-to-exit episodes in this series."},
    {"label": "Sessions beyond entry", "value": f"{prof['pct_entry']:.0f}%",
     "help": f"Share of {prof['sessions']:,} valid sessions with |z| ≥ entry."},
    {"label": "Median |z|", "value": f"{prof['median_abs_z']:.2f}"
     if pd.notna(prof["median_abs_z"]) else "—",
     "help": "Typical distance from the rolling mean, so an entry threshold can "
             "be judged against it."},
])

# ---- z-chart with episode annotations (47) -------------------------------
fig = go.Figure()
fig.add_trace(go.Scatter(
    x=z.index, y=z.values, name="z-score",
    line=dict(color=GOLD_BRIGHT, width=1.9),
    hovertemplate="%{x|%d %b %Y}<br>z %{y:+.3f}<extra></extra>"))
for level, color, dash in ((entry, DOWN, "dash"), (-entry, DOWN, "dash"),
                           (watch, WARN, "dot"), (-watch, WARN, "dot"),
                           (exit_z, UP, "dot"), (-exit_z, UP, "dot")):
    fig.add_hline(y=level, line=dict(color=color, width=1, dash=dash), opacity=.55)
fig.add_hrect(y0=entry, y1=max(entry * 2.2, entry + 1),
              fillcolor=DOWN_SOFT, line_width=0, layer="below")
fig.add_hrect(y0=max(entry * -2.2, -entry - 1), y1=-entry,
              fillcolor=DOWN_SOFT, line_width=0, layer="below")
fig.add_hrect(y0=-exit_z, y1=exit_z, fillcolor=UP_SOFT, line_width=0, layer="below")

if not ep.empty:
    entries = pd.to_datetime(ep["entry"])
    fig.add_trace(go.Scatter(
        x=entries, y=ep["entry_z"], mode="markers", name="Entry",
        marker=dict(symbol="triangle-down", size=9, color=DOWN,
                    line=dict(width=1, color="#FFFFFF")),
        hovertemplate="entry %{x|%d %b %Y}<br>z %{y:+.3f}<extra></extra>"))
    done = ep[pd.notna(ep["exit"])]
    if not done.empty:
        fig.add_trace(go.Scatter(
            x=pd.to_datetime(done["exit"]), y=done["exit_z"], mode="markers",
            name="Exit", marker=dict(symbol="circle-open", size=10, color=UP,
                                     line=dict(width=2)),
            hovertemplate="exit %{x|%d %b %Y}<br>z %{y:+.3f}<extra></extra>"))
fig.update_layout(height=380, yaxis_title="z", showlegend=True,
                  legend=dict(orientation="h", y=1.1, x=0))
st.plotly_chart(fig, width="stretch", config=PLOTLY_CONFIG)
st.caption(f"Red band: beyond entry ±{entry:g}. Green band: inside the exit zone "
           f"±{exit_z:g}. Dotted amber: watch ±{watch:g}. Triangles are entries, "
           f"open circles exits.")

warn = sample_warning(closed, minimum=min_episodes)
if warn:
    caveat_box(f"<strong>Small sample:</strong> {warn}")

def _fmt_day(value) -> str:
    """dd Mon yyyy, or 'open' for an episode that has not closed."""
    return value.strftime("%d %b %Y") if pd.notna(value) else "open"


# ---- Timeline (45) -------------------------------------------------------
section_head("Episode timeline", "each bar is one entry held until it closed")
if ep.empty:
    st.caption("No episode crossed the entry threshold in this series.")
else:
    tl = ep.reset_index(drop=True)
    fig = go.Figure()
    for i, row in tl.iterrows():
        end = row["exit"] if pd.notna(row["exit"]) else z.index[-1]
        colour = DOWN if row["direction"] == "Short A / long B" else GOLD_DEEP
        label = (f"episode {i + 1}<br>{row['entry']:%d %b %Y} → "
                 f"{_fmt_day(row['exit'])}"
                 f"<br>{row['sessions']} sessions<extra></extra>")
        fig.add_trace(go.Scatter(
            x=[row["entry"], end], y=[i, i], mode="lines",
            line=dict(color=colour, width=9), showlegend=False,
            hovertemplate=label))
    fig.update_layout(height=max(180, 22 * len(tl) + 60),
                      yaxis=dict(tickmode="array", tickvals=list(range(len(tl))),
                                 ticktext=[f"{i + 1}" for i in range(len(tl))],
                                 title="episode"),
                      xaxis_title="", showlegend=False)
    st.plotly_chart(fig, width="stretch", config=PLOTLY_CONFIG)
    st.caption("Bars end at the last session for episodes still open — the exit "
               "circle is missing for those on the chart above.")

# ---- Episode table and detail (46) --------------------------------------
section_head("Episode detail", "select one to see how it behaved")
if ep.empty:
    st.caption("Nothing to inspect yet.")
else:
    show = ep.copy()
    show["#"] = range(1, len(show) + 1)
    show["entry"] = pd.to_datetime(show["entry"]).dt.strftime("%d %b %Y")
    show["exit"] = show["exit"].apply(
        lambda v: v.strftime("%d %b %Y") if pd.notna(v) else "open")
    st.dataframe(show[["#", "entry", "entry_z", "exit", "exit_z", "direction",
                       "sessions", "max_abs_z", "open"]].round(3),
                 width="stretch", hide_index=True)
    chart_table(show[["#", "entry", "entry_z", "exit", "exit_z", "direction",
                      "sessions", "max_abs_z"]],
                "Table view — episodes")

    labels = {i: (f"{i + 1}. {ep.iloc[i]['entry']:%d %b %Y} → "
                  f"{_fmt_day(ep.iloc[i]['exit'])}")
              for i in range(len(ep))}
    pick = st.selectbox("Episode", list(labels), format_func=labels.get,
                        key="se_episode")
    row = ep.iloc[pick]
    path = z.loc[row["entry"]: (row["exit"] if pd.notna(row["exit"]) else z.index[-1])]
    d1, d2, d3, d4 = st.columns(4)
    d1.metric("Sessions held", f"{int(row['sessions'])}")
    d2.metric("Entry z", f"{row['entry_z']:+.2f}")
    d3.metric("Max |z| while held", f"{row['max_abs_z']:.2f}")
    d4.metric("Exit z", "open" if pd.isna(row["exit_z"]) else f"{row['exit_z']:+.2f}")
    spark = go.Figure(go.Scatter(x=path.index, y=path.values, mode="lines",
                                 line=dict(color=GOLD_DEEP, width=2),
                                 fill="tozeroy", fillcolor="rgba(201,162,39,.10)"))
    spark.add_hline(y=entry, line=dict(color=DOWN, width=1, dash="dash"), opacity=.5)
    spark.add_hline(y=-entry, line=dict(color=DOWN, width=1, dash="dash"), opacity=.5)
    spark.add_hline(y=exit_z, line=dict(color=UP, width=1, dash="dot"), opacity=.5)
    spark.update_layout(height=200, yaxis_title="z", showlegend=False,
                        title=dict(text=labels[pick], x=0),
                        xaxis=dict(type="date", tickformat="%d %b"))
    st.plotly_chart(spark, width="stretch", config=PLOTLY_CONFIG)

# ---- Dwell and frequency (48/49) ----------------------------------------
section_head("How often, and how long", "description of this pair's history, not a forecast")
f1, f2 = st.columns([1, 1.4])
with f1:
    st.dataframe(pd.DataFrame([
        {"Zone": f"|z| ≥ {entry:g} (entry)", "Share of sessions": f"{prof['pct_entry']:.1f}%"},
        {"Zone": f"{watch:g} ≤ |z| < {entry:g} (watch)", "Share of sessions":
            f"{max(prof['pct_watch'] - prof['pct_entry'], 0):.1f}%"},
        {"Zone": f"|z| ≤ {exit_z:g} (exit zone)", "Share of sessions": f"{prof['pct_exit_zone']:.1f}%"},
        {"Zone": "valid sessions", "Share of sessions": f"{prof['sessions']:,}"},
    ]), width="stretch", hide_index=True)
with f2:
    freq = entry_frequency(ep, "Q")
    if freq.empty:
        st.caption("No episodes to count by quarter.")
    else:
        bar = go.Figure(go.Bar(x=freq["period"], y=freq["entries"],
                               marker=dict(color=GOLD_DEEP),
                               text=freq["entries"], textposition="outside",
                               hovertemplate="%{x}: %{y} episode(s)<extra></extra>"))
        bar.update_layout(height=240, yaxis_title="episodes opened",
                          xaxis_title="", yaxis=dict(dtick=1, rangemode="tozero"))
        st.plotly_chart(bar, width="stretch", config=PLOTLY_CONFIG)
    chart_table(freq, "Table view — episodes per quarter")

# ---- Audit trail (50) ----------------------------------------------------
with st.expander("Calculation audit — the inputs behind the last z-values"):
    trail = audit_trail(spread, window, tail=12)
    trail["trade_date"] = pd.to_datetime(trail["trade_date"]).dt.strftime("%d %b %Y")
    st.dataframe(
        trail.rename(columns={"trade_date": "date", "window_mean": "rolling mean",
                              "window_std": "rolling std", "n_used": "inputs used"})
        .round(4), width="stretch", hide_index=True)
    st.caption(f"mean and std come from the {window} sessions before each row's own "
               f"date, so a value is never part of its own benchmark. `inputs used` "
               f"shows how many observations actually entered the window — the first "
               f"{window} rows cannot be scored. Config hash "
               f"{cfg_hash_chip()} pins the assumptions.")

# ---- Alert log -----------------------------------------------------------
alerts = load_alerts()
section_head("Alert log", "recorded threshold crossings from the pipeline run")
if not alerts:
    st.caption("No alerts recorded. Quiet is the expected state when no signal is present.")
else:
    adf = pd.DataFrame(alerts)
    adf["trade_date"] = pd.to_datetime(adf["trade_date"]).dt.strftime("%d %b %Y")
    keep = [c for c in ["trade_date", "pair", "z_score", "threshold", "config_hash"]
            if c in adf.columns]
    st.dataframe(adf[keep], width="stretch", height=260, hide_index=True)
    chart_table(adf[keep], "Table view — alerts")

caveat_box("<strong>Signals are research outputs</strong>, not trade recommendations, and "
           "no order is placed from this dashboard. The stored z-series uses the "
           "pipeline's own window and thresholds; the controls above recompute from "
           "the same residual spread so you can see how sensitive the picture is.")

disclaimer_footer()
