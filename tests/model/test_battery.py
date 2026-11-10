"""Tests — the battery model: counting, landmarks, meters, restart, persistence."""

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.smart_hass_battery.model.battery import (
    EMPTY,
    FULL,
    STATE_VERSION,
    Battery,
    BatteryConfig,
    BatteryState,
    Reading,
    state_from_dict,
    state_to_dict,
)

T0 = datetime(2026, 11, 6, 22, 0, tzinfo=UTC)
CONFIG = BatteryConfig(19.2)  # 17.47 kWh between the 9 % empty landmark and full
FULL_KWH = 19.2 * 0.91


def at(minutes: float) -> datetime:
    return T0 + timedelta(minutes=minutes)


def battery(config: BatteryConfig = CONFIG, soc_pct: float = 50.0) -> Battery:
    b = Battery(config)
    b.update(T0, Reading(soc_pct, power_w=0.0))
    return b


def test_unknown_until_a_state_of_charge_then_started_from_it():
    b = Battery(CONFIG)
    b.update(T0, Reading(None, power_w=0.0))
    assert b.energy_kwh is None and b.room_kwh is None and b.soc_pct is None and b.uncertainty_kwh is None
    b.update(at(1), Reading(54.5, power_w=0.0))
    assert b.energy_kwh == pytest.approx(FULL_KWH / 2)
    assert b.soc_pct == pytest.approx(54.5)
    assert b.last_landmark is None and b.last_landmark_at is None
    # The BMS's state of charge was off by up to 2 kWh (2026-10-28 to 11-07)
    assert b.uncertainty_kwh == pytest.approx(2.0)


def test_a_configured_full_energy():
    b = battery(BatteryConfig(19.2, full_energy_kwh=16.0), soc_pct=54.5)
    assert b.energy_kwh == pytest.approx(8.0)


def test_the_power_is_counted_with_the_round_trip_on_the_way_in():
    b = battery()
    start = b.energy_kwh
    assert start is not None
    b.update(at(0), Reading(50.0, power_w=2000.0))
    b.update(at(60), Reading(55.0, power_w=-1000.0))
    assert b.energy_kwh == pytest.approx(start + 0.96 * 2.0)
    b.update(at(120), Reading(50.0, power_w=0.0))
    assert b.energy_kwh == pytest.approx(start + 0.96 * 2.0 - 1.0)
    # 2 % of the 3 kWh counted on top of the start's 2 kWh
    assert b.uncertainty_kwh == pytest.approx(2.06)


def test_a_reading_older_than_the_last_counts_no_interval():
    b = battery()
    b.update(at(0), Reading(50.0, power_w=2000.0))
    b.update(at(60), Reading(55.0, power_w=2000.0))
    energy = b.energy_kwh
    b.update(at(30), Reading(55.0, power_w=2000.0))
    assert b.energy_kwh == energy


def test_a_reading_out_of_order_is_ignored():
    b = battery()
    b.update(at(0), Reading(50.0, power_w=2000.0))
    b.update(at(60), Reading(55.0, power_w=0.0))
    energy = b.energy_kwh
    # An older reading arriving late: the newer one's power (0) still holds
    b.update(at(30), Reading(55.0, power_w=2000.0))
    b.update(at(120), Reading(55.0, power_w=0.0))
    assert b.energy_kwh == energy


def test_a_non_finite_value_is_unavailable():
    b = battery()
    start = b.energy_kwh
    b.update(at(0), Reading(float("nan"), power_w=float("inf")))
    b.update(at(60), Reading(50.0, power_w=0.0))
    assert b.energy_kwh == start
    b.update(at(61), Reading(50.0, power_w=float("nan")))
    b.update(at(62), Reading(50.0, power_w=0.0))
    assert b.energy_kwh == start


def test_an_unavailable_state_of_charge_keeps_the_estimate():
    b = battery()
    b.update(at(0), Reading(50.0, power_w=1000.0))
    b.update(at(60), Reading(None, power_w=0.0))
    assert b.energy_kwh == pytest.approx(FULL_KWH * 41 / 91 + 0.96)
    assert b.soc_pct is not None


@pytest.mark.parametrize(
    "config",
    [
        {"empty_soc_pct": 100.0},
        {"empty_soc_pct": -1.0},
        {"nominal_capacity_kwh": 0.0},
        {"full_energy_kwh": 0.0},
        {"efficiency": 0.0},
        {"max_power_kw": 0.0},
    ],
)
def test_a_configuration_without_energy_between_the_landmarks_is_refused(config):
    with pytest.raises(ValueError):
        BatteryConfig(**({"nominal_capacity_kwh": 19.2} | config))


