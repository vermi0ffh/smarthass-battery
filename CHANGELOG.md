# Changelog

## Unreleased (0.1.0)

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
