"""SIG-005 unit tests: transaction cost model."""
from src.backtest.costs import cost_bps_total, leg_cost, round_trip_cost, scenario_names


def test_components_reported():
    c = leg_cost(100000.0, "base")
    # base: 2 + 3 + 2 + 5 = 12 bps
    assert abs(c["total"] - 100000.0 * 12 / 10000) < 1e-9
    assert abs(c["exchange_fee"] - 100000.0 * 2 / 10000) < 1e-9
    assert abs(c["slippage"] - 100000.0 * 5 / 10000) < 1e-9


def test_round_trip_is_twice_legs():
    c = round_trip_cost(100000.0, 50000.0, "base")
    leg_sum = leg_cost(100000.0, "base")["total"] + leg_cost(50000.0, "base")["total"]
    assert abs(c["cost_total"] - 2 * leg_sum) < 1e-9


def test_scenario_ordering():
    lows = cost_bps_total("low")
    base = cost_bps_total("base")
    high = cost_bps_total("high")
    assert lows < base < high


def test_three_scenarios_exist():
    assert scenario_names() == ["low", "base", "high"]
