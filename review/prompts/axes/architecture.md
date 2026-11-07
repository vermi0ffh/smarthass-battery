---
label: Architecture of the integration
rules: [rule-1, rule-2, rule-3, rule-5, rule-6]
docs: [doc/agents/architecture.md, doc/agents/model.md]
---
# Your axis: architecture of the integration

The integration is split as `doc/agents/architecture.md` describes: `model/` (the battery model, pure Python) ←
`tracker.py` (the Home Assistant glue) ← the platforms (`sensor.py`, `binary_sensor.py`), `config_flow.py`,
`__init__.py` (setup, services). Base your judgment on what the project already does elsewhere.

Check that:

- `model/` imports only the standard library: no Home Assistant, no I/O, no reading of the clock (rule 1).
- The Home Assistant semantics (`unavailable`, `unknown`, `on`, units of measurement, event objects) stay in the
  tracker; the platforms and the config flow carry no business rule (rule 2).
- The integration never calls a service that acts on a device or on another integration's entity (rule 3).
- Nothing imports another Smart Hass project (rule 5).
- No installation data (entity id, capacity, voltage, efficiency) is hard-coded outside the config flow defaults
  (rule 6).
- Model objects are not anemic when the matching logic should live in them; the tracker orchestrates, it does not
  compute the physics.
