"""FRESH-01: the six freshness states, their boundaries, and how they read.

The old model had two answers, so a file one session behind and a file six
sessions behind looked the same, and "the pipeline has never run" looked the
same as "the pipeline died this morning". Six states are pinned here:

    FRESH    data is today's session
    CURRENT  one session behind (Friday data on Monday — the normal case)
    RECENT   two to three sessions behind: late, still inside tolerances
    STALE    more than three sessions behind: historical
    NO_DATA  nothing validated yet
    ERROR    a failed attempt outranks the data, or the data is future-dated

Every boundary is driven by a pinned clock, never by the real date.
"""
from __future__ import annotations

import shutil
import textwrap
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from app import components, dataio
from app.dataio import Freshness

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _clear_metadata_caches():
    for cached in (dataio.last_pipeline_run, dataio.last_pipeline_failure):
        cached.clear()
    yield
    for cached in (dataio.last_pipeline_run, dataio.last_pipeline_failure):
        cached.clear()


def _pin(monkeypatch, data_date, today, run=None, failure=None):
    """Freeze the three inputs of ``data_status`` (data, clock, run history)."""
    monkeypatch.setattr(dataio, "as_of",
                        lambda: None if data_date is None else pd.Timestamp(data_date))
    monkeypatch.setattr(dataio, "_today", lambda: pd.Timestamp(today))
    monkeypatch.setattr(dataio, "last_pipeline_run",
                        lambda: None if run is None else pd.Timestamp(run))
    monkeypatch.setattr(dataio, "last_pipeline_failure", lambda: failure)


# ---- States and boundaries ---------------------------------------------
@pytest.mark.parametrize("data_date, today, state, behind", [
    # today's own session
    ("2026-10-26", "2026-10-26", dataio.FRESH, 0),
    # Friday data on Monday: the weekend is not a gap
    ("2026-10-23", "2026-10-26", dataio.CURRENT, 1),
    # Thursday data on Monday: two sessions
    ("2026-10-22", "2026-10-26", dataio.RECENT, 2),
    # Wednesday data on Monday: three sessions — the last RECENT day
    ("2026-10-21", "2026-10-26", dataio.RECENT, 3),
    # Tuesday data on Monday: four sessions — the first STALE day
    ("2026-10-20", "2026-10-26", dataio.STALE, 4),
    # a week of sessions behind
    ("2026-10-19", "2026-10-26", dataio.STALE, 5),
    # month-end rollover counts sessions, it does not reset
    ("2026-09-30", "2026-10-05", dataio.RECENT, 3),
])
def test_state_follows_sessions_behind(monkeypatch, data_date, today, state, behind):
    _pin(monkeypatch, data_date, today, run="2026-10-20T06:00:00+00:00")
    status = dataio.data_status()
    assert status.state == state
    assert status.sessions_behind == behind
    assert status.headline.strip()
    assert status.tone == state.lower()


def test_weekend_today_does_not_advance_the_state(monkeypatch):
    # Friday data, Sunday clock: nothing has traded, so still CURRENT.
    _pin(monkeypatch, "2026-10-23", "2026-10-25", run="2026-10-23T06:00:00+00:00")
    assert dataio.data_status().state == dataio.CURRENT


def test_no_data_is_its_own_state(monkeypatch):
    _pin(monkeypatch, None, "2026-10-26")
    status = dataio.data_status()
    assert status.state == dataio.NO_DATA
    assert status.sessions_behind is None
    assert "No validated market data" in status.headline
    assert status.warns is True


def test_a_timezone_aware_data_date_is_handled(monkeypatch):
    _pin(monkeypatch, pd.Timestamp("2026-10-23", tz="Asia/Kolkata"),
         "2026-10-26", run="2026-10-23T06:00:00+00:00")
    assert dataio.data_status().state == dataio.CURRENT


# ---- ERROR: failures outrank age ---------------------------------------
def test_a_failed_attempt_newer_than_the_run_is_an_error(monkeypatch):
    _pin(monkeypatch, "2026-10-26", "2026-10-26",
         run="2026-10-26T06:00:00+00:00",
         failure={"failed_utc": "2026-10-26T08:00:00+00:00",
                  "stage": "validation", "reason": "no_raw_files"})
    status = dataio.data_status()
    # the data is today's, but the attempt that would have refreshed it died
    assert status.state == dataio.ERROR
    assert "failed at validation" in status.headline
    assert "26 Oct 2026 06:00" in status.headline      # last good run named


