"""Shared cutoff calculation for prospective lottery snapshots."""
from datetime import datetime, timedelta, timezone


def next_draw_deadline(latest_date: str) -> datetime:
    """Find the next regular draw's ticket cutoff in Beijing time.

    @param latest_date ISO date of the latest recorded draw.
    @returns Next Monday, Wednesday or Saturday at 20:00, with timezone.
    """
    date = datetime.fromisoformat(latest_date).replace(hour=20, tzinfo=timezone(timedelta(hours=8)))
    for offset in range(1, 8):
        target = date + timedelta(days=offset)
        if target.weekday() in (0, 2, 5):
            return target
    raise ValueError('Invalid draw calendar')
