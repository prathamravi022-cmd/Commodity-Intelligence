"""Signal Explorer: the controls must change what the page computes (41-43)."""
from pathlib import Path

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "app" / "pages" / "5_Signal_Explorer.py"


def _run():
    at = AppTest.from_file(str(PAGE), default_timeout=120).run()
    assert not at.exception, at.exception
    return at


def _zone_table(at):
    """The dwell table (its first column is 'Zone')."""
    for df in at.dataframe:
        cols = list(df.value.columns)
        if "Zone" in cols and "Share of sessions" in cols:
            return df.value
    return None


def _metric(at, label):
    """Rendered KPI value for a label (kpi_row is st.metric)."""
    for m in at.metric:
        if m.label == label:
            return m.value
    return None


def test_page_renders_its_research_sections():
    at = _run()
    labels = {m.label for m in at.metric}
    assert {"Current z", "Episodes", "Sessions beyond entry", "Median |z|"} <= labels
    body = "\n".join(b.value for b in at.markdown)
    assert "Threshold ladder" in body
    assert _zone_table(at) is not None


def test_entry_threshold_control_recomputes_zones():
    at = _run()
    before = _zone_table(at)
    assert before is not None
    assert before.iloc[0]["Zone"].startswith("|z| ≥ 2")

    # sliders are declared window, watch, entry, exit
    at.slider[2].set_value(3.0).run()
    assert not at.exception, at.exception
    after = _zone_table(at)
    assert after is not None
    assert after.iloc[0]["Zone"].startswith("|z| ≥ 3")
    # a stricter entry can only shrink the share of sessions beyond it
    assert float(after.iloc[0]["Share of sessions"].rstrip("%")) <= \
        float(before.iloc[0]["Share of sessions"].rstrip("%"))


def test_watch_threshold_must_sit_below_entry():
    at = _run()
    at.slider[1].set_value(2.5).run()      # watch above the 2.0 entry
    assert not at.exception, at.exception
    errors = " ".join(e.value for e in at.error)
    assert "must sit below the entry threshold" in errors


def test_exit_threshold_control_is_live():
    at = _run()
    before = _zone_table(at)
    at.slider[3].set_value(1.0).run()
    assert not at.exception, at.exception
    after = _zone_table(at)
    assert after is not None and before is not None
    exit_row_before = [r for r in before["Zone"] if "exit zone" in r][0]
    exit_row_after = [r for r in after["Zone"] if "exit zone" in r][0]
    assert exit_row_before != exit_row_after


def test_window_control_changes_the_episode_count():
    at = _run()
    first = _metric(at, "Episodes")
    assert first is not None
    at.slider[0].set_value(20).run()
    assert not at.exception, at.exception
    assert _metric(at, "Episodes") != first
