"""The Home Assistant glue (rule 2): reads the configured entities, feeds the battery model, persists its state and
tells the entities when the estimate changed."""

import logging
import math
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any, NamedTuple

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfElectricPotential, UnitOfEnergy, UnitOfPower
from homeassistant.core import CALLBACK_TYPE, Event, EventStateChangedData, HomeAssistant, State, callback
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    CONF_CELL_VOLTAGE_ENTITIES,
    CONF_CHARGED_ENTITY,
    CONF_DISCHARGED_ENTITY,
    CONF_EFFICIENCY_PCT,
    CONF_EMPTY_SOC_PCT,
    CONF_FULL_CELL_V,
    CONF_FULL_ENERGY_KWH,
    CONF_INVERT_POWER,
    CONF_LEARN,
    CONF_MAX_POWER_KW,
    CONF_NOMINAL_CAPACITY_KWH,
    CONF_POWER_ENTITY,
    CONF_SOC_ENTITY,
    DEFAULT_EFFICIENCY_PCT,
    DEFAULT_EMPTY_SOC_PCT,
    DEFAULT_FULL_CELL_V,
    DEFAULT_MAX_POWER_KW,
    DOMAIN,
    ENTITY_KEYS,
    FOLLOWED_KEYS,
    METER_KEYS,
)
from .model import Battery, BatteryConfig, Reading, state_from_dict, state_to_dict

_LOGGER = logging.getLogger(__name__)

# The power is counted at its last value between its state changes: the entities are refreshed at least this often,
# so the stored energy moves while the power holds (and a source unavailable is logged at most this late)
REFRESH_INTERVAL = timedelta(minutes=1)
# A source unavailable this long is logged; the flows' sources that long make the estimate unavailable (a flow could
# go unseen). Long enough for a restart of Home Assistant or of the inverter's integration.
UNAVAILABLE_AFTER = timedelta(minutes=15)
# A burst of readings (power every few seconds) is saved once
SAVE_DELAY_S = 30
# The Store's own format: the model's state inside it has its version ("version", read by state_from_dict), so a
# change of the model's format never makes Home Assistant refuse the stored file
STORAGE_VERSION = 1

_POWER_TO_W: dict[str, float] = {UnitOfPower.WATT: 1.0, UnitOfPower.KILO_WATT: 1000.0}
_ENERGY_TO_KWH: dict[str, float] = {
    UnitOfEnergy.WATT_HOUR: 0.001,
    UnitOfEnergy.KILO_WATT_HOUR: 1.0,
    UnitOfEnergy.MEGA_WATT_HOUR: 1000.0,
}
_VOLTAGE_TO_V: dict[str, float] = {UnitOfElectricPotential.VOLT: 1.0, UnitOfElectricPotential.MILLIVOLT: 0.001}
_PERCENT: dict[str, float] = {PERCENTAGE: 1.0}
_FACTORS: dict[str, dict[str, float]] = {
    CONF_SOC_ENTITY: _PERCENT,
    CONF_POWER_ENTITY: _POWER_TO_W,
    CONF_CHARGED_ENTITY: _ENERGY_TO_KWH,
    CONF_DISCHARGED_ENTITY: _ENERGY_TO_KWH,
    CONF_CELL_VOLTAGE_ENTITIES: _VOLTAGE_TO_V,
}
# What the log says of each source, and what its absence costs
_SOURCE_LABELS = {
    CONF_SOC_ENTITY: "state of charge",
    CONF_POWER_ENTITY: "battery power",
    CONF_CHARGED_ENTITY: "energy in meter",
    CONF_DISCHARGED_ENTITY: "energy out meter",
    CONF_CELL_VOLTAGE_ENTITIES: "cell voltages",
}
_CONSEQUENCES = {
    CONF_SOC_ENTITY: "the empty landmark is not seen until it comes back",
    CONF_POWER_ENTITY: "the flows are counted by the energy meters meanwhile, if any",
    CONF_CHARGED_ENTITY: "the flows it counts are counted when it comes back",
    CONF_DISCHARGED_ENTITY: "the flows it counts are counted when it comes back",
    CONF_CELL_VOLTAGE_ENTITIES: "the full landmark is not seen until they come back",
}


class Measure(NamedTuple):
    """A source's value in the model's unit, or None and why."""

    value: float | None
    cause: str | None = None


