"""Timestamp helpers — the backend's single timezone vocabulary.

Every instant the backend stores, broadcasts or serializes is UTC. ``iso_utc``
renders it in the browser-safe ISO-8601 ``...Z`` form so ``new Date(value)``
never re-interprets a UTC instant as local time.
"""
from datetime import datetime, timezone
from typing import Optional


def utc_now() -> datetime:
    """Return current timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


def to_utc(dt: datetime) -> datetime:
    """Return ``dt`` as timezone-aware UTC.

    Naive values are assumed to already be UTC (the storage contract of
    ``app.database.models.UTCDateTime``) — they are labelled, never shifted.
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def iso_utc(dt: Optional[datetime] = None) -> str:
    """Format a datetime as ISO-8601 UTC with an explicit ``Z`` suffix."""
    if dt is None:
        dt = utc_now()
    return to_utc(dt).isoformat().replace("+00:00", "Z")


def format_timestamp(dt: Optional[datetime] = None) -> str:
    """Format datetime as ISO-8601 string (UTC, ``Z`` suffixed)."""
    return iso_utc(dt)


def parse_timestamp(iso_str: str) -> datetime:
    """Parse ISO-8601 string into timezone-aware UTC datetime.

    Accepts a trailing ``Z`` (``datetime.fromisoformat`` only learned that in
    Python 3.11) and treats a naive string as UTC rather than local time.
    """
    dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
    return to_utc(dt)
