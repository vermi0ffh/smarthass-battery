# Tests

`make test` runs everything (`pytest`, `asyncio_mode = auto`) and fails under 95 % coverage of the integration;
`make test-model` only the model.

## Families (rule 14)

- **`tests/model/`**: the pure model, no Home Assistant. Times are fixed `datetime`s with a zone; the values come
  from the measures of a real battery when there are some (cite them, rule 9). A model change validated on a real
  installation replays a recorded history from `tests/model/data/` (the only files the model tests read).
- **`tests/integration/`**: the integration inside a test Home Assistant (`pytest-homeassistant-custom-component`,
  the `hass` fixture; `tests/conftest.py` enables the custom integrations).

## Files

| File | Covers |
|------|--------|
| `tests/model/test_meter.py` | `meter_delta`: counted, daily reset, jitter, first and unavailable readings, increase beyond the physics |
| `review/tests/` | The review tool (see [review.md](review.md)) |
