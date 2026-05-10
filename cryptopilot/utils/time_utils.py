"""Time-related utility functions."""

from __future__ import annotations

import time
from datetime import datetime, timezone


def utc_now() -> datetime:
    """Return current UTC datetime."""
    return datetime.now(tz=timezone.utc)


def utc_timestamp_ms() -> int:
    """Return current UTC time in milliseconds."""
    return int(time.time() * 1000)


def iso_now() -> str:
    """Return ISO 8601 timestamp string."""
    return utc_now().isoformat()


def ts_to_datetime(ts: int | float) -> datetime:
    """Convert a Unix timestamp (seconds or ms) to UTC datetime."""
    if ts > 1e12:  # milliseconds
        ts = ts / 1000.0
    return datetime.fromtimestamp(ts, tz=timezone.utc)
