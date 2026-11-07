# Architecture

## Layers

```
model/  ←  tracker.py  ←  sensor.py, binary_sensor.py, __init__.py (setup, services), config_flow.py
```

- **`model/`** (pure Python, rule 1): the battery model, see [model.md](model.md).
- **`tracker.py`** and the platforms (rule 2): not written yet. The tracker will read the configured entities into
  the model's readings (`unavailable` / `unknown` → None, units converted), update the model on every state change
  (time = the event's `time_fired`) and on a timer, persist its state (`Store`) and notify the entities; the
  platforms will only expose the tracker's values.

## Entities (a contract, rule 20)

None yet. The planned ones: stored energy (kWh), room to full (kWh), corrected state of charge (%), the learned
round-trip efficiency and full energy (diagnostic), whether the estimate is anchored.
