"""Download MCX daily bhavcopy for a date range; cache raw files (FR-1, DATA-001)."""
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests
from yaml import safe_load

from src.utils.config import load_config
from src.utils.logging_config import get_logger

logger = get_logger("ingest.download")

BHAVCOPY_URL = "https://www.mcxindia.com/backpage.aspx/GetBhavCopyData"

GOLD_SYMBOLS = {"GOLDM", "GOLDTEN", "GOLDGUINEA", "GOLDPETAL"}


def is_trading_day(d: date) -> bool:
    """Mon-Fri weekdays. Holidays are left to validation coverage analysis."""
    return d.weekday() < 5


def bhavcopy_payload(d: date) -> dict:
    """MCX request body; request date format is DD/MM/YYYY (validation.date_request_format)."""
    cfg = load_config()
    req_fmt = cfg["validation"]["date_request_format"]
    return {
        "FromDate": d.strftime(req_fmt),
        "ToDate": d.strftime(req_fmt),
    }


def download_for_date(requested: date, out_dir: Path, retry: bool = True) -> Path | None:
    """Download one day's bhavcopy and cache raw CSV. Returns path or None."""
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{requested.isoformat()}.csv"
    if target.exists():
        logger.info("cached: %s", target.name)
        return target
    try:
        resp = requests.post(BHAVCOPY_URL, json=bhavcopy_payload(requested), timeout=30)
        resp.raise_for_status()
        raw = resp.text
        # MCX may return the most recent trading day - strict validation happens
        # downstream (validate/dates.py). We cache raw file first, reproduce exact UX.
        target.write_text(raw, encoding="utf-8", errors="replace")
        return target
    except requests.RequestException as exc:
        if retry:
            logger.warning("retrying %s after error: %s", requested.isoformat(), type(exc).__name__)
            time.sleep(2)
            return download_for_date(requested, out_dir, retry=False)
        logger.error("download failed %s: %s", requested.isoformat(), exc)
        return None


def download_range(start: date, end: date, out_dir: Path | None = None) -> list[Path]:
    """Download all weekday bhavcopies between dates inclusive. Rate-limited >= 1s."""
    cfg = load_config()
    rate_limit = float(cfg["validation"].get("rate_limit_seconds", 1.0))
    out_dir = out_dir or (Path(__file__).resolve().parents[2] / "data" / "raw")
    paths: list[Path] = []
    d = start
    first = True
    while d <= end:
        if is_trading_day(d):
            if not first:
                time.sleep(rate_limit)
            first = False
            p = download_for_date(d, out_dir)
            if p:
                paths.append(p)
        d += timedelta(days=1)
    return paths
