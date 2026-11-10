"""The battery in energy: what it can still deliver above its empty landmark, counted from the DC flows since the last
landmark (full or empty), the BMS's state of charge used only to cross the empty threshold and to start (see
doc/agents/model.md)."""

import math
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any

from .meter import meter_delta

# Landmarks. The BMS's state of charge is right only at its ends: on 4 Pylontech US5000 packs (2026-10-28 to 11-07)
# it ran ahead by up to 2 kWh while charging and lagged by 0.5 kWh while discharging; a cell's voltage at the top of
# the charge and the state of charge crossing the empty threshold are the landmarks the counting restarts from.
FULL = "full"
EMPTY = "empty"
# Not landmarks: the estimate started from the BMS's state of charge, or set by the user
FROM_SOC = "soc"
SET = "set"
LANDMARKS = (FULL, EMPTY)

# A landmark is armed again only once the battery left it: the empty one when the state of charge rose this much above
# the threshold, the full one when this much energy went out — the voltage dips and the state of charge jitters
# around a landmark without the battery leaving it
EMPTY_REARM_PCT = 2.0
FULL_REARM_KWH = 1.0

# Uncertainty of the estimate (kWh): that of its start, then a share of the energy counted since. Measured on
# 2026-10-28 to 11-07: the stored energy at the full landmark (a cell at 3.50 V) spread by ±0.4 kWh between 4 cycles,
# the empty one (the state of charge crossing 9 %) by ±0.8 kWh between 8; the round trip by ±0.7 % between cycles,
# hence 2 % of what flowed. The state of charge itself was off by up to 2 kWh.
START_UNCERTAINTY_KWH = {FULL: 0.4, EMPTY: 0.8, FROM_SOC: 2.0, SET: 0.5}
COUNTED_UNCERTAINTY = 0.02

# The counting is dropped for the state of charge when the two disagree by more than this: beyond the BMS's own error
# (2 kWh measured), the counting has lost track (a meter missed a flow, a wrong efficiency)
DIVERGENCE_KWH = 3.0

# One minute of slack on the battery's maximum power (BatteryConfig.max_power_kw) covers meter readings that arrive
# late
METER_SLACK_H = 1 / 60

# Learning. A cycle between two landmarks of the same kind gives the round trip (what came out over what went in)
# once enough energy flowed: the landmarks' spread (above) weighs too much on a shorter one. Between an empty and a
# full landmark, the energy stored or delivered gives the energy between them.
MIN_CYCLE_FRACTION = 0.5
# The round trip is the ratio of the cycles' totals, each cycle weighing this much less at the next: the empty
# landmark's ±0.8 kWh on an 18 kWh cycle is ±4 % on one cycle (0.918 to 1.027 measured, 2026-10-29 to 11-06), ±0.5 %
# over ten. The energy between the landmarks moves this much toward each new cycle's.
CYCLE_DECAY = 0.9
FULL_ENERGY_WEIGHT = 0.3
# A cycle beyond these bounds is a fault (a meter missing a flow, a landmark seen at the wrong time), not a measure.
# Above 1 on purpose: the landmarks' spread puts some real cycles there, and rejecting them only would bias the round
# trip down.
MIN_EFFICIENCY, MAX_EFFICIENCY = 0.85, 1.05
MIN_FULL_ENERGY_RATIO, MAX_FULL_ENERGY_RATIO = 0.5, 1.1
# A learned value replaces the configured one only from this many cycles: one cycle carries the landmarks' spread
MIN_LEARNED_CYCLES = 3


