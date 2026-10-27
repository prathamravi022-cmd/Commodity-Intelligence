"""Manual CSV import: mapping, pre-write validation, commit and history.

Covers roadmap features 22 (CSV upload), 23 (column mapping), 29 (import
history and run IDs) and 134 (server-side input validation). An uploaded file
passes exactly the validators the download path uses *before* it reaches
`data/raw`, so an import can never be treated more leniently than a download.

The file is written back in the canonical MCX column order, so
`python -m src.pipeline` re-validates it unchanged.
"""
import json
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

from src.ingest.manifest import sha256, update_manifest
from src.utils.config import config_hash, load_config
from src.validate.clean import validate_file
from src.validate.schema import RAW_COLUMNS, check_schema

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
HISTORY_NAME = "imports.json"

# Synonyms seen in exchange exports and broker CSVs. Matched case- and
# separator-insensitively; the canonical name always wins when both exist.
SYNONYMS: dict[str, list[str]] = {
    "Symbol": ["symbol", "scrip", "instrument", "contract", "ticker"],
    "Date": ["date", "tradedate", "sessiondate", "businessdate"],
    "ExpiryDate": ["expirydate", "expiry", "expdate", "expirationdate"],
    "Open": ["open", "openprice"],
    "High": ["high", "highprice"],
    "Low": ["low", "lowprice"],
    "Close": ["close", "closeprice", "lastprice", "settlementprice"],
    "Volume": ["volume", "vol", "qty", "quantity"],
    "OpenInterest": ["openinterest", "oi", "openint"],
}


def _norm(col: str) -> str:
    """'Open Interest' -> 'openinterest'."""
    return "".join(ch for ch in str(col).lower() if ch.isalnum())


def suggest_mapping(columns: list[str]) -> dict[str, str | None]:
    """Map each canonical MCX column to the closest uploaded header.

    Returns {canonical: uploaded column or None}. An exact canonical match is
    preferred; then any synonym. Each uploaded column is consumed at most once.
    """
    by_norm = {_norm(c): c for c in columns}
    taken: set[str] = set()
    mapping: dict[str, str | None] = {}
    for want in RAW_COLUMNS:
        hit = by_norm.get(_norm(want))
        if hit is not None and hit not in taken:
            mapping[want] = hit
            taken.add(hit)
            continue
        found = None
        for alt in SYNONYMS.get(want, []):
            cand = by_norm.get(_norm(alt))
            if cand is not None and cand not in taken:
                found = cand
                break
        mapping[want] = found
        if found is not None:
            taken.add(found)
    return mapping


def apply_mapping(df: pd.DataFrame, mapping: dict[str, str | None]) -> pd.DataFrame:
    """Rename uploaded columns to the canonical set.

    Raises ValueError when a canonical column is unmapped. Non-canonical
    columns are dropped: the validator decides what is kept, not the file.
    """
    missing = [c for c in RAW_COLUMNS if not mapping.get(c)]
    if missing:
        msg = f"No source column chosen for: {', '.join(missing)}."
        raise ValueError(msg)
    out = df.rename(columns={mapping[c]: c for c in RAW_COLUMNS})
    return out[RAW_COLUMNS].copy()


def read_csv(data: bytes) -> pd.DataFrame:
    """Parse an uploaded CSV, tolerating a BOM and alternate delimiters."""
    from io import StringIO
    text = data.decode("utf-8-sig", errors="replace")
    df = pd.read_csv(StringIO(text))
    if len(df.columns) == 1:
        # A single blob of header text means the delimiter is not a comma.
        first = str(df.columns[0])
        if ";" in first or "\t" in first or "|" in first:
            df = pd.read_csv(StringIO(text), sep=None, engine="python")
    return df


def validate_staged(df: pd.DataFrame, requested: date) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run the real validators on an in-memory frame without writing anything.

    Uses a temporary file so the exact same code path as the download flow is
    exercised. Raises SchemaError when required columns are absent.
    """
    check_schema(df)
    with tempfile.TemporaryDirectory() as td:
        staged = Path(td) / f"{requested.isoformat()}.csv"
        df.to_csv(staged, index=False)
        clean, rejected, _ = validate_file(staged, expected_date_str=requested.isoformat())
    return clean, rejected


def commit_import(df: pd.DataFrame, requested: date,
                  raw_dir: Path | None = None,
                  data_dir: Path | None = None,
                  overwrite: bool = False) -> dict:
    """`data_dir` holds imports.json; the manifest is written into `raw_dir`."""
    """Validate `df`, write it to raw_dir/<requested>.csv, record provenance.

    Nothing is written unless at least one row validates. Rejected rows are
    recorded in the import history, not repaired. Returns the history record.
    """
    raw_dir = raw_dir or DATA / "raw"
    data_dir = data_dir or DATA
    raw_dir.mkdir(parents=True, exist_ok=True)
    target = raw_dir / f"{requested.isoformat()}.csv"
    if target.exists() and not overwrite:
        msg = (f"{target.name} already exists in data/raw. Confirm the overwrite — "
               "raw files are treated as read-only evidence.")
        raise FileExistsError(msg)

    check_schema(df)
    clean, rejected = validate_staged(df, requested)
    if clean.empty:
        msg = ("No row passed validation, so nothing was written. "
               f"Reasons: {rejected['__reason__'].value_counts().to_dict() if len(rejected) else 'empty file'}.")
        raise ValueError(msg)

    # Write the *uploaded* frame, not the cleaned one: the pipeline re-validates
    # raw files itself, and an import must survive that re-check unchanged.
    df.to_csv(target, index=False)

    cfg = load_config()
    record = {
        "file": target.name,
        "requested_date": requested.isoformat(),
        "imported_utc": datetime.now(timezone.utc).isoformat(),
        "sha256": sha256(target),
        "rows_in_file": int(len(df)),
        "rows_accepted": int(len(clean)),
        "rows_rejected": int(len(rejected)),
        "rejection_reasons": rejected["__reason__"].value_counts().to_dict()
                             if len(rejected) else {},
        "config_hash": config_hash(cfg),
        "source": "manual-upload",
    }
    # The manifest describes raw evidence, so it lives beside it: the Data
    # Quality page reads data/raw/manifest.json.
    update_manifest(raw_dir, [target], extra={"last_import": record})
    append_import(record, data_dir=data_dir)
    return record


def append_import(record: dict, data_dir: Path | None = None) -> Path:
    """Append one record to data/imports.json (newest last)."""
    data_dir = data_dir or DATA
    path = data_dir / HISTORY_NAME
    history: list[dict] = []
    if path.exists():
        try:
            history = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            history = []
    history.append(record)
    path.write_text(json.dumps(history, indent=2, default=str), encoding="utf-8")
    return path


def load_history(data_dir: Path | None = None) -> list[dict]:
    data_dir = data_dir or DATA
    path = data_dir / HISTORY_NAME
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
