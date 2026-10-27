"""Price Comparison — all four contracts on one basis, with raw values on hover."""
import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.components import (chart_table, contract_key, disclaimer_footer,
                            empty_state, expiry_label, page_header, section_head,
                            stale_banner)
from app.dataio import data_status, load_normalized
from app.theme import (CONTRACT_COLORS, CONTRACT_DASH, PLOTLY_CONFIG,
                       contract_style)
from src.utils.config import load_config

SYMBOLS = ["GOLDM", "GOLDTEN", "GOLDGUINEA", "GOLDPETAL"]

page_header("Price Comparison",
            "Settlement prices restated to fine-gold INR per gram — the only comparable basis",
            actions=[("Spread analytics", "spread-analytics"),
                     ("Backtesting", "backtesting")])

norm = load_normalized()
if norm.empty:
    empty_state("No data yet", "Run python -m src.pipeline, then reload this page.",
                link_slug="data-quality", link_label="Open Data Quality")
    disclaimer_footer()
    st.stop()

status = data_status()
if status.warns and status.data_date is not None:
    stale_banner(status)

spec = load_config()["contracts"]
dmin, dmax = norm["trade_date"].min().date(), norm["trade_date"].max().date()

# ---- Controls ------------------------------------------------------------
with st.container(border=True):
    # The contract field needs room for four chips; squeezed narrower it wraps
    # and pushes its clear button onto a second line outside the control.
    c1, c2, c3 = st.columns([2.4, 1, 1])
    syms = c1.multiselect("Contracts", SYMBOLS, default=SYMBOLS, key="pc_syms")
    d1 = c2.date_input("From", dmin, min_value=dmin, max_value=dmax, key="pc_from")
    d2 = c3.date_input("To", dmax, min_value=dmin, max_value=dmax, key="pc_to")

if not syms:
    empty_state("No contracts selected",
                "Choose at least one contract above — an empty chart would suggest "
                "there is no data, which would be wrong.")
    disclaimer_footer()
    st.stop()

lo, hi = pd.Timestamp(d1), pd.Timestamp(d2)
if lo > hi:
    st.warning("The start date is after the end date — swap them to see a series.")
    disclaimer_footer()
    st.stop()

view = norm[(norm["trade_date"] >= lo) & (norm["trade_date"] <= hi)]
view = view[view["symbol"].isin(syms)]

if view.empty:
    empty_state("No settlements in this range",
                "Widen the date range or add contracts. Dates are trading days only.")
    disclaimer_footer()
    st.stop()

# ---- Chart ---------------------------------------------------------------
# One line per contract, so the key that maps a colour *and dash* to a contract
# belongs directly above the chart rather than in a table further down.
key_day = view["trade_date"].max()
key_items = []
for sym in syms:
    r = view[(view["symbol"] == sym) & (view["trade_date"] == key_day)]
    if r.empty:
        continue
    c = spec.get(sym, {})
    unit, purity = c.get("trading_unit_g"), c.get("purity")
    spec_txt = " · ".join(part for part in (
        f"{float(unit):g} g" if unit is not None else "",
        f"{float(purity):g} fine" if purity is not None else "") if part)
    key_items.append({
        "symbol": sym,
        "spec": spec_txt or "contract size in config",
        "price": f"{float(r['inr_per_g_fine'].iloc[0]):,.2f} INR/g",
        "color": CONTRACT_COLORS[sym],
        "dash": CONTRACT_DASH[sym],
    })
contract_key(key_items)

section_head("Normalized settlement price", f"{lo:%d %b %Y} → {hi:%d %b %Y} · INR per gram (fine)")

fig = go.Figure()
for sym in syms:
    d = (view[view["symbol"] == sym].groupby("trade_date")
         .agg(fine=("inr_per_g_fine", "mean"), raw=("close_raw", "mean")))
    if d.empty:
        continue
    style = contract_style(sym)
    pre, post = d[d.index.year < 2025], d[d.index.year >= 2025]
    hover = ("%{x|%d %b %Y}<br>raw %{customdata:,.0f}<br>"
             "INR/g fine %{y:,.2f}<extra>" + sym + "</extra>")
    if sym == "GOLDTEN" and not pre.empty and not post.empty:
        # GOLDTEN's earlier stretch is drawn dotted and dimmed, never dropped.
        fig.add_trace(go.Scatter(
            x=pre.index, y=pre["fine"], name=f"{sym} (pre-2025)",
            line=dict(color=style["color"], dash="dot", width=1.4), opacity=.45,
            customdata=pre["raw"], hovertemplate=hover))
        fig.add_trace(go.Scatter(x=post.index, y=post["fine"], name=sym,
                                 line=style, customdata=post["raw"], hovertemplate=hover))
        continue
    fig.add_trace(go.Scatter(x=d.index, y=d["fine"], name=sym, line=style,
                             customdata=d["raw"], hovertemplate=hover))

fig.update_layout(height=440, hovermode="x unified", yaxis_title="INR / g (fine)",
                  legend_title_text="Click to isolate a contract")
st.plotly_chart(fig, width="stretch", config=PLOTLY_CONFIG)

if "GOLDTEN" in syms:
    g = view[view["symbol"] == "GOLDTEN"]
    if not g.empty and (g["trade_date"].dt.year < 2025).any():
        st.caption("GOLDTEN: exchange history starts in 2025 — earlier points are drawn "
                   "dotted and are excluded from headline conclusions.")

# ---- Comparison table ----------------------------------------------------
section_head("Latest comparison", "Normalized price and change versus the previous session")

latest = view[view["trade_date"] == view["trade_date"].max()]
days = sorted(view["trade_date"].unique())
prev = view[view["trade_date"] == days[-2]] if len(days) > 1 else view.iloc[0:0]
rows = []
for sym in syms:
    r = latest[latest["symbol"] == sym]
    if r.empty:
        continue
    price = float(r["inr_per_g_fine"].iloc[0])
    p = prev[prev["symbol"] == sym]
    change = (price / float(p["inr_per_g_fine"].iloc[0]) - 1) * 100 if not p.empty else None
    c = spec.get(sym, {})
    rows.append({"Contract": sym, "INR/g fine": round(price, 2),
                 "Change %": None if change is None else round(change, 3),
                 "Contract size (g)": c.get("trading_unit_g"),
                 "Purity": c.get("purity"),
                 "Expiry state": expiry_label(r["days_to_expiry"].iloc[0])})
st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True,
             column_config={"INR/g fine": st.column_config.NumberColumn(format="%.2f"),
                            "Change %": st.column_config.NumberColumn(format="%+.2f")})

# ---- Download ------------------------------------------------------------
section_head("Row data", "Every settlement in the selected window")
out = view[["trade_date", "symbol", "close_raw", "inr_per_g_fine",
            "days_to_expiry"]].copy()
out["contract_size_g"] = out["symbol"].map(lambda s: spec.get(s, {}).get("trading_unit_g"))
out["purity"] = out["symbol"].map(lambda s: spec.get(s, {}).get("purity"))
out = out.rename(columns={"trade_date": "date", "close_raw": "raw_close",
                          "inr_per_g_fine": "inr_per_g_fine"})
st.dataframe(out.sort_values(["date", "symbol"]), width="stretch", height=360,
             hide_index=True)
chart_table(out.sort_values(["date", "symbol"]), "Table view — full series")
st.download_button("Download CSV", out.to_csv(index=False).encode("utf-8"),
                   file_name="normalized_prices.csv", mime="text/csv")

disclaimer_footer()