@dataclass(frozen=True)
class BatteryConfig:
    nominal_capacity_kwh: float
    # The BMS's state of charge at the empty landmark: reaching it while discharging (the threshold where a Home
    # Assistant safety usually switches the house to the grid)
    empty_soc_pct: float = 9.0
    # A cell at this voltage is the full landmark (3.50 V on LFP: reached at the BMS's 97 % on 2026-11-07); None: the
    # BMS's state of charge reaching 100 % is
    full_cell_v: float | None = 3.5
    # The DC round trip (out / in) until one is learned: 0.964 measured over 8 daily cycles, 2026-10-29 to 11-06
    efficiency: float = 0.96
    # The energy between the empty and the full landmarks until one is learned; None: the nominal capacity above the
    # empty threshold
    full_energy_kwh: float | None = None
    # With a DC power, the flows are integrated from it and the energy meters (in and out) only fill its gaps;
    # without, the meters count them
    has_power: bool = True
    has_meters: bool = False
    # The learned efficiency and full energy replace the configured ones once there are some (rule 25: off until
    # validated)
    learn: bool = False
    # The battery's DC flow never exceeds this: a meter increase faster than it is a spurious value. 30 kW: above any
    # home battery
    max_power_kw: float = 30.0

    def __post_init__(self) -> None:
        # The energy between the landmarks divides the state of charge: a configuration without one is refused here
        # rather than failing at every reading
        if not 0.0 <= self.empty_soc_pct < 100.0:
            raise ValueError(f"empty_soc_pct must be in [0, 100): {self.empty_soc_pct}")
        if not self.configured_full_energy_kwh > 0.0:
            raise ValueError(f"the energy between the landmarks must be positive: {self.configured_full_energy_kwh}")
        if not 0.0 < self.efficiency <= MAX_EFFICIENCY:
            raise ValueError(f"efficiency must be in (0, {MAX_EFFICIENCY}]: {self.efficiency}")
        if not self.max_power_kw > 0.0:
            raise ValueError(f"max_power_kw must be positive: {self.max_power_kw}")

    @property
    def configured_full_energy_kwh(self) -> float:
        """The energy between the landmarks as configured (the learned one may replace it)."""
        if self.full_energy_kwh is not None:
            return self.full_energy_kwh
        return self.nominal_capacity_kwh * (100.0 - self.empty_soc_pct) / 100.0


@dataclass(frozen=True)
class Reading:
    """The inputs at a time; None = unavailable (an unavailable input pauses what depends on it)."""

    soc_pct: float | None
    power_w: float | None = None  # DC battery power, positive while charging
    charged_kwh: float | None = None  # cumulative energy into the battery (DC)
    discharged_kwh: float | None = None  # cumulative energy out of the battery (DC)
    cell_high_v: float | None = None  # the highest cell voltage among the battery's packs


@dataclass
class Cycle:
    charged_kwh: float = 0.0
    discharged_kwh: float = 0.0
    complete: bool = False


@dataclass
class BatteryState:
    """What survives a restart (persisted by the tracker)."""

    energy_kwh: float | None = None  # above the empty landmark, in delivered kWh; None until the first state of charge
    start: str | None = None  # what the counting started from: FULL, EMPTY, FROM_SOC or SET
    start_at: datetime | None = None
    counted_kwh: float = 0.0  # what flowed in and out since the start (the uncertainty grows with it)
    updated_at: datetime | None = None
    reading: Reading = field(default_factory=lambda: Reading(None))
    # Last valid value of each energy meter and its time: the base of its next increase
    charged_meter_kwh: float | None = None
    discharged_meter_kwh: float | None = None
    meter_at: datetime | None = None
    # Integrated from the power since the last meter reading, and whether the power was unavailable meanwhile (the
    # meters then count what it missed)
    power_in_kwh: float = 0.0
    power_out_kwh: float = 0.0
    power_gap: bool = False
    full_armed: bool = True
    empty_armed: bool = True
    # The cycles since the last landmark of each kind (a full one and an empty one run together): what went in and
    # out, and whether it started at a landmark seen and every flow of it was seen
    since_full: Cycle = field(default_factory=Cycle)
    since_empty: Cycle = field(default_factory=Cycle)
    last_landmark_kind: str | None = None  # the kind of the latest landmark seen (FULL, EMPTY), None before any
    # When the battery was last at each landmark, seen or told: a restart from the state of charge or a set energy
    # keeps them, unlike last_landmark (a planner asks how long since the battery was full)
    last_full_at: datetime | None = None
    last_empty_at: datetime | None = None
    # Learned: the round trip's decayed totals (out / in) and the energy between the landmarks; None = nothing yet
    efficiency_in_kwh: float = 0.0
    efficiency_out_kwh: float = 0.0
    efficiency_cycles: int = 0
    learned_full_energy_kwh: float | None = None
    full_energy_cycles: int = 0
    # At the last landmark: the counted estimate minus the landmark's value (how far the counting drifted)
    last_landmark_error_kwh: float | None = None


