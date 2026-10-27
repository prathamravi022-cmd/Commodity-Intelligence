"""Pairwise normalized spreads (FR-5, RV-001)."""
from pathlib import Path
from itertools import combinations

import pandas as pd

from src.utils.logging_config import get_logger

logger = get_logger("analytics.spreads")


def pair_label(symbol_a: str, expiry_a, symbol_b: str, expiry_b) -> str:
    exp_a = getattr(expiry_a, "strftime", lambda f: expiry_a)("%Y-%m-%d")
    exp_b = getattr(expiry_b, "strftime", lambda f: expiry_b)("%Y-%m-%d")
    return f"{symbol_a}@{exp_a} vs {symbol_b}@{exp_b}"


def build_spreads(normalized: pd.DataFrame,
                  out_parquet: Path | None = None) -> pd.DataFrame:
    """spread = normalized A - normalized B; only same-date pairs (RV-001)."""
    out_parquet = out_parquet or (Path(__file__).resolve().parents[2]
                                  / "data" / "analytics" / "spreads.parquet")
    out_parquet.parent.mkdir(parents=True, exist_ok=True)
    df = normalized.copy()
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    rows = []
    grouped = df.groupby("trade_date")
    for trade_date, day in grouped:
        syms = day.drop_duplicates("symbol")
        for a, b in combinations(syms.itertuples(index=False), 2):
            spread = a.inr_per_g_fine - b.inr_per_g_fine
            base = max(a.inr_per_g_fine, b.inr_per_g_fine)
            rows.append({
                "trade_date": trade_date,
                "leg_a": f"{a.symbol}@{a.expiry_date.date().isoformat()}",
                "leg_b": f"{b.symbol}@{b.expiry_date.date().isoformat()}",
                "symbol_a": a.symbol,
                "symbol_b": b.symbol,
                "spread_inr_g": spread,
                "spread_pct": spread / base * 100.0,
                "price_a": a.inr_per_g_fine,
                "price_b": b.inr_per_g_fine,
                "dte_a": a.days_to_expiry,
                "dte_b": b.days_to_expiry,
                "volume_a": a.volume,
                "volume_b": b.volume,
                "oi_a": a.open_interest,
                "oi_b": b.open_interest,
            })
    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.sort_values(["trade_date", "leg_a", "leg_b"]).reset_index(drop=True)
    out.to_parquet(out_parquet, index=False)
    logger.info("spreads: %d rows -> %s", len(out), out_parquet.name)
    return out