def test_a_superseded_failure_does_not_hold_the_state_at_error(monkeypatch):
    _pin(monkeypatch, "2026-10-26", "2026-10-26",
         run="2026-10-26T09:00:00+00:00",
         failure={"failed_utc": "2026-10-26T08:00:00+00:00", "stage": "validation"})
    assert dataio.data_status().state == dataio.FRESH


def test_future_dated_data_cannot_be_trusted(monkeypatch):
    _pin(monkeypatch, "2026-10-27", "2026-10-26",
         run="2026-10-26T06:00:00+00:00")
    status = dataio.data_status()
    assert status.state == dataio.ERROR
    assert "later than today" in status.headline
    assert status.sessions_behind is None


# ---- Backwards-compatible boolean --------------------------------------
@pytest.mark.parametrize("state, warns", [
    (dataio.FRESH, False), (dataio.CURRENT, False),
    (dataio.RECENT, True), (dataio.STALE, True),
    (dataio.NO_DATA, True), (dataio.ERROR, True),
])
def test_warns_matches_the_old_boolean_contract(monkeypatch, state, warns):
    monkeypatch.setattr(dataio, "data_status",
                        lambda: Freshness(state, "explanation"))
    assert dataio.is_stale() is warns


# ---- UI rendering -------------------------------------------------------
def _run(tmp_path: Path, body: str) -> AppTest:
    tree = tmp_path / "apptree"
    shutil.copytree(ROOT / "app", tree, ignore=shutil.ignore_patterns("__pycache__"))
    script = tree / "Home.py"
    script.write_text(
        textwrap.dedent(f'''\
            import sys
            sys.path.insert(0, r"{ROOT}")
            import streamlit as st
            st.set_page_config(page_title="probe")
        ''') + textwrap.dedent(body),
        encoding="utf-8",
    )
    return AppTest.from_file(str(script), default_timeout=60).run()


def test_header_names_the_state_and_explains_a_warning(tmp_path, monkeypatch):
    monkeypatch.setattr(
        components, "data_status",
        lambda: Freshness(dataio.RECENT,
                          "2 trading sessions behind the latest expected session.",
                          data_date=pd.Timestamp("2026-10-22"),
                          sessions_behind=2, last_run=pd.Timestamp("2026-10-22 06:00")))
    at = _run(tmp_path, '''
        from app.components import page_header
        page_header("Spread Analytics", "Pairwise spreads")
    ''')
    assert not at.exception, at.exception
    markup = "\n".join(m.value for m in at.markdown)
    assert "RECENT" in markup                       # the word, not colour alone
    assert "freshbar recent" in markup              # the tone class
    assert "2 trading sessions behind" in markup    # the explanation is visible
    assert "Recent" in markup                       # the status chip


def test_a_fresh_page_carries_no_warning_sentence(tmp_path, monkeypatch):
    monkeypatch.setattr(
        components, "data_status",
        lambda: Freshness(dataio.FRESH, "The figures are from today's session.",
                          data_date=pd.Timestamp("2026-10-26")))
    at = _run(tmp_path, '''
        from app.components import page_header
        page_header("Settings", "")
    ''')
    assert not at.exception, at.exception
    markup = "\n".join(m.value for m in at.markdown)
    assert "FRESH" in markup
    assert "fb-note" not in markup


def test_stale_banner_states_the_reason_and_escapes_untrusted_text(tmp_path, monkeypatch):
    monkeypatch.setattr(
        components, "data_status",
        lambda: Freshness(dataio.ERROR,
                          "The last pipeline attempt failed at <script>x</script>.",
                          data_date=pd.Timestamp("2026-09-30")))
    at = _run(tmp_path, '''
        from app.components import data_status, stale_banner
        stale_banner(data_status())
    ''')
    assert not at.exception, at.exception
    markup = "\n".join(m.value for m in at.markdown)
    assert "<strong>Error</strong>" in markup
    assert "30 Sep 2026" in markup
    # a stage name comes from a JSON file, so it is escaped rather than trusted
    assert "<script>" not in markup
    assert "&lt;script&gt;" in markup
