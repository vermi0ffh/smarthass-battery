"""Configuration from the UI: the entities read (changed later by reconfiguring) and the battery's parameters
(changed later in the options)."""

from typing import Any

import probatio
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlowWithReload
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers import selector

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
    RECONFIGURE_KEYS,
)


def _number(minimum: float, maximum: float, step: float, unit: str) -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=minimum, max=maximum, step=step, unit_of_measurement=unit, mode=selector.NumberSelectorMode.BOX
        )
    )


def _suggested(key: str, defaults: dict[str, Any]) -> probatio.Optional:
    value = defaults.get(key)
    return probatio.Optional(key, description={"suggested_value": value} if value else None)


def _sources_schema(defaults: dict[str, Any]) -> probatio.Schema:
    def sensor(device_class: str) -> selector.EntitySelector:
        return selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor", device_class=device_class))

    return probatio.Schema(
        {
            probatio.Required(
                CONF_SOC_ENTITY, default=defaults.get(CONF_SOC_ENTITY, probatio.UNDEFINED)
            ): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            _suggested(CONF_POWER_ENTITY, defaults): sensor("power"),
            probatio.Optional(
                CONF_INVERT_POWER, description={"suggested_value": defaults.get(CONF_INVERT_POWER, False)}
            ): selector.BooleanSelector(),
            _suggested(CONF_CHARGED_ENTITY, defaults): sensor("energy"),
            _suggested(CONF_DISCHARGED_ENTITY, defaults): sensor("energy"),
            _suggested(CONF_CELL_VOLTAGE_ENTITIES, defaults): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor", device_class="voltage", multiple=True)
            ),
        }
    )


def _battery_schema(defaults: dict[str, Any]) -> probatio.Schema:
    return probatio.Schema(
        {
            probatio.Required(
                CONF_NOMINAL_CAPACITY_KWH, default=defaults.get(CONF_NOMINAL_CAPACITY_KWH, probatio.UNDEFINED)
            ): _number(0.5, 1000, 0.1, "kWh"),
            probatio.Required(
                CONF_EMPTY_SOC_PCT, default=defaults.get(CONF_EMPTY_SOC_PCT, DEFAULT_EMPTY_SOC_PCT)
            ): _number(0, 50, 1, "%"),
            probatio.Required(CONF_FULL_CELL_V, default=defaults.get(CONF_FULL_CELL_V, DEFAULT_FULL_CELL_V)): _number(
                2, 5, 0.01, "V"
            ),
            probatio.Required(
                CONF_EFFICIENCY_PCT, default=defaults.get(CONF_EFFICIENCY_PCT, DEFAULT_EFFICIENCY_PCT)
            ): _number(50, 100, 0.1, "%"),
            _suggested(CONF_FULL_ENERGY_KWH, defaults): _number(0.1, 1000, 0.01, "kWh"),
            probatio.Required(
                CONF_MAX_POWER_KW, default=defaults.get(CONF_MAX_POWER_KW, DEFAULT_MAX_POWER_KW)
            ): _number(0.1, 1000, 0.1, "kW"),
            probatio.Optional(
                CONF_LEARN, description={"suggested_value": defaults.get(CONF_LEARN, False)}
            ): selector.BooleanSelector(),
        }
    )


def _source_errors(options: dict[str, Any]) -> dict[str, str]:
    """The flows need a power or both energy meters; one meter alone counts half of them."""
    charged, discharged = bool(options.get(CONF_CHARGED_ENTITY)), bool(options.get(CONF_DISCHARGED_ENTITY))
    if charged != discharged:
        return {"base": "one_meter"}
    if not options.get(CONF_POWER_ENTITY) and not charged:
        return {"base": "no_flow_source"}
    return {}


def _battery_errors(options: dict[str, Any]) -> dict[str, str]:
    """A known energy between the landmarks above the nominal capacity is a typo (the learning bounds it too)."""
    full_energy = options.get(CONF_FULL_ENERGY_KWH)
    if full_energy is not None and float(full_energy) > float(options[CONF_NOMINAL_CAPACITY_KWH]):
        return {"base": "full_energy_above_capacity"}
    return {}


class BatteryConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors = {**_source_errors(user_input), **_battery_errors(user_input)} if user_input is not None else {}
        if user_input is not None and not errors:
            options = dict(user_input)
            name = options.pop(CONF_NAME)
            await self.async_set_unique_id(options[CONF_SOC_ENTITY])
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=name, data={}, options=options)
        defaults = user_input or {}
        schema = (
            probatio.Schema(
                {probatio.Required(CONF_NAME, default=defaults.get(CONF_NAME, "Battery")): selector.TextSelector()}
            )
            .extend(_sources_schema(defaults).schema)
            .extend(_battery_schema(defaults).schema)
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Other source entities (one replaced or removed); the battery's parameters and the estimate stay."""
        entry = self._get_reconfigure_entry()
        errors = _source_errors(user_input) if user_input is not None else {}
        if user_input is not None and not errors:
            soc = user_input[CONF_SOC_ENTITY]
            if any(other.unique_id == soc for other in self._async_current_entries() if other is not entry):
                return self.async_abort(reason="already_configured")
            battery = {key: value for key, value in entry.options.items() if key not in RECONFIGURE_KEYS}
            return self.async_update_reload_and_abort(entry, unique_id=soc, options={**battery, **user_input})
        defaults = user_input if user_input is not None else dict(entry.options)
        return self.async_show_form(step_id="reconfigure", data_schema=_sources_schema(defaults), errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> BatteryOptionsFlow:
        return BatteryOptionsFlow()


class BatteryOptionsFlow(OptionsFlowWithReload):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors = _battery_errors(user_input) if user_input is not None else {}
        if user_input is not None and not errors:
            sources = {key: value for key, value in self.config_entry.options.items() if key in RECONFIGURE_KEYS}
            return self.async_create_entry(data={**sources, **user_input})
        defaults = user_input if user_input is not None else dict(self.config_entry.options)
        return self.async_show_form(step_id="init", data_schema=_battery_schema(defaults), errors=errors)
