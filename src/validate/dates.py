"""Date parsing/validation (DATA-002). Request DD/MM/YYYY, response MM/DD/YYYY."""
from datetime import date, datetime

import pandas as pd

from src.utils.config import load_config


def parse_request_date(s: str) -> date:
    fmt = load_config()["validation"]["date_request_format"]
    return datetime.strptime(str(s), fmt).date()


def parse_response_date(s: str) -> date:
    fmt = load_config()["validation"]["date_response_format"]
    return datetime.strptime(str(s), fmt).date()


def requested_matches_response(requested: str | date, response: str) -> bool:
    """Response Date must equal the requested date. Mismatches are rejected."""
    if isinstance(requested, date):
        req = requested
    else:
        s = str(requested)
        # Accept either DD/MM/YYYY request format or ISO filenames (YYYY-MM-DD)
        try:
            req = parse_request_date(s)
        except ValueError:
            try:
                req = date.fromisoformat(s)
            except ValueError:
                return False
    try:
        resp = parse_response_date(str(response))
    except ValueError:
        return False
    return req == resp


def parse_trade_date_safe(s: str) -> date | None:
    """Parse MM/DD/YYYY response date or None if invalid."""
    try:
        return parse_response_date(str(s))
    except ValueError:
        return None
