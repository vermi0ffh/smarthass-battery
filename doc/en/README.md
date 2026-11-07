# Smart Hass - Battery

Smart Hass - Battery estimates the energy really stored in a home battery. A battery's BMS reports a state of
charge, but on many batteries it is wrong by a few kWh in the middle of the range: it runs ahead while charging,
lags while discharging, and holds on plateaus (e.g. at 89 % while 2 kWh still go in). The integration counts the
energy that flows in and out of the battery (its DC power or energy meters) since the last physical landmark:

- **full**: a cell reaches its full voltage (3.50 V for LFP by default);
- **empty**: the state of charge crosses the empty threshold while discharging.

On each cycle between two landmarks it learns the battery's round-trip efficiency and the energy between empty and
full.

It only reads and estimates: it never drives the inverter or the battery.

**Status**: in development — the model is being written and validated; the Home Assistant entities and the
configuration come next.
