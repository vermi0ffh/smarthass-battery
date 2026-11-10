# Changelog

Versions follow [semantic versioning](https://semver.org/). Before 1.0.0, a minor version may change the options or
the entities; such a change is described here, with what to do.

## 0.2.0 (2026-11-10)

- **Entities**: the stored energy's `last_full_at` and `last_empty_at` attributes (and the diagnostics): when the
  battery was last full and empty, seen or told. Unlike `last_landmark_at`, they survive a restart of the counting
  from the state of charge or a set energy, and the full one survives an empty landmark: a planner or an automation
  charging to full every few days reads `last_full_at`. The weekly full charge example uses it (the former one charged
  every day after an empty landmark).
- **Upgrade**: an estimate saved by 0.1.0 takes its last landmark's time for the matching attribute; the other one is
  unknown until the battery reaches that landmark again.

## 0.1.0 (2026-11-07)

First version.

- **Model**: the energy the battery can still deliver above its empty threshold, counted from its DC power or energy
  meters since the last landmark (full: a cell at the full voltage, or the state of charge at 100 %; empty: the state
  of charge crossing the empty threshold); the round trip and the energy between the landmarks learned on the cycles
  (used once *Use the learned values* is on).
- **Entities**: stored energy (with the attributes a planner needs), state of charge (corrected), room to full;
  diagnostic: uncertainty, learned round trip, learned energy between the landmarks, last landmark.
- **Services**: `mark_full`, `mark_empty`, `set_energy`.
- **Configuration** from the UI (state of charge, power, energy meters, cell voltages, the battery), reconfiguration
  of the entities, options for the battery; diagnostics; repair issues for missing entities; English and French.
