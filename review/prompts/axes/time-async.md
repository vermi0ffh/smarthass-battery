---
label: Time and the event loop
rules: [rule-4, rule-11]
docs: [doc/agents/architecture.md, doc/agents/model.md]
---
# Your axis: time and Home Assistant's event loop

Check that:

- Time is handled as rule 11 says: timezone-aware datetimes only (`homeassistant.util.dt`), durations from the
  events' timestamps, the model never reads the clock.
- Rule 4: the code runs in Home Assistant's event loop without blocking it; callbacks decorated `@callback` do no
  I/O; a blocking operation, if any, goes to the executor; external HTTP uses Home Assistant's `aiohttp` session
  with a timeout.
- Timers (`async_track_point_in_utc_time`, `async_track_time_interval`) are cancelled and replaced correctly: no two
  pending timers for the same check, none left after unload.
- The energy balance integrates each interval once: no double counting when a reading and a timer arrive at the same
  time, no negative interval.
