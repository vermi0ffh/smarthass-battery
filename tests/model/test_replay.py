"""Tests — the model replayed on a real battery: 10 days of a house in late autumn (2026-10-28 to 11-07), 4 Pylontech
US5000 packs (19.2 kWh) on 2 Growatt SPF 5000 ES inverters, charged at night from the grid and emptied each evening
down to the Home Assistant safety at 9 %. The reference is what the battery really delivered: from each half hour to
the next empty landmark, the energy out minus the energy in times the round trip measured over the whole recording
(rule 25)."""

from dataclasses import dataclass
from datetime import datetime, timedelta

import pytest

from custom_components.smart_hass_battery.model.battery import EMPTY, FULL, Battery, BatteryConfig
from tests.model.recording import Event, Flows, empty_crossings, events, flows

NOMINAL_KWH = 19.2
EMPTY_SOC_PCT = 9.0


@dataclass(frozen=True)
class Sample:
    at: datetime
    estimate_kwh: float
    nominal_kwh: float  # the BMS's state of charge times the nominal capacity, above the empty threshold
    truth_kwh: float
    direction: int  # +1 charging, -1 discharging, 0 idle around the sample


@dataclass(frozen=True)
class Replay:
    samples: list[Sample]
    battery: Battery
    landmarks: list[tuple[datetime, str]]


@pytest.fixture(scope="module")
def recorded() -> list[Event]:
    return list(events())


@pytest.fixture(scope="module")
def recorded_flows(recorded: list[Event]) -> Flows:
    return flows(recorded)


def round_trip(recorded: list[Event], recorded_flows: Flows) -> float:
    """What came out over what went in, from the first empty landmark to the last."""
    crossings = empty_crossings(recorded, EMPTY_SOC_PCT)
    (in0, out0), (in1, out1) = recorded_flows.at(crossings[0]), recorded_flows.at(crossings[-1])
    return (out1 - out0) / (in1 - in0)


def replay(recorded: list[Event], recorded_flows: Flows, config: BatteryConfig) -> Replay:
    battery = Battery(config)
    crossings = empty_crossings(recorded, EMPTY_SOC_PCT)
    eta = round_trip(recorded, recorded_flows)
    samples, landmarks = [], []
    soc: float | None = None
    due = recorded[0].at.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    for event in recorded:
        while event.at >= due:
            if crossings[0] <= due < crossings[-1] and battery.energy_kwh is not None and soc is not None:
                samples.append(sample(due, battery.energy_kwh, soc, recorded_flows, crossings, eta))
            due += timedelta(minutes=30)
        soc = event.reading.soc_pct if event.reading.soc_pct is not None else soc
        before = battery.last_landmark_at
        battery.update(event.at, event.reading)
        if battery.last_landmark_at != before and battery.last_landmark is not None:
            landmarks.append((event.at, battery.last_landmark))
    return Replay(samples, battery, landmarks)


def sample(
    at: datetime, estimate_kwh: float, soc_pct: float, recorded_flows: Flows, crossings: list[datetime], eta: float
) -> Sample:
    following = next(t for t in crossings if t > at)
    (in0, out0), (in1, out1) = recorded_flows.at(at), recorded_flows.at(following)
    (in_before, out_before) = recorded_flows.at(at - timedelta(minutes=15))
    (in_after, out_after) = recorded_flows.at(at + timedelta(minutes=15))
    net = (in_after - in_before) - (out_after - out_before)
    return Sample(
        at,
        estimate_kwh,
        (soc_pct - EMPTY_SOC_PCT) * NOMINAL_KWH / 100.0,
        (out1 - out0) - eta * (in1 - in0),
        1 if net > 0.05 else (-1 if net < -0.05 else 0),
    )


def mae(errors: list[float]) -> float:
    return sum(abs(e) for e in errors) / len(errors)


def mean(errors: list[float]) -> float:
    return sum(errors) / len(errors)


@pytest.fixture(scope="module")
def house(recorded: list[Event], recorded_flows: Flows) -> Replay:
    return replay(recorded, recorded_flows, BatteryConfig(NOMINAL_KWH, has_meters=True))


def test_the_recording_s_round_trip(recorded, recorded_flows):
    # 153.5 kWh in, 148.0 out over 8 daily cycles (the reference of the other tests)
    assert round_trip(recorded, recorded_flows) == pytest.approx(0.964, abs=0.001)


def test_counting_since_the_landmarks_beats_the_state_of_charge(house):
    estimate = [s.estimate_kwh - s.truth_kwh for s in house.samples]
    nominal = [s.nominal_kwh - s.truth_kwh for s in house.samples]
    assert len(house.samples) == 382
    # 0.43 kWh against 0.63 on average, 1.09 against 1.89 at worst
    assert mae(estimate) < 0.45
    assert mae(estimate) < 0.75 * mae(nominal)
    assert max(abs(e) for e in estimate) < 1.2 < max(abs(e) for e in nominal)


def test_the_state_of_charge_s_lead_and_lag_are_gone(house):
    for direction in (1, -1):
        samples = [s for s in house.samples if s.direction == direction]
        nominal = mean([s.nominal_kwh - s.truth_kwh for s in samples])
        estimate = mean([s.estimate_kwh - s.truth_kwh for s in samples])
        # The BMS runs ahead while charging (+0.42 kWh on average) and lags while discharging (-0.50); the counting is
        # off by 0.02 and 0.07
        assert nominal * direction > 0.3
        assert abs(estimate) < 0.2


def test_the_landmarks_of_the_recording(house):
    kinds = [kind for _, kind in house.landmarks]
    # A cell at 3.50 V on the 4 nights charged to the top, twice on 11-06 (2.1 kWh went out between the 01:50 and the
    # 03:40 top-ups); the safety's 9 % every evening (three times on 11-03)
    assert kinds.count(FULL) == 5
    assert kinds.count(EMPTY) == 11


def test_what_the_recording_teaches_without_being_used(house):
    battery = house.battery
    assert battery.learned_efficiency == pytest.approx(0.964, abs=0.01)
    assert battery.learned_full_energy_kwh == pytest.approx(17.2, abs=0.4)
    # Learning off: the configured values stay in use
    assert battery.efficiency == 0.96
    assert battery.full_energy_kwh == pytest.approx(17.47, abs=0.01)


def test_learning_corrects_a_wrong_configuration(recorded, recorded_flows):
    wrong_config = BatteryConfig(22.0, efficiency=0.92, has_meters=True)
    uncorrected = replay(recorded, recorded_flows, wrong_config)
    learned = replay(recorded, recorded_flows, BatteryConfig(22.0, efficiency=0.92, has_meters=True, learn=True))
    assert learned.battery.efficiency == pytest.approx(0.964, abs=0.01)
    assert learned.battery.full_energy_kwh == pytest.approx(17.2, abs=0.4)
    since = learned.samples[0].at + timedelta(days=5)

    def late(r: Replay) -> list[float]:
        return [s.estimate_kwh - s.truth_kwh for s in r.samples if s.at >= since]

    # Once learned (the round trip from 11-03, the energy between the landmarks from 11-06): 0.99 kWh against 1.52
    assert mae(late(learned)) < 0.7 * mae(late(uncorrected))
