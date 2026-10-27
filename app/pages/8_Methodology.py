"""Methodology — normalization, spreads, backtest design, costs and limitations."""
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app import artwork
from app.components import (caveat_box, config_chip, disclaimer_footer,
                            page_header, pipeline_steps, section_head)
from app.dataio import cfg_hash_chip
from src.utils.config import load_config

page_header("Methodology",
            "Every assumption in one place — nothing about this research is hard-coded",
            actions=[("Data quality", "data-quality"),
                     ("Backtesting", "backtesting")])

cfg = load_config()

# ---- Pipeline ------------------------------------------------------------
# Drawn in markup rather than shipped as a picture: the order of the stages and
# the file each one writes are what make a number on a page traceable, and text
# stays legible at every width.
section_head("Research pipeline", "From the exchange file to this dashboard — every stage writes a file")
pipeline_steps([
    {"name": "Fetch", "note": "One rate-limited request per day to the MCX bhavcopy.",
     "io": "data/raw/ → raw_manifest.json"},
    {"name": "Validate", "note": "Dates, price ranges, expiry alignment; every rejection keeps its reason.",
     "io": "data/clean/validated.parquet"},
    {"name": "Normalize", "note": "Close ÷ (quoted unit × purity) — one fine-gold INR/gram axis.",
     "io": "data/analytics/normalized.parquet"},
    {"name": "Spread", "note": "Same-date pairs only; carry-adjusted residual, rolling window.",
     "io": "data/analytics/spreads.parquet"},
    {"name": "Signals", "note": "Watch / entry / exit z bands — research states, not trade calls.",
     "io": "data/analytics/signals.parquet"},
    {"name": "Backtest", "note": "60/40 chronological split, cost scenarios, walk-forward refit.",
     "io": "data/results/ → run.json"},
])
st.markdown(
    '<div class="pipe-note-wide"><span>Every threshold is read from '
    '<code>config/config.yaml</code> at run time.</span>'
    '<span>Each stage writes a file; the dashboard reads the outputs and its own chart '
    'figures — no figure on this site is a screenshot of market data.</span></div>',
    unsafe_allow_html=True)
with st.expander("Pipeline stages in text"):
    st.markdown("""
1. **Fetch** — one rate-limited request per day to the exchange bhavcopy; raw files land in `data/raw/`.
2. **Validate** — dates, price ranges and expiry alignment are checked; rejected rows are logged with a reason.
3. **Normalize** — `close ÷ (quoted unit × purity)` gives INR per gram of fine gold.
4. **Spread and z-score** — same-date pairs only; the rolling window excludes the current day.
5. **Signals** — watch, entry and exit are z-score bands, not predictions.
6. **Backtest** — 60/40 chronological split with cost scenarios; results are written to `data/results/`.
""")

# ---- Normalization -------------------------------------------------------
section_head("Price normalization", "The step that makes four contracts comparable")
st.markdown(r"""
All contracts are restated to **fine-gold INR per gram**:

$$\text{inr\_per\_g\_fine} = \frac{\text{Close}}{\text{quoted\_unit\_g} \times \text{purity}}$$
""")
st.caption("Contract terms below are read from config/config.yaml — the same values "
           "the normalization step used to produce this dashboard.")
st.dataframe(pd.DataFrame([
    {"Contract": k, "Trading unit (g)": v["trading_unit_g"],
     "Quoted per (g)": v["quoted_unit_g"], "Purity": v["purity"],
     "Expiry window": f"{v['expiry_window'][0]}–{v['expiry_window'][1]}",
     "First year (config)": v.get("first_year")}
    for k, v in cfg["contracts"].items()
]), width="stretch", hide_index=True)

