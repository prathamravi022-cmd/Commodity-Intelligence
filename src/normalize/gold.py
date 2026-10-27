"""Normalize Close to fine-gold INR per gram (FR-4, NORM-001).

Formula (technical architecture 6.1): inr_per_g_fine = Close / quoted_unit_g / purity
Contracts keyed by (symbol, expiry_date) - no continuous near-month series (FR-3).
"""
from pathlib import Path

import numpy as np
import pandas as pd

from src.utils.config import load_config
from src.utils.logging_config import get_logger

logger = get_logger("normalize.gold")

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"


def normalize_close(close: float, quoted_unit_g: float, purity: float) -> float:
    """Convert a quoted close into fine-gold INR per gram."""
    if quoted_unit_g <= 0 or purity <= 0:
        raise ValueError("quoted_unit_g and purity must be positive")
    return close / quoted_unit_g / purity


def build_normalized(clean_parquet: Path | None = None,
                     out_parquet: Path | None = None) -> pd.DataFrame:
    """Emit normalized.parquet keyed by (symbol, expiry_date, trade_date)."""
    cfg = load_config()
    contracts = cfg["contracts"]
    clean_parquet = clean_parquet or DATA / "clean" / "bhavcopy.parquet"
    out_parquet = out_parquet or DATA / "analytics" / "normalized.parquet"
    out_parquet.parent.mkdir(parents=True, exist_ok=True)
    df = pd.read_parquet(clean_parquet)
    if df.empty:
        raise RuntimeError("bhavcopy.parquet is empty - run validation first")
    rows = []
    for _, r in df.iterrows():
        spec = contracts.get(r["symbol"])
        if spec is None:
            logger.error("unknown symbol %s (missing purity/unit in config): stopping", r["symbol"])
            raise RuntimeError(f"Missing config for symbol {r['symbol']}")
        fine = normalize_close(float(r["close"]), spec["quoted_unit_g"], spec["purity"])
        rows.append({
            "symbol": r["symbol"],
            "expiry_date": r["expiry_date"],
            "trade_date": r["trade_date"],
            "close_raw": r["close"],
            "inr_per_g_fine": fine,
            "volume": r["volume"],
            "open_interest": r["open_interest"],
        })
    out = pd.DataFrame(rows)
    out["trade_date"] = pd.to_datetime(out["trade_date"])
    out["expiry_date"] = pd.to_datetime(out["expiry_date"])
    out["days_to_expiry"] = (out["expiry_date"] - out["trade_date"]).dt.days
    def win(sym: str) -> str:
        lo, hi = contracts[sym]["expiry_window"]
        return f"{lo}-{hi}"
    out["expiry_window"] = out["symbol"].map(win)
    out = out.sort_values(["symbol", "expiry_date", "trade_date"]).drop_duplicates(
        subset=["symbol", "expiry_date", "trade_date"], keep="last")
    out.to_parquet(out_parquet, index=False)
    logger.info("normalized %d rows -> %s", len(out), out_parquet.name)
    return out
