"""Utilities for timezone-aware current date/time handling."""

from __future__ import annotations

import datetime as dt
import os
from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_TIMEZONE = "Asia/Ho_Chi_Minh"

# Official TDTU timetable periods.  The gaps between blocks are intentional
# breaks and must not be removed when constructing Calendar events.
PERIOD_TIME_RANGES: dict[int, tuple[str, str]] = {
    1: ("06:50", "07:40"),
    2: ("07:40", "08:30"),
    3: ("08:30", "09:20"),
    4: ("09:30", "10:20"),
    5: ("10:20", "11:10"),
    6: ("11:10", "12:00"),
    7: ("12:45", "13:35"),
    8: ("13:35", "14:25"),
    9: ("14:25", "15:15"),
    10: ("15:25", "16:15"),
    11: ("16:15", "17:05"),
    12: ("17:05", "17:55"),
    13: ("18:05", "18:55"),
    14: ("18:55", "19:45"),
    15: ("19:45", "20:35"),
}


def period_time_range(start_period: object, end_period: object) -> tuple[str, str] | None:
    """Return exact clock times for an inclusive period range."""
    try:
        start = int(start_period)
        end = int(end_period)
    except (TypeError, ValueError):
        return None
    if start not in PERIOD_TIME_RANGES or end not in PERIOD_TIME_RANGES or start > end:
        return None
    return PERIOD_TIME_RANGES[start][0], PERIOD_TIME_RANGES[end][1]


def period_shift(period: object) -> int | None:
    """Return the official shift number (1–5) containing a period."""
    try:
        value = int(period)
    except (TypeError, ValueError):
        return None
    if 1 <= value <= 3:
        return 1
    if 4 <= value <= 6:
        return 2
    if 7 <= value <= 9:
        return 3
    if 10 <= value <= 12:
        return 4
    if 13 <= value <= 15:
        return 5
    return None


@lru_cache(maxsize=1)
def _resolve_timezone() -> ZoneInfo:
    timezone_name = os.environ.get("APP_TIMEZONE", DEFAULT_TIMEZONE).strip() or DEFAULT_TIMEZONE
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        return ZoneInfo(DEFAULT_TIMEZONE)


def local_now() -> dt.datetime:
    """Return current datetime in application timezone."""
    return dt.datetime.now(_resolve_timezone())


def local_today() -> dt.date:
    """Return current local date in application timezone."""
    return local_now().date()
