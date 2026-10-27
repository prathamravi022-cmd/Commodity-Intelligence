"""DATAIO-001: the run a page reports, and how old the data really is.

Two silent failure modes are pinned here.

*Run selection.* ``last_pipeline_run()`` used to take the alphabetically last
directory under ``data/results``. Today's run ids happen to sort chronologically
(``20261026T055031Z_2432bb86``), so the bug was latent — but nothing in the
contract said so, and a stray folder or a different naming scheme would have
silently dated the whole dashboard from the wrong run. The newest *timestamp*
wins now, with a run record as the authority and file mtime as the fallback.

*Freshness.* ``is_stale()`` counts weekdays, not calendar days, so Friday data
is current on Monday. Every boundary the old calendar arithmetic got wrong is
enumerated below, with the clock injected instead of waiting for a weekend.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd
import pytest

from app import dataio


def _run(results: Path, name: str, started_utc: str | None = None,
         mtime: float | None = None, record: str = "run.json") -> Path:
    run_dir = results / name
    run_dir.mkdir(parents=True, exist_ok=True)
    if started_utc is not None:
        payload = {"run_id": name, "started_utc": started_utc}
        (run_dir / record).write_text(json.dumps(payload), encoding="utf-8")
    if mtime is not None:
        os.utime(run_dir, (mtime, mtime))
    return run_dir


@pytest.fixture
def results(tmp_path, monkeypatch):
    """Point ``app.dataio`` at an empty results tree and drop its caches."""
    data = tmp_path / "data"
    (data / "results").mkdir(parents=True)
    monkeypatch.setattr(dataio, "DATA", data)
    # every cached reader, not just the run metadata: a reader that caches an
    # empty frame for this temporary DATA would leak into the next test
    _CACHED = (dataio.load_normalized, dataio.load_signals, dataio.load_rejections,
               dataio.load_clean, dataio.last_pipeline_run,
               dataio.latest_backtest_run, dataio.last_pipeline_failure)
    for cached in _CACHED:
        cached.clear()
    yield data / "results"
    for cached in _CACHED:
        cached.clear()


# ---- Run selection ------------------------------------------------------
def test_newest_run_is_chosen_by_time_not_by_name(results):
    # The reported example: alphabetical order says run_10, time says run_2.
    _run(results, "run_2", "2026-10-26T09:00:00+00:00")
    _run(results, "run_10", "2026-10-20T09:00:00+00:00")
    stamp = dataio.last_pipeline_run()
    assert stamp == pd.Timestamp("2026-10-26 09:00:00")


def test_run_record_beats_the_directory_timestamp(results):
    # touch can change mtime; the run record is the authoritative start.
    _run(results, "20261101T000000Z_aaaaaaaa", "2026-11-01T00:00:00+00:00",
         mtime=1_000_000_000)
    _run(results, "20261001T000000Z_bbbbbbbb", "2026-10-01T00:00:00+00:00",
         mtime=2_000_000_000)
    assert dataio.last_pipeline_run() == pd.Timestamp("2026-11-01 00:00:00")


def test_pipeline_record_wins_over_the_backtest_record(results):
    # The label says *pipeline* run; the backtest starts seconds later.
    run_dir = results / "20261026T060000Z_cccccccc"
    run_dir.mkdir()
    (run_dir / "run.json").write_text(
        json.dumps({"started_utc": "2026-10-26T06:00:09+00:00"}), encoding="utf-8")
    (run_dir / "pipeline.json").write_text(
        json.dumps({"started_utc": "2026-10-26T06:00:00+00:00"}), encoding="utf-8")
    assert dataio.last_pipeline_run() == pd.Timestamp("2026-10-26 06:00:00")


def test_corrupt_record_falls_back_to_the_directory_timestamp(results):
    run_dir = results / "20261026T060000Z_dddddddd"
    run_dir.mkdir()
    (run_dir / "run.json").write_text("{not json", encoding="utf-8")
    os.utime(run_dir, (1_700_000_000, 1_700_000_000))
    assert dataio.last_pipeline_run() == pd.Timestamp(1_700_000_000, unit="s")


def test_tz_aware_start_times_are_reported_as_naive_utc(results):
    _run(results, "20261026T060000Z_eeeeeeee", "2026-10-26T11:30:00+05:30")
    assert dataio.last_pipeline_run() == pd.Timestamp("2026-10-26 06:00:00")


def test_a_directory_without_a_run_record_is_not_a_run(results):
    _run(results, "20261026T060000Z_ffffffff", "2026-10-26T06:00:00+00:00")
    stray = results / ".ipynb_checkpoints"
    stray.mkdir()
    os.utime(stray, (2_000_000_000, 2_000_000_000))
    assert dataio.last_pipeline_run() == pd.Timestamp("2026-10-26 06:00:00")


def test_empty_results_directory_means_never_run(results):
    assert dataio.last_pipeline_run() is None
    assert dataio.latest_backtest_run() is None


def test_missing_results_directory_means_never_run(tmp_path, monkeypatch):
    monkeypatch.setattr(dataio, "DATA", tmp_path / "nowhere")
    dataio.last_pipeline_run.clear()
    assert dataio.last_pipeline_run() is None
    assert dataio.latest_backtest_run() is None


def test_latest_backtest_run_loads_the_newest_artifacts(results):
    old = _run(results, "20261001T000000Z_11111111", "2026-10-01T00:00:00+00:00")
    new = _run(results, "20261020T000000Z_22222222", "2026-10-20T00:00:00+00:00")
    for run_dir, value in ((old, 1), (new, 2)):
        (run_dir / "trades.csv").write_text(f"net_pnl\n{value}\n", encoding="utf-8")
        (run_dir / "metrics.json").write_text(json.dumps({"value": value}),
                                             encoding="utf-8")
    latest = dataio.latest_backtest_run()
    assert latest is not None
    assert latest["run_id"] == new.name
    assert latest["trades"]["net_pnl"].iloc[0] == 2
    assert latest["metrics"]["value"] == 2


# ---- Freshness ----------------------------------------------------------
@pytest.mark.parametrize("data_date, today, stale", [
    # Friday data is current on the following Monday: the weekend is not a gap.
    ("2026-10-23", "2026-10-26", False),
    # Two trading days without a new file is stale.
    ("2026-10-22", "2026-10-26", True),
    # Weekend today: nothing has traded since Friday, so still current.
    ("2026-10-23", "2026-10-25", False),
    # Monday + Tuesday without data.
    ("2026-10-23", "2026-10-27", True),
    # Same day is current; a future-dated file is an ERROR in the six-state
    # model (a session that has not happened cannot be trusted), so it is
    # asserted by state in tests/test_freshness.py instead of here.
    ("2026-10-23", "2026-10-23", False),
    # Month-end and year-end rollovers.
    ("2026-09-30", "2026-10-05", True),
    ("2025-12-31", "2026-01-05", True),
    # Leap day.
    ("2028-02-29", "2028-03-02", True),
])
def test_is_stale_counts_trading_days(monkeypatch, data_date, today, stale):
    monkeypatch.setattr(dataio, "as_of", lambda: pd.Timestamp(data_date))
    monkeypatch.setattr(dataio, "_today", lambda: pd.Timestamp(today))
    assert dataio.is_stale() is stale


def test_is_stale_handles_a_tz_aware_data_date(monkeypatch):
    monkeypatch.setattr(dataio, "as_of",
                        lambda: pd.Timestamp("2026-10-23", tz="Asia/Kolkata"))
    monkeypatch.setattr(dataio, "_today", lambda: pd.Timestamp("2026-10-26"))
    assert dataio.is_stale() is False


def test_is_stale_with_no_data(monkeypatch):
    monkeypatch.setattr(dataio, "as_of", lambda: None)
    monkeypatch.setattr(dataio, "_today", lambda: pd.Timestamp("2026-10-26"))
    assert dataio.is_stale() is True


# ---- Failed attempts ----------------------------------------------------
def _failure(results: Path, **payload) -> Path:
    path = results / dataio.FAILURE_NAME
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_failure_record_is_read_from_the_results_directory(results):
    _failure(results, failed_utc="2026-10-26T07:00:00+00:00",
             stage="validation", error_type="ValidationError",
             reason="no_raw_files")
    dataio.last_pipeline_failure.clear()
    record = dataio.last_pipeline_failure()
    assert record is not None
    assert record["stage"] == "validation"
    assert record["reason"] == "no_raw_files"


def test_missing_or_corrupt_failure_record_is_none(results):
    assert dataio.last_pipeline_failure() is None
    (results / dataio.FAILURE_NAME).write_text("nope", encoding="utf-8")
    dataio.last_pipeline_failure.clear()
    assert dataio.last_pipeline_failure() is None


def test_failure_outranks_only_when_it_is_newer_than_the_last_run():
    run = pd.Timestamp("2026-10-26 09:00:00")
    newer = {"failed_utc": "2026-10-26T10:00:00+00:00"}
    older = {"failed_utc": "2026-10-26T08:00:00+00:00"}
    assert dataio.failure_outranks(newer, run) is True
    assert dataio.failure_outranks(older, run) is False
    assert dataio.failure_outranks(None, run) is False
    # a failure we cannot date still counts: it was written after a stage raised
    assert dataio.failure_outranks({"stage": "validation"}, run) is True
    assert dataio.failure_outranks({"failed_utc": "not-a-date"}, run) is True
    assert dataio.failure_outranks(newer, None) is True
