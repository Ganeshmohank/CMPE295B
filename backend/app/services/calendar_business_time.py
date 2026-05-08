"""Business-calendar rules for event start times (orchestration / invites)."""

from datetime import datetime, timedelta


def move_weekend_to_monday(event_start: datetime) -> datetime:
    """
    If the event falls on Saturday or Sunday, shift to the next Monday
    keeping the same clock time.

    Example: Friday + default "tomorrow 9 AM" would be Saturday 9 AM → Monday 9 AM.
    "Today" on Friday stays Friday.
    """
    w = event_start.weekday()
    if w < 5:
        return event_start
    if w == 5:
        return event_start + timedelta(days=2)
    return event_start + timedelta(days=1)
