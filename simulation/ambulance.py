# simulation/ambulance.py — Ambulance green corridor service.
# Finds shortest path, overrides signals to green along the route,
# tracks ETA, and restores signals after passage.

import networkx as nx
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from utils.helpers import SIM_DT, clamp


@dataclass
class AmbulanceUnit:
    unit_id: str
    origin: str
    destination: str
    route: List[str]            # junction IDs in order
    current_idx: int = 0        # index into route (current position)
    elapsed: float = 0.0        # seconds since dispatch
    eta_seconds: float = 0.0
    status: str = "en_route"    # en_route | arrived | idle
    overridden_junctions: List[str] = field(default_factory=list)

    @property
    def current_junction(self) -> str:
        if self.current_idx < len(self.route):
            return self.route[self.current_idx]
        return self.destination

    @property
    def progress_pct(self) -> float:
        if len(self.route) <= 1:
            return 100.0
        return clamp(self.current_idx / (len(self.route) - 1) * 100, 0, 100)


class AmbulanceService:
    """
    Manages ambulance dispatch, green corridor override, and signal recovery.
    """

    def __init__(self, junctions, graph: nx.DiGraph):
        self.junctions = junctions
        self.graph = graph
        self.units: Dict[str, AmbulanceUnit] = {}
        self._counter = 0

    # ── Dispatch ──────────────────────────────────────────────────────────────

    def dispatch(self, origin: str, destination: str) -> Optional[AmbulanceUnit]:
        """Dispatch a new ambulance from origin to destination."""
        if origin == destination:
            return None
        try:
            route = nx.shortest_path(self.graph, origin, destination, weight="travel_time")
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return None

        # Estimate ETA using travel_time edge weights
        eta = 0.0
        for i in range(len(route) - 1):
            data = self.graph.get_edge_data(route[i], route[i + 1]) or {}
            eta += data.get("travel_time", 60.0)

        self._counter += 1
        uid = f"AMB-{self._counter:03d}"
        unit = AmbulanceUnit(
            unit_id=uid,
            origin=origin,
            destination=destination,
            route=route,
            eta_seconds=eta,
        )
        self.units[uid] = unit
        self._apply_green_corridor(unit)
        return unit

    # ── Green corridor ────────────────────────────────────────────────────────

    def _apply_green_corridor(self, unit: AmbulanceUnit):
        """Force all signals green along the ambulance route."""
        unit.overridden_junctions = []
        for jid in unit.route:
            junc = self.junctions.get(jid)
            if junc is None:
                continue
            # Determine dominant direction of travel through this junction
            idx = unit.route.index(jid)
            if idx < len(unit.route) - 1:
                next_jid = unit.route[idx + 1]
                road_key = f"{jid}_{next_jid}"
                road = junc.roads_out.get(road_key)
                direction = road.direction if road else "N"
                opp = {"N": "S", "S": "N", "E": "W", "W": "E"}.get(direction, "N")
                junc.apply_phase([direction, opp], {direction: 90, opp: 90})
            else:
                # Last junction — all green
                junc.apply_phase(["N", "S"], {"N": 90, "S": 90})
            unit.overridden_junctions.append(jid)

    def _restore_signals(self, unit: AmbulanceUnit):
        """Restore normal N/S default phase for overridden junctions."""
        for jid in unit.overridden_junctions:
            junc = self.junctions.get(jid)
            if junc:
                junc.apply_phase(["N", "S"], {"N": 30, "S": 30})
        unit.overridden_junctions = []

    # ── Step ──────────────────────────────────────────────────────────────────

    def step(self):
        """Advance all active ambulances by one simulation tick (SIM_DT seconds)."""
        for uid, unit in list(self.units.items()):
            if unit.status != "en_route":
                continue

            unit.elapsed += SIM_DT

            # Advance ambulance along route based on elapsed time vs ETA
            if unit.eta_seconds > 0:
                progress = clamp(unit.elapsed / unit.eta_seconds, 0.0, 1.0)
                unit.current_idx = int(progress * (len(unit.route) - 1))

            if unit.current_idx >= len(unit.route) - 1:
                unit.current_idx = len(unit.route) - 1
                unit.status = "arrived"
                self._restore_signals(unit)

    # ── Cancel / clear ────────────────────────────────────────────────────────

    def cancel(self, unit_id: str):
        unit = self.units.get(unit_id)
        if unit:
            self._restore_signals(unit)
            unit.status = "idle"

    def clear_arrived(self):
        self.units = {uid: u for uid, u in self.units.items() if u.status != "arrived"}

    # ── Query ─────────────────────────────────────────────────────────────────

    def active_routes(self) -> List[List[str]]:
        """Return all en-route ambulance routes (list of junction ID lists)."""
        return [u.route for u in self.units.values() if u.status == "en_route"]

    def all_route_junctions(self) -> List[str]:
        """Flat list of all junction IDs currently on any active ambulance route."""
        jids = []
        for u in self.units.values():
            if u.status == "en_route":
                jids.extend(u.route)
        return list(set(jids))