def stored_state(hass: HomeAssistant, entry_id: str) -> Store[dict[str, Any]]:
    """Where a battery's estimate is stored (.storage/)."""
    return Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry_id}")


def battery_config(options: dict[str, Any]) -> BatteryConfig:
    full_energy = options.get(CONF_FULL_ENERGY_KWH)
    return BatteryConfig(
        nominal_capacity_kwh=float(options[CONF_NOMINAL_CAPACITY_KWH]),
        empty_soc_pct=float(options.get(CONF_EMPTY_SOC_PCT, DEFAULT_EMPTY_SOC_PCT)),
        # Without cell voltages, the state of charge reaching 100 % is the full landmark
        full_cell_v=float(options.get(CONF_FULL_CELL_V, DEFAULT_FULL_CELL_V))
        if options.get(CONF_CELL_VOLTAGE_ENTITIES)
        else None,
        efficiency=float(options.get(CONF_EFFICIENCY_PCT, DEFAULT_EFFICIENCY_PCT)) / 100.0,
        full_energy_kwh=None if full_energy is None else float(full_energy),
        has_power=bool(options.get(CONF_POWER_ENTITY)),
        has_meters=all(options.get(key) for key in METER_KEYS),
        learn=bool(options.get(CONF_LEARN, False)),
        max_power_kw=float(options.get(CONF_MAX_POWER_KW, DEFAULT_MAX_POWER_KW)),
    )


