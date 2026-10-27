"""Parse ExpiryDate in compact format like 04SEP2026 (DATA-003)."""
import calendar
from datetime import datetime

from src.utils.config import load_config

_MONTHS = {m.upper(): i for i, m in enumerate(calendar.month_abbr) if m}


def parse_expiry(s: str) -> datetime | None:
    """Parse '04SEP2026' using config expiry_format. Returns None if invalid."""
    fmt = load_config()["validation"]["expiry_format"]
    try:
        return datetime.strptime(str(s).strip().upper(), fmt) if fmt == "%d%b%Y" else datetime.strptime(str(s), fmt)
    except ValueError:
        return None


def valid_expiry_month_token(tok: str) -> bool:
    """Check a 3-letter month token like SEP is real (unit tests cover all 12)."""
    return str(tok).upper() in _MONTHS
