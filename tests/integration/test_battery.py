"""Tests — the integration in Home Assistant: config flow, entities following the measures, landmarks, restart,
services, unavailable or missing sources, diagnostics."""

from datetime import timedelta

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from probatio import Invalid
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed
from pytest_homeassistant_custom_component.components.diagnostics import get_diagnostics_for_config_entry
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from custom_components.smart_hass_battery.const import DOMAIN

SOC, POWER = "sensor.bms_soc", "sensor.battery_power"
CHARGED, DISCHARGED = "sensor.battery_energy_in", "sensor.battery_energy_out"
CELLS = ["sensor.pack_1_cell_high", "sensor.pack_2_cell_high"]
SOURCES = {"soc_entity": SOC, "power_entity": POWER, "cell_voltage_entities": CELLS}
BATTERY = {
    "nominal_capacity_kwh": 19.2,
    "empty_soc_pct": 9.0,
    "full_cell_v": 3.5,
    "efficiency_pct": 96.0,
    "max_power_kw": 30.0,
}
OPTIONS = {**SOURCES, **BATTERY}
FULL_KWH = 19.2 * 0.91  # the nominal capacity above the 9 % empty threshold
ENERGY, PCT, ROOM = "sensor.battery_stored_energy", "sensor.battery_state_of_charge", "sensor.battery_room_to_full"
LANDMARK = "sensor.battery_last_landmark"


def _measures(hass: HomeAssistant, soc_pct: float = 54.5, power_w: float = 0.0, cell_v: float = 3.3) -> None:
    hass.states.async_set(SOC, str(soc_pct), {"unit_of_measurement": "%"})
    hass.states.async_set(POWER, str(power_w), {"unit_of_measurement": "W"})
    for cell in CELLS:
        hass.states.async_set(cell, str(cell_v), {"unit_of_measurement": "V"})


def _meters(hass: HomeAssistant, charged_kwh: float, discharged_kwh: float) -> None:
    hass.states.async_set(CHARGED, str(charged_kwh), {"unit_of_measurement": "kWh"})
    hass.states.async_set(DISCHARGED, str(discharged_kwh), {"unit_of_measurement": "kWh"})


async def _setup(hass: HomeAssistant, options: dict | None = None, entry_id: str | None = None) -> MockConfigEntry:
    options = OPTIONS if options is None else options
    kwargs = {} if entry_id is None else {"entry_id": entry_id}
    entry = MockConfigEntry(domain=DOMAIN, title="Battery", options=options, unique_id=SOC, **kwargs)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _value(hass: HomeAssistant, entity_id: str) -> float:
    return float(hass.states.get(entity_id).state)


async def _later(hass: HomeAssistant, freezer: FrozenDateTimeFactory, delay: timedelta) -> None:
    """Home Assistant's timers read the clock when they fire: move it, then fire them."""
    freezer.tick(delay)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


async def _call(hass: HomeAssistant, service: str, entry: MockConfigEntry, **data: object) -> None:
    await hass.services.async_call(DOMAIN, service, {"config_entry_id": entry.entry_id, **data}, blocking=True)


# --- Config flow ---


async def test_config_flow_creates_the_entry(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"name": "Battery", **OPTIONS})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Battery" and result["options"] == OPTIONS
    assert result["result"].unique_id == SOC


@pytest.mark.parametrize(
    ("sources", "error"),
    [
        ({"soc_entity": SOC}, "no_flow_source"),
        ({"soc_entity": SOC, "power_entity": POWER, "charged_entity": CHARGED}, "one_meter"),
    ],
)
async def test_config_flow_needs_the_flows(hass: HomeAssistant, sources: dict, error: str) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"name": "Battery", **sources, **BATTERY}
    )
    assert result["type"] is FlowResultType.FORM and result["errors"] == {"base": error}
    # Meters alone are enough
    meters = {"soc_entity": SOC, "charged_entity": CHARGED, "discharged_entity": DISCHARGED}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"name": "Battery", **meters, **BATTERY})
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_config_flow_refuses_an_energy_above_the_capacity(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"name": "Battery", **OPTIONS, "full_energy_kwh": 20.0}
    )
    assert result["errors"] == {"base": "full_energy_above_capacity"}


