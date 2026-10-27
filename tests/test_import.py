"""Manual import slice: mapping, validation, commit and history (22/23/29/30)."""
import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from src.ingest import import_csv
from src.ingest.manifest import sha256
from src.validate.report import build_quality_report


def _frame(rows=2):
    """A well-formed two-row MCX-shaped frame."""
    return pd.DataFrame({
        "Symbol": ["GOLDM"] * rows,
        "Date": ["05/04/2026"] * rows,
        "ExpiryDate": ["04MAY2026"] * rows,
        "Open": [7299.0] * rows,
        "High": [7310.0] * rows,
        "Low": [7295.0] * rows,
        "Close": [7300.0 + i for i in range(rows)],
        "Volume": [1000] * rows,
        "OpenInterest": [5000] * rows,
    })


# ---- mapping (feature 23) ------------------------------------------------

def test_suggest_mapping_identity():
    df = _frame()
    mapping = import_csv.suggest_mapping(list(df.columns))
    assert all(v == k for k, v in mapping.items())


def test_suggest_mapping_lowercased_and_spaced():
    df = _frame().rename(columns={
        "Symbol": "symbol", "Date": "Trade Date", "ExpiryDate": "expiry",
        "OpenInterest": "Open Interest", "Close": "Settlement Price"})
    mapping = import_csv.suggest_mapping(list(df.columns))
    assert mapping["Symbol"] == "symbol"
    assert mapping["Date"] == "Trade Date"
    assert mapping["ExpiryDate"] == "expiry"
    assert mapping["OpenInterest"] == "Open Interest"
    assert mapping["Close"] == "Settlement Price"


def test_suggest_mapping_leaves_absent_columns_none():
    df = _frame().drop(columns=["Volume", "OpenInterest"])
    mapping = import_csv.suggest_mapping(list(df.columns))
    assert mapping["Volume"] is None and mapping["OpenInterest"] is None
    assert mapping["Close"] == "Close"


def test_suggest_mapping_never_assigns_one_column_twice():
    # An uploaded column may satisfy only one canonical name, even when it
    # resembles several ('Close' is not also 'Open').
    df = _frame().rename(columns={"Open": "Close", "Close": "LastPrice"})
    mapping = import_csv.suggest_mapping(list(df.columns))
    given = [v for v in mapping.values() if v is not None]
    assert len(given) == len(set(given))
    assert mapping["Open"] is None          # 'Close' is not an alias for Open
    assert mapping["Close"] in {"Close", "LastPrice"}


def test_apply_mapping_orders_and_drops_extras():
    df = _frame().rename(columns={"Symbol": "scrip", "Volume": "qty"})
    df["Junk"] = 1
    mapping = import_csv.suggest_mapping(list(df.columns))
    out = import_csv.apply_mapping(df, mapping)
    assert list(out.columns) == import_csv.RAW_COLUMNS
    assert "Junk" not in out.columns


def test_apply_mapping_refuses_missing_column():
    df = _frame().drop(columns=["ExpiryDate"])
    mapping = import_csv.suggest_mapping(list(df.columns))
    with pytest.raises(ValueError, match="ExpiryDate"):
        import_csv.apply_mapping(df, mapping)


# ---- validation before any write (features 22/134) ------------------------

def test_validate_staged_rejects_bad_rows_without_writing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)            # any stray write lands here
    df = _frame()
    df.loc[1, "Close"] = 99_999.0          # > High: PRICE_RANGE
    clean, rejected = import_csv.validate_staged(df, date(2026, 5, 4))
    assert len(clean) == 1 and rejected["__reason__"].iloc[0] == "PRICE_RANGE"
    assert list(tmp_path.iterdir()) == []  # nothing written anywhere


def test_validate_staged_enforces_requested_date():
    df = _frame()
    df["Date"] = "05/03/2026"              # MCX answered a different session
    clean, rejected = import_csv.validate_staged(df, date(2026, 5, 4))
    assert clean.empty and set(rejected["__reason__"]) == {"DATE_MISMATCH"}


# ---- commit and history (features 29/30) ----------------------------------

