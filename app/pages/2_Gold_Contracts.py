"""Gold Contracts — specifications, expiry/liquidity and the settlement curve."""
import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app import artwork
from app.components import (caveat_box, chart_table, config_chip, disclaimer_footer,
                            empty_state, expiry_label, page_header, section_head)
from app.dataio import cfg_hash_chip, load_normalized
from app.theme import (CONTRACT_COLORS, GOLD_BRIGHT, GOLD_DEEP, PLOTLY_CONFIG,
                       SURFACE, contract_style)
from src.utils.config import load_config

SYMBOLS = ["GOLDM", "GOLDTEN", "GOLDGUINEA", "GOLDPETAL"]

page_header("Gold Contracts",
            "Four contracts, four different units — and the normalization that makes them comparable",
            actions=[("Price comparison", "price-comparison"),
                     ("Methodology", "methodology")])

norm = load_normalized()
if norm.empty:
    empty_state("No data yet", "Run python -m src.pipeline, then reload this page.",
                link_slug="data-quality", link_label="Open Data Quality")
    disclaimer_footer()
    st.stop()

cfg = load_config()
spec = cfg["contracts"]
latest_day = norm["trade_date"].max()
snap = norm[norm["trade_date"] == latest_day].copy()

tab_spec, tab_expiry, tab_curve = st.tabs(
    ["Specifications", "Expiry & liquidity", "Term structure"])

# =========================================================================
with tab_spec:
    section_head("Contract sheet", "Settlement values as of the latest data date")

    cards = ""
    for sym in SYMBOLS:
        row = snap[snap["symbol"] == sym]
        if row.empty:
            continue
        price = float(row["inr_per_g_fine"].iloc[0])
        c = spec.get(sym, {})
        # The bullion frame is a background layer under the glass at ~20% — it
        # names the physical product without ever being read as the contract.
        # The numbers come from config/config.yaml, not from the picture.
        shot = artwork.contract_background(sym, 640)
        cards += f"""
<div class="spec-card" style="--accent:{CONTRACT_COLORS[sym]};--shot:url('{shot}')">
  <div class="spec-sym">{sym}</div>
  <div class="spec-price">{price:,.2f}</div>
  <div class="spec-unit">INR per gram (fine)</div>
  <div class="spec-rows">
    <div class="spec-row"><span class="k">Contract size</span><span class="v">{c.get('trading_unit_g')} g</span></div>
    <div class="spec-row"><span class="k">Quoted per</span><span class="v">{c.get('quoted_unit_g')} g</span></div>
    <div class="spec-row"><span class="k">Purity</span><span class="v">{c.get('purity')}</span></div>
    <div class="spec-row"><span class="k">Expiry</span><span class="v">{expiry_label(row['days_to_expiry'].iloc[0])}</span></div>
  </div>
</div>"""
    st.markdown(f'<div class="spec-grid">{cards}</div>', unsafe_allow_html=True)
    st.caption("Each card carries a bullion frame behind the glass — an illustration "
               "of the physical product, not a picture of the MCX contract. Author "
               "and licence are listed on Methodology → Image credits.")

    section_head("Why raw prices cannot be compared",
                 "Same metal, different contract sizes")
    raw_rows = []
    for sym in SYMBOLS:
        row = snap[snap["symbol"] == sym]
        if row.empty:
            continue
        c = spec.get(sym, {})
        raw = float(row["close_raw"].iloc[0])
        unit = float(c.get("quoted_unit_g", 1))
        purity = float(c.get("purity", 1))
        raw_rows.append({
            "Contract": sym,
            "Raw close (quoted)": round(raw, 2),
            "Quoted unit (g)": unit,
            "Purity": purity,
            "Normalized (INR/g fine)": round(raw / (unit * purity), 2),
        })
    st.dataframe(pd.DataFrame(raw_rows), width="stretch", hide_index=True)
    st.caption("A 100 g contract quoted per 10 g looks an order of magnitude 'cheaper' "
               "than a 1 g contract quoted per gram. Dividing by quoted unit × purity "
               "puts all four on one axis.")

    section_head("Full specification table")
    st.dataframe(pd.DataFrame([
        {"Contract": k, "Contract size (g)": v["trading_unit_g"],
         "Quoted per (g)": v["quoted_unit_g"], "Purity": v["purity"],
         "Expiry window (day of month)": f"{v['expiry_window'][0]}–{v['expiry_window'][1]}",
         "First year (config)": v.get("first_year")}
        for k, v in spec.items()
    ]), width="stretch", hide_index=True)
    config_chip(cfg_hash_chip())

