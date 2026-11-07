"""The estimate as sensors: stored energy, corrected state of charge, room to full, and for diagnostics its
uncertainty, the learned round trip and energy between the landmarks, the last landmark."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import BatteryConfigEntry
from .const import DOMAIN
from .tracker import BatteryTracker

# No polling: the tracker pushes every change
PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class BatterySensorDescription(SensorEntityDescription):
    value: Callable[[BatteryTracker], float | datetime | None]
    # Unavailable while the flows' sources are (the learned values and the last landmark stay known facts)
    needs_sources: bool = False
    attributes: Callable[[BatteryTracker], dict[str, Any]] | None = None


def _pct(value: float | None) -> float | None:
    return None if value is None else 100.0 * value


SENSORS = (
    BatterySensorDescription(
        key="energy",
        needs_sources=True,
        # Everything a planner needs in one entity (contract, doc/agents/architecture.md)
        attributes=lambda t: t.planner_attributes(),
        translation_key="energy",
        device_class=SensorDeviceClass.ENERGY_STORAGE,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value=lambda t: t.battery.energy_kwh,
    ),
    BatterySensorDescription(
        key="soc",
        needs_sources=True,
        translation_key="soc",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value=lambda t: t.battery.soc_pct,
    ),
    BatterySensorDescription(
        key="room",
        needs_sources=True,
        translation_key="room",
        device_class=SensorDeviceClass.ENERGY_STORAGE,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value=lambda t: t.battery.room_kwh,
    ),
    BatterySensorDescription(
        key="uncertainty",
        needs_sources=True,
        translation_key="uncertainty",
        device_class=SensorDeviceClass.ENERGY_STORAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value=lambda t: t.battery.uncertainty_kwh,
    ),
    BatterySensorDescription(
        key="learned_efficiency",
        translation_key="learned_efficiency",
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        attributes=lambda t: t.efficiency_attributes(),
        value=lambda t: _pct(t.battery.learned_efficiency),
    ),
    BatterySensorDescription(
        key="learned_full_energy",
        translation_key="learned_full_energy",
        device_class=SensorDeviceClass.ENERGY_STORAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        attributes=lambda t: t.full_energy_attributes(),
        value=lambda t: t.battery.learned_full_energy_kwh,
    ),
    BatterySensorDescription(
        key="last_landmark",
        translation_key="last_landmark",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        attributes=lambda t: t.landmark_attributes(),
        value=lambda t: t.battery.last_landmark_at,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: BatteryConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities(BatterySensor(entry.runtime_data, description) for description in SENSORS)


class BatterySensor(SensorEntity):
    entity_description: BatterySensorDescription
    _attr_has_entity_name = True
    _attr_should_poll = False
    # The energy's attributes that move with every update: their history would only fill the database (Home Assistant
    # reads this per class)
    _unrecorded_attributes = frozenset({"room_kwh", "uncertainty_kwh", "soc_pct"})

    def __init__(self, tracker: BatteryTracker, description: BatterySensorDescription) -> None:
        self._tracker = tracker
        self.entity_description = description
        entry = tracker.entry
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry.entry_id)}, name=entry.title)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        attributes = self.entity_description.attributes
        return None if attributes is None else attributes(self._tracker)

    @property
    def available(self) -> bool:
        return not self.entity_description.needs_sources or self._tracker.estimate_available

    @property
    def native_value(self) -> float | datetime | None:
        return self.entity_description.value(self._tracker)

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self._tracker.add_listener(self.async_write_ha_state))