def test_an_unavailable_power_pauses_the_counting():
    b = battery()
    start = b.energy_kwh
    b.update(at(0), Reading(50.0, power_w=None))
    b.update(at(60), Reading(50.0, power_w=0.0))
    assert b.energy_kwh == start


def test_the_meters_fill_what_the_power_missed():
    b = battery(BatteryConfig(19.2, has_meters=True))
    start = b.energy_kwh
    assert start is not None
    b.update(at(0), Reading(50.0, power_w=-1000.0, charged_kwh=5.0, discharged_kwh=1.0))
    b.update(at(30), Reading(50.0, power_w=None, charged_kwh=5.0, discharged_kwh=1.5))
    # Down for an hour, discharging 1 kW: the meters count it at their next reading
    b.update(at(90), Reading(50.0, power_w=-1000.0, charged_kwh=5.0, discharged_kwh=2.5))
    assert b.energy_kwh == pytest.approx(start - 1.5)
    # The power back, the meters no longer count: their next increase is the power's
    b.update(at(120), Reading(50.0, power_w=-1000.0, charged_kwh=5.0, discharged_kwh=3.0))
    assert b.energy_kwh == pytest.approx(start - 2.0)


def test_one_meter_unavailable_keeps_both_bases():
    b = battery(BatteryConfig(19.2, has_power=False, has_meters=True))
    start = b.energy_kwh
    assert start is not None
    b.update(at(0), Reading(50.0, charged_kwh=5.0, discharged_kwh=1.0))
    b.update(at(30), Reading(50.0, charged_kwh=None, discharged_kwh=1.5))
    # Counted from the last reading with both: the discharge's 0.5 kWh is not lost
    b.update(at(60), Reading(50.0, charged_kwh=5.0, discharged_kwh=2.0))
    assert b.energy_kwh == pytest.approx(start - 1.0)


def test_a_meter_reset_during_a_power_gap_counts_what_it_counted_since():
    b = battery(BatteryConfig(19.2, has_meters=True))
    start = b.energy_kwh
    assert start is not None
    b.update(at(0), Reading(50.0, power_w=-1000.0, charged_kwh=5.0, discharged_kwh=20.0))
    b.update(at(30), Reading(50.0, power_w=None, charged_kwh=5.0, discharged_kwh=20.5))
    # Midnight: the daily meter starts again from 0 and has counted 0.4 kWh since
    b.update(at(60), Reading(50.0, power_w=-1000.0, charged_kwh=0.0, discharged_kwh=0.4))
    assert b.energy_kwh == pytest.approx(start - 0.5 - 0.4)


def test_a_spurious_meter_jump_during_a_power_gap_counts_nothing():
    b = battery(BatteryConfig(19.2, has_meters=True))
    start = b.energy_kwh
    assert start is not None
    b.update(at(0), Reading(50.0, power_w=-1000.0, charged_kwh=5.0, discharged_kwh=1.0))
    b.update(at(30), Reading(50.0, power_w=None, charged_kwh=5.0, discharged_kwh=1.5))
    # 100 kWh in 30 min: beyond what the battery's 30 kW allows
    b.update(at(60), Reading(50.0, power_w=-1000.0, charged_kwh=5.0, discharged_kwh=101.5))
    assert b.energy_kwh == pytest.approx(start - 0.5)


def test_without_a_power_the_meters_count_with_their_daily_reset():
    b = battery(BatteryConfig(19.2, has_power=False, has_meters=True))
    start = b.energy_kwh
    assert start is not None
    b.update(at(0), Reading(50.0, charged_kwh=24.0, discharged_kwh=20.0))
    b.update(at(60), Reading(50.0, charged_kwh=24.2, discharged_kwh=21.0))
    # Midnight: the Growatt counters start again from 0
    b.update(at(120), Reading(50.0, charged_kwh=0.3, discharged_kwh=0.0))
    assert b.energy_kwh == pytest.approx(start + 0.96 * (0.2 + 0.3) - 1.0)
    # A jump beyond 30 kW since the last reading is no measure
    b.update(at(121), Reading(50.0, charged_kwh=50.0, discharged_kwh=0.0))
    assert b.energy_kwh == pytest.approx(start + 0.96 * 0.5 - 1.0)


