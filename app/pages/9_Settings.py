"""Settings — analysis defaults, data maintenance and configuration.

Everything on this page does something. There is no theme switch: Streamlit
themes are fixed per deployment (`.streamlit/config.toml`), and a half-working
toggle that flipped our CSS while native widgets stayed light would be worse
than none, so the light workspace ships as the single, tested appearance.
"""
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.components import (caveat_box, config_chip, disclaimer_footer,
                            page_header, section_head)
from app.dataio import DATA, cfg_hash_chip, last_pipeline_run, load_alerts, load_clean, load_normalized, load_signals
from src.utils.config import load_config

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "config" / "config.yaml"

page_header("Settings",
            "Defaults for this session, data maintenance and the configuration in force",
            actions=[("Data quality", "data-quality"), ("Overview", "")])

cfg = load_config()

# ---- Analysis defaults ---------------------------------------------------
section_head("Analysis defaults", "Applied as the starting point on the analysis pages")
c1, c2, c3 = st.columns(3)
c1.slider("Default z-score window", 20, 120, 60, 5, key="default_window",
          help="Starting window on Spread Analytics. Each page can override it.")
c2.slider("Default entry threshold (|z|)", 1.5, 3.0, 2.0, 0.1, key="default_entry",
          help="Starting threshold on Spread Analytics; the pipeline's own threshold "
               "stays in config/config.yaml and is not changed here.")
c3.select_slider("Default cost scenario", options=["low", "base", "high"],
                 value="base", key="default_scenario",
                 help="Scenario pre-selected on the Backtesting page.")

caveat_box("These are <strong>display defaults for this browser session</strong>. They do "
           "not rewrite config/config.yaml, so a backtest cannot silently change its "
           "assumptions from a dashboard control.")

# ---- Data maintenance ----------------------------------------------------
section_head("Data", "What is loaded, and how to reload it")
norm = load_normalized()
clean = load_clean()
sig = load_signals()
alerts = load_alerts()
run = last_pipeline_run()

rows = [
    {"Dataset": "Normalized prices", "Rows": len(norm),
     "Coverage": (f"{norm['trade_date'].min():%d %b %Y} → {norm['trade_date'].max():%d %b %Y}"
                  if not norm.empty else "—")},
    {"Dataset": "Spread / z-score history", "Rows": len(sig),
     "Coverage": (f"{sig['trade_date'].min():%d %b %Y} → {sig['trade_date'].max():%d %b %Y}"
                  if not sig.empty else "—")},
    {"Dataset": "Clean bhavcopy", "Rows": len(clean),
     "Coverage": (f"{clean['trade_date'].min():%d %b %Y} → {clean['trade_date'].max():%d %b %Y}"
                  if not clean.empty else "—")},
    {"Dataset": "Alerts", "Rows": len(alerts), "Coverage": "—"},
]
st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

c1, c2 = st.columns([1, 2])
with c1:
    if st.button("Reload from disk", type="primary", width="stretch",
                 help="Clear cached parquet reads and re-read data/."):
        st.cache_data.clear()
        st.session_state["data_reloaded"] = True
        st.rerun()
with c2:
    st.caption(f"Last pipeline run: **{run:%d %b %Y %H:%M}**" if run is not None
               else "No recorded pipeline run yet.")

st.markdown("**Regenerate everything** (terminal, from the project root):")
st.code("python -X utf8 tests/fixtures.py\npython -X utf8 -m src.pipeline", language="bash")

# ---- Configuration -------------------------------------------------------
section_head("Configuration", "Read-only here — edits belong in config/config.yaml")
config_chip(cfg_hash_chip())
with st.expander("View the configuration in force"):
    st.code(CONFIG_PATH.read_text(encoding="utf-8"), language="yaml")
st.download_button("Download config.yaml", CONFIG_PATH.read_bytes(),
                   file_name="config.yaml", mime="text/yaml")

# ---- Environment ---------------------------------------------------------
section_head("Environment")
import plotly
import streamlit

st.dataframe(pd.DataFrame([
    {"Item": "Project root", "Value": str(ROOT)},
    {"Item": "Data directory", "Value": str(DATA)},
    {"Item": "Config hash", "Value": cfg_hash_chip()},
    {"Item": "Streamlit", "Value": streamlit.__version__},
    {"Item": "Plotly", "Value": plotly.__version__},
    {"Item": "Pandas", "Value": pd.__version__},
]), width="stretch", hide_index=True)
st.caption("Paths are absolute because this dashboard reads local parquet files; no "
           "market API is called at page load.")

disclaimer_footer()
