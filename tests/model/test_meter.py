"""Tests — increase of a cumulative meter: resets, jitter, unavailable readings."""

import pytest

from custom_components.smart_hass_battery.model.meter import meter_delta


@pytest.mark.parametrize(
    ("previous", "current", "expected"),
    [
        (10.0, 12.5, 2.5),  # counted
        (24.2, 0.3, 0.3),  # daily reset at midnight (the Growatt counters): the new value counts fully
        (12.5, 12.4, 0.0),  # jitter
        (None, 12.0, 0.0),  # first reading: nothing to count yet
        (12.0, None, 0.0),  # unavailable
    ],
)
def test_meter_delta(previous, current, expected):
    assert meter_delta(previous, current) == pytest.approx(expected)


def test_an_increase_beyond_the_physics_is_spurious():
    assert meter_delta(0.3, 24.2, max_delta=5.0) == 0.0
    assert meter_delta(0.3, 2.8, max_delta=5.0) == pytest.approx(2.5)