def test_the_empty_landmark_when_the_state_of_charge_crosses_its_threshold():
    b = battery(soc_pct=12.0)
    b.update(at(0), Reading(12.0, power_w=-1000.0))
    b.update(at(60), Reading(10.0, power_w=-1000.0))
    counted = b.energy_kwh
    assert counted is not None
    b.update(at(70), Reading(9.0, power_w=0.0))
    assert b.energy_kwh == 0.0 and b.soc_pct == pytest.approx(9.0)
    assert b.last_landmark == EMPTY and b.last_landmark_at == at(70)
    assert b.last_landmark_error_kwh == pytest.approx(counted - 1.0 / 6)
    assert b.uncertainty_kwh == pytest.approx(0.8)
    assert b.room_kwh == pytest.approx(FULL_KWH)


def test_the_state_of_charge_jittering_at_the_threshold_is_one_landmark():
    b = battery(soc_pct=10.0)
    b.update(at(0), Reading(9.0, power_w=-200.0))
    b.update(at(60), Reading(10.0, power_w=-200.0))
    b.update(at(61), Reading(9.0, power_w=-200.0))
    assert b.last_landmark_at == at(0)
    assert b.energy_kwh == pytest.approx(-0.2 - 0.2 / 60)
    # Back 2 points above the threshold, the landmark is armed again
    b.update(at(62), Reading(11.0, power_w=0.0))
    b.update(at(63), Reading(9.0, power_w=0.0))
    assert b.last_landmark_at == at(63)


def test_the_full_landmark_at_a_cell_s_full_voltage():
    b = battery(soc_pct=95.0)
    b.update(at(0), Reading(96.0, power_w=2000.0, cell_high_v=3.49))
    b.update(at(10), Reading(97.0, power_w=1500.0, cell_high_v=3.50))
    assert b.last_landmark == FULL and b.energy_kwh == pytest.approx(FULL_KWH)
    assert b.soc_pct == 100.0 and b.room_kwh == 0.0
    assert b.uncertainty_kwh == pytest.approx(0.4)
    # The charge goes on to the BMS's 100 %: above the landmark, no new one
    b.update(at(30), Reading(100.0, power_w=0.0, cell_high_v=3.55))
    assert b.last_landmark_at == at(10)
    assert b.energy_kwh == pytest.approx(FULL_KWH + 0.96 * 0.5)
    assert b.soc_pct == 100.0


def test_the_full_landmark_is_armed_again_once_a_kwh_went_out():
    b = battery(soc_pct=97.0)
    b.update(at(0), Reading(97.0, power_w=-1000.0, cell_high_v=3.5))
    # 0.83 kWh out: still the same landmark
    b.update(at(50), Reading(94.0, power_w=-1000.0, cell_high_v=3.5))
    assert b.last_landmark_at == at(0)
    b.update(at(70), Reading(93.0, power_w=2000.0, cell_high_v=3.4))
    b.update(at(100), Reading(97.0, power_w=0.0, cell_high_v=3.5))
    assert b.last_landmark_at == at(100)


def test_without_cell_voltages_the_full_landmark_is_the_state_of_charge_at_100():
    b = battery(BatteryConfig(19.2, full_cell_v=None), soc_pct=99.0)
    b.update(at(0), Reading(99.0, power_w=1000.0, cell_high_v=3.6))
    assert b.last_landmark is None
    b.update(at(10), Reading(100.0, power_w=0.0))
    assert b.last_landmark == FULL and b.energy_kwh == pytest.approx(FULL_KWH)


def test_the_counting_is_dropped_when_it_left_the_state_of_charge_far_behind():
    b = battery(soc_pct=50.0)
    b.update(at(0), Reading(50.0, power_w=4000.0))
    # 4 kWh in, the state of charge has not moved: a meter or a sign is wrong
    b.update(at(60), Reading(50.0, power_w=0.0))
    assert b.energy_kwh == pytest.approx(FULL_KWH * 41 / 91)
    # Restarted from the state of charge: its 2 kWh uncertainty, nothing counted since
    assert b.uncertainty_kwh == pytest.approx(2.0) and b.last_landmark is None


