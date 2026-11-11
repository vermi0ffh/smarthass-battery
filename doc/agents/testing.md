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
| `tests/model/test_battery.py` | Unknown until a state of charge then started from it, a configured full energy, a refused configuration, counting by power (round trip on the way in, uncertainty), a late reading (no interval, then ignored), a non-finite value, an unavailable power pauses, an unavailable state of charge keeps the estimate, the meters fill a power gap then stop counting (also across a daily reset, not a spurious jump), one meter unavailable, meters alone with the daily reset and a spurious jump, the empty landmark (crossing, error, room), its jitter and re-arming, the full landmark by cell voltage (and the charge past it), its re-arming after 1 kWh out, by state of charge without cell voltages, the counting dropped beyond 3 kWh from the state of charge, round trip and full energy learned on cycles, used only from 5 cycles and with learning on, pending / ready / far (a far one still used), short or impossible cycles, unseen flows (a power gap without meters, before the meters' first reading), landmarks told by the user (teaching nothing; with an estimate: values, uncertainty, re-arming), `set_energy`, the last full and empty times outliving the counting's restarts (and told landmarks), a restart not holding the power and the meters counting the downtime, a replaced meter (with and without a power), state round trip, its version, a 0.1.0 state's last full and empty times (a saved unknown one stays unknown), those times through a restart and unreadable stored states |
| `tests/model/test_replay.py` | The recording replayed (`tests/model/recording.py`): its round trip (0.964), counting against the BMS's state of charge (average, worst), the lead and lag gone, the landmarks seen, what is learned without being used, learning correcting a wrong configuration |
| `tests/integration/test_battery.py` | The config flow (entry created with learning on, the flows needed, an energy above the capacity, one entry per state of charge), the options (reload, sources kept, the error, learning kept off for a battery saved without it), reconfiguring (meters replaced: not taken for an increase of the old ones, then counting a power gap; the checks, another battery's state of charge); the estimate (started from the state of charge, the power counted while it holds, inverted, the full landmark at the highest cell in mV with one cell unavailable, at 100 % without cells, the empty landmark, the services and their refusals, an unloaded entry included), meters alone in Wh, kWh and MWh, the learned values and the planner's attributes (with the last full and empty times); restart (the estimate kept, the last interval counted at unload, the meters counting the downtime, an unreadable stored state, the store removed with the entry); unavailable sources (15 min then unavailable, logged once and back, kept with meters, meters alone), missing ones (an error issue for the power until reconfigured, a warning for the cells cleared when back), units and non-numbers; the learning's issues (ready while learning is off and its one-click repair, none with learning on or before 5 cycles, a far round trip or energy and its issue cleared once configured, an ignored issue kept through a reload and removed with the battery); diagnostics |
| `review/tests/` | The review tool (see [review.md](review.md)) |
