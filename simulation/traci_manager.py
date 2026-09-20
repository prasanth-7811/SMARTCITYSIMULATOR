# simulation/traci_manager.py — Manage SUMO lifecycle + TraCI queries.
from __future__ import annotations
import os
import shutil
import socket
import subprocess
import time
from typing import Dict, List, Optional

SUMO_PORT_START = 8873
SUMO_PORT_END = 8899

_AXIS_TO_PHASE_HINT = {
    "NS": {"N", "S"},
    "EW": {"E", "W"},
}


def _venv_site_packages():
    here = os.path.abspath(os.path.dirname(__file__))
    root = os.path.abspath(os.path.join(here, os.pardir))
    return os.path.join(root, "venv", "Lib", "site-packages")

def ensure_traci_on_path():
    sp = _venv_site_packages()
    for cand in (os.path.join(sp, "sumo", "tools"),
                 os.path.join(sp, "sumo_data", "tools")):
        if os.path.isdir(cand):
            import sys
            if cand not in sys.path:
                sys.path.append(cand)
    os.environ.setdefault("SUMO_HOME", os.path.join(sp, "sumo"))

def sumo_binary(gui=False):
    name = "sumo-gui" if gui else "sumo"
    exe = shutil.which(name)
    if exe:
        return exe
    # Fall back to venv Scripts directory on Windows.
    fallback = os.path.join(
        os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)),
        "venv", "Scripts", f"{name}.exe")
    return fallback if os.path.exists(fallback) else None

def find_free_port(exclude=()):
    for port in range(SUMO_PORT_START, SUMO_PORT_END):
        if port in (exclude or ()):
            continue
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return SUMO_PORT_START