# The fields added since version 1 are read with their default when absent
STATE_VERSION = 1


def state_to_dict(state: BatteryState) -> dict[str, Any]:
    """The state as JSON-compatible data (persisted by the tracker, format STATE_VERSION)."""
    r = state.reading
    return {
        "version": STATE_VERSION,
        "energy_kwh": state.energy_kwh,
        "start": state.start,
        "start_at": _iso(state.start_at),
        "counted_kwh": state.counted_kwh,
        "updated_at": _iso(state.updated_at),
        "reading": {
            "soc_pct": r.soc_pct,
            "power_w": r.power_w,
            "charged_kwh": r.charged_kwh,
            "discharged_kwh": r.discharged_kwh,
            "cell_high_v": r.cell_high_v,
        },
        "charged_meter_kwh": state.charged_meter_kwh,
        "discharged_meter_kwh": state.discharged_meter_kwh,
        "meter_at": _iso(state.meter_at),
        "power_in_kwh": state.power_in_kwh,
        "power_out_kwh": state.power_out_kwh,
        "power_gap": state.power_gap,
        "full_armed": state.full_armed,
        "empty_armed": state.empty_armed,
        "since_full": _cycle_to_dict(state.since_full),
        "since_empty": _cycle_to_dict(state.since_empty),
        "last_landmark_kind": state.last_landmark_kind,
        "efficiency_in_kwh": state.efficiency_in_kwh,
        "efficiency_out_kwh": state.efficiency_out_kwh,
        "efficiency_cycles": state.efficiency_cycles,
        "learned_full_energy_kwh": state.learned_full_energy_kwh,
        "full_energy_cycles": state.full_energy_cycles,
        "last_landmark_error_kwh": state.last_landmark_error_kwh,
        "last_full_at": _iso(state.last_full_at),
        "last_empty_at": _iso(state.last_empty_at),
    }


def state_from_dict(data: Any) -> BatteryState:
    """The state persisted by state_to_dict, of any version up to STATE_VERSION ("version"; 1 when absent). A
    missing or unreadable field (a truncated or edited file) takes its default: the estimate then starts again from the
    state of charge rather than being wrong."""
    if not isinstance(data, dict):
        return BatteryState()
    r = data.get("reading")
    r = r if isinstance(r, dict) else {}
    start = data.get("start")
    start = start if start in (FULL, EMPTY, FROM_SOC, SET) else None
    energy = _float(data.get("energy_kwh"))
    kind = data.get("last_landmark_kind")
    # Totals without one another are no ratio
    efficiency_in = _non_negative(data.get("efficiency_in_kwh"))
    efficiency_out = _non_negative(data.get("efficiency_out_kwh"))
    has_ratio = efficiency_in > 0 and efficiency_out > 0
    learned_full = _positive(data.get("learned_full_energy_kwh"))
    start_at = _parse(data.get("start_at"))
    return BatteryState(
        energy_kwh=energy if start is not None else None,
        start=start if energy is not None else None,
        start_at=start_at,
        counted_kwh=_non_negative(data.get("counted_kwh")),
        updated_at=_parse(data.get("updated_at")),
        reading=Reading(
            _float(r.get("soc_pct")),
            _float(r.get("power_w")),
            _float(r.get("charged_kwh")),
            _float(r.get("discharged_kwh")),
            _float(r.get("cell_high_v")),
        ),
        charged_meter_kwh=_float(data.get("charged_meter_kwh")),
        discharged_meter_kwh=_float(data.get("discharged_meter_kwh")),
        meter_at=_parse(data.get("meter_at")),
        power_in_kwh=_non_negative(data.get("power_in_kwh")),
        power_out_kwh=_non_negative(data.get("power_out_kwh")),
        power_gap=data.get("power_gap") is True,
        full_armed=data.get("full_armed") is not False,
        empty_armed=data.get("empty_armed") is not False,
        since_full=_cycle_from(data.get("since_full")),
        since_empty=_cycle_from(data.get("since_empty")),
        last_landmark_kind=kind if kind in LANDMARKS else None,
        efficiency_in_kwh=efficiency_in if has_ratio else 0.0,
        efficiency_out_kwh=efficiency_out if has_ratio else 0.0,
        efficiency_cycles=_count(data.get("efficiency_cycles")) if has_ratio else 0,
        learned_full_energy_kwh=learned_full,
        full_energy_cycles=_count(data.get("full_energy_cycles")) if learned_full is not None else 0,
        last_landmark_error_kwh=_float(data.get("last_landmark_error_kwh")),
        last_full_at=_last_at(data, FULL, start, start_at),
        last_empty_at=_last_at(data, EMPTY, start, start_at),
    )