def test_commit_writes_raw_file_manifest_and_history(tmp_path):
    raw = tmp_path / "raw"
    df = _frame()
    record = import_csv.commit_import(df, date(2026, 5, 4), raw_dir=raw,
                                      data_dir=tmp_path)
    target = raw / "2026-05-04.csv"
    assert target.exists()
    assert record["sha256"] == sha256(target)
    # The manifest sits beside the raw evidence it describes, which is where
    # the Data Quality page reads it from.
    manifest = json.loads((raw / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["2026-05-04.csv"]["sha256"] == record["sha256"]
    assert manifest["_meta"]["last_import"]["source"] == "manual-upload"
    assert not (tmp_path / "manifest.json").exists()
    assert record["rows_accepted"] == 2 and record["rows_rejected"] == 0
    assert record["source"] == "manual-upload"
    history = import_csv.load_history(data_dir=tmp_path)
    assert [h["file"] for h in history] == ["2026-05-04.csv"]
    # The written file still carries the raw schema, so the pipeline can
    # re-validate it exactly as it would a downloaded file.
    assert "Symbol" in pd.read_csv(target).columns


def test_commit_refuses_to_overwrite_without_confirmation(tmp_path):
    raw = tmp_path / "raw"
    import_csv.commit_import(_frame(), date(2026, 5, 4), raw_dir=raw,
                             data_dir=tmp_path)
    with pytest.raises(FileExistsError):
        import_csv.commit_import(_frame(), date(2026, 5, 4), raw_dir=raw,
                                 data_dir=tmp_path)
    # ...and writes nothing when every row fails validation
    bad = _frame()
    bad["Date"] = "04/30/2026"
    with pytest.raises(ValueError, match="No row passed validation"):
        import_csv.commit_import(bad, date(2026, 5, 4), raw_dir=raw,
                                 data_dir=tmp_path, overwrite=True)
    assert len(import_csv.load_history(data_dir=tmp_path)) == 1


def test_commit_rejects_schema_mismatch_before_writing(tmp_path):
    from src.validate.schema import SchemaError
    raw = tmp_path / "raw"
    with pytest.raises(SchemaError):
        import_csv.commit_import(_frame().drop(columns=["Open"]),
                                 date(2026, 5, 4), raw_dir=raw, data_dir=tmp_path)
    assert list(raw.iterdir()) == []


def test_commit_counts_rejection_reasons(tmp_path):
    df = _frame(rows=3)
    df.loc[2, "Close"] = 1.0                # below Low
    record = import_csv.commit_import(df, date(2026, 5, 4), raw_dir=tmp_path / "raw",
                                      data_dir=tmp_path)
    assert record["rows_accepted"] == 2
    assert record["rejection_reasons"] == {"PRICE_RANGE": 1}


def test_read_csv_handles_bom_and_semicolons():
    payload = ("﻿Symbol;Date;ExpiryDate;Open;High;Low;Close;Volume;OpenInterest\n"
               "GOLDM;05/04/2026;04MAY2026;1;2;0.5;1.5;10;20\n").encode("utf-8")
    df = import_csv.read_csv(payload)
    assert list(df.columns)[:3] == ["Symbol", "Date", "ExpiryDate"]
    clean, _ = import_csv.validate_staged(df, date(2026, 5, 4))
    assert len(clean) == 1


# ---- report (features 30/126) ---------------------------------------------

def test_report_lists_coverage_reasons_and_checksums():
    clean = pd.DataFrame({
        "symbol": ["GOLDM", "GOLDTEN"],
        "trade_date": pd.to_datetime(["2026-05-04", "2026-05-05"]),
    })
    rej = pd.DataFrame({"reason": ["DATE_MISMATCH", "PRICE_RANGE", "PRICE_RANGE"]})
    manifest = {"2026-05-04.csv": {"sha256": "a" * 64, "row_count": 2}}
    report = build_quality_report(clean, rej, manifest,
                                  {"date_response_format": "%m/%d/%Y"},
                                  history=[{"file": "2026-05-04.csv",
                                            "imported_utc": "2026-05-04T10:00:00",
                                            "rows_accepted": 1, "rows_rejected": 2}])
    assert "GOLDTEN" in report and "PRICE_RANGE" in report
    assert "a" * 16 in report            # checksum, truncated
    assert "DATE_MISMATCH" in report
    assert "not executable fills" in report


def test_report_on_clean_data_says_so(tmp_path):
    clean = pd.DataFrame({"symbol": [], "trade_date": pd.Series([], dtype="datetime64[ns]")})
    report = build_quality_report(clean, pd.DataFrame(), {}, {}, history=None)
    assert "No rows were rejected." in report


def test_import_history_is_json_and_append_only(tmp_path):
    for i in range(3):
        import_csv.append_import({"file": f"{i}.csv"}, data_dir=tmp_path)
    history = import_csv.load_history(data_dir=tmp_path)
    assert [h["file"] for h in history] == ["0.csv", "1.csv", "2.csv"]
