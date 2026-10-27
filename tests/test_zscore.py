"""SIG-001 unit tests: z-score correctness, scale invariance, and no look-ahead."""
import numpy as np
import pandas as pd

from src.analytics.zscore import rolling_zscores, signal_state


def test_known_series():
    spread = pd.Series([10.0] * 65 + [13.0])
    z = rolling_zscores(spread, window=60)
    # Constant history -> std=0 -> NaN
    assert pd.isna(z.iloc[65])


def test_zscore_uses_only_past_data():
    rng = np.random.default_rng(7)
    s = pd.Series(rng.normal(0, 1, 120))
    z = rolling_zscores(s, window=20)
    # Recompute manually at index 100 using values up to 99
    past = s.iloc[80:100]
    expected = (s.iloc[100] - past.mean()) / past.std(ddof=1)
    assert abs(z.iloc[100] - expected) < 1e-9


def test_early_values_nan():
    s = pd.Series(np.arange(30, dtype=float))
    z = rolling_zscores(s, window=10)
    assert z.iloc[:10].isna().all()
    assert z.iloc[11:].notna().all()


def test_signal_states():
    entry, watch = 2.0, 1.5
    assert signal_state(None, entry, watch) == "Unvalidated"
    assert signal_state(float("nan"), entry, watch) == "Unvalidated"
    assert signal_state(2.1, entry, watch) == "Signal"
    assert signal_state(-1.7, entry, watch) == "Watch"
    assert signal_state(0.4, entry, watch) == "Neutral"


def test_scale_invariance():
    rng = np.random.default_rng(3)
    s = pd.Series(rng.normal(100, 5, 100))
    z1 = rolling_zscores(s, 20)
    z2 = rolling_zscores(s * 3 + 7, 20)
    np.testing.assert_allclose(z1.dropna().to_numpy(),
                               z2.dropna().to_numpy(), rtol=1e-9)