class SumoTraciManager:
    """Owns the SUMO subprocess + TraCI queries for one config file."""

    def __init__(self):
        self.config_path: Optional[str] = None
        self.port: Optional[int] = None
        self.proc: Optional[subprocess.Popen] = None
        self.connected = False
        self.paused = True
        self.speed = 1
        self.step_count = 0
        self.elapsed = 0.0
        self.density = "medium"
        self.junction_tls: Dict[str, str] = {}
        self.tls_phases: Dict[str, List[dict]] = {}
        self.overrides: Dict[str, str] = {}
        self.closed_edges: List[str] = []
        self.closed_edge_state: Dict[str, dict] = {}
        self.history: List[dict] = []

    @property
    def running(self):
        return self.proc is not None and self.proc.poll() is None

    def _require_traci(self):
        ensure_traci_on_path()
        try:
            import traci  # noqa: F401
        except Exception as exc:
            raise RuntimeError(
                "TraCI bindings unavailable. Install SUMO with "
                "`pip install eclipse-sumo` inside the project venv.") from exc

    def _start_sumo_process(self, gui: bool):
        binary = sumo_binary(gui=gui)
        if not binary or not os.path.exists(binary):
            raise FileNotFoundError(
                f"SUMO binary not found ({'sumo-gui' if gui else 'sumo'}). "
                "Install with `pip install eclipse-sumo` inside the venv.")
        cmd = [binary, "-c", self.config_path,
               "--remote-port", str(self.port), "--num-clients", "1",
               "--start", "--quit-on-end"]
        self.proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL)
        time.sleep(1.5)
        if not self.running:
            raise RuntimeError("SUMO process exited immediately. "
                               "Check the .sumocfg and generated network.")

    def _connect_traci(self):
        import traci
        for attempt in range(10):
            try:
                traci.init(self.port, numRetries=5)
                self.connected = True
                return
            except Exception:
                time.sleep(0.5)
        raise RuntimeError(
            f"Could not connect TraCI to SUMO on port {self.port}.")

    def start(self, config_path, gui=True, density="medium",
              reused_ports=()):
        self._require_traci()
        self.stop()
        self.config_path = config_path
        self.density = density
        self.port = find_free_port(exclude=reused_ports)
        self._start_sumo_process(gui=gui)
        self._connect_traci()
        self._discover_tls()
        self.step_count = 0
        self.elapsed = 0.0
        self.paused = True
        self.history = []
        self.overrides = {}
        self.closed_edges = []
        self.closed_edge_state = {}

    def stop(self):
        try:
            import traci
            if self.connected:
                try:
                    traci.close()
                except Exception:
                    pass
        except Exception:
            pass
        self.connected = False
        if self.proc is not None:
            try:
                if self.proc.poll() is None:
                    self.proc.terminate()
                    try:
                        self.proc.wait(timeout=5)
                    except Exception:
                        self.proc.kill()
            except Exception:
                pass
        self.proc = None
        self.paused = True

    def _discover_tls(self):
        import traci
        self.junction_tls = {}
        self.tls_phases = {}
        tls_ids = list(traci.trafficlight.getIDList())

        import re
        norm = {re.sub(r"[^a-z0-9]", "", t.lower()): t for t in tls_ids}

        from simulation.sumo_env import RING
        for jid in RING:
            key = re.sub(r"[^a-z0-9]", "", jid.lower())
            if key in norm:
                self.junction_tls[jid] = norm[key]
            elif tls_ids:
                # Fallback: round-robin assign so every junction is controllable
                self.junction_tls[jid] = tls_ids[RING.index(jid) % len(tls_ids)]

        for tls in set(self.junction_tls.values()):
            try:
                logics = traci.trafficlight.getAllProgramLogics(tls)
            except Exception:
                logics = []
            entries = []
            for logic in logics or []:
                for ph in getattr(logic, "phases", []) or []:
                    entries.append({
                        "program": getattr(logic, "programID", "0"),
                        "state": getattr(ph, "state", ""),
                        "duration": float(getattr(ph, "duration", 30) or 30),
                    })
            if entries:
                self.tls_phases[tls] = entries
            else:
                try:
                    cur = traci.trafficlight.getRedYellowGreenState(tls)
                    self.tls_phases[tls] = [
                        {"program": "0", "state": cur, "duration": 30.0}]
                except Exception:
                    self.tls_phases[tls] = []

    def apply_signal(self, junction_id, axis):
        import traci
        tls = self.junction_tls.get(junction_id)
        if not tls:
            return f"SUMO junction {junction_id} has no traffic light."
        entries = self.tls_phases.get(tls, [])
        want = _AXIS_TO_PHASE_HINT.get(axis.upper(), {"N", "S"})
        best = None
        best_score = -1
        for idx, e in enumerate(entries):
            st = (e.get("state") or "").upper()
            if not st:
                continue
            green_letters = {"NESW"[i % 4] for i, s in enumerate(st)
                             if s == "G"}
            score = len(green_letters & want) * 2 - len(green_letters - want)
            if score > best_score:
                best_score = score
                best = (idx, e)
        if best is None:
            return f"No usable phase found on SUMO TLS {tls}."
        idx, e = best
        traci.trafficlight.setPhase(tls, idx)
        traci.trafficlight.setPhaseDuration(
            tls, float(e.get("duration", 30.0)))
        self.overrides[junction_id] = axis.upper()
        return (f"SUMO TLS {tls} set to {axis.upper()} phase "
                f"(state {e.get('state')}).")

    def set_green_duration(self, junction_id, seconds):
        import traci
        tls = self.junction_tls.get(junction_id)
        if not tls:
            return f"SUMO junction {junction_id} has no traffic light."
        seconds = max(5.0, min(90.0, float(seconds)))
        try:
            traci.trafficlight.setPhaseDuration(tls, seconds)
            return f"SUMO TLS {tls} phase duration set to {seconds:.0f}s."
        except Exception as exc:
            return f"Could not set SUMO duration: {exc}"

    def set_road_closed(self, edge_id, closed=True):
        import traci
        try:
            if closed:
                edges = [edge_id]
                if edge_id.startswith("E_") is False:
                    edges += [e for e in traci.edge.getIDList()
                              if edge_id in e][:1]
                for e in edges:
                    try:
                        lanes = traci.edge.getLaneNumber(e)
                    except Exception:
                        continue
                    self.closed_edge_state.setdefault(e, {})
                    for i in range(lanes):
                        lane = f"{e}_{i}"
                        try:
                            cur = traci.lane.getAllowed(lane)
                            self.closed_edge_state[e].setdefault(
                                lane, list(cur))
                            traci.lane.setDisallowed(lane, list(cur))
                        except Exception:
                            continue
                if edge_id not in self.closed_edges:
                    self.closed_edges.append(edge_id)
                return f"Edge {edge_id} closed in SUMO."
            else:
                restored = False
                for e, lanes in list(self.closed_edge_state.items()):
                    if edge_id in e or e in edge_id:
                        for lane, allowed in lanes.items():
                            try:
                                traci.lane.setAllowed(lane, allowed)
                                restored = True
                            except Exception:
                                continue
                        self.closed_edge_state.pop(e, None)
                self.closed_edges = [e for e in self.closed_edges
                                     if e != edge_id]
                return (f"Edge {edge_id} reopened."
                        if restored else f"Edge {edge_id} reopened.")
        except Exception as exc:
            return f"Road closure failed: {exc}"

    def step(self, n=1):
        import traci
        if not self.connected:
            raise RuntimeError("TraCI is not connected.")
        for _ in range(max(1, int(n))):
            traci.simulationStep()
            self.step_count += 1
            self.elapsed += 1.0
        return self.collect_metrics()

    def collect_metrics(self):
        import traci
        try:
            veh_ids = traci.vehicle.getIDList()
        except Exception:
            return {"connected": False}
        waiting = 0
        moving = 0
        speeds = []
        waits = []
        per_edge_wait: Dict[str, list] = {}
        per_edge_count: Dict[str, int] = {}
        for vid in veh_ids:
            try:
                sp = float(traci.vehicle.getSpeed(vid))
                wt = float(traci.vehicle.getWaitingTime(vid))
                edge = str(traci.vehicle.getRoadID(vid))
            except Exception:
                continue
            speeds.append(sp)
            waits.append(wt)
            per_edge_wait.setdefault(edge, []).append(wt)
            per_edge_count[edge] = per_edge_count.get(edge, 0) + 1
            if sp < 0.1:
                waiting += 1
            else:
                moving += 1
        tls_states = {}
        for jid, tls in self.junction_tls.items():
            try:
                tls_states[jid] = traci.trafficlight.getRedYellowGreenState(tls)
            except Exception:
                tls_states[jid] = ""
        queue_by_junction: Dict[str, float] = {}
        for edge, ws in per_edge_wait.items():
            halted = sum(1 for w in ws if w > 1.0)
            for jid in self.junction_tls:
                if jid in edge:
                    queue_by_junction[jid] = (
                        queue_by_junction.get(jid, 0.0) + halted)
        snap = {
            "connected": True,
            "step": self.step_count,
            "elapsed": self.elapsed,
            "total_vehicles": len(veh_ids),
            "moving": moving,
            "waiting": waiting,
            "avg_speed": (sum(speeds) / len(speeds)) if speeds else 0.0,
            "avg_wait": (sum(waits) / len(waits)) if waits else 0.0,
            "queue_by_junction": queue_by_junction,
            "tls_states": tls_states,
            "closed_edges": list(self.closed_edges),
            "overrides": dict(self.overrides),
            "density": self.density,
        }
        self.history.append(snap)
        if len(self.history) > 600:
            self.history = self.history[-600:]
        return snap

    def get_vehicle_positions(self):
        """Return SUMO vehicles as map-ready dicts (folium 'transit' style).

        Positions are converted from SUMO network coordinates to (lat, lon)
        via ``simulation.sumo_env.sumo_to_ll`` so they can be overlaid on the
        real Coimbatore map.
        """
        if not self.connected:
            return []
        import traci
        from simulation.sumo_env import sumo_to_ll
        out = []
        try:
            ids = traci.vehicle.getIDList()
        except Exception:
            return out
        for vid in ids:
            try:
                x, y = traci.vehicle.getPosition(vid)
                wt = float(traci.vehicle.getWaitingTime(vid))
                lat, lon = sumo_to_ll(x, y)
            except Exception:
                continue
            out.append({
                "type": "transit", "lat": lat, "lon": lon, "id": vid,
                "wait_time": wt, "position": 0.0,
                "color": "#00e5a0", "size": 4,
            })
        return out