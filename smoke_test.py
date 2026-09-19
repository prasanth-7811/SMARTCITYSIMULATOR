"""Smoke test — verifies all modules import and core logic runs."""
import sys
sys.stdout.reconfigure(encoding="utf-8")

from map.coimbatore_map import build_fallback_network
from simulation.traffic_engine import TrafficEngine
from simulation.scenarios import apply_scenario
from optimization.classical_optimizer import classical_optimize
from optimization.quantum_optimizer import quantum_optimize, QUANTUM_AVAILABLE

print("Quantum available:", QUANTUM_AVAILABLE)

# Build network
junctions, graph = build_fallback_network()
print("Junctions loaded:", len(junctions))

# Build engine and run steps
engine = TrafficEngine(junctions, graph)
engine.paused = False
for _ in range(5):
    engine.step_sim()
print("Sim steps OK  vehicles=" + str(len(engine.vehicles)) +
      "  queue=" + str(round(engine.current_metrics()["total_queue"], 1)))

# Manual signal control
warns = engine.set_junction_signal("gandhipuram", "N", True, 40.0)
print("Signal set OK  warnings=" + str(warns))

# Scenario
apply_scenario(engine, "heavy_traffic")
engine.force_step()
print("Scenario OK  demand_mult=" + str(engine._demand_multiplier))

# Adjacency
adj = []
for jid, junc in junctions.items():
    for rid, road in junc.roads_out.items():
        if road.to_junction in junctions:
            adj.append((jid, road.to_junction))
adj = list(set(adj))

# Classical optimizer
cr = classical_optimize(junctions, adj)
print("Classical OK  method=" + cr["method"] + "  energy=" + str(round(cr["energy"], 3)))

# Quantum optimizer
qr = quantum_optimize(junctions, adj)
print("Quantum OK  method=" + qr["method"] + "  energy=" + str(round(qr["energy"], 3)))

# Apply plan
engine.apply_signal_plan(cr["plan"])
print("Plan applied OK")

# ── Control-room upgrade: manual/automatic mode ───────────────────────────────
from simulation.traffic_engine import CONTROL_AUTO, CONTROL_MANUAL, CONTROL_MODES
from simulation.junction import DIRECTIONS, NS_GROUP, EW_GROUP

engine.set_control_mode(CONTROL_MANUAL)
assert engine.control_mode == CONTROL_MANUAL and engine.is_manual()
print("Control mode OK  mode=" + engine.control_mode)

# Manual mode must NOT auto-cycle signals when the green timer expires
jid0 = list(junctions.keys())[0]
junc0 = junctions[jid0]
junc0.apply_phase(["N", "S"], {"N": 10, "S": 10})
for _ in range(20):          # 200 s of sim time, far beyond the 10 s green
    engine.force_step()
assert set(junc0.active_greens()) & set(NS_GROUP), "manual phase was auto-cycled!"
print("Manual mode holds phase OK  greens=" + str(junc0.active_greens()))

# Automatic mode DOES auto-cycle
engine.set_control_mode(CONTROL_AUTO)
observed = set()
for _ in range(20):
    engine.force_step()
    observed.add(frozenset(junc0.active_greens()))
assert len(observed) > 1, "auto mode never cycled the phase"
print("Auto mode cycles phase OK  observed=" +
      str(sorted(tuple(sorted(p)) for p in observed)))

# ── Conflict resolution: N/S + E/W requested together ─────────────────────────
junc0.apply_phase(["N", "S"], {"N": 30, "S": 30})
greens, warns = junc0.resolve_phase({"N": True, "S": True, "E": True, "W": True})
assert not (set(greens) & set(NS_GROUP) and set(greens) & set(EW_GROUP)), \
    "resolve_phase produced an illegal phase!"
assert warns, "expected a conflict warning"
print("Conflict resolution OK  applied=" + str(greens))

# ── Atomic operator apply ────────────────────────────────────────────────────
warns = engine.apply_junction_signals(
    jid0, {"E": True, "W": True, "N": False, "S": False}, {"E": 45, "W": 45}
)
assert set(junc0.active_greens()) == {"E", "W"}, "apply_junction_signals failed"
assert int(junc0.signals["E"].green_duration) == 45, "duration not committed"
print("Atomic apply OK  greens=" + str(junc0.active_greens()) +
      "  E_dur=" + str(int(junc0.signals["E"].green_duration)))

# ── Operator vehicle injection ───────────────────────────────────────────────
n_before = len(engine.vehicles)
added = engine.add_vehicles(jid0, 7)
assert added == 7 and len(engine.vehicles) == n_before + 7, "add_vehicles failed"
print("Add vehicles OK  added=" + str(added))

# ── Signals drive the simulation: green clears queue, red holds it ────────────
junc_a = junctions[jid0]
road = next(iter(junc_a.roads_out.values()), None)
if road is not None:
    junc_a.apply_phase([road.direction], {road.direction: 90})
    road.queue = 20.0
    engine.set_control_mode(CONTROL_MANUAL)
    engine.force_step()
    q_after_green = road.queue
    assert q_after_green < 20.0, "queue did not clear on green"

    red_dir = next(d for d in DIRECTIONS if d not in (road.direction,))
    junc_a.apply_phase([red_dir], {red_dir: 90})
    road.queue = 20.0
    engine.force_step()
    assert road.queue >= q_after_green, "queue dropped on red"
    print("Signal->simulation linkage OK  green=" + str(round(q_after_green, 1)) +
          " (from 20.0), red held=" + str(round(road.queue, 1)))
else:
    print("Signal->simulation linkage SKIPPED (no outgoing road on " + jid0 + ")")

print("ALL SMOKE TESTS PASSED")
