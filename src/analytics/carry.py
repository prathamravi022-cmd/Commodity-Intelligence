"""Simple carry adjustment (FR-6, RV-003, technical architecture 6.4).

carry_adj_t = spread_t - r * (dte_A - dte_B) / 365 * price_B
residual_t = carry_adj_t
"""
import pandas as pd

from src.utils.config import load_config


def carry_adjusted_spread(spread: float, dte_a: int, dte_b: int,
                          price_b: float, annual_carry_rate: float) -> float:
    """First-approximation carry adjustment. Document r via config."""
    return spread - annual_carry_rate * (dte_a - dte_b) / 365.0 * price_b


def add_carry(spreads: pd.DataFrame) -> pd.DataFrame:
    cfg = load_config()
    rate = float(cfg.get("carry", {}).get("annual_carry_rate", 0.0))
    method = cfg.get("carry", {}).get("method", "simple")
    out = spreads.copy()
    if rate == 0.0:
        out["residual_after_carry"] = out["spread_inr_g"]
    else:
        out["residual_after_carry"] = [
            carry_adjusted_spread(s, int(a), int(b), p, rate)
            for s, a, b, p in zip(out["spread_inr_g"], out["dte_a"],
                                  out["dte_b"], out["price_b"])
        ]
    out["carry_method"] = method
    out["carry_rate"] = rate
    return out
