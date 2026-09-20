  
# simulation/sumo_backend.py — Glue between app session state and SUMO.
from __future__ import annotations
import os
from typing import Dict, Optional

from simulation.sumo_env import DEMAND_VPH, build_network
from simulation.traci_manager import SumoTraciManager, ensure_traci_on_path

_managers: Dict[str, SumoTraciManager] = {}


def get_manager(key: str = "default") -> SumoTraciManager:
    if key not in _managers:
        _managers[key] = SumoTraciManager()
    return _managers[key]


def ensure_network(density: str = "medium"):
    build_network(density=density)
    return refresh_routes(density)


def refresh_routes(density: str = "medium"):
    from simulation.sumo_env import SUMO_DIR, write_routes, write_config
    routes = os.path.join(SUMO_DIR, "routes.rou.xml")
    net = os.path.join(SUMO_DIR, "coimbatore_traffic.net.xml")
    cfg = os.path.join(SUMO_DIR, "coimbatore_sumo.sumocfg")
    if not os.path.exists(net):
        build_network(density=density)
    write_routes(routes, density=density)
    write_config(cfg, net, routes)
    return {"net": net, "routes": routes, "config": cfg}


def describe_backend() -> dict:
    ensure_traci_on_path()
    try:
        from simulation.traci_manager import sumo_binary
        gui = sumo_binary(gui=True)
        cli = sumo_binary(gui=False)
    except Exception:
        gui, cli = None, None
    return {"sumo_gui": gui, "sumo_cli": cli,
            "traci_importable": _traci_importable()}


def _traci_importable() -> bool:
    try:
        ensure_traci_on_path()
        import traci  # noqa: F401
        return True
    except Exception:
        return False


def connect(manager: SumoTraciManager, density: str = "medium",
            gui: bool = True) -> dict:
    paths = ensure_network(density=density)
    used = [m.port for m in _managers.values()
            if m is not manager and m.port]
    manager.start(paths["config"], gui=gui, density=density,
                  reused_ports=used)
    return manager.collect_metrics()