"""DATA-002 unit tests: exact match, previous-trading-day return, day/month swap."""
from datetime import date

from src.validate.dates import parse_request_date, parse_response_date, requested_matches_response


def test_exact_match():
    assert requested_matches_response("05/01/2026", "01/05/2026")


def test_mcx_returns_previous_trading_day():
    assert not requested_matches_response("06/01/2026", "03/01/2026")


def test_day_month_swap_detected():
    # Requested 2026-01-05; response 05/01/2026 reads as May 1 2026 -> mismatch
    assert not requested_matches_response("05/01/2026", "05/01/2026")


def test_invalid_response_date_rejected():
    assert not requested_matches_response("05/01/2026", "not-a-date")


def test_parse_both_formats():
    assert parse_request_date("04/09/2026") == date(2026, 9, 4)
    assert parse_response_date("09/04/2026") == date(2026, 9, 4)


def test_explicit_payoff_symmetry():
    from datetime import datetime
    assert datetime.strptime("04/09/2026", "%d/%m/%Y").date() == date(2026, 9, 4)
