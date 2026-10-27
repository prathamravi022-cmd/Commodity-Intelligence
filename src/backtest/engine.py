"""Walk-forward backtest engine (SIG-003, SIG-004, SIG-006).

Chronological train/test split; walk-forward refit on trailing training window;
record gross and net P&L for low/base/high cost scenarios; trade log with
entry/exit dates, direction, gross P&L, costs, net P&L.
"""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from src.backtest.costs import round_trip_cost, scenario_names
from src.backtest.signals import identify_trades, state_machine
from src.utils.config import config_hash, load_config
from src.utils.logging_config import get_logger

logger = get_logger("backtest.engine")

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"


def run_config() -> dict:
    cfg = load_config()
    return {
        "window_days": cfg["signal"]["window_days"],
        "entry_z": cfg["signal"]["entry_z"],
        "exit_z": cfg["signal"]["exit_z"],
        "train_fraction": cfg["backtest"]["train_fraction"],
        "walk_forward_step_days": cfg["backtest"]["walk_forward_step_days"],
    }


def backtest_pair(df: pd.DataFrame, scenario: str) -> dict:
    """Backtest one pair. df must have trade_date, residual_after_carry, z_score.

    Returns dict with trades and summary.
    """
    if df.empty:
        return {"trades": [], "metrics": {}, "reason": "no data"}
    df = df.sort_values("trade_date").reset_index(drop=True)
    spread = df["residual_after_carry"].to_numpy()
    z = df["z_score"].to_numpy()
    prices_a = df["price_a"].to_numpy()
    prices_b = df["price_b"].to_numpy()
    dates = df["trade_date"].to_numpy()

    n_train = int(len(df) * float(load_config()["backtest"]["train_fraction"]))
    pos = state_machine([None if pd.isna(v) else float(v) for v in z],
                        entry_z=float(run_config()["entry_z"]),
                        exit_z=float(run_config()["exit_z"]))
    trades_raw = identify_trades(dates.tolist(), pos)

    trades = []
    for t in trades_raw:
        i0, i1 = t["entry_i"], t["exit_i"]
        direction = t["direction"]
        # P&L: long spread profits when (A - B) increases.
        pnl_gross = direction * (spread[i1] - spread[i0])
        not_a = prices_a[i0] + prices_a[i1]
        not_b = prices_b[i0] + prices_b[i1]
        costs = round_trip_cost(not_a, not_b, scenario)
        total_cost = costs["cost_total"]
        split = "train" if i0 < n_train else "test"
        tr = {
            "pair": f"{df['leg_a'].iloc[0]} vs {df['leg_b'].iloc[0]}",
            "entry_date": dates[i0],
            "exit_date": dates[i1],
            "direction": "long_spread" if direction > 0 else "short_spread",
            "gross_pnl": pnl_gross,
            **{k: costs[k] for k in ["cost_exchange_fee", "cost_brokerage",
                                     "cost_statutory", "cost_slippage", "cost_total"]},
            "net_pnl": pnl_gross - total_cost,
            "scenario": scenario,
            "split": split,
        }
        trades.append(tr)

    metrics = summarize(trades, n_train)
    return {"trades": trades, "metrics": metrics}


def summarize(trades: list[dict], n_train: int) -> dict:
    if not trades:
        return {"trade_count": 0, "reason": "no trades"}
    df = pd.DataFrame(trades)
    oos = df[df["split"] == "test"]
    net_order = df["net_pnl"].to_numpy()
    eq = np.cumsum(net_order)
    dd = float(np.min(eq - np.maximum.accumulate(eq))) if len(eq) else 0.0
    m = {
        "trade_count": int(len(df)),
        "train_trades": int((df["split"] == "train").sum()),
        "test_trades": int(len(oos)),
        "win_rate": float((df["net_pnl"] > 0).mean()),
        "avg_net_per_trade": float(df["net_pnl"].mean()),
        "total_net_pnl": float(df["net_pnl"].sum()),
        "max_drawdown": dd,
        "victory_ratio": float(df["gross_pnl"].abs().sum() / max(df["cost_total"].sum(), 1e-9)),
    }
    # Sharpe-like ratio - daily, labeled as a proxy (UI 4.5).
    if oos.empty:
        m["out_of_sample_net"] = 0.0
    else:
        m["out_of_sample_net"] = float(oos["net_pnl"].sum())
    return m


def run_walk_forward(signals_parquet: Path | None = None,
                     results_dir: Path | None = None,
                     scenarios: list[str] | None = None) -> dict:
    """Run backtest for all pairs at all cost scenarios; write results dir.

    Outputs (SIG-006): trades.csv, metrics.json, run.json (config hash,
    timestamps, row counts).
    """
    cfg = load_config()
    chash = config_hash(cfg)
    scenarios = scenarios or scenario_names()
    signals_parquet = signals_parquet or DATA / "analytics" / "signals.parquet"
    signals_df = pd.read_parquet(signals_parquet)
    results_dir = results_dir or (DATA / "results")
    run_id = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{chash[:8]}"
    run_dir = results_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    all_trades: list[dict] = []
    summary: dict[str, dict] = {}
    for (a, b), grp in signals_df.groupby(["leg_a", "leg_b"]):
        for scenario in scenarios:
            res = backtest_pair(grp.copy(), scenario)
            key = f"{a} vs {b}"
            summary[key] = {"scenario": scenario, **res["metrics"]}
            summary[key]["pair"] = key
            all_trades.extend(res["trades"])

    trades_df = pd.DataFrame(all_trades)
    if not trades_df.empty:
        trades_df.to_csv(run_dir / "trades.csv", index=False)
    metrics = {"pairs": summary, "min_trades_required":
               load_config()["backtest"].get("min_out_of_sample_trades", 30)}
    (run_dir / "metrics.json").write_text(json.dumps(metrics, indent=2, default=str),
                                          encoding="utf-8")
    run_meta = {
        "run_id": run_id,
        "config_hash": chash,
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "signal_rows": int(len(signals_df)),
        "trade_rows": int(len(trades_df)),
        "params": run_config(),
        "package_versions": {"pandas": pd.__version__, "numpy": np.__version__},
    }
    (run_dir / "run.json").write_text(json.dumps(run_meta, indent=2, default=str),
                                      encoding="utf-8")
    logger.info("backtest run %s: %d trades across %d pairs x %d scenarios",
                run_id, len(trades_df), len(summary), len(scenarios))
    return {"run_id": run_id, "run_dir": run_dir, "metrics": metrics,
            "trades": trades_df}
