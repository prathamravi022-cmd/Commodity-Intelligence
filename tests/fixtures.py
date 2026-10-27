"""Generate a synthetic MCX bhavcopy fixture covering ~1.5 years of trading days.

Columns/quirks mimic real MCX responses: response Date MM/DD/YYYY,
ExpiryDate compact (e.g., 04SEP2026), DD/MM/YYYY request dates in filename.
"""
from datetime import date, timedelta
from pathlib import Path
import calendar

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"

CONTRACTS = {
    # symbol: (quoted_unit_g, purity, base_price_per_quoted_unit)
    "GOLDM": (10, 0.995, 7300.0),
    "GOLDTEN": (10, 0.999, 7310.0),
    "GOLDGUINEA": (8, 0.999, 5880.0),
    "GOLDPETAL": (1, 0.999, 735.0),
}


def month_expiry(year: int, month: int, symbol: str) -> date:
    """Fixed long-dated expiry per symbol so each (symbol, expiry) contract has
    the full fixture history (needed for a 60-day rolling window)."""
    fixed = {
        "GOLDM": (5, 5, 2026),        # 5 May 2026 (3rd-5th window)
        "GOLDTEN": (28, 4, 2026),
        "GOLDGUINEA": (29, 4, 2026),
        "GOLDPETAL": (30, 4, 2026),
    }
    d, m, y = fixed[symbol]
    return date(y, m, d)


def generate(days: int = 380, end_day: date | None = None, seed: int = 42) -> list[Path]:
    rng = np.random.default_rng(seed)
    RAW.mkdir(parents=True, exist_ok=True)
    end_day = end_day or date(2026, 9, 30)
    d = end_day - timedelta(days=days)
    files = []
    spread_drift = 0.0
    while d <= end_day:
        if d.weekday() >= 5:
            d += timedelta(days=1)
            continue
        rows = []
        base_fine = 7280.0 + 3.0 * (np.sin(d.timetuple().tm_yday / 47) + rng.normal(0, 1) * .4)
        spread_drift = 0.9 * spread_drift + rng.normal(0, .35)
        spike = 6.5 * (rng.random() < .01)  # occasional mispricing episode
        for sym, (q, purity, bp) in CONTRACTS.items():
            if sym == "GOLDTEN" and d < date(2025, 1, 1):
                continue  # GOLDTEN data exists only from 2025
            # normalized fine-gold price with spread noise
            fine = (base_fine + spread_drift * ({"GOLDM": 0, "GOLDTEN": 1.6,
                                                 "GOLDGUINEA": -1.1, "GOLDPETAL": 1.0}[sym])
                    + spike * (2.0 if sym in ("GOLDPETAL", "GOLDGUINEA") else -2.0)
                    + rng.normal(0, .8))
            close = fine * purity * q
            o = close + rng.normal(0, close * .001)
            h = max(close, o) + abs(rng.normal(0, close * .0015))
            lo = min(close, o) - abs(rng.normal(0, close * .0015))
            y, m = d.year, d.month + (1 if sym == "GOLDM" else 0)
            if m > 12:
                m, y = 1, y + 1
            exp = month_expiry(y, m, sym)
            rows.append({
                "Symbol": sym,
                "Date": d.strftime("%m/%d/%Y"),
                "ExpiryDate": exp.strftime("%d%b%Y").upper(),
                "Open": round(o, 2),
                "High": round(h, 2),
                "Low": round(lo, 2),
                "Close": round(close, 2),
                "Volume": int(rng.integers(500, 20000)),
                "OpenInterest": int(rng.integers(2000, 80000)),
            })
        fname = RAW / f"{d.isoformat()}.csv"
        pd.DataFrame(rows).to_csv(fname, index=False)
        files.append(fname)
        d += timedelta(days=1)
    return files


if __name__ == "__main__":
    fs = generate()
    print(f"wrote {len(fs)} fixture files to data/raw")
