# The battery model

`custom_components/smart_hass_battery/model/` — pure Python (rule 1).

## Meters

`meter.py`: `meter_delta(previous, current, max_delta)`, what a cumulative meter counted between two readings
(rule 12): a drop below half the previous value is a reset (the inverters' daily energy counters at midnight) and the
new value counts fully; a smaller drop is jitter and counts nothing; an increase beyond `max_delta` (more than the
battery's power allows since the previous reading) is a spurious value; an unavailable reading counts nothing.