# ---- Spread, carry, signal ----------------------------------------------
section_head("Spread, carry and signal")
st.markdown(r"""
**Spread** (same-date pairs only): $spread_t = P_{A,t} - P_{B,t}$

**Carry adjustment** (simple first approximation):
$$residual_t = spread_t - r \times \frac{dte_A - dte_B}{365} \times P_{B,t}$$

**Rolling z-score** (the window excludes day $t$, so no look-ahead):
$$z_t = \frac{spread_t - \mu(spread_{t-W..t-1})}{\sigma(spread_{t-W..t-1})}$$

**Signal state**: $|z| \geq$ entry → **Signal**; $|z| \geq$ watch → **Watch**; else
**Neutral**. Entry at $|z| \geq entry$, exit at $|z| \leq exit$.
""")

sig_cfg, bt_cfg = cfg["signal"], cfg["backtest"]
c = st.columns(6)
c[0].metric("Window", f"{sig_cfg['window_days']} d")
c[1].metric("Entry z", sig_cfg["entry_z"])
c[2].metric("Watch z", sig_cfg["watch_z"])
c[3].metric("Exit z", sig_cfg["exit_z"])
c[4].metric("Train split", f"{bt_cfg['train_fraction']:.0%}")
c[5].metric("Cooldown", f"{cfg['alerts']['cooldown_days']} d")

# ---- Costs ---------------------------------------------------------------
section_head("Transaction cost assumptions", "Per leg, per side")
st.caption("These are illustrative placeholders — replace them with documented fee "
           "schedules and record the source before drawing production conclusions.")
costs = cfg["costs"]["scenarios"]
cdf = pd.DataFrame(costs).T
cdf.loc["total (bps)"] = cdf.sum()
st.dataframe(cdf, width="stretch")
st.markdown(r"""
**Cost model**: $cost_{leg} = notional \times \frac{fee + brokerage + statutory + slippage}{10000}$

Charged at entry and exit for both legs, so a round trip is $2 \times (cost_A + cost_B)$.
""")

# ---- Backtest design -----------------------------------------------------
section_head("Backtest design")
st.markdown(f"""
- **Chronological split**: the first {bt_cfg['train_fraction']:.0%} of dates are in-sample;
  evaluation uses only the remaining {1 - bt_cfg['train_fraction']:.0%}.
- **Walk-forward**: parameters refit on the trailing window and applied to the next
  {bt_cfg['walk_forward_step_days']}-day step.
- **Frozen evaluation**: the config is frozen before the out-of-sample run and its hash logged.
- **Minimum trades**: fewer than {bt_cfg['min_out_of_sample_trades']} out-of-sample trades is
  flagged **not statistically meaningful**.
- **Prices**: exchange settlement prices, which are not executable fill prices.
""")

caveat_box("<strong>Settlement prices are not fills.</strong> A backtest on settlement "
           "prices assumes an execution quality the market may not offer. Treat the "
           "results as a research signal, not a track record.")

# ---- Limitations ---------------------------------------------------------
section_head("Known limitations", "Stated plainly rather than buried")
st.markdown("""
1. Daily settlement prices only — not executable fill prices.
2. Volume is not market depth; liquidity estimates are proxies.
3. The carry model is a simple first approximation, and its rate is set in config.
4. Cost assumptions are estimates unless sourced from an actual fee schedule.
5. GOLDTEN has a short history (from 2025) — excluded from headline conclusions.
6. Short backtest windows make results sensitive to a handful of trades.
7. Pairs without out-of-sample support are shown as *unvalidated*, not as signals.
""")

section_head("Data sources")
st.markdown("""
- MCX Daily Bhavcopy — mcxindia.com/market-data/bhavcopy
- MCX gold contract specifications — mcxindia.com/products/bullion/gold
- Confirm MCX terms of use before redistributing raw data.
""")

section_head("Image credits", "Photographs are licensed third-party material")
st.caption("Every photograph in the product is a background layer — the canvas, the "
           "Overview band, the closing band and the frame behind each contract card. "
           "None is placed inline as content, none is a screenshot of market data, "
           "and none is presented as the specification of an MCX contract.")
st.markdown("\n".join(f"- {line}" for line in artwork.credit_lines()))
st.caption("Full framing notes, including the exact crop used for each file, are in "
           "docs/photo-credits.md.")

st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
config_chip(cfg_hash_chip())
disclaimer_footer()
