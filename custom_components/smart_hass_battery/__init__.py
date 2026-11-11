"""Smart Hass - Battery: the energy really stored in a home battery, counted from Home Assistant's measures since the
last landmark (full or empty). Reads only: it never drives the inverter or the battery (rule 3)."""

import math

import probatio
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.typing import ConfigType

from .const import (
    ATTR_CONFIG_ENTRY_ID,
    ATTR_ENERGY_KWH,
    DOMAIN,
    SERVICE_MARK_EMPTY,
    SERVICE_MARK_FULL,
    SERVICE_SET_ENERGY,
)
from .tracker import LEARNING_ISSUES, BatteryTracker, learning_issue_id, stored_state

PLATFORMS = [Platform.SENSOR]

type BatteryConfigEntry = ConfigEntry[BatteryTracker]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


def _finite(value: float) -> float:
    """ "nan" and "inf" coerce to floats: refused, they would become the persisted estimate."""
    if not math.isfinite(value):
        raise probatio.Invalid("not a finite number")
    return value


_ENTRY_SCHEMA = probatio.Schema({probatio.Required(ATTR_CONFIG_ENTRY_ID): cv.string})
_SET_ENERGY_SCHEMA = probatio.Schema(
    {
        probatio.Required(ATTR_CONFIG_ENTRY_ID): cv.string,
        probatio.Required(ATTR_ENERGY_KWH): probatio.All(probatio.Coerce(float), _finite, probatio.Range(min=0)),
    }
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """The services, registered once for every battery."""

    def tracker_of(call: ServiceCall) -> BatteryTracker:
        entry = hass.config_entries.async_get_entry(call.data[ATTR_CONFIG_ENTRY_ID])
        if entry is None or entry.domain != DOMAIN or entry.state is not ConfigEntryState.LOADED:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="unknown_entry",
                translation_placeholders={"entry": call.data[ATTR_CONFIG_ENTRY_ID]},
            )
        tracker: BatteryTracker = entry.runtime_data
        return tracker

    async def mark_full(call: ServiceCall) -> None:
        tracker_of(call).mark_full()

    async def mark_empty(call: ServiceCall) -> None:
        tracker_of(call).mark_empty()

    async def set_energy(call: ServiceCall) -> None:
        tracker_of(call).set_energy(call.data[ATTR_ENERGY_KWH])

    hass.services.async_register(DOMAIN, SERVICE_MARK_FULL, mark_full, schema=_ENTRY_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_MARK_EMPTY, mark_empty, schema=_ENTRY_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_SET_ENERGY, set_energy, schema=_SET_ENERGY_SCHEMA)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: BatteryConfigEntry) -> bool:
    tracker = BatteryTracker(hass, entry)
    # Stopped (listeners off, estimate saved) at unload, and also when the setup fails after it started
    entry.async_on_unload(tracker.async_stop)
    await tracker.async_start()
    entry.runtime_data = tracker
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: BatteryConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: BatteryConfigEntry) -> None:
    """The battery deleted: its stored estimate and its learning's repair issues go with it (they outlive an unload)."""
    await stored_state(hass, entry.entry_id).async_remove()
    for key in LEARNING_ISSUES:
        ir.async_delete_issue(hass, DOMAIN, learning_issue_id(key, entry.entry_id))
