"""DATA-003 unit tests: compact expiry strings for all 12 months (all 12 months)."""
from datetime import datetime

from src.validate.expiry import parse_expiry, valid_expiry_month_token


def test_all_twelve_months():
    month_numbers = {tok: i for i, tok in enumerate(
        ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], 1)}
    for tok, num in month_numbers.items():
        s = f"04{tok}2026"
        parsed = parse_expiry(s)
        assert parsed is not None
        assert parsed.month == num, f"{s} -> {parsed}"


def test_invalid_expiry_returns_none():
    assert parse_expiry("32MRC2026") is None
    assert parse_expiry("") is None
    assert parse_expiry("99XXX2026") is None


def test_month_tokens():
    assert valid_expiry_month_token("SEP")
    assert not valid_expiry_month_token("XYZ")


def test_lowercase_is_normalized():
    assert parse_expiry("04sep2026") == datetime(2026, 9, 4)
