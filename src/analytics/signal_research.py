"""Signal research: episodes, dwell statistics, frequency and audit trail.

Covers roadmap features 41-50 (configurable thresholds, timeline, event detail,
annotations, frequency, time beyond thresholds, calculation audit) and 80
(sample-size warnings). Everything here is pure: it takes the stored z-series
and thresholds and returns frames, so the numbers can be tested without the
dashboard and cannot quietly diverge from what the chart draws.

No function looks ahead: the rolling statistics use the same
`shift(1)` convention as `src.analytics.zscore`.
"""
import numpy as np
import pandas as pd


def episodes(z: pd.Series, entry: float, exit_: float) -> pd.DataFrame:
    """Completed and open threshold episodes from a z-series.

    An episode opens on the first session with |z| >= entry and closes on the
    next session with |z| <= exit. A trailing open episode keeps exit = NaT.
    NaN z (not enough history) never opens or closes anything.
    """
    rows: list[dict] = []
    open_at = None
    open_z = None
    open_max = 0.0
    for day, value in z.items():
        if pd.isna(value):
            continue
        az = abs(float(value))
        if open_at is None:
            if az >= entry:
                open_at, open_z, open_max = day, float(value), az
            continue
        open_max = max(open_max, az)
        if az <= exit_:
            rows.append({"entry": open_at, "entry_z": open_z,
                         "exit": day, "exit_z": float(value),
                         "max_abs_z": open_max, "open": False})
            open_at = None
    if open_at is not None:
        rows.append({"entry": open_at, "entry_z": open_z, "exit": pd.NaT,
                     "exit_z": np.nan, "max_abs_z": open_max, "open": True})

    columns = ["entry", "entry_z", "exit", "exit_z", "max_abs_z", "open",
               "direction", "sessions"]
    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(columns=columns)
    df["direction"] = np.where(df["entry_z"] >= 0, "Short A / long B",
                               "Long A / short B")
    # Duration is elapsed sessions, so a gap of missing data still counts —
    # the position was held through it, it just could not be evaluated.
    index = z.index
    df["sessions"] = [
        int(index.get_loc(x) - index.get_loc(e) + 1) if pd.notna(x)
        else int(len(index) - index.get_loc(e))
        for e, x in zip(df["entry"], df["exit"])
    ]
    return df


def dwell_profile(z: pd.Series, watch: float, entry: float,
                  exit_: float) -> dict:
    """How often the spread sits in each zone, over valid sessions only."""
    valid = z.dropna()
    n = int(len(valid))
    if n == 0:
        return {"sessions": 0, "pct_watch": np.nan, "pct_entry": np.nan,
                "pct_exit_zone": np.nan, "median_abs_z": np.nan,
                "max_abs_z": np.nan}
    az = valid.abs()
    return {
        "sessions": n,
        "pct_watch": float((az >= watch).mean() * 100),
        "pct_entry": float((az >= entry).mean() * 100),
        "pct_exit_zone": float((az <= exit_).mean() * 100),
        "median_abs_z": float(az.median()),
        "max_abs_z": float(az.max()),
    }


def entry_frequency(ep: pd.DataFrame, freq: str = "Q") -> pd.DataFrame:
    """Episodes opened per calendar period (default quarter).

    Accepts either period or offset spellings ('Q'/'QE', 'M'/'ME').
    """
    if ep.empty:
        return pd.DataFrame(columns=["period", "entries", "closed", "mean_sessions"])
    freq = {"QE": "Q", "ME": "M", "YE": "Y"}.get(freq.upper(), freq.upper())
    work = ep.copy()
    work["period"] = pd.to_datetime(work["entry"]).dt.to_period(freq).astype(str)
    closed = work[~work["open"]]
    g = work.groupby("period").agg(
        entries=("entry", "size"),
        closed=("open", lambda s: int((~s).sum())),
        mean_sessions=("sessions", "mean"),
    ).reset_index()
    g["mean_sessions"] = g["mean_sessions"].round(1)
    return g.sort_values("period").reset_index(drop=True)


def audit_trail(spread: pd.Series, window: int, tail: int = 12) -> pd.DataFrame:
    """The inputs behind each z-value, for the last `tail` sessions.

    mean/std are computed over the `window` sessions *before* the row's own
    date, matching `rolling_zscores`; `n_used` shows how many observations
    actually entered the calculation.
    """
    past = spread.shift(1)
    mu = past.rolling(window, min_periods=window).mean()
    sd = past.rolling(window, min_periods=window).std(ddof=1)
    n_used = past.rolling(window, min_periods=1).count()
    z = (spread - mu) / sd.replace(0.0, np.nan)
    out = pd.DataFrame({"spread": spread, "window_mean": mu,
                        "window_std": sd, "n_used": n_used, "z": z})
    out.index.name = "trade_date"
    return out.tail(tail).reset_index()


def sample_warning(closed_episodes: int, minimum: int = 30) -> str | None:
    """Plain-language warning when there is too little evidence (feature 80)."""
    if closed_episodes >= minimum:
        return None
    return (f"Only {closed_episodes} closed episode(s): too few to describe a "
            f"reliable habit. Treat the frequency and duration figures as "
            f"description, not evidence — {minimum} is the config minimum.")


def oos_split(ep: pd.DataFrame, split_date) -> pd.DataFrame:
    """Tag episodes by whether they opened before or after the OOS boundary."""
    if ep.empty:
        return ep.assign(split=pd.Series(dtype=object))
    work = ep.copy()
    work["split"] = np.where(pd.to_datetime(work["entry"]) >= pd.Timestamp(split_date),
                             "test", "train")
    return work
