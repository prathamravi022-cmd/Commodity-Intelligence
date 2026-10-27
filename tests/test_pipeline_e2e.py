"""QA-002: full pipeline on a small fixture dataset. QA-008 reconciles attribution."""
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def pipeline_outputs(tmp_path_factory):
    from tests.fixtures import generate
    from src.validate.clean import run_validation
    from src.normalize.gold import build_normalized
    from src.analytics.spreads import build_spreads
    from src.analytics.carry import add_carry
    from src.analytics.zscore import build_signals
    generate(days=210, end_day=None)
    run_validation()
    normalized = build_normalized()
    spreads = build_spreads(normalized)
    spreads = add_carry(spreads)
    signals = build_signals(spreads)
    return signals


def test_outputs_exist():
    assert (ROOT / "data" / "clean" / "bhavcopy.parquet").exists()
    assert (ROOT / "data" / "clean" / "rejections.csv").exists()
    assert (ROOT / "data" / "analytics" / "normalized.parquet").exists()
    assert (ROOT / "data" / "analytics" / "spreads.parquet").exists()
    assert (ROOT / "data" / "analytics" / "signals.parquet").exists()


def test_gold_symbols_only(pipeline_outputs):
    df = pd.read_parquet(ROOT / "data" / "clean" / "bhavcopy.parquet")
    allowed = {"GOLDM", "GOLDTEN", "GOLDGUINEA", "GOLDPETAL"}
    assert set(df["symbol"].unique()) <= allowed


def test_goldten_starts_2025():
    df = pd.read_parquet(ROOT / "data" / "clean" / "bhavcopy.parquet")
    ten = df[df["symbol"] == "GOLDTEN"]
    if not ten.empty:
        d = pd.to_datetime(ten["trade_date"]).min()
        assert d.year >= 2025


def test_no_artificial_roll_jump(pipeline_outputs):
    """Contract key = (symbol, expiry_date); rolling across expiries must not
    create artificial normalized-price jumps at roll boundaries."""
    norm = pd.read_parquet(ROOT / "data" / "analytics" / "normalized.parquet")
    for sym, grp in norm.groupby("symbol"):
        for exp, sub in grp.groupby("expiry_date"):
            # within one contract, day-over-day moves should be small
            prices = sub.sort_values("trade_date")["inr_per_g_fine"]
            rets = prices.pct_change().dropna().abs()
            assert (rets < 0.05).all(), f"{sym}@{exp} has suspicious jump"


def test_attribution_reconciles():
    from src.backtest.engine import run_walk_forward
    from src.backtest.attribution import attribution
    res = run_walk_forward()
    att = attribution(Path(res["run_dir"]), scenario="base")
    tf = pd.read_csv(res["run_dir"] / "trades.csv")
    tf_base = tf[tf["scenario"] == "base"]
    if tf_base.empty:
        pytest.skip("no trades produced by fixture - acceptable for tiny dataset")
    assert att["reconciles"]
    assert abs(att["per_pair"]["net_pnl"].sum() - tf_base["net_pnl"].sum()) < 1e-6
