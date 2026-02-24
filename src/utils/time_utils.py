# src/utils/time_utils.py
"""
Time-related utilities.

What:
  Provide timezone-aware, reproducible timestamp helpers.

Why:
  - Avoid scattered datetime.now() usage across pipeline.
  - Ensure all timestamps are UTC and ISO-8601 compliant.
  - Keep time logic centralized for artifacts, logs, and manifests.
"""

from __future__ import annotations

from datetime import datetime, timezone


def utc_now_iso() -> str:
    """
    Return current UTC timestamp in ISO-8601 format.

    Returns
    -------
    str
        ISO-8601 formatted UTC timestamp, e.g. "2025-01-12T21:43:10.123456+00:00"
    """
    return datetime.now(timezone.utc).isoformat()

def utc_from_timestamp_iso(ts: float) -> str:
    """Convert a POSIX timestamp (seconds) to UTC ISO 8601."""
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