# =========================================================================
with tab_expiry:
    section_head("Lifecycle status", f"Days to expiry as of {latest_day:%d %b %Y}")

    def window_status(dte: int) -> str:
        if dte < 0:
            return "Expired in fixture set"
        if dte <= 5:
            return "Expiring / roll zone"
        if dte <= 30:
            return "Near expiry"
        return "Active"

    life = snap[["symbol", "expiry_date", "days_to_expiry", "expiry_window"]].copy()
    life["expiry_date"] = pd.to_datetime(life["expiry_date"]).dt.strftime("%d %b %Y")
    life["status"] = life["days_to_expiry"].map(window_status)
    life = life.rename(columns={"days_to_expiry": "days to expiry (signed)"})
    st.dataframe(life.sort_values("days to expiry (signed)"), width="stretch",
                 hide_index=True)
    if (snap["days_to_expiry"] < 0).any():
        caveat_box("The bundled fixture set assigns each contract one fixed long-dated "
                   "expiry so every symbol has full history. Later sessions therefore "
                   "show settled contracts (negative days). Regenerate with rolling "
                   "expiries before drawing conclusions about the curve or liquidity.")

    section_head("Volume & open interest", "Average per session, last 120 sessions")
    sym = st.selectbox("Contract", SYMBOLS, key="lifecycle_sym")
    series = (norm[norm["symbol"] == sym]
              .groupby("trade_date")[["volume", "open_interest"]].mean().tail(120))
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=series.index, y=series["volume"], name="Volume",
        line=dict(color=CONTRACT_COLORS[sym], width=1.8),
        fill="tozeroy", fillcolor="rgba(232,205,138,.10)"))
    fig.add_trace(go.Scatter(
        x=series.index, y=series["open_interest"], name="Open interest",
        line=dict(color=GOLD_DEEP, width=1.8, dash="dot")))
    fig.update_layout(height=330, hovermode="x unified", yaxis_title="Contracts")
    st.plotly_chart(fig, width="stretch", config=PLOTLY_CONFIG)
    chart_table(series.round(0).reset_index().tail(60), "Table view — volume and OI")

    caveat_box("<strong>Volume is not market depth.</strong> Liquidity here is a proxy "
               "from exchange volume and open interest — no order-book data is used.")

# =========================================================================
with tab_curve:
    section_head("Settlement curve", "Price versus time to expiry on a chosen date")
    carry_cfg = cfg["carry"]
    rate = float(carry_cfg["annual_carry_rate"])
    method = carry_cfg["method"]

    dates = pd.to_datetime(sorted(norm["trade_date"].unique()))
    day = st.select_slider("Settlement date", options=list(dates), value=dates[-1],
                           format_func=lambda d: pd.Timestamp(d).strftime("%d %b %Y"),
                           key="curve_day")
    st.caption(f"Carry model: {method} · r = {rate:.2%} (config/config.yaml)")

    curve = norm[norm["trade_date"] == day].copy()
    fig = go.Figure()
    for sym in SYMBOLS:
        s = curve[curve["symbol"] == sym]
        if s.empty:
            continue
        fig.add_trace(go.Scatter(
            x=s["days_to_expiry"], y=s["inr_per_g_fine"], name=sym,
            mode="lines+markers", line=contract_style(sym),
            marker=dict(size=9, line=dict(width=1.5, color=SURFACE)),
            customdata=s["close_raw"],
            hovertemplate="%{customdata:,.0f} raw<br>DTE %{x}d<br>"
                          "%{y:,.2f} INR/g<extra>" + sym + "</extra>"))
    fig.update_layout(height=400, yaxis_title="INR / g (fine)",
                      xaxis_title="Days to expiry (signed)", hovermode="closest")
    st.plotly_chart(fig, width="stretch", config=PLOTLY_CONFIG)
    if (curve["days_to_expiry"] < 0).any():
        st.caption("Negative days mean the fixture expiry is already behind the session "
                   "date; points are plotted where they fall rather than clamped to zero.")

    front = curve.loc[curve["days_to_expiry"].idxmin()]
    carry = rate * curve["days_to_expiry"] / 365 * curve["inr_per_g_fine"]
    front_carry = float(carry.loc[front.name])
    tab = curve[["symbol", "expiry_date", "days_to_expiry", "close_raw",
                 "inr_per_g_fine"]].copy()
    tab["carry_to_expiry"] = carry.values
    tab["spread_vs_front"] = tab["inr_per_g_fine"] - float(front["inr_per_g_fine"])
    tab["residual_after_carry"] = tab["spread_vs_front"] - (tab["carry_to_expiry"] - front_carry)
    tab = tab.rename(columns={"inr_per_g_fine": "normalized (INR/g)",
                              "days_to_expiry": "DTE"})
    st.markdown("**Residual spread after carry adjustment** (versus front contract)")
    num = ["close_raw", "normalized (INR/g)", "carry_to_expiry",
           "spread_vs_front", "residual_after_carry"]
    tab[num] = tab[num].round(3)
    st.dataframe(tab.sort_values("DTE", ascending=False), width="stretch",
                 hide_index=True)

    section_head("Curve surface", "The whole history in one view — drag to rotate")
    piv = (norm.groupby(["trade_date", "days_to_expiry"])["inr_per_g_fine"]
           .mean().reset_index()
           .pivot(index="trade_date", columns="days_to_expiry",
                  values="inr_per_g_fine").sort_index().tail(120))
    if not piv.empty:
        piv = piv.interpolate(axis=1).ffill().bfill()
        surf = go.Figure(go.Surface(
            z=piv.values, x=piv.columns.astype(int), y=piv.index,
            colorscale=[[0.0, "#0B1526"], [0.45, GOLD_DEEP], [1.0, GOLD_BRIGHT]],
            showscale=False, opacity=0.97,
            hovertemplate="DTE %{x}d · %{y|%d %b %Y}<br>%{z:,.2f} INR/g<extra></extra>"))
        surf.update_layout(height=470, scene=dict(
            xaxis_title="Days to expiry", yaxis_title="Date",
            zaxis_title="INR/g fine"))
        st.plotly_chart(surf, width="stretch", config=PLOTLY_CONFIG)
        chart_table(piv.tail(30).reset_index(), "Table view — surface (last 30 dates)")

    caveat_box(f"<strong>Carry is a first approximation</strong> — {method} at "
               f"r = {rate:.2%}, applied as r × DTE/365 × price. With r = 0 the "
               f"residual equals the raw spread; that is consistent with this config, "
               f"not evidence that carry is small in reality.")

disclaimer_footer()
