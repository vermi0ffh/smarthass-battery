"""Diagnostics: the options, the estimate, the model's stored state and what the source entities show now — what is
needed to understand an estimate. Nothing to redact: entity ids and measures only."""

from typing import Any

from homeassistant.core import HomeAssistant

from . import BatteryConfigEntry
from .model import state_to_dict


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: BatteryConfigEntry) -> dict[str, Any]:
    tracker = entry.runtime_data
    battery = tracker.battery
    landmark_at, full_at, empty_at = battery.last_landmark_at, battery.last_full_at, battery.last_empty_at
    return {
        "options": dict(entry.options),
        "estimate": {
            "energy_kwh": battery.energy_kwh,
            "room_kwh": battery.room_kwh,
            "soc_pct": battery.soc_pct,
            "uncertainty_kwh": battery.uncertainty_kwh,
            "full_energy_kwh": battery.full_energy_kwh,
            "efficiency": battery.efficiency,
            "learned_efficiency": battery.learned_efficiency,
            "learned_full_energy_kwh": battery.learned_full_energy_kwh,
            "last_landmark": battery.last_landmark,
            "last_landmark_at": None if landmark_at is None else landmark_at.isoformat(),
            "last_landmark_error_kwh": battery.last_landmark_error_kwh,
            "last_full_at": None if full_at is None else full_at.isoformat(),
            "last_empty_at": None if empty_at is None else empty_at.isoformat(),
            "available": tracker.estimate_available,
        },
        "state": state_to_dict(battery.state),
        "sources": tracker.source_states(),
    }
