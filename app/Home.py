"""Team Starway — Commodity Intelligence. Application entry point.

This file is only the router. It applies the design system once, builds the
``st.navigation`` page list from the single navigation registry in
``app.components``, gates the session on sign-in, draws the rail, and hands the
body to the page the reader selected. Anything rendered here would appear on
*every* page (Streamlit re-runs this script before the page script), so the
dashboard body belongs in ``app/pages/1_Overview.py``.

The rail navigation, page registry and shared chrome live in
``app.components``; the stylesheet lives in ``app.theme``.

Run: ``python -m streamlit run app/Home.py --server.port 8601``
"""
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import artwork
from app.auth import require_auth
from app.components import (NAV_PAGES, SECTIONS, brand_block, flash_reload_notice,
                            rail_nav, rail_search, rail_status, rail_user)
from app.theme import apply_theme

st.set_page_config(
    page_title="Commodity Intelligence · Team Starway",
    page_icon=artwork.favicon_path() or "◆",
    layout="wide",
    # "auto": the rail opens on a desktop's first visit and stays out of the
    # way as a drawer on a phone, instead of covering the dashboard.
    initial_sidebar_state="auto",
)

apply_theme()

# ---- Router -------------------------------------------------------------
# st.navigation gives every page a stable URL, a title we control (not a file
# name) and a real client-side transition. The native page list is hidden by the
# stylesheet and replaced with the rail in components.rail_nav.
pages: dict[str, list] = {}
registry: dict[str, tuple] = {}
for meta in NAV_PAGES:
    # The first page is the default; it owns "/" and ignores url_path.
    kwargs = {} if meta["slug"] == "" else {"url_path": meta["slug"]}
    page = st.Page(meta["path"], title=meta["title"], icon=meta["icon"], **kwargs)
    pages.setdefault(meta["section"], []).append(page)
    registry[meta["title"]] = (page, meta)

current = st.navigation(pages, position="sidebar")

# ---- Sign-in gate -------------------------------------------------------
# One check for the whole application, before the rail and before any page
# script runs, so a new page cannot forget it. It is a no-op unless an [auth]
# block exists in .streamlit/secrets.toml (see app/auth.py).
require_auth()

# ---- Rail ---------------------------------------------------------------
with st.sidebar:
    brand_block()
    rail_search([(m["title"], registry[m["title"]][0]) for m in NAV_PAGES],
                current.title)
    rail_nav([(s, [registry[m["title"]] for m in NAV_PAGES if m["section"] == s])
              for s in SECTIONS], current.title)
    st.markdown('<div class="divider" style="background:rgba(255,255,255,.08);'
                'margin:1.1rem 0"></div>', unsafe_allow_html=True)
    if st.button("Reload data", width="stretch",
                 help="Clear cached parquet reads and re-read data/ from disk."):
        st.cache_data.clear()
        st.session_state["data_reloaded"] = True
        st.rerun()
    rail_status()
    rail_user()

# Both reload buttons (here and on Settings) raise the same once-only notice,
# so a real cache clear always confirms itself instead of silently rerunning.
# It runs before the page body: session state is already cleared here, so the
# toast belongs to this rerun and cannot repeat on the next one.
flash_reload_notice()

current.run()
