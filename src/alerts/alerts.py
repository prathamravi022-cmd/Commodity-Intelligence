"""Alerts (ALT-001, ALT-002): quiet-by-default, threshold crossing only."""
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from src.utils.config import config_hash, load_config
from src.utils.logging_config import get_logger

logger = get_logger("alerts")


def cross_events(df: pd.DataFrame, entry_z: float) -> pd.DataFrame:
    """Alert fires only when |z| crosses entry threshold from below."""
    out = []
    df = df.sort_values("trade_date")
    prev = None
    for row in df.itertuples(index=False):
        if row.z_score is None or pd.isna(row.z_score):
            prev = None
            continue
        az = abs(row.z_score)
        if prev is not None and prev < entry_z and az >= entry_z:
            out.append(row)
        prev = az
    return pd.DataFrame(out)


def generate_alerts(signals_parquet: Path | None = None,
                    out_path: Path | None = None) -> pd.DataFrame:
    cfg = load_config()
    if not cfg["alerts"]["enabled"]:
        logger.info("alerts disabled by config")
        return pd.DataFrame()
    chash = config_hash(cfg)
    entry_z = float(cfg["signal"]["entry_z"])
    cooldown = int(cfg["alerts"]["cooldown_days"])
    alerts = []
    cross = cross_events(
        pd.read_parquet(signals_parquet or (Path(__file__).resolve().parents[2]
                                            / "data" / "analytics" / "signals.parquet")),
        entry_z)
    last_alert: dict[tuple, int] = {}
    for row in cross.itertuples(index=False):
        key = (row.leg_a, row.leg_b)
        day = pd.Timestamp(row.trade_date).value // 86400000000000  # days epoch
        if key in last_alert and day - last_alert[key] < cooldown:
            continue
        last_alert[key] = day
        alerts.append({
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "trade_date": row.trade_date,
            "pair": f"{row.leg_a} vs {row.leg_b}",
            "leg_a": row.leg_a,
            "leg_b": row.leg_b,
            "z_score": float(row.z_score),
            "threshold": entry_z,
            "config_hash": chash,
        })
    out_path = out_path or (Path(__file__).resolve().parents[2]
                            / "data" / "alerts.json")
    out_path.write_text(json.dumps(alerts, indent=2, default=str), encoding="utf-8")
    logger.info("alerts generated: %d (cooldown %d days)", len(alerts), cooldown)
    return pd.DataFrame(alerts)