def _last_at(data: dict[str, Any], kind: str, start: str | None, start_at: datetime | None) -> datetime | None:
    """When the battery was last at the `kind` landmark. A state saved by 0.1.0 has no such field: the start of its
    counting, when it is that landmark, is the last one it knows."""
    key = f"last_{kind}_at"
    if key in data:
        return _parse(data[key])
    return start_at if start == kind else None


def _cycle_to_dict(cycle: Cycle) -> dict[str, Any]:
    return {"charged_kwh": cycle.charged_kwh, "discharged_kwh": cycle.discharged_kwh, "complete": cycle.complete}


def _cycle_from(value: Any) -> Cycle:
    """A stored cycle; an unreadable one is incomplete (learns nothing)."""
    if not isinstance(value, dict):
        return Cycle()
    return Cycle(
        _non_negative(value.get("charged_kwh")),
        _non_negative(value.get("discharged_kwh")),
        value.get("complete") is True,
    )


def _iso(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


def _parse(value: Any) -> datetime | None:
    """An aware datetime, None when absent or unreadable."""
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _count(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def _non_negative(value: Any) -> float:
    number = _float(value)
    return number if number is not None and number >= 0 else 0.0


def _positive(value: Any) -> float | None:
    number = _float(value)
    return number if number is not None and number > 0 else None


def _float(value: Any) -> float | None:
    """A finite number, None otherwise (bool, text, nan, inf)."""
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        return None
    return float(value)


class Battery:
    def __init__(self, config: BatteryConfig, state: BatteryState | None = None):
        self.config = config
        self.state = state if state is not None else BatteryState()

    # --- Reading ---

    @property
    def energy_kwh(self) -> float | None:
        """What the battery can still deliver above its empty landmark (DC, kWh); None until the first state of
        charge. Slightly negative below the landmark, above full_energy_kwh past the full one."""
        return self.state.energy_kwh

    @property
    def room_kwh(self) -> float | None:
        """What it can still take before the full landmark, in delivered kWh (0 once there)."""
        energy = self.state.energy_kwh
        return None if energy is None else max(self.full_energy_kwh - energy, 0.0)

    @property
    def soc_pct(self) -> float | None:
        """The state of charge on the BMS's scale (the empty threshold at the empty landmark, 100 % at the full one),
        but linear in energy."""
        energy = self.state.energy_kwh
        if energy is None:
            return None
        empty = self.config.empty_soc_pct
        return min(max(empty + (100.0 - empty) * energy / self.full_energy_kwh, 0.0), 100.0)

    @property
    def uncertainty_kwh(self) -> float | None:
        start = self.state.start
        if start is None:
            return None
        return START_UNCERTAINTY_KWH[start] + COUNTED_UNCERTAINTY * self.state.counted_kwh

    @property
    def learned_efficiency(self) -> float | None:
        state = self.state
        return state.efficiency_out_kwh / state.efficiency_in_kwh if state.efficiency_in_kwh > 0 else None

    @property
    def learned_full_energy_kwh(self) -> float | None:
        return self.state.learned_full_energy_kwh

    @property
    def efficiency(self) -> float:
        """The round trip in use: the learned one once learning is on and there is one."""
        learned = self.learned_efficiency
        if self.config.learn and learned is not None and self.state.efficiency_cycles >= MIN_LEARNED_CYCLES:
            return learned
        return self.config.efficiency

    @property
    def full_energy_kwh(self) -> float:
        learned = self.state.learned_full_energy_kwh
        if self.config.learn and learned is not None and self.state.full_energy_cycles >= MIN_LEARNED_CYCLES:
            return learned
        return self.config.configured_full_energy_kwh

    @property
    def last_landmark(self) -> str | None:
        """FULL or EMPTY when the counting started from a landmark, else None."""
        return self.state.start if self.state.start in LANDMARKS else None

    @property
    def last_landmark_at(self) -> datetime | None:
        return self.state.start_at if self.last_landmark is not None else None

    @property
    def last_landmark_error_kwh(self) -> float | None:
        return self.state.last_landmark_error_kwh

    @property
    def last_full_at(self) -> datetime | None:
        """When the battery was last full (its full landmark seen or told), whatever the counting restarted from
        since; None before any."""
        return self.state.last_full_at

    @property
    def last_empty_at(self) -> datetime | None:
        return self.state.last_empty_at

    # --- Updating ---

    def update(self, at: datetime, reading: Reading) -> None:
        """Counts the flows of the interval since the last update at the power then in force (held), then takes
        `reading`: its meters' increases, its landmarks. A reading older than the last update is ignored (events out
        of order: the newer one already holds the inputs); a non-finite value is unavailable."""
        state = self.state
        if state.updated_at is not None and at < state.updated_at:
            return
        reading = _finite(reading)
        if state.updated_at is not None:
            self._integrate(state.updated_at, at, state.reading)
        self._take_meters(at, reading)
        # The landmarks compare the new state of charge with the previous one (state.reading, replaced below); the
        # check against the state of charge comes last, as it overrides a landmark that disagrees too far
        self._follow_landmarks(at, reading)
        self._check(at, reading)
        state.reading = reading
        state.updated_at = at

    def resume(self) -> None:
        """After a restart: the power last read is not held over the downtime; the energy meters count it at their
        next reading (the same day: a daily meter's reset meanwhile loses what it counted before midnight)."""
        state = self.state
        state.reading = replace(state.reading, power_w=None)
        state.power_gap = True

    def forget_meters(self) -> None:
        """Other meters replace the ones counted so far: their values are no increase of the previous ones. Their next
        readings are the base they are counted from; the flows meanwhile are unknown."""
        state = self.state
        state.charged_meter_kwh = state.discharged_meter_kwh = state.meter_at = None
        state.reading = replace(state.reading, charged_kwh=None, discharged_kwh=None)
        self._miss_flows()

    def mark_full(self, at: datetime) -> None:
        """The user says the battery is full now: the counting restarts there; no cycle is learned up to it nor from
        it (a landmark told, not seen)."""
        self._restart(at, FULL, self.full_energy_kwh)
        self._miss_flows()

    def mark_empty(self, at: datetime) -> None:
        """The user says the battery is at its empty landmark now."""
        self._restart(at, EMPTY, 0.0)
        self._miss_flows()

    def set_energy(self, at: datetime, energy_kwh: float) -> None:
        """The user gives the stored energy above the empty landmark; the cycles in progress go on (the flows are
        still seen)."""
        if math.isfinite(energy_kwh):
            self._restart(at, SET, energy_kwh)

    # --- Internals ---

    def _integrate(self, start: datetime, end: datetime, held: Reading) -> None:
        if not self.config.has_power:
            return
        if held.power_w is None:
            self.state.power_gap = True
            if not self.config.has_meters:
                # Nothing will tell what flowed meanwhile
                self._miss_flows()
            return
        kwh = held.power_w * (end - start).total_seconds() / 3.6e6
        charged, discharged = max(kwh, 0.0), max(-kwh, 0.0)
        if self.config.has_meters:
            # What the meters' next increase is compared with, should the power fail meanwhile
            self.state.power_in_kwh += charged
            self.state.power_out_kwh += discharged
        self._flow(charged, discharged)

    def _take_meters(self, at: datetime, reading: Reading) -> None:
        """The meters' increases: the flows without a power, what the power missed during its gaps with one."""
        state = self.state
        if reading.charged_kwh is None or reading.discharged_kwh is None:
            return
        cap = self.config.max_power_kw * (_hours(state.meter_at, at) + METER_SLACK_H)
        charged = meter_delta(state.charged_meter_kwh, reading.charged_kwh, cap)
        discharged = meter_delta(state.discharged_meter_kwh, reading.discharged_kwh, cap)
        counted = state.charged_meter_kwh is not None and state.discharged_meter_kwh is not None
        if not self.config.has_power:
            self._flow(charged, discharged)
        elif state.power_gap and counted:
            # What the meters counted beyond the power integrated around the gap is what the gap missed
            self._flow(max(charged - state.power_in_kwh, 0.0), max(discharged - state.power_out_kwh, 0.0))
        elif state.power_gap:
            # A gap without a base to count it from: its flows are unknown
            self._miss_flows()
        state.charged_meter_kwh, state.discharged_meter_kwh, state.meter_at = (
            reading.charged_kwh,
            reading.discharged_kwh,
            at,
        )
        state.power_in_kwh = state.power_out_kwh = 0.0
        state.power_gap = False

    def _flow(self, charged_kwh: float, discharged_kwh: float) -> None:
        state = self.state
        for cycle in (state.since_full, state.since_empty):
            cycle.charged_kwh += charged_kwh
            cycle.discharged_kwh += discharged_kwh
        if state.energy_kwh is None:
            return
        state.energy_kwh += self.efficiency * charged_kwh - discharged_kwh
        state.counted_kwh += charged_kwh + discharged_kwh
        if not state.full_armed and state.energy_kwh <= self.full_energy_kwh - FULL_REARM_KWH:
            state.full_armed = True

    def _follow_landmarks(self, at: datetime, reading: Reading) -> None:
        state, cfg = self.state, self.config
        soc, previous_soc = reading.soc_pct, state.reading.soc_pct
        if soc is not None and soc >= cfg.empty_soc_pct + EMPTY_REARM_PCT:
            state.empty_armed = True
        if cfg.full_cell_v is not None:
            full = reading.cell_high_v is not None and reading.cell_high_v >= cfg.full_cell_v
        else:
            full = soc is not None and soc >= 100.0
        if full and state.full_armed:
            self._landmark(at, FULL)
        elif (
            state.empty_armed
            and soc is not None
            and previous_soc is not None
            and previous_soc > cfg.empty_soc_pct >= soc
        ):
            self._landmark(at, EMPTY)

    def _landmark(self, at: datetime, kind: str) -> None:
        """A landmark seen: learns from the cycles it closes, then the counting restarts from it."""
        state = self.state
        if state.energy_kwh is not None:
            target = self.full_energy_kwh if kind == FULL else 0.0
            state.last_landmark_error_kwh = state.energy_kwh - target
        same = state.since_full if kind == FULL else state.since_empty
        if same.complete:
            self._learn_efficiency(same)
        previous = state.last_landmark_kind
        if previous is not None and previous != kind:
            self._learn_full_energy(kind, state.since_full if previous == FULL else state.since_empty)
        self._restart(at, kind, self.full_energy_kwh if kind == FULL else 0.0)
        state.last_landmark_kind = kind
        if kind == FULL:
            state.since_full = Cycle(complete=True)
        else:
            state.since_empty = Cycle(complete=True)

    def _learn_efficiency(self, cycle: Cycle) -> None:
        """From one landmark to the next of the same kind, the battery is where it was: what came out over what went
        in is the round trip."""
        state = self.state
        charged, discharged = cycle.charged_kwh, cycle.discharged_kwh
        if charged < MIN_CYCLE_FRACTION * self.config.configured_full_energy_kwh or charged <= 0:
            return
        if MIN_EFFICIENCY <= discharged / charged <= MAX_EFFICIENCY:
            state.efficiency_in_kwh = CYCLE_DECAY * state.efficiency_in_kwh + charged
            state.efficiency_out_kwh = CYCLE_DECAY * state.efficiency_out_kwh + discharged
            state.efficiency_cycles += 1

    def _learn_full_energy(self, kind: str, cycle: Cycle) -> None:
        """From the empty landmark to the full one, what was stored; from the full one to the empty one, what was
        delivered: both the energy between them, in delivered kWh."""
        if not cycle.complete:
            return
        state, eta = self.state, self.efficiency
        charged, discharged = cycle.charged_kwh, cycle.discharged_kwh
        sample = eta * charged - discharged if kind == FULL else discharged - eta * charged
        reference = self.config.configured_full_energy_kwh
        if MIN_FULL_ENERGY_RATIO * reference <= sample <= MAX_FULL_ENERGY_RATIO * reference:
            learned = state.learned_full_energy_kwh
            state.learned_full_energy_kwh = (
                sample if learned is None else learned + FULL_ENERGY_WEIGHT * (sample - learned)
            )
            state.full_energy_cycles += 1

    def _miss_flows(self) -> None:
        """Some flows went unseen: no cycle in progress can be learned from."""
        self.state.since_full.complete = False
        self.state.since_empty.complete = False

    def _restart(self, at: datetime, start: str, energy_kwh: float) -> None:
        """The counting restarts from `start`; at a landmark, that landmark waits until the battery left it (armed
        again in _flow for the full one, in _follow_landmarks for the empty one)."""
        state = self.state
        state.energy_kwh = energy_kwh
        state.start, state.start_at = start, at
        state.counted_kwh = 0.0
        if start == FULL:
            state.full_armed = False
            state.last_full_at = at
        elif start == EMPTY:
            state.empty_armed = False
            state.last_empty_at = at

    def _from_soc(self, soc_pct: float) -> float:
        empty = self.config.empty_soc_pct
        return (soc_pct - empty) / (100.0 - empty) * self.full_energy_kwh

    def _check(self, at: datetime, reading: Reading) -> None:
        """Starts from the state of charge without an estimate; drops the counting when it left the state of charge
        too far behind."""
        state, soc = self.state, reading.soc_pct
        if soc is None:
            return
        from_soc = self._from_soc(soc)
        # A divergence leaves the cycles in progress complete: they count the flows, which were seen (a missed one
        # already marked them), not the estimate; and a wrong configuration, which learning corrects, diverges too
        if state.energy_kwh is None or abs(state.energy_kwh - from_soc) > DIVERGENCE_KWH:
            self._restart(at, FROM_SOC, from_soc)


def _finite(reading: Reading) -> Reading:
    """The reading with its non-finite values (nan, inf: a broken sensor) unavailable: one would poison the estimate,
    and no divergence check catches a nan."""
    broken = [name for name in _READING_FIELDS if not _known_or_finite(getattr(reading, name))]
    return replace(reading, **dict.fromkeys(broken)) if broken else reading


_READING_FIELDS = ("soc_pct", "power_w", "charged_kwh", "discharged_kwh", "cell_high_v")


def _known_or_finite(value: float | None) -> bool:
    return value is None or math.isfinite(value)


def _hours(since: datetime | None, at: datetime) -> float:
    return 0.0 if since is None else max(0.0, (at - since).total_seconds() / 3600.0)