def test_the_round_trip_and_the_full_energy_learned_on_cycles():
    b = battery(BatteryConfig(19.2, learn=True), soc_pct=10.0)
    for day in range(4):
        base = day * 1092
        # Empty, 18 kWh in for 8 h, full; 17.3 kWh out for 10 h, empty again
        b.update(at(base), Reading(10.0, power_w=-100.0))
        b.update(at(base + 6), Reading(9.0, power_w=2250.0))
        b.update(at(base + 486), Reading(97.0, power_w=-1730.0, cell_high_v=3.5))
        b.update(at(base + 1086), Reading(10.0, power_w=-100.0, cell_high_v=3.3))
    # 0.01 kWh out before each empty landmark, 0.01 after
    assert b.learned_efficiency == pytest.approx(17.32 / 18.0, abs=0.001)
    assert b.learned_full_energy_kwh == pytest.approx(17.3, abs=0.2)
    assert b.efficiency == b.learned_efficiency
    assert b.full_energy_kwh == b.learned_full_energy_kwh


def test_a_learned_value_is_used_only_from_three_cycles_and_with_learning_on():
    b = battery(BatteryConfig(19.2, learn=True), soc_pct=97.0)
    b.update(at(0), Reading(97.0, power_w=-2000.0, cell_high_v=3.5))
    b.update(at(540), Reading(10.0, power_w=2000.0, cell_high_v=3.3))
    b.update(at(1080), Reading(97.0, power_w=0.0, cell_high_v=3.5))
    assert b.learned_efficiency == pytest.approx(1.0)
    assert b.efficiency == 0.96
    off = battery(BatteryConfig(19.2), soc_pct=97.0)
    for minutes, soc, power, cell in ((0, 97.0, -2000.0, 3.5), (540, 10.0, 2000.0, 3.3), (1080, 97.0, 0.0, 3.5)):
        off.update(at(minutes), Reading(soc, power_w=power, cell_high_v=cell))
    assert off.learned_efficiency == pytest.approx(1.0) and off.efficiency == 0.96


def test_a_short_or_impossible_cycle_teaches_nothing():
    b = battery(soc_pct=97.0)
    # Half the battery did not flow: the landmarks' spread would weigh too much
    b.update(at(0), Reading(97.0, power_w=-1000.0, cell_high_v=3.5))
    b.update(at(120), Reading(85.0, power_w=2000.0, cell_high_v=3.3))
    b.update(at(180), Reading(97.0, power_w=-2000.0, cell_high_v=3.5))
    assert b.learned_efficiency is None
    # 10 kWh out for 18 in between two full landmarks: a meter missed a flow
    b.update(at(480), Reading(50.0, power_w=2000.0, cell_high_v=3.3))
    b.update(at(1020), Reading(97.0, power_w=0.0, cell_high_v=3.5))
    assert b.learned_efficiency is None


def test_unseen_flows_teach_nothing():
    b = battery(soc_pct=97.0)
    b.update(at(0), Reading(97.0, power_w=-2000.0, cell_high_v=3.5))
    b.update(at(270), Reading(50.0, power_w=None, cell_high_v=3.3))
    b.update(at(300), Reading(45.0, power_w=-2000.0, cell_high_v=3.3))
    b.update(at(540), Reading(9.0, power_w=2000.0, cell_high_v=3.3))
    b.update(at(1080), Reading(97.0, power_w=0.0, cell_high_v=3.5))
    # Only the charge after the empty landmark was fully seen: 18 kWh in, 17.28 stored
    assert b.learned_efficiency is None
    assert b.learned_full_energy_kwh == pytest.approx(17.28)


def test_a_power_gap_before_the_meters_first_reading_teaches_nothing():
    b = battery(BatteryConfig(19.2, has_meters=True), soc_pct=97.0)
    b.update(at(0), Reading(97.0, power_w=-2000.0, cell_high_v=3.5))
    b.update(at(270), Reading(50.0, power_w=None, cell_high_v=3.3))
    # The meters' first reading: no base to count the gap from
    b.update(at(300), Reading(45.0, power_w=-2000.0, charged_kwh=1.0, discharged_kwh=9.0, cell_high_v=3.3))
    b.update(at(540), Reading(9.0, power_w=2000.0, charged_kwh=1.0, discharged_kwh=17.0, cell_high_v=3.3))
    b.update(at(1080), Reading(97.0, power_w=0.0, charged_kwh=19.0, discharged_kwh=17.0, cell_high_v=3.5))
    assert b.learned_efficiency is None
    assert b.learned_full_energy_kwh == pytest.approx(17.28)


