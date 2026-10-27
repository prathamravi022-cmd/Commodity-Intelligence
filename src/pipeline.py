"""Pipeline stages 1-5 end to end (technical architecture diagram).

One command rebuilds all outputs from raw files:
    python -m src.pipeline
Each stage reads files from the previous stage and writes files for the next.
"""
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from src.alerts.alerts import generate_alerts
from src.analytics.carry import add_carry
from src.analytics.spreads import build_spreads
from src.analytics.zscore import build_signals
from src.backtest.engine import run_walk_forward
from src.ingest.manifest import update_manifest
from src.normalize.gold import build_normalized
from src.utils.config import config_hash, load_config
from src.utils.logging_config import get_logger
from src.validate.clean import ValidationError, run_validation

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

#: Name of the failed-attempt record written next to the run directories. It is
#: a file, so the dashboard's run scanner (which only looks at directories with a
#: run record) can never mistake it for a run. ``app/dataio.py`` reads this name.
FAILURE_NAME = "_last_failure.json"

logger = get_logger("pipeline", log_dir=DATA)


def _record_failure(stage: str, exc: BaseException) -> dict:
    """Record a failed attempt, then let the caller re-raise.

    Without this the dashboard has no way to tell "the pipeline has not run since
    Tuesday" from "the pipeline ran this morning and died at validation": both
    look like an old timestamp, and the second one is a data-quality incident.
    No secret and no full traceback is stored — the log file keeps that.
    """
    results = DATA / "results"
    results.mkdir(parents=True, exist_ok=True)
    record = {
        "failed_utc": datetime.now(timezone.utc).isoformat(),
        "stage": stage,
        "error_type": type(exc).__name__,
        "reason": getattr(exc, "reason", None),
        "message": str(exc)[:500],
    }
    (results / FAILURE_NAME).write_text(json.dumps(record, indent=2),
                                        encoding="utf-8")
    logger.error("pipeline stage '%s' failed (%s): %s", stage,
                 record["error_type"], record["message"])
    return record


def _stage(name: str, func, *args, **kwargs):
    """Run one stage, recording the failure against its name before re-raising."""
    try:
        return func(*args, **kwargs)
    except Exception as exc:
        _record_failure(name, exc)
        raise


def main(
    raw_dir: Path | None = None,
    skip_download: bool = True,
    start=None,
    end=None,
):
    t0 = time.time()
    cfg = load_config()
    chash = config_hash(cfg)
    raw_dir = raw_dir or DATA / "raw"

    logger.info("pipeline start | config_hash=%s", chash)

    # Stage 1: ingestion is normally a separate download step (src.ingest.download);
    # here we validate whatever raw files exist in data/raw. A failure here is a
    # data problem, not a code problem, so it is recorded as its own stage.
    stats_val = _stage("validation", run_validation, raw_dir=raw_dir)

    # Stage 3: normalization
    normalized = _stage("normalization", build_normalized)

    # Stage 4: analytics
    spreads = _stage("analytics", build_spreads, normalized)
    spreads = _stage("analytics", add_carry, spreads)
    signals = _stage("analytics", build_signals, spreads)

    # Alerts
    alerts = _stage("alerts", generate_alerts)

    # Stage 5: backtest
    bt = _stage("backtest", run_walk_forward)

    counts = {
        "clean_rows": stats_val.get("clean_rows", 0),
        "rejected_rows": stats_val.get("rejected_rows", 0),
        "signal_rows": int(len(signals)),
        "alert_count": int(len(alerts)),
        "backtest_trades": int(bt.get("trade_rows", 0) or 0),
    }
    run_meta = {
        "run_id": bt["run_id"],
        "config_hash": chash,
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "duration_sec": round(time.time() - t0, 2),
        "row_counts": counts,
        # A run that dropped unreadable raw files is not a clean run. Recorded
        # rather than hidden, so "every file was valid" is a claim the artifact
        # can back up.
        "failed_files": list(stats_val.get("failed_files", [])),
        "partial": bool(stats_val.get("failed_files")),
        "package_versions": {"pandas": pd.__version__},
    }
    out = DATA / "results" / bt["run_id"] / "pipeline.json"
    out.write_text(json.dumps(run_meta, indent=2, default=str), encoding="utf-8")
    logger.info("pipeline done in %.1fs | %s", time.time() - t0, run_meta["run_id"])
    return run_meta


def cli(argv: list[str] | None = None) -> int:
    """Command-line entry point. Returns the process exit code.

    Non-zero on failure, so a scheduled job can tell the difference: ``2`` means
    ``data/raw`` is unusable (a data problem someone must fix on the exchange
    side), ``1`` means anything else. Returned rather than raised so the mapping
    is testable without spawning a process.
    """
    argv = sys.argv[1:] if argv is None else argv
    try:
        main(skip_download="--with-download" not in argv)
    except ValidationError as exc:
        logger.error("pipeline stopped at validation (%s)", exc.reason)
        return 2
    except Exception:
        logger.exception("pipeline failed")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(cli())
