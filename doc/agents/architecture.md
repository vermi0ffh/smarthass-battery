# Architecture

## Layers

```
model/  ←  tracker.py  ←  sensor.py, diagnostics.py, __init__.py (setup, services), config_flow.py
```

- **`model/`** (pure Python, rule 1): `battery.py` (`BatteryConfig`, `Reading`, `BatteryState`, `Battery`: the
  counting, the landmarks, the learning, see [model.md](model.md); `state_to_dict` / `state_from_dict` for
  persistence), `meter.py` (`meter_delta`, rule 12).
- **`tracker.py`** (rule 2): `battery_config(options)` builds the model's configuration from the entry's options
  (`has_power` / `has_meters` from the entities given, `full_cell_v` only with cell voltages, the round trip from
  percent). `BatteryTracker` reads the configured entities into a `Reading` (`unavailable`, `unknown`, a non-number
  or an unknown unit → None; units converted: W/kW, Wh/kWh/MWh, V/mV; the power negated with `invert_power`; the
  highest of the cell voltages that read), updates the model on every state change (time = the event's
  `time_fired`) and every minute (`REFRESH_INTERVAL`: the power is counted at its last value while it holds),
  persists its state, and notifies the entities.
- **`__init__.py`**: setup and unload of an entry (the tracker's stop registered with `async_on_unload`: it also
  runs when the setup fails after the tracker started), the services (registered once in `async_setup`, refused with a
  translated error for an unknown entry, `set_energy` refusing a non-finite value), the stored state removed with
  the entry.
- **`config_flow.py`**: the user step (name, sources, battery), `reconfigure` (the sources only; the battery and the
  estimate stay), the options (the battery only). Unique id: the state of charge entity. Errors: neither a power nor
  both meters (`no_flow_source`), one meter alone (`one_meter`), an energy between the landmarks above the nominal
  capacity (`full_energy_above_capacity`).
- **The platforms** (`sensor.py`) only expose the tracker's values; `diagnostics.py` the options, the estimate, the
  stored state and the source entities' states.

## Sources

| Option | Entity | Role |
|--------|--------|------|
| `soc_entity` | sensor, % | The empty landmark; the start and the divergence check |
| `power_entity` (+ `invert_power`) | sensor, power | The flows, integrated |
| `charged_entity`, `discharged_entity` | sensor, energy | The flows without a power; with one, what it missed |
| `cell_voltage_entities` | sensors, voltage | The full landmark (the highest of them) |

A source unreadable for 15 minutes (`UNAVAILABLE_AFTER`) is logged once with its cause, and once when it is back;
an entity that no longer exists raises a repair issue (`missing_<key>`), an error for a source the flows depend on
(the power without meters, a meter without power), a warning otherwise; it is deleted when the source reads again
and at unload. The estimate's entities are unavailable while the flows are unknown: the power unreadable (unless
both meters read), or a meter unreadable without a power.

## Persistence

`Store` `smart_hass_battery.<entry_id>` (`stored_state`), version `STORAGE_VERSION` (1): `state_to_dict` of the
model, which carries its own `version`, plus `sources` (the entity ids the state was measured with). The Store's
version stays 1 when the model's format changes (Home Assistant refuses a file of another major version without a
migration); `state_from_dict` reads the model's older formats. Saved 30 s after a change (`SAVE_DELAY_S`) and at
unload, after counting the interval since the last update. At start: an unreadable file starts from the state of
charge; the state restored, `resume()` (the power is not held over the downtime: the meters count it), `forget_meters()` when the
stored meters differ from the configured ones (reconfigured).

## Entities (a contract, rule 20)

Unique id `<entry_id>_<key>`, one device per entry.

| Key | Unit, class | Value | Attributes |
|-----|-------------|-------|------------|
| `energy` | kWh, `energy_storage`, measurement | `energy_kwh` | For a planner: `nominal_capacity_kwh`, `full_energy_kwh` and `efficiency` in use, `empty_soc_pct`, `room_kwh`, `uncertainty_kwh`, `soc_pct`, `last_landmark`, `last_landmark_at`, the source entity ids |
| `soc` | %, `battery`, measurement | `soc_pct` (corrected) | |
| `room` | kWh, `energy_storage`, measurement | `room_kwh` | |
| `uncertainty` | kWh, diagnostic | `uncertainty_kwh` | |
| `learned_efficiency` | %, diagnostic | `learned_efficiency` × 100 | `configured_efficiency`, `efficiency_in_use`, `learning_enabled`, `cycles` |
| `learned_full_energy` | kWh, diagnostic | `learned_full_energy_kwh` | `configured_full_energy_kwh`, `full_energy_in_use_kwh`, `learning_enabled`, `cycles` |
| `last_landmark` | timestamp, diagnostic | `last_landmark_at` | `kind` (`full`, `empty`), `error_kwh` |

The first four are unavailable while the flows are unknown (above); the learned values and the last landmark stay.
The energy's `room_kwh`, `uncertainty_kwh` and `soc_pct` attributes are not recorded (they move with every update).

## Services

`mark_full`, `mark_empty` (`config_entry_id`), `set_energy` (`config_entry_id`, `energy_kwh` ≥ 0): the tracker
counts the interval up to now, then calls the model's method.
