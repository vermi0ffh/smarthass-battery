# Smart Hass - Battery

A Home Assistant integration that estimates the energy **really** stored in a home battery, from the measures Home
Assistant already has: the state of charge reported by the BMS, the battery's DC power or energy meters and its
cells' voltages.

A BMS's state of charge is often wrong by a few kWh in the middle of the range: it runs ahead while charging, lags
while discharging and holds on plateaus. Smart Hass - Battery counts the energy flowing in and out since the last
physical landmark (battery full, battery empty), learns the battery's round-trip efficiency and usable energy on
each cycle, and exposes a stored energy, a room to full and a corrected state of charge that automations and energy
planners can rely on.

It only reads and estimates: it never drives the inverter or the battery.

Installation with HACS (custom repository `https://github.com/vermi0ffh/smarthass-battery`, category *Integration*).
Documentation: [English](doc/en/README.md), [français](doc/fr/README.md).

## License

Apache License 2.0 — see [LICENSE](LICENSE) and [NOTICE](NOTICE). Community project, not affiliated with Home
Assistant or the Open Home Foundation.