def test_landmarks_told_by_the_user_teach_nothing():
    b = battery(soc_pct=50.0)
    b.mark_full(at(0))
    assert b.last_landmark == FULL and b.energy_kwh == pytest.approx(FULL_KWH)
    b.update(at(0), Reading(97.0, power_w=-2000.0, cell_high_v=3.3))
    b.update(at(540), Reading(10.0, power_w=0.0))
    b.mark_empty(at(540))
    assert b.last_landmark == EMPTY and b.energy_kwh == 0.0
    b.update(at(541), Reading(9.0, power_w=2000.0))
    # Told empty: the state of charge crossing just after is the same landmark
    assert b.last_landmark_at == at(540)
    b.update(at(1080), Reading(97.0, power_w=0.0, cell_high_v=3.5))
    assert b.learned_efficiency is None and b.learned_full_energy_kwh is None


def test_landmarks_told_by_the_user_with_an_estimate():
    b = battery()
    b.mark_full(at(0))
    assert b.energy_kwh == pytest.approx(FULL_KWH) and b.uncertainty_kwh == pytest.approx(0.4)
    assert b.last_landmark == FULL and b.last_landmark_at == at(0)
    b.mark_empty(at(1))
    assert b.energy_kwh == 0.0 and b.uncertainty_kwh == pytest.approx(0.8) and b.last_landmark == EMPTY
    # Not seen again until the state of charge left it
    b.update(at(2), Reading(10.0, power_w=0.0))
    b.update(at(3), Reading(9.0, power_w=0.0))
    assert b.last_landmark_at == at(1)


def test_the_last_full_and_empty_times_outlive_the_counting_s_restarts():
    b = battery(soc_pct=10.0)
    assert b.last_full_at is None and b.last_empty_at is None
    b.update(at(0), Reading(9.0, power_w=2000.0, cell_high_v=3.2))
    b.update(at(540), Reading(97.0, power_w=-1000.0, cell_high_v=3.5))
    assert (b.last_full_at, b.last_empty_at) == (at(540), at(0))
    # Neither an energy set by the user nor a restart from the state of charge is a landmark: both times stay
    b.set_energy(at(600), 8.0)
    b.update(at(601), Reading(90.0, power_w=0.0, cell_high_v=3.3))
    assert b.last_landmark is None
    assert (b.last_full_at, b.last_empty_at) == (at(540), at(0))
    # A landmark told counts as one
    b.mark_empty(at(700))
    assert (b.last_full_at, b.last_empty_at) == (at(540), at(700))
    b.mark_full(at(800))
    assert (b.last_full_at, b.last_empty_at) == (at(800), at(700))


@pytest.mark.parametrize(
    ("start", "full_at", "empty_at"),
    [("full", T0, None), ("empty", None, T0), ("soc", None, None)],
)
def test_a_state_saved_by_0_1_0_knows_its_last_landmark_from_its_start(start, full_at, empty_at):
    state = state_from_dict({"version": 1, "energy_kwh": 5.0, "start": start, "start_at": T0.isoformat()})
    assert (state.last_full_at, state.last_empty_at) == (full_at, empty_at)


def test_a_last_full_time_saved_unknown_stays_unknown():
    stored = {"energy_kwh": 5.0, "start": "full", "start_at": T0.isoformat(), "last_full_at": None}
    assert state_from_dict(stored).last_full_at is None


def test_the_last_full_and_empty_times_survive_a_restart():
    b = battery(soc_pct=10.0)
    b.update(at(0), Reading(9.0, power_w=2000.0, cell_high_v=3.2))
    b.update(at(540), Reading(97.0, power_w=0.0, cell_high_v=3.5))
    b.set_energy(at(600), 8.0)
    restored = Battery(CONFIG, state_from_dict(state_to_dict(b.state)))
    assert (restored.last_full_at, restored.last_empty_at) == (at(540), at(0))


def test_the_state_carries_its_version():
    assert state_to_dict(BatteryState())["version"] == STATE_VERSION


def test_an_energy_set_by_the_user():
    b = battery()
    b.set_energy(at(0), 8.0)
    assert b.energy_kwh == 8.0 and b.last_landmark is None and b.uncertainty_kwh == pytest.approx(0.5)
    b.set_energy(at(1), float("nan"))
    assert b.energy_kwh == 8.0


def test_a_restart_does_not_hold_the_power_over_the_downtime():
    b = battery()
    b.update(at(0), Reading(50.0, power_w=2000.0))
    energy = b.energy_kwh
    restored = Battery(CONFIG, state_from_dict(state_to_dict(b.state)))
    restored.resume()
    restored.update(at(60), Reading(50.0, power_w=2000.0))
    assert restored.energy_kwh == energy


