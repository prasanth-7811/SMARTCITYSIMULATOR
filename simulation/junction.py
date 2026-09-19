# simulation/junction.py — Junction and road data models.

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import numpy as np
from utils.helpers import MIN_GREEN, MAX_GREEN, DEFAULT_GREEN, clamp

# Valid signal directions
DIRECTIONS = ["N", "S", "E", "W"]

# Allowed concurrent-green phase groups (single source of truth).
# N/S share one axis and E/W share the other; the two groups must never
# both receive green at the same time.
NS_GROUP = ("N", "S")
EW_GROUP = ("E", "W")

# Derived conflict table: every direction conflicts with the *other* axis.
CONFLICTS = {
    d: [o for o in DIRECTIONS if o not in group]
    for group in (NS_GROUP, EW_GROUP)
    for d in group
}


@dataclass
class SignalState:
    direction: str          # N / S / E / W
    is_green: bool = False
    green_duration: float = DEFAULT_GREEN   # seconds
    elapsed: float = 0.0                   # seconds since phase start

    def remaining(self) -> float:
        if self.is_green:
            return max(0.0, self.green_duration - self.elapsed)
        return 0.0


@dataclass
class Road:
    road_id: str
    from_junction: str
    to_junction: str
    length_m: float = 500.0
    capacity: int = 40          # max vehicles
    speed_kmph: float = 40.0
    density: float = 0.0        # 0–1 normalised
    queue: float = 0.0          # vehicles queued
    direction: str = "N"        # which direction this road feeds into junction

    def travel_time(self) -> float:
        """Free-flow travel time in seconds."""
        return (self.length_m / 1000.0) / self.speed_kmph * 3600.0

    def congested_speed(self) -> float:
        """Speed under current density (BPR-like)."""
        return self.speed_kmph * max(0.1, 1.0 - 0.8 * self.density)


@dataclass
class Junction:
    junction_id: str
    name: str
    lat: float
    lon: float
    roads_in: Dict[str, Road] = field(default_factory=dict)   # direction → Road
    roads_out: Dict[str, Road] = field(default_factory=dict)
    signals: Dict[str, SignalState] = field(default_factory=dict)
    demand: float = 0.3         # base arrival rate (vehicles/step)
    is_blocked: bool = False

    def __post_init__(self):
        # Initialise signals for each direction that has a road
        for d in DIRECTIONS:
            if d not in self.signals:
                self.signals[d] = SignalState(direction=d, is_green=(d in ["N", "S"]))

    def active_greens(self) -> List[str]:
        return [d for d, s in self.signals.items() if s.is_green]

    def total_queue(self) -> float:
        return sum(r.queue for r in self.roads_in.values())

    def avg_density(self) -> float:
        roads = list(self.roads_in.values())
        if not roads:
            return 0.0
        return float(np.mean([r.density for r in roads]))

    def set_signal(self, direction: str, is_green: bool, duration: float = None) -> List[str]:
        """
        Set a direction green/red. Returns list of conflict warnings.
        Enforces: N/S and E/W are the two allowed concurrent green groups.
        """
        warnings = []
        if direction not in self.signals:
            return [f"Unknown direction: {direction}"]

        if is_green:
            # Determine which group must yield to avoid an illegal phase
            conflict_group = EW_GROUP if direction in NS_GROUP else NS_GROUP

            # Turn off conflicting group
            for d in conflict_group:
                if d in self.signals and self.signals[d].is_green:
                    self.signals[d].is_green = False
                    warnings.append(f"⚠️ {d} turned RED to avoid conflict with {direction}.")

        self.signals[direction].is_green = is_green
        if duration is not None:
            self.signals[direction].green_duration = clamp(duration, MIN_GREEN, MAX_GREEN)
        self.signals[direction].elapsed = 0.0
        return warnings

    def apply_phase(self, green_directions: List[str], durations: Dict[str, float] = None):
        """Apply a full signal phase — set greens, turn off others."""
        durations = durations or {}
        for d in DIRECTIONS:
            is_g = d in green_directions
            self.signals[d].is_green = is_g
            if is_g and d in durations:
                self.signals[d].green_duration = clamp(durations[d], MIN_GREEN, MAX_GREEN)
            self.signals[d].elapsed = 0.0

    def commit_durations(self, durations: Dict[str, float]) -> None:
        """
        Persist green durations for the given directions.

        Red directions are updated too: their duration is used the next time
        that direction receives green, so an operator can pre-set both axes.
        """
        for d, val in (durations or {}).items():
            if d in self.signals and val is not None:
                self.signals[d].green_duration = clamp(val, MIN_GREEN, MAX_GREEN)

    def resolve_phase(self, desired: Dict[str, bool]) -> Tuple[List[str], List[str]]:
        """
        Map desired per-direction on/off states onto ONE conflict-free phase.

        Directions omitted from ``desired`` keep their current state.

        Returns (green_directions, warnings). If the operator requests both
        axes green at once, the larger request wins (ties favour N/S) and a
        warning is returned instead of raising.
        """
        warnings: List[str] = []
        want = {d: bool(desired.get(d, self.signals[d].is_green)) for d in DIRECTIONS}

        ns = [d for d in NS_GROUP if want[d]]
        ew = [d for d in EW_GROUP if want[d]]

        if ns and ew:
            # Illegal phase request — only one axis may run.
            if len(ew) > len(ns):
                greens, held = ew, ns
            else:
                greens, held = ns, ew
            warnings.append(
                "⚠️ Conflicting request (N/S + E/W both GREEN). "
                f"Applied {'/'.join(greens)} and held {'/'.join(held)} on RED."
            )
        elif ns:
            greens = ns
        elif ew:
            greens = ew
        else:
            # All-red is not a valid operating phase; keep the current axis.
            greens = [d for d in DIRECTIONS if self.signals[d].is_green] or list(NS_GROUP)
            warnings.append("⚠️ No direction selected — kept the current phase.")

        return greens, warnings
