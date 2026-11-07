"""Increase of a cumulative meter between two readings (the battery's energy in and out): resets, jitter and spurious
values."""

# A drop below this fraction of the previous value is a reset (a daily meter at midnight); a smaller drop is jitter
RESET_RATIO = 0.5


def meter_delta(previous: float | None, current: float | None, max_delta: float | None = None) -> float:
    """What the meter counted since `previous`: 0 without a previous reading or with a small drop (jitter); after a
    reset, the new value counts fully. An increase above `max_delta` (more than the physics allows since the previous
    reading) is a spurious value and counts nothing: a transient drop to a low value then back counts only the low
    value, not the way back. An unavailable reading (None) counts nothing: the caller keeps the last valid value."""
    if previous is None or current is None:
        return 0.0
    if current >= previous:
        delta = current - previous
    elif current < previous * RESET_RATIO:
        delta = current
    else:
        return 0.0
    return 0.0 if max_delta is not None and delta > max_delta else delta
