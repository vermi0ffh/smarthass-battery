"""The repair that turns learning on, from the issue saying the learned values are ready (tracker.py)."""

from typing import Any

from homeassistant.components.repairs import ConfirmRepairFlow, RepairsFlow, RepairsFlowResult
from homeassistant.core import HomeAssistant

from .const import CONF_LEARN


class TurnLearningOnFlow(ConfirmRepairFlow):
    def __init__(self, entry_id: str) -> None:
        self._entry_id = entry_id

    async def async_step_confirm(self, user_input: dict[str, str] | None = None) -> RepairsFlowResult:
        """Confirmed: the option on, and the battery reloaded with it (as from its options)."""
        if user_input is not None:
            entry = self.hass.config_entries.async_get_entry(self._entry_id)
            if entry is not None:
                self.hass.config_entries.async_update_entry(entry, options={**entry.options, CONF_LEARN: True})
                self.hass.config_entries.async_schedule_reload(entry.entry_id)
        return await super().async_step_confirm(user_input)


async def async_create_fix_flow(hass: HomeAssistant, issue_id: str, data: dict[str, Any] | None) -> RepairsFlow:
    return TurnLearningOnFlow(str((data or {}).get("entry_id")))
