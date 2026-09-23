"""Recurring weekly schedule matching."""

from __future__ import annotations

from datetime import datetime
from typing import Any


DAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def format_days(days: list[int]) -> str:
    normalized = sorted({day for day in days if day in range(7)})
    if normalized == list(range(7)):
        return "Every day"
    if normalized == list(range(5)):
        return "Weekdays"
    if normalized == [5, 6]:
        return "Weekends"
    return ", ".join(DAY_NAMES[day] for day in normalized) or "Never"


def schedule_matches(schedule: dict[str, Any], now: datetime) -> bool:
    return bool(
        schedule.get("enabled", True)
        and now.weekday() in schedule.get("days", [])
        and schedule.get("time") == now.strftime("%H:%M")
    )


def schedule_key(index: int, now: datetime) -> str:
    return f"{now:%Y-%m-%dT%H:%M}:{index}"
