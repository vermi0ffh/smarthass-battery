"""A recorded history of a real battery (tests/model/data/), replayed through the model as Home Assistant would feed
it: each recorded state change updates the model with the latest value of every input."""

import gzip
from collections.abc import Iterator
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from custom_components.smart_hass_battery.model.battery import Reading

DATA = Path(__file__).parent / "data"
HOUSE = DATA / "battery_2026-10-28_2026-11-07.csv.gz"
KEYS = ("soc_pct", "power_w", "charged_kwh", "discharged_kwh", "cell_high_v")


@dataclass(frozen=True)
class Event:
    at: datetime
    reading: Reading  # every input at its latest recorded value


def events(path: Path = HOUSE) -> Iterator[Event]:
    start: datetime | None = None
    reading = Reading(None)
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            if line.startswith("# start="):
                start = datetime.fromisoformat(line.removeprefix("# start=").strip()).astimezone(UTC)
                continue
            if line.startswith("#") or line.startswith("offset_s"):
                continue
            assert start is not None
            offset, key, value = line.rstrip("\n").split(",")
            assert key in KEYS
            reading = replace(reading, **{key: float(value)})
            yield Event(start + timedelta(seconds=int(offset)), reading)


@dataclass(frozen=True)
class Flows:
    """The DC energy that went in and out since the start of the recording, integrated from its power."""

    times: list[datetime]
    charged_kwh: list[float]
    discharged_kwh: list[float]

    def at(self, t: datetime) -> tuple[float, float]:
        lo, hi = 0, len(self.times)
        while lo < hi:
            mid = (lo + hi) // 2
            if self.times[mid] <= t:
                lo = mid + 1
            else:
                hi = mid
        i = max(lo - 1, 0)
        return self.charged_kwh[i], self.discharged_kwh[i]


def flows(recorded: list[Event]) -> Flows:
    times, charged, discharged = [recorded[0].at], [0.0], [0.0]
    for previous, event in zip(recorded, recorded[1:], strict=False):
        power = previous.reading.power_w or 0.0
        kwh = power * (event.at - previous.at).total_seconds() / 3.6e6
        times.append(event.at)
        charged.append(charged[-1] + max(kwh, 0.0))
        discharged.append(discharged[-1] + max(-kwh, 0.0))
    return Flows(times, charged, discharged)


def empty_crossings(recorded: list[Event], empty_soc_pct: float) -> list[datetime]:
    """When the BMS's state of charge crossed the empty threshold downward."""
    crossings, previous = [], None
    for event in recorded:
        soc = event.reading.soc_pct
        if soc is not None and previous is not None and previous > empty_soc_pct >= soc:
            crossings.append(event.at)
        if soc is not None:
            previous = soc
    return crossings
