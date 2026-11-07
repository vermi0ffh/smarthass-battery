"""Constants of the integration: domain, option keys and their defaults."""

DOMAIN = "smart_hass_battery"

# Entities read (rule 3: only read)
CONF_SOC_ENTITY = "soc_entity"
CONF_POWER_ENTITY = "power_entity"
CONF_CHARGED_ENTITY = "charged_entity"
CONF_DISCHARGED_ENTITY = "discharged_entity"
CONF_CELL_VOLTAGE_ENTITIES = "cell_voltage_entities"
SOURCE_KEYS = (CONF_SOC_ENTITY, CONF_POWER_ENTITY, CONF_CHARGED_ENTITY, CONF_DISCHARGED_ENTITY)
# The power is read positive while charging; on: the inverter reports it the other way (positive while discharging)
CONF_INVERT_POWER = "invert_power"

# The battery
CONF_NOMINAL_CAPACITY_KWH = "nominal_capacity_kwh"
CONF_EMPTY_SOC_PCT = "empty_soc_pct"
CONF_FULL_CELL_V = "full_cell_v"
CONF_EFFICIENCY_PCT = "efficiency_pct"
CONF_FULL_ENERGY_KWH = "full_energy_kwh"
CONF_MAX_POWER_KW = "max_power_kw"
# Count the learned round trip and energy between the landmarks in place of the configured ones (off by default:
# rule 25)
CONF_LEARN = "learn"

# The defaults of the model (doc/agents/model.md): 9 % is the threshold where the recorded house's Home Assistant
# safety switches to the grid; 3.50 V an LFP cell at the top of the charge (the BMS's 97 % on 2026-11-07); 96 % the
# DC round trip (0.964 over 8 daily cycles, 2026-10-29 to 11-06)
DEFAULT_EMPTY_SOC_PCT = 9.0
DEFAULT_FULL_CELL_V = 3.5
DEFAULT_EFFICIENCY_PCT = 96.0
DEFAULT_MAX_POWER_KW = 30.0

# Services
SERVICE_MARK_FULL = "mark_full"
SERVICE_MARK_EMPTY = "mark_empty"
SERVICE_SET_ENERGY = "set_energy"
ATTR_CONFIG_ENTRY_ID = "config_entry_id"
ATTR_ENERGY_KWH = "energy_kwh"
