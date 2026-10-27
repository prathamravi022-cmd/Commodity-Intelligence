"""Signal research maths: episodes, dwell, frequency, audit trail (41-50, 80)."""
import numpy as np
import pandas as pd
import pytest

from src.analytics.signal_research import (audit_trail, dwell_profile,
                                           entry_frequency, episodes,
                                           oos_split, sample_warning)


def _series(values, start="2026-01-05"):
    idx = pd.bdate_range(start=start, periods=len(values))
    return pd.Series(values, index=idx, dtype="float64")


# ---- episodes (45/46/47) --------------------------------------------------

def test_episode_opens_above_entry_and_closes_inside_exit():
    z = _series([0.1, 0.4, 2.5, 1.9, 0.9, 0.4, -0.2])
    ep = episodes(z, entry=2.0, exit_=0.5)
    assert len(ep) == 1
    row = ep.iloc[0]
    assert row["entry_z"] == 2.5 and row["exit_z"] == 0.4
    assert bool(row["open"]) is False
    assert row["direction"] == "Short A / long B"
    # entry .. exit inclusive = 4 sessions
    assert row["sessions"] == 4
    assert row["max_abs_z"] == 2.5


def test_episode_direction_for_negative_z():
    z = _series([-2.4, -1.0, -0.2])
    ep = episodes(z, entry=2.0, exit_=0.5)
    assert ep.iloc[0]["direction"] == "Long A / short B"


def test_open_episode_is_kept_and_flagged():
    z = _series([0.1, 2.2, 1.6, 1.2])
    ep = episodes(z, entry=2.0, exit_=0.5)
    assert len(ep) == 1
    row = ep.iloc[0]
    assert bool(row["open"]) is True
    assert pd.isna(row["exit"])
    assert row["sessions"] == 3          # entry day through the last session


def test_nan_z_never_opens_or_closes():
    z = _series([np.nan, np.nan, 2.6, np.nan, 0.1])
    ep = episodes(z, entry=2.0, exit_=0.5)
    assert len(ep) == 1
    assert ep.iloc[0]["sessions"] == 3


def test_no_episodes_when_threshold_never_crossed():
    ep = episodes(_series([0.1, 0.2, -0.3]), entry=2.0, exit_=0.5)
    assert ep.empty
    assert isinstance(ep, pd.DataFrame)


# ---- dwell profile (49) ---------------------------------------------------

def test_dwell_profile_shares_are_of_valid_sessions_only():
    z = _series([np.nan, 0.2, 1.6, 2.2, -2.5, 0.1])
    prof = dwell_profile(z, watch=1.5, entry=2.0, exit_=0.5)
    assert prof["sessions"] == 5
    assert prof["pct_watch"] == pytest.approx(60.0)   # 1.6, 2.2, -2.5
    assert prof["pct_entry"] == pytest.approx(40.0)   # 2.2, -2.5
    assert prof["pct_exit_zone"] == pytest.approx(40.0)  # 0.2, 0.1
    assert prof["max_abs_z"] == pytest.approx(2.5)


def test_dwell_profile_on_empty_series():
    prof = dwell_profile(_series([np.nan]), watch=1.5, entry=2.0, exit_=0.5)
    assert prof["sessions"] == 0 and np.isnan(prof["pct_watch"])


# ---- frequency (48) -------------------------------------------------------

def test_frequency_counts_entries_per_quarter():
    z = _series([2.5, 0.1, 0.1, 0.1, 0.1, 2.4, 0.2, 2.6, 0.1])
    ep = episodes(z, entry=2.0, exit_=0.5)
    freq = entry_frequency(ep, "ME")
    assert freq["entries"].sum() == len(ep) == 3
    assert list(freq.columns) == ["period", "entries", "closed", "mean_sessions"]


def test_frequency_of_empty_episodes():
    freq = entry_frequency(pd.DataFrame(), "QE")
    assert freq.empty and "entries" in freq.columns


# ---- audit trail (50) -----------------------------------------------------

def test_audit_trail_mean_uses_prior_window_only():
    values = [10.0, 11.0, 12.0, 13.0]
    spread = _series(values)
    trail = audit_trail(spread, window=2, tail=4).set_index("trade_date")
    last = trail.iloc[-1]
    # window excludes the row's own value: mean(12, 13) is not used; it is mean(11, 12)
    assert last["window_mean"] == pytest.approx(11.5)
    assert last["n_used"] == 2
    assert last["z"] == pytest.approx((13.0 - 11.5) / np.std([11.0, 12.0], ddof=1))
    # the first row has no history, so the mean is NaN rather than zero-filled
    assert np.isnan(trail.iloc[0]["window_mean"])


def test_audit_trail_reports_how_many_inputs_were_used():
    trail = audit_trail(_series([1.0, 2.0, 3.0]), window=60, tail=3)
    assert list(trail["n_used"]) == [0, 1, 2]
    assert trail["z"].isna().all()      # min_periods=window not yet met


# ---- warnings and split (80) ----------------------------------------------

def test_sample_warning_is_silent_with_enough_episodes():
    assert sample_warning(30, minimum=30) is None
    assert sample_warning(40, minimum=30) is None


def test_sample_warning_names_the_count():
    msg = sample_warning(4, minimum=30)
    assert msg and "4" in msg and "30" in msg


def test_oos_split_tags_by_entry_date():
    z = _series([2.5, 0.1, 0.1, 2.5, 0.1, 0.1])
    ep = episodes(z, entry=2.0, exit_=0.5)
    split_date = ep.iloc[0]["entry"]
    tagged = oos_split(ep, split_date)
    assert set(tagged["split"]) <= {"train", "test"}
    assert tagged.iloc[0]["split"] == "test"
