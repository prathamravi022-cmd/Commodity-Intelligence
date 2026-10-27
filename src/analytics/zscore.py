"""Rolling z-score signal - window excludes current day (SIG-001, formula 6.3).

z_t = (spread_t - mean(spread_{t-W ..t-1})) / std(spread_{t-W ..t-1})
The window uses only past data, so no look-ahead.
"""
from pathlib import Path

import numpy as np
import pandas as pd

from src.utils.config import load_config
from src.utils.logging_config import get_logger

logger = get_logger("analytics.zscore")


def rolling_zscores(spreads: pd.Series, window: int) -> pd.Series:
    """Vectorized no-look-ahead z-score. NaN until window periods of history."""
    past = spreads.shift(1)
    roll_mean = past.rolling(window, min_periods=window).mean()
    roll_std = past.rolling(window, min_periods=window).std(ddof=1)
    return (spreads - roll_mean) / roll_std.replace(0.0, np.nan)


def signal_state(z: float | None, entry_z: float, watch_z: float) -> str:
    """Signal state machine (formula 6.5)."""
    if z is None or pd.isna(z):
        return "Unvalidated"
    az = abs(z)
    if az >= entry_z:
        return "Signal"
    if az >= watch_z:
        return "Watch"
    return "Neutral"


def build_signals(spreads: pd.DataFrame,
                  out_path: Path | None = None) -> pd.DataFrame:
    """Attach rolling z-scores and signal states per pair."""
    cfg = load_config()
    sig = cfg["signal"]
    window = int(sig["window_days"])
    entry_z = float(sig["entry_z"])
    watch_z = float(sig["watch_z"])
    out_path = out_path or (Path(__file__).resolve().parents[2]
                            / "data" / "analytics" / "signals.parquet")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out = spreads.copy()
    out["z_score"] = np.nan
    out["signal_state"] = "Unvalidated"
    for pair, idx in out.groupby(["leg_a", "leg_b"], sort=False).indices.items():
        sub = out.loc[idx].sort_values("trade_date")
        z = rolling_zscores(sub["residual_after_carry"], window)
        states = z.map(lambda v: signal_state(v, entry_z, watch_z))
        out.loc[sub.index, "z_score"] = z.to_numpy()
        out.loc[sub.index, "signal_state"] = states.to_numpy()
    out = out.sort_values(["trade_date", "leg_a", "leg_b"]).reset_index(drop=True)
    out.to_parquet(out_path, index=False)
    logger.info("signals: %d rows -> %s", len(out), out_path.name)
    return out
