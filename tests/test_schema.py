"""DATA-004: schema check and range validation tests."""
from pathlib import Path

import numpy as np
import pandas as pd

from src.validate.schema import SchemaError, check_schema


def _valid_df():
    return pd.DataFrame({
        "Symbol": ["GOLDM"],
        "Date": ["01/05/2026"],
        "ExpiryDate": ["04MAY2026"],
        "Open": [7299.0],
        "High": [7310.0],
        "Low": [7295.0],
        "Close": [7300.0],
        "Volume": [1000],
        "OpenInterest": [5000],
    })


def test_schema_ok():
    check_schema(_valid_df())


def test_missing_column_stops_pipeline():
    df = _valid_df().drop(columns=["ExpiryDate"])
    try:
        check_schema(df)
        assert False, "should have raised"
    except SchemaError as e:
        assert "ExpiryDate" in str(e)


def test_range_violation_reason():
    from src.validate.clean import validate_file
    import tempfile
    df = _valid_df()
    df.loc[0, "Close"] = 9000.0  # Close > High
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "2026-05-01.csv"
        df.to_csv(p, index=False)
        clean, rejected, _ = validate_file(p, expected_date_str="2026-05-01")
        assert rejected.iloc[0]["__reason__"] == "PRICE_RANGE"


def test_date_mismatch_reason():
    from src.validate.clean import validate_file
    import tempfile
    df = _valid_df()
    # MCX returned the previous trading day (parseable, but != requested)
    df.loc[0, "Date"] = "04/30/2026"
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "2026-05-01.csv"
        df.to_csv(p, index=False)
        clean, rejected, _ = validate_file(p, expected_date_str="2026-05-01")
        assert rejected.iloc[0]["__reason__"] == "DATE_MISMATCH"


def test_unparseable_date_reason():
    from src.validate.clean import validate_file
    import tempfile
    df = _valid_df()
    df.loc[0, "Date"] = "30/04/2026"  # month 30: invalid in MM/DD/YYYY
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "2026-05-01.csv"
        df.to_csv(p, index=False)
        clean, rejected, _ = validate_file(p, expected_date_str="2026-05-01")
        assert rejected.iloc[0]["__reason__"] == "BAD_DATE_FORMAT"
