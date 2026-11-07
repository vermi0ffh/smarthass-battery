# The battery model

`custom_components/smart_hass_battery/model/` — pure Python (rule 1): `battery.py` (`BatteryConfig`, `Reading`,
`BatteryState`, `Battery`; `state_to_dict` / `state_from_dict` for persistence) and `meter.py`.

## What it estimates

`Battery.energy_kwh`: what the battery can still **deliver** (DC, kWh) above its **empty landmark**. "Delivered"
units: a kWh charged counts as the round trip times a kWh (`efficiency`), a kWh discharged as a kWh — the losses are
all put on the way in, so the estimate is what will come out. From it:

- `room_kwh`: what it can still take before the full landmark, in delivered kWh (0 past it);
- `soc_pct`: a state of charge on the BMS's scale (`empty_soc_pct` at the empty landmark, 100 % at the full one)
  but linear in energy, clamped to 0–100 %;
- `uncertainty_kwh`: the uncertainty of the start (full landmark 0.4 kWh, empty 0.8, the BMS's state of charge 2.0,
  set by the user 0.5) plus 2 % of what flowed since (`START_UNCERTAINTY_KWH`, `COUNTED_UNCERTAINTY`, from the
  spread measured below).

Why: on 4 Pylontech US5000 packs (19.2 kWh, 2026-10-28 to 11-07), the BMS's state of charge times the nominal
capacity was off by 0.63 kWh on average and 1.89 at worst; it runs ahead while charging (+0.42 kWh on average,
up to 2 kWh between 50 and 88 %, then holds at 89 % while 1.6–1.9 kWh go in) and lags while discharging (−0.50; 0.7
kWh still there at "11 %"). Its total is right (17.5 kWh from 100 % to 9 %): it is the shape that is wrong.

## Counting

`update(at, reading)` first counts the interval since the previous update at the power **then** in force (held: Home
Assistant records a state only when it changes), then takes `reading`. A reading older than the last update is
ignored (events out of order: the newer one already holds the inputs); a non-finite value (nan, inf) is unavailable:
no divergence check would catch a nan.

- **With a power** (`has_power`, DC, positive while charging): the flows are its integral. An unavailable power
  pauses the counting; with energy meters (`has_meters`), the meters count what the gap missed at their next
  reading (their increase beyond the power integrated since their previous reading); without, the cycles in
  progress are marked incomplete (nothing is learned from them).
- **Without a power**: the energy meters' increases are the flows, through `meter_delta` (below).

On the recording the power's integral matched the daily meters within 0.1–0.2 kWh a day; the meters' resolution
(0.1 kWh) is why the power comes first.

## Landmarks

The counting restarts from a landmark, where the battery's state is known:

- **full** (`FULL`): the highest cell voltage reaching `full_cell_v` (3.50 V by default: reached at the BMS's 97 %
  on 2026-11-07; 3.55 V at its 100 %), or without cell voltages (`full_cell_v=None`) the state of charge reaching
  100 %. The estimate becomes `full_energy_kwh`. Armed again once 1 kWh went out (`FULL_REARM_KWH`): the voltage dips
  when the charge slows, without the battery leaving full.
- **empty** (`EMPTY`): the state of charge crossing `empty_soc_pct` downward (9 % by default: the Home Assistant
  safety of the recorded house switches to the grid below 10 %). The estimate becomes 0. Armed again once the state
  of charge rose 2 points above the threshold (`EMPTY_REARM_PCT`): it jitters around it.

`last_landmark_error_kwh` keeps, at each landmark, how far the counting was from it. Measured spread: ±0.4 kWh at the
full landmark between 4 cycles, ±0.8 kWh at the empty one between 8.

Without an estimate (first start, an unreadable stored state), the first state of charge starts the counting
(`start = "soc"`): `(soc − empty) / (100 − empty) × full_energy_kwh`. When the counting and that value disagree by more
than 3 kWh (`DIVERGENCE_KWH`, beyond the BMS's own 2 kWh error), the counting has lost track (a missed flow, a wrong
sign or efficiency) and starts again from the state of charge.

## Learning