class BatteryTracker:
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self._options = dict(entry.options)
        self._store = stored_state(hass, entry.entry_id)
        self.battery = Battery(battery_config(self._options))
        self._listeners: list[Callable[[], None]] = []
        self._unsubscribe: list[CALLBACK_TYPE] = []
        # Each source unavailable since when (first seen so), and those already logged as unavailable
        self._unavailable_since: dict[str, datetime] = {}
        self._reported_unavailable: set[str] = set()

    # --- Lifecycle ---

    async def async_start(self) -> None:
        stored = await self._store.async_load()
        if isinstance(stored, dict):
            self.battery = Battery(battery_config(self._options), state_from_dict(stored))
            self.battery.resume()
            # Meters replaced (reconfigured): their values are no increase of the previous ones
            previous = stored.get("sources")
            if isinstance(previous, dict) and any(previous.get(key) != self._options.get(key) for key in METER_KEYS):
                self.battery.forget_meters()
        self._update(dt_util.utcnow())
        self._unsubscribe.append(async_track_state_change_event(self.hass, self._entities(), self._on_state_change))
        self._unsubscribe.append(async_track_time_interval(self.hass, self._on_refresh, REFRESH_INTERVAL))

    async def async_stop(self) -> None:
        for unsubscribe in self._unsubscribe:
            unsubscribe()
        self._unsubscribe.clear()
        # What flowed since the last update is counted before saving: after the restart, the power is not held over
        # the downtime
        self.battery.update(dt_util.utcnow(), self._reading())
        for key in FOLLOWED_KEYS:  # raised again after 15 min if still true (e.g. after reconfiguring)
            ir.async_delete_issue(self.hass, DOMAIN, self._issue_id(key))
        await self._store.async_save(self._stored())

    # --- For the entities and the services ---

    @property
    def estimate_available(self) -> bool:
        """False while the flows are unknown: the power unavailable for UNAVAILABLE_AFTER, unless both meters count
        what it misses."""
        cfg, out = self.battery.config, self._reported_unavailable
        power_reads = cfg.has_power and CONF_POWER_ENTITY not in out
        meters_read = cfg.has_meters and not out.intersection(METER_KEYS)
        return power_reads or meters_read

    @callback
    def add_listener(self, listener: Callable[[], None]) -> CALLBACK_TYPE:
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    def mark_full(self) -> None:
        self._act(lambda now: self.battery.mark_full(now))

    def mark_empty(self) -> None:
        self._act(lambda now: self.battery.mark_empty(now))

    def set_energy(self, energy_kwh: float) -> None:
        self._act(lambda now: self.battery.set_energy(now, energy_kwh))

    def planner_attributes(self) -> dict[str, Any]:
        """The battery and its estimate for a planner reading one entity: what it would otherwise configure again
        (capacity, round trip, the empty threshold, the source entities) and how far to trust the estimate."""
        battery, cfg = self.battery, self.battery.config
        return {
            "nominal_capacity_kwh": cfg.nominal_capacity_kwh,
            "full_energy_kwh": round(battery.full_energy_kwh, 3),
            "efficiency": round(battery.efficiency, 4),
            "empty_soc_pct": cfg.empty_soc_pct,
            "room_kwh": _round(battery.room_kwh, 3),
            "uncertainty_kwh": _round(battery.uncertainty_kwh, 3),
            "soc_pct": _round(battery.soc_pct, 1),
            "last_landmark": battery.last_landmark,
            "last_landmark_at": _iso(battery.last_landmark_at),
            "last_full_at": _iso(battery.last_full_at),
            "last_empty_at": _iso(battery.last_empty_at),
            **{key: self._options.get(key) for key in ENTITY_KEYS},
        }

    def efficiency_attributes(self) -> dict[str, Any]:
        """Where the learned round trip comes from, and whether the estimate counts it."""
        battery = self.battery
        return {
            "configured_efficiency": battery.config.efficiency,
            "efficiency_in_use": round(battery.efficiency, 4),
            "learning_enabled": battery.config.learn,
            "cycles": battery.state.efficiency_cycles,
        }

    def full_energy_attributes(self) -> dict[str, Any]:
        battery = self.battery
        return {
            "configured_full_energy_kwh": round(battery.config.configured_full_energy_kwh, 3),
            "full_energy_in_use_kwh": round(battery.full_energy_kwh, 3),
            "learning_enabled": battery.config.learn,
            "cycles": battery.state.full_energy_cycles,
        }

    def landmark_attributes(self) -> dict[str, Any]:
        battery = self.battery
        return {"kind": battery.last_landmark, "error_kwh": _round(battery.last_landmark_error_kwh, 3)}

    def source_states(self) -> dict[str, Any]:
        """What each configured source entity shows now, as Home Assistant has it (diagnostics); None = missing."""
        sources: dict[str, Any] = {}
        for key in ENTITY_KEYS:
            entity_id = self._options.get(key)
            if entity_id:
                sources[key] = self._source_state(entity_id)
        cells = self._entity_ids(CONF_CELL_VOLTAGE_ENTITIES)
        if cells:
            sources[CONF_CELL_VOLTAGE_ENTITIES] = [self._source_state(entity_id) for entity_id in cells]
        return sources

    def _source_state(self, entity_id: str) -> dict[str, Any] | None:
        state = self.hass.states.get(entity_id)
        if state is None:
            return None
        return {
            "entity_id": entity_id,
            "state": state.state,
            "unit": state.attributes.get("unit_of_measurement"),
            "last_changed": state.last_changed.isoformat(),
        }

    def _act(self, action: Callable[[datetime], None]) -> None:
        """A service: the interval up to now is counted first, then the action."""
        now = dt_util.utcnow()
        self.battery.update(now, self._reading())
        action(now)
        self._changed()

    # --- Events ---

    @callback
    def _on_state_change(self, event: Event[EventStateChangedData]) -> None:
        self._update(event.time_fired)

    @callback
    def _on_refresh(self, now: datetime) -> None:
        self._update(dt_util.utcnow())

    def _update(self, at: datetime) -> None:
        self.battery.update(at, self._reading())
        for key in FOLLOWED_KEYS:
            if self._entity_ids(key):
                self._follow_source(key, at)
        self._changed()

    def _follow_source(self, key: str, at: datetime) -> None:
        """Logs a source unavailable for UNAVAILABLE_AFTER with the cause, once, and once when it is back."""
        cause = self._unavailable_cause(key)
        if cause is None:
            self._unavailable_since.pop(key, None)
            if key in self._reported_unavailable:
                self._source_back(key)
            return
        since = self._unavailable_since.setdefault(key, at)
        if key not in self._reported_unavailable and at - since >= UNAVAILABLE_AFTER:
            self._report_unavailable(key, since, cause)

    def _source_back(self, key: str) -> None:
        self._reported_unavailable.discard(key)
        ir.async_delete_issue(self.hass, DOMAIN, self._issue_id(key))
        _LOGGER.info(
            "%s: the %s %s available again", self.entry.title, _SOURCE_LABELS[key], _names(self._entity_ids(key))
        )

    def _report_unavailable(self, key: str, since: datetime, cause: str) -> None:
        """Logged with its cause; an entity that no longer exists (renamed, its device removed) will not come back by
        itself: a repair issue."""
        self._reported_unavailable.add(key)
        entity_ids = self._entity_ids(key)
        _LOGGER.info(
            "%s: the %s %s unavailable since %s (%s): %s",
            self.entry.title,
            _SOURCE_LABELS[key],
            _names(entity_ids),
            dt_util.as_local(since).isoformat(timespec="seconds"),
            cause,
            _CONSEQUENCES[key],
        )
        missing = [entity_id for entity_id in entity_ids if self.hass.states.get(entity_id) is None]
        if missing:
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                self._issue_id(key),
                is_fixable=False,
                severity=ir.IssueSeverity.ERROR if self._flows_depend_on(key) else ir.IssueSeverity.WARNING,
                translation_key=f"missing_{key}",
                translation_placeholders={"name": self.entry.title, "entity": ", ".join(missing)},
            )

    def _flows_depend_on(self, key: str) -> bool:
        """Without this source alone, the flows are unknown (see estimate_available)."""
        cfg = self.battery.config
        if key == CONF_POWER_ENTITY:
            return not cfg.has_meters
        return key in METER_KEYS and not cfg.has_power

    def _issue_id(self, key: str) -> str:
        return f"missing_{key}_{self.entry.entry_id}"

    def _changed(self) -> None:
        self._store.async_delay_save(self._stored, SAVE_DELAY_S)
        for listener in list(self._listeners):
            listener()

    def _stored(self) -> dict[str, Any]:
        """The model's state, and the source entities it was measured with (replaced meters are forgotten)."""
        return {**state_to_dict(self.battery.state), "sources": {key: self._options.get(key) for key in ENTITY_KEYS}}

    # --- Reading the entities (their Home Assistant semantics stay here, rule 2) ---

    def _entity_ids(self, key: str) -> list[str]:
        if key == CONF_CELL_VOLTAGE_ENTITIES:
            return list(self._options.get(key) or [])
        entity_id = self._options.get(key)
        return [entity_id] if entity_id else []

    def _entities(self) -> list[str]:
        return [entity_id for key in FOLLOWED_KEYS for entity_id in self._entity_ids(key)]

    def _reading(self) -> Reading:
        power = self._value(CONF_POWER_ENTITY)
        if power is not None and self._options.get(CONF_INVERT_POWER):
            power = -power
        cells = [
            value
            for entity_id in self._entity_ids(CONF_CELL_VOLTAGE_ENTITIES)
            if (value := _measure(self.hass.states.get(entity_id), _VOLTAGE_TO_V).value) is not None
        ]
        return Reading(
            soc_pct=self._value(CONF_SOC_ENTITY),
            power_w=power,
            charged_kwh=self._value(CONF_CHARGED_ENTITY),
            discharged_kwh=self._value(CONF_DISCHARGED_ENTITY),
            # The highest cell among the packs: the first to reach the full voltage
            cell_high_v=max(cells) if cells else None,
        )

    def _value(self, key: str) -> float | None:
        """The numeric state in the model's unit; None when not configured, unavailable, not a number or in an
        unknown unit."""
        entity_id = self._options.get(key)
        return None if not entity_id else _measure(self.hass.states.get(entity_id), _FACTORS[key]).value

    def _unavailable_cause(self, key: str) -> str | None:
        """Why the source gives no reading, None when it gives one (the cell voltages: when none of them gives one)."""
        measures = [_measure(self.hass.states.get(entity_id), _FACTORS[key]) for entity_id in self._entity_ids(key)]
        if any(measure.value is not None for measure in measures):
            return None
        return measures[0].cause


def _names(entity_ids: list[str]) -> str:
    return f"{entity_ids[0]} is" if len(entity_ids) == 1 else f"{', '.join(entity_ids)} are"


def _round(value: float | None, digits: int) -> float | None:
    return None if value is None else round(value, digits)


def _iso(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


def _measure(state: State | None, factors: dict[str, float]) -> Measure:
    if state is None:
        return Measure(None, "the entity does not exist")
    if state.state in ("unavailable", "unknown"):
        return Measure(None, f"state {state.state}")
    try:
        value = float(state.state)
    except ValueError:
        return Measure(None, f"state {state.state!r} is not a number")
    if not math.isfinite(value):  # "nan" / "inf" parse as floats
        return Measure(None, f"state {state.state!r} is not a number")
    unit = state.attributes.get("unit_of_measurement")
    factor = factors.get(unit) if unit is not None else 1.0
    if factor is None:
        return Measure(None, f"unit {unit!r} is not supported")
    return Measure(value * factor)
