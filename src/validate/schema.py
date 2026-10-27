"""Schema and range validation (DATA-004, security doc 6.2/6.4)."""
from pathlib import Path

import pandas as pd

RAW_COLUMNS = ["Symbol", "Date", "ExpiryDate", "Open", "High", "Low", "Close",
               "Volume", "OpenInterest"]


class SchemaError(RuntimeError):
    """Stop the pipeline with a clear diff message."""


def check_schema(df: pd.DataFrame, required: list[str] | None = None) -> None:
    """Missing or renamed columns stop the pipeline with a clear message."""
    required = required or RAW_COLUMNS
    missing = [c for c in required if c not in df.columns]
    extra = [c for c in df.columns if c not in required]
    if missing:
        raise SchemaError(
            f"Schema mismatch. Missing columns: {missing}. Unexpected columns: {extra}. "
            "Update loader after review (security doc incident response)."
        )


def validate_range(df: pd.DataFrame) -> pd.DataFrame:
    """Prices must be positive; Close must lie between Low and High.

    Returns rows that pass; range violations get reason PRICE_RANGE.
    """
    num = ["Open", "High", "Low", "Close"]
    for col in num:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    ok = (
        df[num].notna().all(axis=1)
        & (df[num] > 0).all(axis=1)
        & (df["Close"] >= df["Low"])
        & (df["Close"] <= df["High"])
        & df["ExpiryDate"].notna()
    )
    return df[ok].copy()
