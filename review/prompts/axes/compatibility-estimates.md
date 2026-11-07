---
label: Backward compatibility and validated estimates
rules: [rule-3, rule-20, rule-25]
docs: [doc/en/README.md, doc/agents/model.md]
---
# Your axis: backward compatibility and validated estimates

The integration runs at the users' homes, and its estimate drives their battery through their automations or an
energy planner: an update must not break an installation that worked, and must not change the estimate without a
validation.

Check that:

- Config entries (rule 20): a changed schema bumps the entry's `VERSION` and migrates the old entries
  (`async_migrate_entry`); a new option has a default that keeps the old behavior.
- Stored state (rule 20): a changed format of the persisted state bumps its version and still reads the previous
  one; a restart never loses the estimate or the calibration.
- Entities (rule 20): `unique_id`, meaning, unit, `device_class` and `state_class` of an existing entity are kept; a
  change is announced in the changelog as a breaking change.
- Estimates (rule 25): a change to the model or its calibration comes with its replay on a recorded history and the
  comparison with the previous version; a new calibration arrives behind an option until validated.
- Read only (rule 3): nothing new switches a device.
