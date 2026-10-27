"""Transaction cost model (SIG-005, formula 6.6).

cost_leg = notional * (fee + brokerage + statutory + slippage) / 10000
Applied on entry and exit for both legs; round trip = 2 * (cost_leg_A + cost_leg_B).
"""
import pandas as pd

from src.utils.config import load_config

COST_COMPONENTS = ["exchange_fee", "brokerage", "statutory", "slippage"]


def scenario_costs(scenario: str) -> dict:
    cfg = load_config()
    return cfg["costs"]["scenarios"][scenario]


def leg_cost(notional: float, scenario: str) -> dict:
    """Per-leg cost broken down by component."""
    c = scenario_costs(scenario)
    total_bps = sum(float(c[f"{k}_bps"]) for k in COST_COMPONENTS)
    break_down = {k: notional * float(c[f"{k}_bps"]) / 10000.0 for k in COST_COMPONENTS}
    break_down["total"] = notional * total_bps / 10000.0
    return break_down


def round_trip_cost(notional_a: float, notional_b: float, scenario: str) -> dict:
    """2x entry/exit cost for both legs, with each component reported."""
    a = leg_cost(notional_a, scenario)
    b = leg_cost(notional_b, scenario)
    out = {}
    for k in [*COST_COMPONENTS, "total"]:
        out[f"cost_{k}"] = 2 * (a[k] + b[k])
    return out


def scenario_names() -> list[str]:
    return list(load_config()["costs"]["scenarios"].keys())


def cost_bps_total(scenario: str) -> float:
    c = scenario_costs(scenario)
    return sum(float(v) for v in c.values())
