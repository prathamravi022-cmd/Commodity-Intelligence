"""Row-level validation producing clean parquet + rejections.csv (FR-2/FR-3)."""
from pathlib import Path

import pandas as pd

from src.ingest.manifest import sha256
from src.utils.config import load_config
from src.utils.logging_config import get_logger
from src.validate.dates import parse_response_date
from src.validate.expiry import parse_expiry
from src.validate.schema import check_schema

logger = get_logger("validate.clean")

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"

REQUIRED_RAW = ["Symbol", "Date", "ExpiryDate", "Open", "High", "Low", "Close",
                "Volume", "OpenInterest"]


class ValidationError(RuntimeError):
    """No usable rows were produced from ``data/raw``.

    ``reason`` separates the two causes a caller has to report differently:

    * ``no_raw_files``   — there is nothing to validate (ingestion has not run);
    * ``invalid_raw_files`` — files exist but every one of them failed.

    It subclasses ``RuntimeError`` so existing callers that catch the broad type
    keep working.
    """

    def __init__(self, message: str, reason: str = "no_clean_rows") -> None:
        super().__init__(message)
        self.reason = reason


def _safe_parse(s) -> bool:
    """True if the response date string parses in MM/DD/YYYY."""
    try:
        parse_response_date(s)
        return True
    except (ValueError, TypeError):
        return False


def validate_file(raw_path: Path,
                  expected_date_str: str | None = None) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Validate one raw bhavcopy file.

    Returns (clean_df, rejected_df, raw_df). Raw file's own Date column is the
    response date; if the caller supplies the requested date (`expected_date_str`),
    mismatched rows get reason DATE_MISMATCH. Prices must be positive and Close
    must lie between Low and High.
    """
    try:
        raw = pd.read_csv(raw_path)
    except (UnicodeDecodeError, pd.errors.ParserError):
        raw = pd.read_csv(raw_path, encoding="utf-8", errors="replace", on_bad_lines="skip")
    check_schema(raw)
    raw["__reason__"] = None
    raw["__reason__"] = raw["__reason__"].astype(object)

    # Expiry parsing
    parsed_expiry = raw["ExpiryDate"].map(parse_expiry)
    bad_expiry = parsed_expiry.isna() & raw["ExpiryDate"].notna()
    raw.loc[bad_expiry, "__reason__"] = "BAD_EXPIRY"
    raw["expiry_date"] = parsed_expiry.dt.date

    # Response date parsing (MM/DD/YYYY) - safe: invalid -> None
    parsed_trade = raw["Date"].map(
        lambda s: parse_response_date(s) if pd.notna(s) and _safe_parse(s) else None
    )
    bad_date = parsed_trade.isna() & raw["Date"].notna()
    raw.loc[bad_date & raw["__reason__"].isna(), "__reason__"] = "BAD_DATE_FORMAT"
    raw["trade_date"] = parsed_trade

    # Range checks run before DATE_MISMATCH so price problems are reported
    # with the more specific reason.
    numeric_cols = ["Open", "High", "Low", "Close"]
    for col in numeric_cols:
        raw[col] = pd.to_numeric(raw[col], errors="coerce")
    for col in ["Volume", "OpenInterest"]:
        raw[col] = pd.to_numeric(raw[col], errors="coerce").fillna(0).astype("int64")
    bad_range = (
        raw[numeric_cols].notna().all(axis=1)
        & ((raw[numeric_cols] <= 0).any(axis=1)
           | (raw["Close"] < raw["Low"]) | (raw["Close"] > raw["High"]))
    )
    raw.loc[bad_range & raw["__reason__"].isna(), "__reason__"] = "PRICE_RANGE"

    # Optional strict match against the requested date (T2 control)
    if expected_date_str is not None:
        from src.validate.dates import requested_matches_response
        good = raw["Date"].map(lambda s: requested_matches_response(expected_date_str, s))
        mismatch = ~good.fillna(False) & raw["__reason__"].isna()
        raw.loc[mismatch, "__reason__"] = "DATE_MISMATCH"

    # Missing required fields
    missing_mask = raw[REQUIRED_RAW].isna().any(axis=1)
    raw.loc[missing_mask & raw["__reason__"].isna(), "__reason__"] = "MISSING_FIELD"

    rejected = raw[raw["__reason__"].notna()].copy()
    clean = raw[raw["__reason__"].isna()].copy()
    clean = clean[clean["Symbol"].isin(["GOLDM", "GOLDTEN", "GOLDGUINEA", "GOLDPETAL"])]
    clean["source_file"] = raw_path.name
    return clean, rejected, raw


def run_validation(raw_dir: Path | None = None,
                   clean_dir: Path | None = None) -> dict:
    """Validate all raw files, write clean parquet + rejections.csv."""
    raw_dir = raw_dir or DATA / "raw"
    clean_dir = clean_dir or DATA / "clean"
    clean_dir.mkdir(parents=True, exist_ok=True)
    all_clean: list[pd.DataFrame] = []
    rejections: list[dict] = []
    checksums: dict[str, str] = {}
    failed_files: list[str] = []
    rj_cols = ["source_file", "Symbol", "Date", "ExpiryDate", "reason"]
    raw_files = sorted(raw_dir.glob("*.csv"))
    for raw_path in raw_files:
        checksums[raw_path.name] = sha256(raw_path)
        expected = raw_path.stem  # requested date encoded in filename YYYY-MM-DD
        try:
            clean, rejected, _ = validate_file(raw_path, expected_date_str=expected)
        except Exception as e:
            # One unreadable file must not stop the others, but it must not be
            # forgotten either: the name is reported in ``failed_files`` so the
            # run can be marked partial instead of silently short.
            failed_files.append(raw_path.name)
            logger.error("validation failed for %s: %s", raw_path.name, e)
            continue
        all_clean.append(clean)
        for _, row in rejected.iterrows():
            rejections.append({
                "source_file": raw_path.name,
                "symbol": row["Symbol"],
                "response_date": row.get("Date"),
                "reason": row["__reason__"],
                "expiry": row.get("ExpiryDate"),
            })
    if not all_clean:
        if not raw_files:
            raise ValidationError(
                "No CSV files in data/raw — ingestion has not run, so there is "
                "nothing to validate.",
                reason="no_raw_files",
            )
        raise ValidationError(
            f"None of the {len(raw_files)} raw file(s) in data/raw produced a "
            f"clean row (failed: {', '.join(failed_files)}).",
            reason="invalid_raw_files",
        )
    if failed_files:
        logger.warning("%d of %d raw files were rejected outright: %s",
                       len(failed_files), len(raw_files), ", ".join(failed_files))
    clean_all = pd.concat(all_clean, ignore_index=True)
    clean_all = clean_all.drop_duplicates(
        subset=["Symbol", "trade_date", "expiry_date"], keep="last"
    )
    out = clean_dir / "bhavcopy.parquet"
    clean_all[[
        "Symbol", "trade_date", "expiry_date", "Open", "High", "Low", "Close",
        "Volume", "OpenInterest", "source_file"]].rename(
        columns={"Symbol": "symbol", "Open": "open", "High": "high", "Low": "low",
                 "Close": "close", "Volume": "volume", "OpenInterest": "open_interest"}
    ).to_parquet(out, index=False)
    rej_path = clean_dir / "rejections.csv"
    pd.DataFrame(rejections).to_csv(rej_path, index=False)
    logger.info("validation complete: %d clean rows, %d rejections",
                len(clean_all), len(rejections))
    return {"clean_rows": len(clean_all), "rejected_rows": len(rejections),
            "files": len(checksums), "failed_files": failed_files}
