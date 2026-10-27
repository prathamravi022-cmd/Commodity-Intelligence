"""Performance attribution (FR-12, SIG-008): gross -> costs -> net per pair."""
from pathlib import Path

import pandas as pd


def waterfall_rows(trades_df: pd.DataFrame) -> list[dict]:
    """One waterfall per pair for the given trade set (single scenario input)."""
    rows = []
    grosssum = trades_df["gross_pnl"].sum()
    fees = trades_df["cost_exchange_fee"].sum()
    broker = trades_df["cost_brokerage"].sum()
    stat = trades_df["cost_statutory"].sum()
    slip = trades_df["cost_slippage"].sum()
    net = trades_df["net_pnl"].sum()
    rows.append({"stage": "gross_pnl", "value": float(grosssum)})
    rows.append({"stage": "exchange_fee", "value": float(-fees)})
    rows.append({"stage": "brokerage", "value": float(-broker)})
    rows.append({"stage": "statutory", "value": float(-stat)})
    rows.append({"stage": "slippage", "value": float(-slip)})
    rows.append({"stage": "net_pnl", "value": float(net)})
    return rows


def per_pair_rows(trades_df: pd.DataFrame) -> pd.DataFrame:
    g = trades_df.groupby("pair").agg(
        trades=("pair", "size"),
        gross_pnl=("gross_pnl", "sum"),
        costs=("cost_total", "sum"),
        net_pnl=("net_pnl", "sum"),
    ).reset_index()
    return g


def attribution(run_dir: Path, scenario: str = "base") -> dict:
    tf_path = run_dir / "trades.csv"
    if not tf_path.exists():
        return {"waterfall": [], "per_pair": pd.DataFrame()}
    df = pd.read_csv(tf_path)
    df = df[df["scenario"] == scenario]
    if df.empty:
        return {"waterfall": [], "per_pair": pd.DataFrame()}
    return {"waterfall": waterfall_rows(df), "per_pair": per_pair_rows(df),
            "reconciles": bool(abs(waterfall_rows(df)[-1]["value"]
                                   - df["net_pnl"].sum()) < 1e-6)}
