# Smart Hass - Battery

Smart Hass - Battery estimates the energy really stored in a home battery. A battery's BMS reports a state of
charge, but on many batteries it is wrong by a few kWh in the middle of the range: it runs ahead while charging,
lags while discharging, and holds on plateaus (e.g. at 89 % while 2 kWh still go in). The integration counts the
energy that flows in and out of the battery since the last physical landmark, and exposes a stored energy, a room to
full and a corrected state of charge.

It only reads and estimates: it never drives the inverter or the battery.

## How it estimates

- **Landmarks**: the battery is **full** when a cell reaches its full voltage (3.50 V for LFP by default; without
  cell voltages, when the state of charge reaches 100 %), **empty** when the state of charge crosses the empty
  threshold while discharging. At a landmark the stored energy is known: the energy between the landmarks at full,
  0 at empty.
- **Counting**: between landmarks, the energy that flows in and out (the battery's DC power, or its energy meters)
  moves the estimate; what goes in counts times the round trip (the losses are put on the way in, so the estimate is
  what will come out).
- **Learning**: from one landmark to the next of the same kind, what came out over what went in is the round trip;
  from one kind to the other, the energy between them. Both are always measured (diagnostic sensors); they replace
  the configured values once *Use the learned values* is on, from 3 cycles.
- **Start**: before the first landmark, the estimate starts from the state of charge, and starts from it again if
  the counting drifts more than 3 kWh away from it.

On 10 days of a real battery (4 Pylontech US5000, 19.2 kWh), the state of charge times the capacity was off by
0.63 kWh on average and 1.89 at worst; the counting since the landmarks by 0.43 and 1.09.

## Requirements

- Home Assistant 2026.10 or later.
- The battery's **state of charge** from its BMS (%).
- Its **DC power** (W or kW) and/or its **energy meters** in and out (DC, cumulative or daily; Wh, kWh, MWh): the
  power, or both meters. With both, the meters count what the power misses while unavailable (and during a restart
  of Home Assistant).
- Recommended: the **highest cell voltage** of each pack (V or mV): the full landmark. Without it, the state of
  charge reaching 100 % is — later and less exact on batteries whose BMS jumps to 100 %.

## Installation

With HACS: add `https://github.com/vermi0ffh/smarthass-battery` as a custom repository (category *Integration*),
install **Smart Hass - Battery**, restart Home Assistant, then *Settings → Devices & services → Add integration*.

## Configuration

| Option | Default | Description |
|--------|---------|-------------|
| Name | Battery | The device's name |
| State of charge | — | The BMS's state of charge (%) |
| Battery power | none | DC power (W or kW), positive while charging |
| Power positive while discharging | off | For an inverter that reports it the other way |
| Energy in, Energy out | none | Cumulative or daily meters of the DC energy in and out (both or none) |
| Cell voltages | none | The highest cell voltage of each pack (the highest of them is used) |
| Nominal capacity | — | The battery's capacity on its datasheet (kWh) |
| Empty threshold | 9 % | The state of charge taken as empty (where your automation switches the house to the grid) |
| Full cell voltage | 3.50 V | A cell at this voltage is the full landmark |
| Round trip | 96 % | DC energy out for energy in (96.4 % measured over 8 daily cycles on LFP) |
| Energy between the landmarks | the nominal capacity above the empty threshold | What the battery delivers from full to empty |
| Maximum power | 30 kW | A meter increase faster than this is ignored as spurious |
| Use the learned values | off | Count the learned round trip and energy in place of the two above |

The battery's parameters can be changed later (*Configure* on the integration), the entities read by reconfiguring
it (*Reconfigure* in its menu): the estimate stays, replaced meters are counted from their first reading.

## Entities

| Entity | Unit | Description |
|--------|------|-------------|
| Stored energy | kWh | What the battery can still deliver above the empty threshold; its attributes give a planner the battery (capacity, energy between the landmarks and round trip in use, empty threshold), the room, the uncertainty, the last landmark and the source entities |
| State of charge | % | The stored energy on the BMS's scale (the empty threshold at empty, 100 % at full), linear in energy |
| Room to full | kWh | What it can still take before full, in delivered kWh |
| Uncertainty (diagnostic) | kWh | How far the estimate may be off: that of its start (full 0.4 kWh, empty 0.8, the state of charge 2, set by hand 0.5) plus 2 % of what flowed since |
| Learned round trip (diagnostic) | % | Measured on the cycles; attributes: the configured one, the one in use, the cycles counted |
| Learned energy between the landmarks (diagnostic) | kWh | Measured on the cycles; same attributes |
| Last landmark (diagnostic) | time | The last landmark seen; attributes: its kind (full, empty) and how far the counting was from it |

The stored energy, the state of charge, the room and the uncertainty become unavailable when the flows have not
been readable for 15 minutes (the power, unless both meters count; the meters, without a power).

## Services

- `smart_hass_battery.mark_full` (`config_entry_id`): the battery is full now.
- `smart_hass_battery.mark_empty` (`config_entry_id`): the battery is at its empty threshold now.
- `smart_hass_battery.set_energy` (`config_entry_id`, `energy_kwh`): the energy it can still deliver above the empty
  threshold.

A landmark given by hand teaches nothing (the learning only trusts the landmarks it saw). If the state of charge
disagrees with it by more than 3 kWh, the next reading starts again from the state of charge.

## How the data is updated

Nothing is polled. The estimate follows **every state change** of the source entities, and is refreshed every minute
in between (the power is counted at its last value). It is saved 30 s after a change and when Home Assistant stops;
after a restart, the energy meters (if any) count the downtime, the power is not assumed to have held.

## Use cases

- **Plan the battery**: an energy planner (e.g. Smart Hass - Energy Optimizer) reads the stored energy and the room
  instead of the BMS's state of charge: the night charge stops at the right energy, the evening does not run out
  earlier than planned.
- **Charge targets in energy**: an automation that charges to a target compares it with the corrected state of
  charge, which does not hold at 89 % while 2 kWh still go in.
- **Watch the battery age**: the learned energy between the landmarks falls as the battery loses capacity.

## Examples

The entity ids below are those of a battery named *Battery*, with Home Assistant in English; yours follow the name
you gave and Home Assistant's language when it was created.

Stop a night charge from the grid once 12 kWh are stored (`switch.grid_charge` stands for what your inverter's
integration offers to allow the grid charge):

```yaml
automation:
  - alias: Battery - stop the night charge at 12 kWh
    triggers:
      - trigger: numeric_state
        entity_id: sensor.battery_stored_energy
        above: 12
    conditions:
      - condition: time
        after: "22:00:00"
        before: "06:00:00"
    actions:
      - action: switch.turn_off
        target:
          entity_id: switch.grid_charge
```

A notification when less than 2 kWh are left, with how far to trust it:

```yaml
automation:
  - alias: Battery - low
    triggers:
      - trigger: numeric_state
        entity_id: sensor.battery_stored_energy
        below: 2
    actions:
      - action: notify.notify
        data:
          message: >-
            {{ states('sensor.battery_stored_energy') | float | round(1) }} kWh left
            (± {{ state_attr('sensor.battery_stored_energy', 'uncertainty_kwh') | round(1) }} kWh).
```

A charge to the top at least once a week, so the full landmark and the learning stay fresh:

```yaml
automation:
  - alias: Battery - weekly full charge
    triggers:
      - trigger: time
        at: "22:00:00"
    conditions:
      - condition: template
        value_template: >-
          {{ state_attr('sensor.battery_stored_energy', 'last_landmark') != 'full'
             or (now() - as_datetime(state_attr('sensor.battery_stored_energy', 'last_landmark_at'))).days >= 7 }}
    actions:
      - action: switch.turn_on
        target:
          entity_id: switch.grid_charge
```

The energy's attributes are what a planner needs: `full_energy_kwh` (the energy between the landmarks in use),
`efficiency` (the round trip in use), `room_kwh`, `uncertainty_kwh`, `empty_soc_pct`, the source entities.

## Known limitations

- **DC counting**: the inverters' losses (AC side) are not counted; the round trip is the battery's.
- **Idle consumption**: what the battery feeds at rest (its BMS, the inverter idle) is counted like any discharge;
  it is not learned separately.
- **One empty threshold**: the empty landmark is the state of charge's crossing, as precise as the BMS near empty
  (±0.8 kWh measured).
- **Landmarks needed**: a battery that never reaches full nor the empty threshold keeps counting from its last start;
  the uncertainty grows with what flowed. Charge it full now and then.
- **One battery per entry**: packs on separate inverters with separate measures are one battery only if one state
  of charge and one power (or one pair of meters) cover all of them.

## Troubleshooting

| Symptom | What to check |
|---------|---------------|
| The stored energy is *unavailable* | The power (or the meters) has been unavailable for 15 minutes: the log says which and why; *Settings* > *Repairs* if the entity no longer exists |
| The energy moves the wrong way | The power's sign: *Power positive while discharging* in the reconfiguration |
| The full landmark is never seen | The cell voltages and the full cell voltage: a cell must reach it at the top of the charge |
| It jumps back to the state of charge | The counting drifted more than 3 kWh from it: a wrong round trip, capacity or power sign, or flows missed |

To report a problem, attach the **diagnostics** (*Settings* > *Devices & services* > *Smart Hass - Battery* > the
battery > ⋮ > *Download diagnostics*): the options, the estimate, the model's state and what each source entity
shows.

## Removal

1. *Settings* > *Devices & services* > *Smart Hass - Battery* > ⋮ on each battery > *Delete*: its entities and its
   stored estimate are removed.
2. In HACS, remove *Smart Hass - Battery*, then restart Home Assistant.

Update first what reads its entities (automations, dashboards, an energy planner): they become unavailable.
