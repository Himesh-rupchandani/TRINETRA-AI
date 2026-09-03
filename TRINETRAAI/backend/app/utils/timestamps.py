from datetime import datetime, timezone
from typing import Optional


def utc_now() -> datetime:
    """Return current timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


def format_timestamp(dt: Optional[datetime] = None) -> str:
    """Format datetime as ISO-8601 string."""
    if dt is None:
        dt = utc_now()
    return dt.isoformat()


def parse_timestamp(iso_str: str) -> datetime:
    """Parse ISO-8601 string into timezone-aware datetime."""
    return datetime.fromisoformat(iso_str)