Two cycles run together: since the last full landmark and since the last empty one (`Cycle`: energy in, energy out,
complete when it started at a landmark seen and every flow of it was seen).

- **Round trip**: at a landmark, the cycle since the previous landmark of the **same** kind ends where it started:
  out / in is the round trip. Counted from half a battery of energy in (`MIN_CYCLE_FRACTION`), between 0.85 and 1.05
  (above 1 on purpose: the landmarks' spread puts real cycles there, and rejecting them only would bias the round
  trip down). The learned value is the ratio of the cycles' totals, each cycle weighing 0.9 less at the next
  (`CYCLE_DECAY`): one cycle carries ±4 % of the empty landmark's spread (0.918 to 1.027 measured), ten ±0.5 %.
- **Full energy**: at a landmark of the other kind than the previous one, the energy stored (empty → full:
  `efficiency × in − out`) or delivered (full → empty: `out − efficiency × in`) is the energy between the
  landmarks; it moves 30 % toward each new cycle's (`FULL_ENERGY_WEIGHT`), within 0.5–1.1 times the configured one.
- `learned_efficiency` and `learned_full_energy_kwh` are always measured; they replace the configured values only
  with `learn` on (rule 25) and from 3 cycles (`MIN_LEARNED_CYCLES`).

A landmark told by the user (`mark_full`, `mark_empty`) ends and starts no learned cycle; `set_energy` restarts the
counting but not the cycles (the flows are still seen).

`BatteryConfig` refuses (`ValueError`) a configuration without energy between the landmarks (an empty threshold
outside 0–100 %, a nil capacity or full energy), a nil or impossible round trip, a nil maximum power: the config flow
will check the same first.

Defaults: `efficiency` 0.96 (0.964 measured over 8 daily cycles), `full_energy_kwh` the nominal capacity above the
empty threshold (17.47 kWh for 19.2 kWh at 9 %; 17.2 learned on the recording).

## Restart

`resume()` after a restart: the power last read is not held over the downtime; the energy meters count it at their
next reading (the same day: a daily meter reset meanwhile loses what it counted before midnight). `forget_meters()`
when other meters replace the configured ones: their next readings are the base, the flows meanwhile unknown (the
cycles in progress are incomplete).

## Persistence

`state_to_dict` / `state_from_dict`, format `STATE_VERSION` (1, written as `version`; absent = 1). A missing or unreadable field takes its default; an
unreadable estimate or start makes the estimate unknown (it starts again from the state of charge), an unreadable
cycle is incomplete, unreadable learned totals are dropped.

## Validation on a real battery (rule 25)

`tests/model/test_replay.py` replays the recording of `tests/model/data/` (see [testing.md](testing.md)). The
reference, every half hour: what the battery really delivered until the next empty landmark (energy out minus energy
in times the recording's round trip, 0.964). With the defaults:

| | Average error | Worst | While charging | While discharging |
|---|---|---|---|---|
| BMS state of charge × nominal capacity | 0.63 kWh | 1.89 | +0.42 | −0.50 |
| Counting since the landmarks | 0.43 kWh | 1.09 | +0.02 | +0.07 |

Learning on brings nothing on this battery (its defaults are close: 0.96 configured, 0.965 learned; 17.47 kWh
configured, 17.2 learned); from a wrong configuration (22 kWh, round trip 0.92) it learns 0.964 and 17.2 kWh and
halves the error of the last 3.5 days (0.80 kWh against 1.52).

## Not modeled yet

The idle consumption the battery feeds (about 80 W measured at night) is counted like any discharge; it is not
learned separately. The losses of the inverters (AC side) are out of the model: it counts DC flows only.

## Meters

`meter.py`: `meter_delta(previous, current, max_delta)`, what a cumulative meter counted between two readings
(rule 12): a drop below half the previous value is a reset (the inverters' daily energy counters at midnight) and the
new value counts fully; a smaller drop is jitter and counts nothing; an increase beyond `max_delta` (more than the
battery's power allows since the previous reading: `max_power_kw`, 30 kW by default, plus a minute) is a spurious
value; an unavailable reading counts nothing. A reading with only one of the two meters keeps both bases.