async def test_one_entry_per_state_of_charge(hass: HomeAssistant) -> None:
    await _setup(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"name": "Again", **OPTIONS})
    assert result["type"] is FlowResultType.ABORT and result["reason"] == "already_configured"


async def test_options_flow_reloads_with_the_new_battery(hass: HomeAssistant) -> None:
    _measures(hass, soc_pct=100.0)  # a state of charge far from full would restart the counting from it
    entry = await _setup(hass)
    await _call(hass, "mark_full", entry)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {**BATTERY, "full_energy_kwh": 17.2, "learn": True}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.options == {**OPTIONS, "full_energy_kwh": 17.2, "learn": True}  # the sources kept
    # Full stays full: the landmark's energy is the restored estimate, the room is 0
    assert _value(hass, ROOM) == 0.0
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {**BATTERY, "nominal_capacity_kwh": 10.0, "full_energy_kwh": 17.2}
    )
    assert result["errors"] == {"base": "full_energy_above_capacity"}


async def test_reconfigure_replaces_the_meters(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    """New meters' values are no flow: counted from their first reading. The battery and its estimate stay."""
    _measures(hass)
    _meters(hass, 5.0, 3.0)
    # Close to the old ones: taken for an increase of them, 1 kWh out would be counted
    hass.states.async_set("sensor.new_in", "5", {"unit_of_measurement": "kWh"})
    hass.states.async_set("sensor.new_out", "4", {"unit_of_measurement": "kWh"})
    entry = await _setup(hass, {**OPTIONS, "charged_entity": CHARGED, "discharged_entity": DISCHARGED})
    await _call(hass, "set_energy", entry, energy_kwh=10.0)
    result = await entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM and result["step_id"] == "reconfigure"
    sources = {**SOURCES, "charged_entity": "sensor.new_in", "discharged_entity": "sensor.new_out"}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], sources)
    assert result["type"] is FlowResultType.ABORT and result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()
    assert entry.options == {**BATTERY, **sources}
    assert _value(hass, ENERGY) == pytest.approx(10.0, abs=0.01)
    hass.states.async_set("sensor.new_out", "5.5", {"unit_of_measurement": "kWh"})
    await hass.async_block_till_done()
    assert _value(hass, ENERGY) == pytest.approx(10.0, abs=0.01)  # the power counted it (0 W): no gap to fill
    hass.states.async_set(POWER, "unavailable")
    await hass.async_block_till_done()
    freezer.tick(timedelta(minutes=10))  # a meter's increase is bounded by the maximum power over the time elapsed
    hass.states.async_set("sensor.new_out", "6.5", {"unit_of_measurement": "kWh"})
    await hass.async_block_till_done()
    assert _value(hass, ENERGY) == pytest.approx(9.0, abs=0.01)  # the new meter counts the power's gap


async def test_reconfigure_checks_the_sources(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    MockConfigEntry(domain=DOMAIN, title="Other", options=OPTIONS, unique_id="sensor.other_soc").add_to_hass(hass)
    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"soc_entity": SOC})
    assert result["type"] is FlowResultType.FORM and result["errors"] == {"base": "no_flow_source"}
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"soc_entity": SOC, "discharged_entity": DISCHARGED}
    )
    assert result["errors"] == {"base": "one_meter"}
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"soc_entity": "sensor.other_soc", "power_entity": POWER}
    )
    assert result["type"] is FlowResultType.ABORT and result["reason"] == "already_configured"
    assert entry.unique_id == SOC


# --- The estimate ---


async def test_started_from_the_state_of_charge(hass: HomeAssistant) -> None:
    _measures(hass, soc_pct=54.5)
    await _setup(hass)
    assert _value(hass, ENERGY) == pytest.approx(FULL_KWH / 2, abs=0.001)
    assert _value(hass, PCT) == pytest.approx(54.5)
    assert _value(hass, ROOM) == pytest.approx(FULL_KWH / 2, abs=0.001)
    assert _value(hass, "sensor.battery_uncertainty") == pytest.approx(2.0)
    assert hass.states.get(LANDMARK).state == "unknown"


