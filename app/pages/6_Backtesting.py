"""Backtesting — walk-forward results with explicit costs, plus P&L attribution."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.components import (caveat_box, chart_table, config_chip,
                            disclaimer_footer, empty_state, kpi_row, page_header,
                            section_head)
from app.dataio import cfg_hash_chip, cost_scenarios, latest_backtest_run
from app.theme import (DOWN, GOLD_DEEP, LINE_STRONG, PLOTLY_CONFIG, SURFACE, UP,
                       signed_color)
from src.utils.config import load_config

page_header("Backtesting",
            "Historical research on settlement prices — not executable trading performance",
            actions=[("Signal explorer", "signal-explorer"),
                     ("Data quality", "data-quality")])

run = latest_backtest_run()
if not run or "trades" not in run:
    empty_state("No backtest recorded yet",
                "Run python -m src.pipeline to produce a walk-forward run, then reload.",
                link_slug="methodology", link_label="Read the backtest design")
    disclaimer_footer()
    st.stop()

cfg = load_config()
trades: pd.DataFrame = run["trades"]
scenarios = trades["scenario"].unique().tolist()
run_meta = run.get("run", {})
metrics_meta = run.get("metrics", {})
params = run_meta.get("params", {})
train_fraction = float(params.get("train_fraction", cfg["backtest"]["train_fraction"]))
min_trades = int(metrics_meta.get("min_trades_required",
                                  cfg["backtest"]["min_out_of_sample_trades"]))

with st.container(border=True):
    scenario = st.select_slider("Cost scenario", scenarios,
                                value="base" if "base" in scenarios else scenarios[0],
                                key="bt_scenario",
                                help="Per-leg, per-side cost assumptions. Switching "
                                     "scenario re-reads the same recorded trades.")

t = trades[trades["scenario"] == scenario].copy()
t["entry_date"] = pd.to_datetime(t["entry_date"])
t["exit_date"] = pd.to_datetime(t["exit_date"])
t = t.sort_values("entry_date")
if t.empty:
    empty_state("No trades in this scenario", "Try another cost scenario.")
    disclaimer_footer()
    st.stop()

costs = cost_scenarios().get(scenario, {})
net = t["net_pnl"].to_numpy()
eqn = np.cumsum(net)
mdd = float(np.min(eqn - np.maximum.accumulate(eqn))) if len(eqn) else 0.0
oos = t[t["split"] == "test"]
oos_period = (f"{oos['entry_date'].min():%d %b %Y} → {oos['exit_date'].max():%d %b %Y}"
              if len(oos) else "no out-of-sample trades")
split_date = (t.iloc[int((t['split'] == 'train').sum())]["entry_date"]
              if (t["split"] == "train").sum() < len(t) else None)

# ---- KPI strip -----------------------------------------------------------
kpi_row([
    {"label": "Gross P&L", "value": f"{t['gross_pnl'].sum():,.0f}",
     "help": "Sum of trade P&L before transaction costs, INR per gram."},
    {"label": "Net P&L", "value": f"{net.sum():,.0f}",
     "delta": f"{net.sum() - t['gross_pnl'].sum():,.0f} after costs",
     "help": "After exchange fee, brokerage, statutory charges and slippage."},
    {"label": "Trades", "value": f"{len(t)}",
     "delta": f"{len(oos)} out-of-sample",
     "help": "Closed trades in this scenario; the second line is the test portion."},
    {"label": "Win rate", "value": f"{(net > 0).mean() * 100:.0f}%",
     "help": "Share of trades with positive net P&L."},
    {"label": "Max drawdown", "value": f"{mdd:,.0f}",
     "help": "Largest peak-to-trough decline of the cumulative net P&L curve."},
])

# ---- Equity curve --------------------------------------------------------
section_head("Cumulative P&L", f"{scenario} cost scenario · split at {train_fraction:.0%} of dates")
eq = t[["entry_date", "gross_pnl", "net_pnl"]].set_index("entry_date").cumsum().reset_index()
fig = go.Figure()
fig.add_trace(go.Scatter(x=eq["entry_date"], y=eq["gross_pnl"], name="Gross",
                         line=dict(color=GOLD_DEEP, width=1.6, dash="dash")))
# A cumulative curve that ends negative must not be painted green: green and
# red mean signed movement everywhere else on this page.
fig.add_trace(go.Scatter(x=eq["entry_date"], y=eq["net_pnl"], name="Net (after costs)",
                         line=dict(color=signed_color(float(eq["net_pnl"].iloc[-1])),
                                   width=2.1)))
if split_date is not None:
    fig.add_vline(x=split_date.isoformat(),
                  line=dict(color=LINE_STRONG, dash="dash"),
                  annotation_text="out-of-sample →", annotation_position="top")
fig.update_layout(height=400, yaxis_title="Cumulative P&L (INR/g)", hovermode="x unified")
st.plotly_chart(fig, width="stretch", config=PLOTLY_CONFIG)
eq_table = eq.rename(columns={"entry_date": "date", "gross_pnl": "cum_gross",
                              "net_pnl": "cum_net"})
eq_table[["cum_gross", "cum_net"]] = eq_table[["cum_gross", "cum_net"]].round(2)
chart_table(eq_table, "Table view — equity curve")

# ---- Cost sensitivity ----------------------------------------------------
section_head("Cost sensitivity", "Net P&L under each recorded cost scenario")
sens = (trades.groupby("scenario")["net_pnl"].sum().reindex(scenarios))
bar = go.Figure(go.Bar(
    x=sens.index, y=sens.values,
    marker=dict(color=[signed_color(v) for v in sens.values]),
    text=[f"{v:,.0f}" for v in sens.values], textposition="outside",
    hovertemplate="%{x}: net %{y:,.0f} INR/g<extra></extra>"))
bar.update_layout(height=280, showlegend=False, yaxis_title="Net P&L (INR/g)",
                  margin=dict(t=30))
st.plotly_chart(bar, width="stretch", config=PLOTLY_CONFIG)
spread_cost = float(sens.max() - sens.min()) if len(sens) else 0.0
st.caption(f"Moving between the cheapest and most expensive recorded scenario changes "
           f"net P&L by {spread_cost:,.0f} INR/g — the assumptions matter as much as the signal.")
# The bar chart is not the only way to read this: the same three numbers, at
# full precision, so a screen reader (or a reader who distrusts a bar's height)
# is not asked to estimate a value from a picture.
chart_table(
    pd.DataFrame({"Scenario": sens.index,
                  "Net P&L (INR/g)": sens.to_numpy()}).round(2),
    "Table view — cost sensitivity",
)

# ---- Trade log -----------------------------------------------------------
section_head("Trade log", "Every closed trade in this scenario")
st.dataframe(
    t[["pair", "entry_date", "exit_date", "direction", "gross_pnl", "cost_total",
       "net_pnl", "split"]].sort_values("entry_date"),
    width="stretch", height=340, hide_index=True)

cost_txt = ", ".join(f"{k.replace('_bps', '').replace('_', ' ')} {v} bps"
                     for k, v in costs.items())
caveat_box(f"<strong>Out-of-sample period:</strong> {oos_period}. The first "
           f"{train_fraction:.0%} of dates are in-sample; only the remainder is used "
           f"for evaluation (walk-forward step "
           f"{cfg['backtest']['walk_forward_step_days']} days).")
caveat_box(f"<strong>Costs assumed ({scenario}, per leg per side):</strong> "
           f"{cost_txt or 'not configured'} — charged at entry and exit on both legs, "
           f"so a round trip costs 2 × (leg A + leg B). Settlement prices are not "
           f"executable fills; this is research, not realised performance.")
if len(oos) < min_trades:
    caveat_box(f"<strong>Low trade count:</strong> {len(oos)} out-of-sample trades is below "
               f"the {min_trades} minimum — these results are not statistically meaningful.")

# ---- Attribution ---------------------------------------------------------
section_head("Attribution", "Where the gross P&L goes, and which pair produced it")

all_pairs = sorted(t["pair"].unique())
picked = st.multiselect("Pairs included", all_pairs, default=all_pairs, key="bt_pairs")
if not picked:
    empty_state("No pairs selected",
                "Select at least one pair — an all-zero chart would misrepresent the run.")
else:
    at = t[t["pair"].isin(picked)]
    wf = go.Figure(go.Waterfall(
        x=["Gross P&L", "Exchange fee", "Brokerage", "Statutory", "Slippage", "Net P&L"],
        measure=["absolute", "relative", "relative", "relative", "relative", "total"],
        y=[at["gross_pnl"].sum(), -at["cost_exchange_fee"].sum(),
           -at["cost_brokerage"].sum(), -at["cost_statutory"].sum(),
           -at["cost_slippage"].sum(), 0],
        text=[f"{at['gross_pnl'].sum():,.0f}", None, None, None, None,
              f"{at['net_pnl'].sum():,.0f}"],
        decreasing=dict(marker=dict(color=DOWN)),
        increasing=dict(marker=dict(color=UP)),
        totals=dict(marker=dict(color=GOLD_DEEP)),
        connector=dict(line=dict(color=LINE_STRONG))))
    wf.update_layout(height=380, yaxis_title="P&L (INR/g)", showlegend=False)
    st.plotly_chart(wf, width="stretch", config=PLOTLY_CONFIG)

    pp = (at.groupby("pair")
          .agg(trades=("pair", "size"), gross=("gross_pnl", "sum"),
               costs=("cost_total", "sum"), net=("net_pnl", "sum"))
          .reset_index().sort_values("net"))
    st.dataframe(pp.round(2), width="stretch", hide_index=True)
    st.caption("A pair's P&L belongs to both of its legs. The leg view below therefore "
               "double-counts across legs and is not a partition of portfolio P&L.")

disclaimer_footer()
