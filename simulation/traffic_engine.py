# simulation/traffic_engine.py — Core traffic simulation engine.

import numpy as np
import networkx as nx
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
import copy

from simulation.junction import Junction, Road, SignalState, DIRECTIONS, NS_GROUP, EW_GROUP
from simulation.vehicle import Vehicle
from utils.helpers import SIM_DT, clamp, safe_div

SAT_FLOW = 1.6   # vehicles cleared per second of green (saturation flow)
QUEUE_UNITS_PER_VEHICLE = 1.0   # queue is measured in vehicles

# ── Control modes ─────────────────────────────────────────────────────────────
CONTROL_AUTO   = "auto"     # engine cycles phases on green-time expiry
CONTROL_MANUAL = "manual"   # operator owns the signals; no auto phase switching
CONTROL_MODES  = (CONTROL_AUTO, CONTROL_MANUAL)


@dataclass
class SimSnapshot:
    """Immutable snapshot of key metrics for history tracking."""
    step: int
    elapsed: float
    total_vehicles: int
    vehicles_moving: int = 0
    vehicles_stopped: int = 0
    avg_wait: float = 0.0
    total_queue: float = 0.0
    avg_density: float = 0.0
    congestion_pct: float = 0.0


class TrafficEngine:
    def __init__(self, junctions: Dict[str, Junction], graph: nx.DiGraph):
        self.junctions  = junctions
        self.graph      = graph
        self.vehicles: List[Vehicle] = []
        self.step       = 0
        self.elapsed    = 0.0   # seconds
        self.history: List[SimSnapshot] = []
        self.paused     = True
        self._rng       = np.random.default_rng(42)
        self._demand_multiplier = 1.0   # scenario override
        self.control_mode = CONTROL_AUTO   # ← manual/automatic signal ownership

    # ── Demand & arrivals ─────────────────────────────────────────────────────

    def _arrival_count(self, junction: Junction) -> int:
        """Poisson arrivals scaled by demand and multiplier."""
        rate = junction.demand * self._demand_multiplier
        return int(self._rng.poisson(rate))

    def _dispatch_vehicle(self, origin: str) -> Optional[Vehicle]:
        """
        Create one vehicle departing ``origin`` toward a random other junction.

        Shared by the automatic Poisson arrivals and the operator's manual
        "Add Vehicles" control so both behave identically.
        """
        junc = self.junctions.get(origin)
        if junc is None:
            return None

        dests = [j for j in self.junctions if j != origin]
        if not dests:
            return None

        dest = self._rng.choice(dests)
        try:
            route = nx.shortest_path(self.graph, origin, dest, weight="travel_time")
        except nx.NetworkXNoPath:
            route = [origin, dest]
        except Exception:
            route = [origin, dest]

        v = Vehicle(current_junction=origin, destination_junction=dest, route=route)
        self.vehicles.append(v)

        # The vehicle joins the queue on the first road of its route
        if len(route) > 1:
            road = junc.roads_out.get(f"{origin}_{route[1]}")
            if road is not None:
                road.queue = min(road.queue + 1, road.capacity)
        return v

    def _spawn_vehicles(self):
        for jid, junc in self.junctions.items():
            if junc.is_blocked:
                continue
            for _ in range(self._arrival_count(junc)):
                self._dispatch_vehicle(jid)

    # ── Signal phase advancement ──────────────────────────────────────────────

    def _advance_signals(self):
        """Age green timers, and in AUTOMATIC mode cycle the phase on expiry.

        In MANUAL mode the operator owns the signals: timers still advance so
        the UI can display elapsed/remaining time, but no phase is ever
        switched automatically.
        """
        for junc in self.junctions.values():
            for sig in junc.signals.values():
                if not sig.is_green:
                    continue

                sig.elapsed += SIM_DT

                if self.control_mode != CONTROL_AUTO:
                    continue        # manual mode: operator has control

                # Auto-cycle: when green time expires, switch to the other axis
                if sig.elapsed >= sig.green_duration:
                    sig.elapsed = 0.0
                    current_greens = set(junc.active_greens())
                    if current_greens & set(NS_GROUP):
                        junc.apply_phase(list(EW_GROUP))
                    else:
                        junc.apply_phase(list(NS_GROUP))
                    break   # phase switched; restart loop for this junction

    # ── Vehicle movement ──────────────────────────────────────────────────────

    def _move_vehicles(self):
        """Advance every vehicle one step, honouring the live signal states.

        A vehicle only crosses a junction when the signal facing its exit road
        is green. Vehicles that cannot cross accumulate waiting time; each
        vehicle that does cross removes itself from that road's queue.
        """
        arrived = []
        cleared: Dict[str, float] = {}      # junction -> vehicles cleared this step
        step_capacity = SAT_FLOW * SIM_DT   # veh a junction can clear per step

        for v in self.vehicles:
            junc = self.junctions.get(v.current_junction)
            if junc is None or v.is_at_destination():
                arrived.append(v)
                continue

            # Determine which direction vehicle wants to leave
            if len(v.route) < 2:
                arrived.append(v)
                continue

            next_jid = v.route[1]
            # Find the road connecting current → next
            road = junc.roads_out.get(f"{v.current_junction}_{next_jid}")

            # Find signal direction for this road
            direction = road.direction if road else "N"
            sig = junc.signals.get(direction)

            at_capacity = cleared.get(v.current_junction, 0.0) >= step_capacity

            if sig and sig.is_green and not at_capacity:
                # Green: vehicle crosses and leaves the queue
                cleared[v.current_junction] = cleared.get(v.current_junction, 0.0) + 1.0
                v.route.pop(0)
                v.current_junction = next_jid
                v.travel_time += SIM_DT
                if road:
                    road.queue = max(0.0, road.queue - QUEUE_UNITS_PER_VEHICLE)
            else:
                # Red (or junction saturated): vehicle waits
                v.wait_time += SIM_DT

        self.vehicles = [v for v in self.vehicles if v not in arrived]

    # ── Density update ────────────────────────────────────────────────────────

    def _update_densities(self):
        for junc in self.junctions.values():
            for road in list(junc.roads_in.values()) + list(junc.roads_out.values()):
                road.density = clamp(safe_div(road.queue, road.capacity), 0.0, 1.0)

    # ── Public step ───────────────────────────────────────────────────────────

    def step_sim(self):
        if self.paused:
            return
        self._spawn_vehicles()
        self._advance_signals()
        self._move_vehicles()
        self._update_densities()
        self.step    += 1
        self.elapsed += SIM_DT
        self._record_snapshot()

    def force_step(self):
        """Step regardless of paused state (used by manual step button)."""
        was_paused = self.paused
        self.paused = False
        self.step_sim()
        self.paused = was_paused

    def _record_snapshot(self):
        waits = [v.wait_time for v in self.vehicles] or [0.0]
        all_roads = [r for j in self.junctions.values()
                     for r in list(j.roads_in.values()) + list(j.roads_out.values())]
        densities = [r.density for r in all_roads] or [0.0]
        queues    = [r.queue   for r in all_roads]
        moving    = sum(1 for v in self.vehicles if not v.is_at_destination() and v.route)
        stopped   = len(self.vehicles) - moving
        heavy     = sum(1 for d in densities if d > 0.65)
        self.history.append(SimSnapshot(
            step=self.step,
            elapsed=self.elapsed,
            total_vehicles=len(self.vehicles),
            vehicles_moving=moving,
            vehicles_stopped=stopped,
            avg_wait=float(np.mean(waits)),
            total_queue=float(sum(queues)),
            avg_density=float(np.mean(densities)),
            congestion_pct=safe_div(heavy, len(densities), 0) * 100,
        ))

    # ── Metrics ───────────────────────────────────────────────────────────────

    def current_metrics(self) -> dict:
        waits = [v.wait_time for v in self.vehicles] or [0.0]
        all_roads = [r for j in self.junctions.values()
                     for r in list(j.roads_in.values()) + list(j.roads_out.values())]
        densities = [r.density for r in all_roads] or [0.0]
        queues    = [r.queue   for r in all_roads]
        moving    = sum(1 for v in self.vehicles if not v.is_at_destination() and v.route)
        stopped   = len(self.vehicles) - moving
        return {
            "total_vehicles": len(self.vehicles),
            "avg_wait":       float(np.mean(waits)),
            "total_queue":    float(sum(queues)),
            "avg_density":    float(np.mean(densities)),
            "active_junctions": len([j for j in self.junctions.values() if not j.is_blocked]),
            "congestion_pct": safe_div(
                sum(1 for d in densities if d > 0.65), len(densities), 0
            ) * 100,
            "vehicles_moving": moving,
            "vehicles_stopped": stopped,
        }

    # ── Manual signal control ─────────────────────────────────────────────────

    def set_junction_signal(
        self,
        junction_id: str,
        direction: str,
        is_green: bool,
        duration: float = None,
    ) -> List[str]:
        junc = self.junctions.get(junction_id)
        if junc is None:
            return [f"Junction {junction_id} not found."]
        return junc.set_signal(direction, is_green, duration)

    def apply_signal_plan(self, plan: Dict[str, Dict]):
        """
        plan = { junction_id: { "greens": ["N","S"], "durations": {"N":30,"S":30} } }
        """
        for jid, cfg in plan.items():
            junc = self.junctions.get(jid)
            if junc:
                junc.apply_phase(cfg.get("greens", ["N", "S"]),
                                 cfg.get("durations", {}))

    # ── Control mode (manual vs automatic) ────────────────────────────────────

    def set_control_mode(self, mode: str) -> str:
        """
        Switch between AUTOMATIC (engine cycles phases) and MANUAL (operator
        owns the signals). Manual mode is never overridden by the engine.
        """
        if mode not in CONTROL_MODES:
            raise ValueError(
                f"Unknown control mode: {mode!r}. Expected one of {CONTROL_MODES}."
            )
        self.control_mode = mode
        return self.control_mode

    def is_manual(self) -> bool:
        return self.control_mode == CONTROL_MANUAL

    @property
    def demand_multiplier(self) -> float:
        """Public read access to the arrival-rate multiplier (traffic load)."""
        return self._demand_multiplier

    # ── Operator input ────────────────────────────────────────────────────────

    def add_vehicles(self, junction_id: str, count: int = 1) -> int:
        """
        Inject ``count`` vehicles at ``junction_id`` (operator "Add Vehicles").

        Returns the number of vehicles actually created.
        """
        if count <= 0 or junction_id not in self.junctions:
            return 0
        added = 0
        for _ in range(int(count)):
            if self._dispatch_vehicle(junction_id) is not None:
                added += 1
        return added

    def apply_junction_signals(
        self,
        junction_id: str,
        desired: Dict[str, bool],
        durations: Dict[str, float] = None,
    ) -> List[str]:
        """
        Atomically apply an operator-authored phase to one junction.

        ``desired``   maps direction -> should-be-green, e.g. {"N": True, "E": False}
        ``durations`` optionally pre-sets green times for any direction (red
        directions included, so both axes can be prepared in advance).

        Conflicting requests are resolved by :meth:`Junction.resolve_phase`
        instead of being rejected. Returns operator-facing warnings.
        """
        junc = self.junctions.get(junction_id)
        if junc is None:
            return [f"Junction {junction_id} not found."]

        if durations:
            junc.commit_durations(durations)

        greens, warnings = junc.resolve_phase(desired or {})
        applied = {d: junc.signals[d].green_duration for d in greens}
        junc.apply_phase(greens, applied)

        if self.is_manual():
            warnings.append(f"✅ Manual phase applied — {', '.join(greens)} GREEN.")
        else:
            warnings.append(
                "ℹ️ Control mode is AUTOMATIC — the engine may cycle this "
                "phase when the green timer expires."
            )
        return warnings

    # ── Scenario helpers ──────────────────────────────────────────────────────

    def set_demand_multiplier(self, m: float):
        self._demand_multiplier = clamp(m, 0.1, 5.0)

    def close_road(self, junction_id: str):
        junc = self.junctions.get(junction_id)
        if junc:
            junc.is_blocked = True

    def open_road(self, junction_id: str):
        junc = self.junctions.get(junction_id)
        if junc:
            junc.is_blocked = False

    def reset(self):
        self.vehicles = []
        self.step     = 0
        self.elapsed  = 0.0
        self.history  = []
        self._demand_multiplier = 1.0
        for junc in self.junctions.values():
            junc.is_blocked = False
            for road in list(junc.roads_in.values()) + list(junc.roads_out.values()):
                road.queue   = 0.0
                road.density = 0.0
            junc.apply_phase(["N", "S"])
