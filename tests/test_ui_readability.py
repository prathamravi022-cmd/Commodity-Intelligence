"""UIX-GLASS-02: panels that stay readable over the page canvas.

The per-page scenes are drawn to be atmosphere, but an atmosphere drawn *through*
a control is a legibility bug: the old glass recipe was white alpha only, so the
gold curve in ``bg-spreads.svg`` ran straight through the filter panel and the
figure behind a KPI tile. Three invariants are pinned here:

* every raised content surface carries the navy pane beneath its white sheen, so
  the worst case is a faint texture, never a bright stroke;
* the hero glass is deep enough for the white headline it holds.

A sticky provenance strip was tried and rejected: the chart beneath it painted
over the explanation line, so the strip obscured the very figures it annotates.
The stamp stays in the flow, where nothing can cover it.

The chart-table checks at the end are the accessibility half: a bar, a ribbon or
a heatmap may not be the only way to read a value.
"""
from __future__ import annotations

import re
from pathlib import Path

from streamlit.testing.v1 import AppTest

from app.theme import GLASS_PANE, rendered_css

ROOT = Path(__file__).resolve().parents[1]
PAGES = ROOT / "app" / "pages"

#: Surfaces that hold controls or figures over the canvas. Each must sit on the
#: pane; a surface added later without it is the failure this test exists for.
PANE_SURFACES = (
    ".pagehead",
    'div[data-testid="stMetric"]',
    'div[data-testid="stVerticalBlockBorderWrapper"]',
    'div[data-testid="stPlotlyChart"]',
    ".caveat",
    ".empty-state",
)


def _rule(css: str, selector: str) -> str:
    """The first declaration block for ``selector``."""
    start = css.index(selector + " {")
    return css[start:css.index("}", start)]


def test_the_pane_token_is_a_navy_gradient_not_a_white_wash():
    assert "rgba(22,33,51,0.84)" in GLASS_PANE
    assert "rgba(9,15,26,0.78)" in GLASS_PANE


def test_every_raised_content_surface_carries_the_navy_pane():
    css = rendered_css()
    pane = GLASS_PANE.replace("\n", " ")
    for selector in PANE_SURFACES:
        block = " ".join(_rule(css, selector).split())
        assert pane in block, f"{selector} would let the scene show through"


def test_the_hero_glass_is_deep_enough_for_white_headline_text():
    # 0.42 left the photograph reading through the h1; 0.56 keeps the picture as
    # atmosphere while the white headline keeps its contrast.
    block = _rule(rendered_css(), ".hero-glass")
    alpha = float(re.search(r"rgba\(9,\s*15,\s*26,\s*([0-9.]+)\)", block).group(1))
    assert alpha >= 0.5


def test_nothing_is_pinned_over_the_charts():
    # A sticky stamp was tested in the browser and dropped: Plotly painted over
    # the explanation line, so the strip covered the figures it annotates.
    assert "position: sticky" not in rendered_css()


def _run(page: str) -> AppTest:
    at = AppTest.from_file(str(PAGES / page), default_timeout=180).run()
    assert not at.exception, at.exception
    return at


def test_backtesting_cost_chart_has_a_table_view():
    at = _run("6_Backtesting.py")
    labels = [expander.label for expander in at.expander]
    assert "Table view — cost sensitivity" in labels


def test_data_quality_coverage_and_heatmap_have_table_views():
    at = _run("7_Data_Quality.py")
    labels = [expander.label for expander in at.expander]
    assert "Table view — coverage per contract" in labels
    assert "Table view — missing settlements" in labels
