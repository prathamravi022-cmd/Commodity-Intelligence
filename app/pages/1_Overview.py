"""Overview — the state of the four MCX gold contracts at a glance."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.components import (chart_table, disclaimer_footer, empty_state,
                            expiry_label, kpi_row, page_header, section_head,
                            signal_badge, stale_banner)
from app.dataio import (data_status, latest_backtest_run, load_clean,
                        load_normalized, load_rejections, load_signals)
from app.theme import (CONTRACT_COLORS, GOLD_BRIGHT, LINE_STRONG, PLOTLY_CONFIG,
                       TEXT_MUTED, contract_style)
from src.utils.config import load_config

SYMBOLS = ["GOLDM", "GOLDTEN", "GOLDGUINEA", "GOLDPETAL"]

page_header(
    "Overview",
    "Four MCX gold contracts validated and restated to one fine-gold INR/gram "
    "basis — pairwise spreads, research signals and walk-forward backtests.",
    band="backdrop-hero",
    actions=[("Explore analytics", "spread-analytics"),
             ("Methodology", "methodology")],
)

norm = load_normalized()
if norm.empty:
    empty_state("No data yet",
                "Run the pipeline first: python -m src.pipeline, then reload this page.",
                link_slug="data-quality", link_label="Open Data Quality")
    disclaimer_footer()
    st.stop()

status = data_status()
if status.warns and status.data_date is not None:
    stale_banner(status)

sig = load_signals()
run = latest_backtest_run()
spec = load_config()["contracts"]

# ---- KPI strip -----------------------------------------------------------
latest_day = norm["trade_date"].max()
latest = norm[norm["trade_date"] == latest_day]
rej = load_rejections()
clean = load_clean()
# "All rows pass" is only claimable when clean rows exist: an empty rejection
# file with no accepted rows means no validation evidence, not a clean bill.
validation = ("No data" if clean.empty and rej.empty else
              "All rows pass" if rej.empty else f"{len(rej):,} rejected")
trades = run.get("trades") if run else None
n_trades = int(len(trades[trades["scenario"] == "base"])) if trades is not None else 0

kpi_row([
    {"label": "Contracts tracked", "value": f"{norm['symbol'].nunique()}",
     "icon": ":material/workspaces:",
     "help": "Distinct MCX gold contracts present in the normalized dataset."},
    {"label": "Latest data date",
     "value": latest_day.strftime("%d %b %Y"),
     "delta": f"{norm['trade_date'].nunique()} trading days",
     "icon": ":material/event_available:",
     "help": "Most recent settlement date in data/analytics/normalized.parquet."},
    {"label": "Validation",
     "value": validation,
     "icon": ":material/verified:",
     "help": "Schema validation of the latest pipeline output: accepted rows in "
             "data/clean/, every rejected row with its reason on Data Quality. "
             "A rejected row never becomes a zero on this page."},
    {"label": "Backtest",
     "value": f"{n_trades} trades" if n_trades else "Not run",
     "icon": ":material/calculate:",
     "help": "Closed trades in the latest recorded run, base cost scenario."},
])

# ---- Main chart ----------------------------------------------------------
section_head("Normalized price history", "INR per gram of fine gold · click a legend entry to isolate a contract")

hist = norm.copy()
fig = go.Figure()
for sym in SYMBOLS:
    d = hist[hist["symbol"] == sym].groupby("trade_date")["inr_per_g_fine"].mean()
    if d.empty:
        continue
    fig.add_trace(go.Scatter(
        x=d.index, y=d.values, name=sym, line=contract_style(sym),
        hovertemplate="%{x|%d %b %Y}<br>%{y:,.2f} INR/g<extra>" + sym + "</extra>"))
fig.update_layout(
    height=430, hovermode="x unified", yaxis_title="INR / g (fine)",
    xaxis=dict(rangeselector=dict(
        buttons=[dict(count=1, label="1M", step="month", stepmode="backward"),
                 dict(count=3, label="3M", step="month", stepmode="backward"),
                 dict(count=6, label="6M", step="month", stepmode="backward"),
                 dict(count=1, label="YTD", step="year", stepmode="todate"),
                 dict(step="all", label="All")],
        bgcolor="rgba(12,20,34,0.92)", activecolor="rgba(232,205,138,0.22)",
        font=dict(color=TEXT_MUTED, size=11), x=0, y=1.14),
        rangeslider=dict(visible=False)))
st.plotly_chart(fig, width="stretch", config=PLOTLY_CONFIG)
chart_table(hist.pivot_table(index="trade_date", columns="symbol",
                             values="inr_per_g_fine").round(2).tail(120)
            .reset_index(), "Table view — normalized prices (last 120 dates)")

# ---- Pair snapshot + spread chart ---------------------------------------
section_head("Relative value", "Pair spreads and rolling z-scores as of the latest date")

if sig.empty:
    empty_state("No signal history yet", "Run the pipeline to compute spreads and z-scores.")
else:
    latest_sig = sig[sig["trade_date"] == sig["trade_date"].max()].copy()
    latest_sig["abs_z"] = latest_sig["z_score"].abs()
    latest_sig["state"] = np.where(
        latest_sig["abs_z"] >= 2.0, "Signal",
        np.where(latest_sig["abs_z"] >= 1.5, "Watch", "Neutral"))
    latest_sig["direction"] = np.where(
        latest_sig["z_score"].fillna(0) >= 0, "Short A / long B", "Long A / short B")
    strongest = latest_sig.sort_values("abs_z", ascending=False).head(1)

    # Full width rather than a half-width column: six pairs carry four facts each,
    # and a narrow panel truncates the very leg names that identify a pair.
    # The snapshot is per contract, so it reads by symbol — the exact expiry
    # series are named in full on Spread Analytics.
    rows = latest_sig.assign(
        pair=(latest_sig["leg_a"].str.split("@").str[0] + " vs "
              + latest_sig["leg_b"].str.split("@").str[0]),
    )[["pair", "z_score", "direction", "state"]]
    st.dataframe(rows.round(4), width="stretch", hide_index=True,
                 column_config={
                     "pair": st.column_config.TextColumn(
                         "Pair (leg A vs leg B)", width="medium"),
                     "z_score": st.column_config.NumberColumn(
                         "z", format="%+.3f", width="small"),
                     "direction": st.column_config.TextColumn(
                         "Direction", width="medium"),
                     "state": st.column_config.TextColumn("State", width="small"),
                 })
    if not strongest.empty:
        s0 = strongest.iloc[0]
        st.markdown(
            f'<div class="caveat">Strongest pair: <strong>{s0["leg_a"]} vs '
            f'{s0["leg_b"]}</strong>, z = {s0["z_score"]:+.3f} '
            f'{signal_badge(s0["state"])}</div>', unsafe_allow_html=True)

    top_a, top_b = strongest.iloc[0]["leg_a"], strongest.iloc[0]["leg_b"]
    pair_sig = sig[(sig["leg_a"] == top_a) & (sig["leg_b"] == top_b)] \
        .sort_values("trade_date").tail(180)
    zfig = go.Figure()
    zfig.add_trace(go.Scatter(
        x=pair_sig["trade_date"], y=pair_sig["z_score"], name="z-score",
        line=dict(color=GOLD_BRIGHT, width=1.8),
        hovertemplate="%{x|%d %b %Y}<br>z %{y:+.3f}<extra></extra>"))
    for level, dash in ((2.0, "dash"), (-2.0, "dash"), (1.5, "dot"), (-1.5, "dot")):
        zfig.add_hline(y=level, line=dict(color=LINE_STRONG, width=1, dash=dash))
    # The pair is named in the caveat above; repeating the full series ids in
    # the chart title only truncates them on a narrow screen.
    zfig.update_layout(height=300, showlegend=False, yaxis_title="z",
                       title="Rolling z-score · last 180 sessions")
    st.plotly_chart(zfig, width="stretch", config=PLOTLY_CONFIG)
    st.caption("Dashed lines: entry threshold ±2.0. Dotted: watch level ±1.5.")

# ---- Contract comparison -------------------------------------------------
section_head("Contract comparison", "Specifications are read from config/config.yaml")

prev_days = sorted(norm["trade_date"].unique())
prev_day = prev_days[-2] if len(prev_days) > 1 else None
prev = norm[norm["trade_date"] == prev_day] if prev_day is not None else norm.iloc[0:0]
rows = []
for sym in SYMBOLS:
    row = latest[latest["symbol"] == sym]
    if row.empty:
        continue
    price = float(row["inr_per_g_fine"].iloc[0])
    prev_row = prev[prev["symbol"] == sym]
    change = (price / float(prev_row["inr_per_g_fine"].iloc[0]) - 1) * 100 \
        if not prev_row.empty else np.nan
    cfg = spec.get(sym, {})
    rows.append({
        "Contract": sym,
        "Contract size (g)": cfg.get("trading_unit_g"),
        "Quoted per (g)": cfg.get("quoted_unit_g"),
        "Purity": cfg.get("purity"),
        "Normalized (INR/g fine)": round(price, 2),
        "Day change %": None if pd.isna(change) else round(change, 3),
        "Expiry state": expiry_label(row["days_to_expiry"].iloc[0]),
    })
st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True,
             column_config={
                 "Normalized (INR/g fine)": st.column_config.NumberColumn(format="%.2f"),
                 "Day change %": st.column_config.NumberColumn(format="%+.2f%%"),
             })
st.caption("Raw quoted prices are not comparable across contracts: each is quoted "
           "for a different quantity and purity. The normalized column divides by "
           "both, which is the only basis on which these four can be compared.")

disclaimer_footer()
