# simulation/scenarios.py — Scenario definitions and appliers.

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from simulation.traffic_engine import TrafficEngine


SCENARIOS = {
    "normal":        {"label": "Normal Traffic",       "demand": 1.0,  "desc": "Baseline traffic conditions."},
    "heavy_traffic": {"label": "Heavy Traffic",        "demand": 2.8,  "desc": "High vehicle demand on all roads."},
    "large_event":   {"label": "Large Event",          "demand": 3.5,  "desc": "Sudden surge near event area."},
    "road_closure":  {"label": "Road Closure",         "demand": 1.5,  "desc": "A junction is blocked; traffic reroutes."},
    "emergency":     {"label": "Emergency Vehicle",    "demand": 1.0,  "desc": "Ambulance priority corridor active."},
}


def apply_scenario(engine: "TrafficEngine", scenario: str, target_junction: str = None):
    """Apply a scenario to the running engine."""
    cfg = SCENARIOS.get(scenario, SCENARIOS["normal"])
    engine.set_demand_multiplier(cfg["demand"])

    # Reset any previous closures
    for jid in engine.junctions:
        engine.open_road(jid)

    if scenario == "road_closure" and target_junction:
        engine.close_road(target_junction)

    if scenario == "emergency" and target_junction:
        _apply_emergency_corridor(engine, target_junction)


def _apply_emergency_corridor(engine: "TrafficEngine", origin_jid: str):
    """Give green to all junctions on the shortest path from origin."""
    import networkx as nx
    jids = list(engine.junctions.keys())
    if len(jids) < 2:
        return
    dest = jids[-1] if jids[-1] != origin_jid else jids[0]
    try:
        path = nx.shortest_path(engine.graph, origin_jid, dest, weight="travel_time")
    except Exception:
        path = [origin_jid]

    for jid in path:
        junc = engine.junctions.get(jid)
        if junc:
            junc.apply_phase(["N", "S"], {"N": 60, "S": 60})