def test_after_a_restart_the_meters_count_the_downtime():
    config = BatteryConfig(19.2, has_meters=True)
    b = battery(config)
    b.update(at(0), Reading(50.0, power_w=-1000.0, charged_kwh=5.0, discharged_kwh=1.0))
    b.update(at(30), Reading(50.0, power_w=-1000.0, charged_kwh=5.0, discharged_kwh=1.5))
    energy = b.energy_kwh
    assert energy is not None
    restored = Battery(config, state_from_dict(state_to_dict(b.state)))
    restored.resume()
    # Down for 2 hours at 1 kW out; the first reading after the restart has its meters
    restored.update(at(150), Reading(50.0, power_w=-1000.0, charged_kwh=5.0, discharged_kwh=3.5))
    assert restored.energy_kwh == pytest.approx(energy - 2.0)
    restored.update(at(180), Reading(50.0, power_w=-1000.0, charged_kwh=5.0, discharged_kwh=4.0))
    assert restored.energy_kwh == pytest.approx(energy - 2.5)


def test_a_replaced_meter_with_a_power_teaches_nothing_and_keeps_the_power():
    b = battery(BatteryConfig(19.2, has_meters=True), soc_pct=9.5)
    b.update(at(0), Reading(8.0, power_w=2000.0, charged_kwh=1.0, discharged_kwh=1.0, cell_high_v=3.3))
    b.forget_meters()
    b.update(at(540), Reading(97.0, power_w=0.0, charged_kwh=0.0, discharged_kwh=0.0, cell_high_v=3.5))
    # The 18 kWh the power counted from the empty landmark still count (0.96 × 18 against 17.47); the cycle up to
    # full teaches nothing
    assert b.last_landmark == FULL
    assert b.last_landmark_error_kwh == pytest.approx(0.96 * 18.0 - FULL_KWH)
    assert b.learned_full_energy_kwh is None


def test_a_replaced_meter_is_counted_from_its_first_reading():
    b = battery(BatteryConfig(19.2, has_power=False, has_meters=True))
    start = b.energy_kwh
    b.update(at(0), Reading(50.0, charged_kwh=10.0, discharged_kwh=5.0))
    b.forget_meters()
    b.update(at(10), Reading(50.0, charged_kwh=1.0, discharged_kwh=0.5))
    assert b.energy_kwh == start


def test_the_state_survives_a_round_trip():
    b = battery(BatteryConfig(19.2, has_meters=True), soc_pct=97.0)
    b.update(at(0), Reading(97.0, power_w=-2000.0, charged_kwh=1.0, discharged_kwh=2.0, cell_high_v=3.5))
    b.update(at(540), Reading(9.0, power_w=2000.0, charged_kwh=1.0, discharged_kwh=20.0, cell_high_v=3.3))
    b.update(at(1080), Reading(97.0, power_w=0.0, charged_kwh=19.0, discharged_kwh=20.0, cell_high_v=3.5))
    restored = state_from_dict(state_to_dict(b.state))
    assert restored == b.state


@pytest.mark.parametrize(
    "stored",
    [None, [], {"energy_kwh": "x"}, {"energy_kwh": 5.0}, {"energy_kwh": 5.0, "start": "nowhere"}],
)
def test_an_unreadable_state_starts_again_from_the_state_of_charge(stored):
    state = state_from_dict(stored)
    assert state.energy_kwh is None and state.start is None
    b = Battery(CONFIG, state)
    b.update(T0, Reading(54.5, power_w=0.0))
    assert b.energy_kwh == pytest.approx(FULL_KWH / 2)


def test_unreadable_learned_values_are_dropped():
    state = state_from_dict(
        {
            "energy_kwh": 5.0,
            "start": "full",
            "start_at": "2026-11-06T22:00:00",  # no zone
            "updated_at": "yesterday",
            "efficiency_in_kwh": 10.0,
            "efficiency_out_kwh": -1.0,
            "efficiency_cycles": 4,
            "learned_full_energy_kwh": float("inf"),
            "full_energy_cycles": True,
            "since_full": {"charged_kwh": "a", "complete": True},
            "since_empty": "x",
            "last_landmark_kind": "soc",
        }
    )
    assert state == BatteryState(
        energy_kwh=5.0,
        start=FULL,
        since_full=state.since_full,
    )
    assert state.since_full.charged_kwh == 0.0 and state.since_full.complete
    assert not state.since_empty.complete
