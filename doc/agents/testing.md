# Tests

`make test` runs everything (`pytest`, `asyncio_mode = auto`) and fails under 95 % coverage of the integration;
`make test-model` only the model.

## Families (rule 14)

- **`tests/model/`**: the pure model, no Home Assistant. Times are fixed `datetime`s with a zone; the values come
  from the measures of a real battery when there are some (cite them, rule 9). A model change validated on a real
  installation replays a recorded history from `tests/model/data/` (the only files the model tests read).
- **`tests/integration/`**: the integration inside a test Home Assistant (`pytest-homeassistant-custom-component`,
  the `hass` fixture; `tests/conftest.py` enables the custom integrations).

## Recorded histories

`tests/model/data/battery_2026-10-28_2026-11-07.csv.gz`: 10 days of a real house (4 Pylontech US5000 packs, 19.2 kWh,
on 2 Growatt SPF 5000 ES inverters, charged from the grid at night, emptied each evening to the 9 % safety), exported
from Home Assistant's history: `offset_s,key,value` after a `# start=` line, keys `soc_pct` (the BMS), `power_w` (DC,
positive while charging), `charged_kwh` / `discharged_kwh` (the daily meters), `cell_high_v` (the highest cell of
the 4 packs, as the tracker will compute it). Only these measures: entity ids renamed, dates kept (rule 22).
`tests/model/recording.py` reads it into the model's readings (`events`), integrates its power (`flows`) and finds
the empty crossings — the reference of `test_replay.py`.

## Files

| File | Covers |
|------|--------|
| `tests/model/test_meter.py` | `meter_delta`: counted, daily reset, jitter, first and unavailable readings, increase beyond the physics |
| `tests/model/test_battery.py` | Unknown until a state of charge then started from it, a configured full energy, counting by power (round trip on the way in, uncertainty), a late reading, an unavailable power pauses, the meters fill a power gap then stop counting, meters alone with the daily reset and a spurious jump, the empty landmark (crossing, error, room), its jitter and re-arming, the full landmark by cell voltage (and the charge past it), its re-arming after 1 kWh out, by state of charge without cell voltages, the counting dropped beyond 3 kWh from the state of charge, round trip and full energy learned on cycles, used only from 3 cycles and with learning on, short or impossible cycles, unseen flows (a power gap without meters, before the meters' first reading), landmarks told by the user, `set_energy`, a restart not holding the power, a replaced meter, state round trip and unreadable stored states |
| `tests/model/test_replay.py` | The recording replayed (`tests/model/recording.py`): its round trip (0.964), counting against the BMS's state of charge (average, worst), the lead and lag gone, the landmarks seen, what is learned without being used, learning correcting a wrong configuration |
| `review/tests/` | The review tool (see [review.md](review.md)) |