async def test_the_power_is_counted_while_it_holds(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    _measures(hass)
    entry = await _setup(hass)
    await _call(hass, "set_energy", entry, energy_kwh=8.0)
    hass.states.async_set(POWER, "2", {"unit_of_measurement": "kW"})
    await hass.async_block_till_done()
    # No new state for an hour: the refresh counts it (96 % on the way in)
    await _later(hass, freezer, timedelta(minutes=60))
    assert _value(hass, ENERGY) == pytest.approx(8.0 + 0.96 * 2.0, abs=0.01)


async def test_an_inverted_power(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    _measures(hass)
    entry = await _setup(hass, {**OPTIONS, "invert_power": True})
    await _call(hass, "set_energy", entry, energy_kwh=8.0)
    hass.states.async_set(POWER, "1000", {"unit_of_measurement": "W"})  # discharging, for this inverter
    await hass.async_block_till_done()
    await _later(hass, freezer, timedelta(minutes=60))
    assert _value(hass, ENERGY) == pytest.approx(7.0, abs=0.01)


async def test_the_full_landmark_at_the_highest_cell(hass: HomeAssistant) -> None:
    _measures(hass, soc_pct=95.0)
    await _setup(hass)
    hass.states.async_set(CELLS[0], "unavailable")
    hass.states.async_set(CELLS[1], "3500", {"unit_of_measurement": "mV"})
    await hass.async_block_till_done()
    assert _value(hass, ENERGY) == pytest.approx(FULL_KWH, abs=0.001)
    assert _value(hass, ROOM) == 0.0
    landmark = hass.states.get(LANDMARK)
    assert landmark.state != "unknown" and landmark.attributes["kind"] == "full"
    # The counting was at the state of charge's 95 %: its error at the landmark
    assert landmark.attributes["error_kwh"] == pytest.approx(-FULL_KWH * 5 / 91, abs=0.001)


async def test_without_cells_the_full_landmark_is_the_state_of_charge_at_100(hass: HomeAssistant) -> None:
    _measures(hass, soc_pct=99.0)
    await _setup(hass, {**OPTIONS, "cell_voltage_entities": []})
    hass.states.async_set(SOC, "100", {"unit_of_measurement": "%"})
    await hass.async_block_till_done()
    assert hass.states.get(LANDMARK).attributes["kind"] == "full"


async def test_the_empty_landmark_and_the_user_s_landmarks(hass: HomeAssistant) -> None:
    _measures(hass, soc_pct=10.0)
    entry = await _setup(hass)
    hass.states.async_set(SOC, "9", {"unit_of_measurement": "%"})
    await hass.async_block_till_done()
    assert _value(hass, ENERGY) == 0.0 and hass.states.get(LANDMARK).attributes["kind"] == "empty"
    await _call(hass, "mark_full", entry)
    assert _value(hass, ENERGY) == pytest.approx(FULL_KWH, abs=0.001)
    assert _value(hass, "sensor.battery_uncertainty") == pytest.approx(0.4)
    await _call(hass, "mark_empty", entry)
    assert _value(hass, ENERGY) == 0.0 and hass.states.get(LANDMARK).attributes["kind"] == "empty"


async def test_the_energy_tells_when_the_battery_was_last_full_and_empty(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    _measures(hass, soc_pct=10.0)
    entry = await _setup(hass)
    attributes = hass.states.get(ENERGY).attributes
    assert (attributes["last_full_at"], attributes["last_empty_at"]) == (None, None)
    hass.states.async_set(SOC, "9", {"unit_of_measurement": "%"})
    await hass.async_block_till_done()
    empty_at = hass.states.get(ENERGY).attributes["last_empty_at"]
    assert empty_at == dt_util.utcnow().isoformat()
    freezer.tick(timedelta(hours=1))
    await _call(hass, "mark_full", entry)
    full_at = dt_util.utcnow().isoformat()
    # A set energy is no landmark: the last landmark is gone, not when the battery was full or empty
    await _call(hass, "set_energy", entry, energy_kwh=8.0)
    attributes = hass.states.get(ENERGY).attributes
    assert attributes["last_landmark"] is None
    assert (attributes["last_full_at"], attributes["last_empty_at"]) == (full_at, empty_at)


async def test_the_services_refuse_an_unknown_entry_or_energy(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(DOMAIN, "mark_full", {"config_entry_id": "nope"}, blocking=True)
    with pytest.raises(Invalid):
        await _call(hass, "set_energy", entry, energy_kwh="nan")
    assert await hass.config_entries.async_unload(entry.entry_id)
    with pytest.raises(ServiceValidationError):
        await _call(hass, "mark_full", entry)


async def test_learned_values_published(hass: HomeAssistant) -> None:
    _measures(hass)
    await _setup(hass)
    efficiency = hass.states.get("sensor.battery_learned_round_trip")
    assert efficiency.state == "unknown"  # no cycle yet
    assert efficiency.attributes["configured_efficiency"] == 0.96
    assert (efficiency.attributes["efficiency_in_use"], efficiency.attributes["cycles"]) == (0.96, 0)
    assert efficiency.attributes["learning_enabled"] is False
    full = hass.states.get("sensor.battery_learned_energy_between_the_landmarks")
    assert full.state == "unknown"
    assert full.attributes["configured_full_energy_kwh"] == pytest.approx(FULL_KWH, abs=0.001)
    registry = er.async_get(hass)
    assert registry.async_get("sensor.battery_learned_round_trip").entity_category is er.EntityCategory.DIAGNOSTIC
    assert registry.async_get(ENERGY).entity_category is None


async def test_the_energy_gives_a_planner_the_battery_and_its_sources(hass: HomeAssistant) -> None:
    _measures(hass)
    entry = await _setup(hass)
    await _call(hass, "set_energy", entry, energy_kwh=8.0)
    attributes = hass.states.get(ENERGY).attributes
    assert (attributes["nominal_capacity_kwh"], attributes["efficiency"], attributes["empty_soc_pct"]) == (
        19.2,
        0.96,
        9.0,
    )
    assert attributes["full_energy_kwh"] == pytest.approx(FULL_KWH, abs=0.001)
    assert attributes["room_kwh"] == pytest.approx(FULL_KWH - 8.0, abs=0.001)
    assert attributes["uncertainty_kwh"] == pytest.approx(0.5)
    assert attributes["soc_pct"] == pytest.approx(9.0 + 91.0 * 8.0 / FULL_KWH, abs=0.1)
    assert (attributes["last_landmark"], attributes["last_landmark_at"]) == (None, None)
    assert (attributes["soc_entity"], attributes["power_entity"], attributes["charged_entity"]) == (SOC, POWER, None)


# --- Restart ---


async def test_the_estimate_survives_a_restart(hass: HomeAssistant) -> None:
    _measures(hass)
    entry = await _setup(hass)
    await _call(hass, "set_energy", entry, energy_kwh=8.0)
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert _value(hass, ENERGY) == pytest.approx(8.0, abs=0.01)


async def test_the_meters_count_the_downtime(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    _measures(hass, power_w=-1000.0)
    _meters(hass, 5.0, 3.0)
    entry = await _setup(hass, {**OPTIONS, "charged_entity": CHARGED, "discharged_entity": DISCHARGED})
    await _call(hass, "set_energy", entry, energy_kwh=10.0)
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    freezer.tick(timedelta(hours=2))
    _meters(hass, 5.0, 5.0)  # 2 kWh out while Home Assistant was down
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert _value(hass, ENERGY) == pytest.approx(8.0, abs=0.01)


async def test_unloading_counts_the_last_interval(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    _measures(hass)
    entry = await _setup(hass)
    await _call(hass, "set_energy", entry, energy_kwh=8.0)
    hass.states.async_set(POWER, "6000", {"unit_of_measurement": "W"})
    await hass.async_block_till_done()
    freezer.tick(timedelta(seconds=59))  # before the next refresh
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert _value(hass, ENERGY) == pytest.approx(8.0 + 0.96 * 6.0 * 59 / 3600, abs=0.002)


@pytest.mark.parametrize("stored", [[1, 2], {"energy_kwh": "x", "sources": "y"}])
async def test_an_unreadable_stored_state_starts_from_the_state_of_charge(
    hass: HomeAssistant, hass_storage: dict, stored: object
) -> None:
    hass_storage[f"{DOMAIN}.battery"] = {"version": 1, "key": f"{DOMAIN}.battery", "data": stored}
    _measures(hass, soc_pct=54.5)
    await _setup(hass, entry_id="battery")
    assert _value(hass, ENERGY) == pytest.approx(FULL_KWH / 2, abs=0.001)


@pytest.mark.parametrize(("unit", "factor"), [("Wh", 1000.0), ("kWh", 1.0), ("MWh", 0.001)])
async def test_meters_alone_in_any_energy_unit(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, unit: str, factor: float
) -> None:
    _measures(hass)
    options = {**BATTERY, "soc_entity": SOC, "charged_entity": CHARGED, "discharged_entity": DISCHARGED}
    hass.states.async_set(CHARGED, str(5.0 * factor), {"unit_of_measurement": unit})
    hass.states.async_set(DISCHARGED, str(3.0 * factor), {"unit_of_measurement": unit})
    entry = await _setup(hass, options)
    await _call(hass, "set_energy", entry, energy_kwh=8.0)
    freezer.tick(timedelta(minutes=10))
    hass.states.async_set(CHARGED, str(6.0 * factor), {"unit_of_measurement": unit})
    hass.states.async_set(DISCHARGED, str(3.5 * factor), {"unit_of_measurement": unit})
    await hass.async_block_till_done()
    assert _value(hass, ENERGY) == pytest.approx(8.0 + 0.96 - 0.5, abs=0.01)


async def test_deleting_the_battery_removes_its_stored_estimate(hass: HomeAssistant, hass_storage: dict) -> None:
    _measures(hass)
    entry = await _setup(hass)
    assert await hass.config_entries.async_unload(entry.entry_id)  # saves the estimate
    assert f"{DOMAIN}.{entry.entry_id}" in hass_storage
    await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()
    assert f"{DOMAIN}.{entry.entry_id}" not in hass_storage


# --- Unavailable or missing sources ---


async def test_the_estimate_waits_15_minutes_before_an_unavailable_power(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture, freezer: FrozenDateTimeFactory
) -> None:
    _measures(hass)
    entry = await _setup(hass)
    await _call(hass, "set_energy", entry, energy_kwh=8.0)
    hass.states.async_set(POWER, "unavailable")
    await hass.async_block_till_done()
    await _later(hass, freezer, timedelta(minutes=14))
    assert hass.states.get(ENERGY).state != "unavailable"
    await _later(hass, freezer, timedelta(minutes=1, seconds=1))
    for entity_id in (ENERGY, PCT, ROOM, "sensor.battery_uncertainty"):
        assert hass.states.get(entity_id).state == "unavailable"
    assert hass.states.get("sensor.battery_learned_round_trip").state != "unavailable"  # a known fact
    assert f"Battery: the battery power {POWER} is unavailable since" in caplog.text
    await _later(hass, freezer, timedelta(minutes=30))
    assert caplog.text.count("is unavailable since") == 1  # logged once, not at every refresh
    hass.states.async_set(POWER, "0", {"unit_of_measurement": "W"})
    await hass.async_block_till_done()
    assert _value(hass, ENERGY) == pytest.approx(8.0, abs=0.01)
    assert f"Battery: the battery power {POWER} is available again" in caplog.text


async def test_with_meters_an_unavailable_power_keeps_the_estimate(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    _measures(hass)
    _meters(hass, 5.0, 3.0)
    entry = await _setup(hass, {**OPTIONS, "charged_entity": CHARGED, "discharged_entity": DISCHARGED})
    await _call(hass, "set_energy", entry, energy_kwh=8.0)
    hass.states.async_set(POWER, "unavailable")
    await hass.async_block_till_done()
    await _later(hass, freezer, timedelta(minutes=20))
    _meters(hass, 5.0, 3.5)
    await hass.async_block_till_done()
    assert _value(hass, ENERGY) == pytest.approx(7.5, abs=0.01)


async def test_a_removed_power_raises_an_issue_until_reconfigured(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture, freezer: FrozenDateTimeFactory
) -> None:
    _measures(hass)
    entry = await _setup(hass)
    hass.states.async_remove(POWER)
    await hass.async_block_till_done()
    await _later(hass, freezer, timedelta(minutes=16))
    assert "(the entity does not exist)" in caplog.text
    issue = ir.async_get(hass).async_get_issue(DOMAIN, f"missing_power_entity_{entry.entry_id}")
    assert issue is not None and issue.severity is ir.IssueSeverity.ERROR
    assert issue.translation_placeholders == {"name": "Battery", "entity": POWER}
    hass.states.async_set("sensor.new_power", "0", {"unit_of_measurement": "W"})
    result = await entry.start_reconfigure_flow(hass)
    await hass.config_entries.flow.async_configure(result["flow_id"], {**SOURCES, "power_entity": "sensor.new_power"})
    await hass.async_block_till_done()
    assert ir.async_get(hass).async_get_issue(DOMAIN, f"missing_power_entity_{entry.entry_id}") is None
    assert hass.states.get(ENERGY).state != "unavailable"


async def test_removed_cells_raise_a_warning_cleared_when_back(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture, freezer: FrozenDateTimeFactory
) -> None:
    _measures(hass)
    entry = await _setup(hass)
    hass.states.async_remove(CELLS[0])
    await hass.async_block_till_done()
    await _later(hass, freezer, timedelta(minutes=16))
    assert "cell voltages" not in caplog.text  # one pack still reads
    hass.states.async_remove(CELLS[1])
    await hass.async_block_till_done()
    await _later(hass, freezer, timedelta(minutes=16))
    assert f"the cell voltages {CELLS[0]}, {CELLS[1]} are unavailable since" in caplog.text
    issue = ir.async_get(hass).async_get_issue(DOMAIN, f"missing_cell_voltage_entities_{entry.entry_id}")
    assert issue is not None and issue.severity is ir.IssueSeverity.WARNING
    assert hass.states.get(ENERGY).state != "unavailable"
    hass.states.async_set(CELLS[1], "3.3", {"unit_of_measurement": "V"})
    await hass.async_block_till_done()
    assert ir.async_get(hass).async_get_issue(DOMAIN, f"missing_cell_voltage_entities_{entry.entry_id}") is None


async def test_units_and_non_numbers(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture, freezer: FrozenDateTimeFactory
) -> None:
    _measures(hass)
    entry = await _setup(hass)
    await _call(hass, "set_energy", entry, energy_kwh=8.0)
    hass.states.async_set(POWER, "nan", {"unit_of_measurement": "W"})
    await hass.async_block_till_done()
    await _later(hass, freezer, timedelta(minutes=5))
    hass.states.async_set(POWER, "charging", {"unit_of_measurement": "W"})
    await hass.async_block_till_done()
    await _later(hass, freezer, timedelta(minutes=5))
    hass.states.async_set(POWER, "2", {"unit_of_measurement": "hp"})
    await hass.async_block_till_done()
    await _later(hass, freezer, timedelta(minutes=16))
    assert "(unit 'hp' is not supported)" in caplog.text
    hass.states.async_set(POWER, "0", {"unit_of_measurement": "W"})
    await hass.async_block_till_done()
    assert _value(hass, ENERGY) == pytest.approx(8.0, abs=0.01)  # the gaps counted nothing


async def test_meters_alone_unavailable_make_the_estimate_unavailable(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    _measures(hass)
    _meters(hass, 5.0, 3.0)
    options = {**BATTERY, "soc_entity": SOC, "charged_entity": CHARGED, "discharged_entity": DISCHARGED}
    await _setup(hass, options)
    hass.states.async_set(DISCHARGED, "unknown")
    await hass.async_block_till_done()
    await _later(hass, freezer, timedelta(minutes=16))
    assert hass.states.get(ENERGY).state == "unavailable"


# --- Diagnostics ---


async def test_diagnostics_show_the_estimate_and_the_sources(
    hass: HomeAssistant, hass_client: ClientSessionGenerator
) -> None:
    _measures(hass)
    entry = await _setup(hass)
    await _call(hass, "set_energy", entry, energy_kwh=8.0)
    hass.states.async_remove(CELLS[1])
    await hass.async_block_till_done()
    assert await async_setup_component(hass, "diagnostics", {})
    diagnostics = await get_diagnostics_for_config_entry(hass, hass_client, entry)
    assert diagnostics["options"] == OPTIONS
    assert diagnostics["estimate"]["energy_kwh"] == pytest.approx(8.0, abs=0.01)
    assert diagnostics["estimate"]["available"] is True
    assert (diagnostics["estimate"]["last_full_at"], diagnostics["estimate"]["last_empty_at"]) == (None, None)
    assert diagnostics["state"]["energy_kwh"] == pytest.approx(diagnostics["estimate"]["energy_kwh"])
    assert diagnostics["sources"]["soc_entity"]["state"] == "54.5"
    assert diagnostics["sources"]["power_entity"]["unit"] == "W"
    assert diagnostics["sources"]["cell_voltage_entities"][1] is None
    assert "charged_entity" not in diagnostics["sources"]  # not configured
