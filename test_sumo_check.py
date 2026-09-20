# Test SUMO network generation + TraCI queries end to end.
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from simulation.sumo_backend import (
    connect, describe_backend, ensure_network, get_manager)

backend = describe_backend()
print("sumo-gui:", backend["sumo_gui"] or "NOT FOUND")
print("sumo-cli:", backend["sumo_cli"] or "NOT FOUND")
print("traci importable:", backend["traci_importable"])
assert backend["sumo_gui"] and backend["sumo_cli"], "SUMO binaries missing"
assert backend["traci_importable"], "traci bindings missing"

paths = ensure_network("low")
print("net:", paths["net"])
print("routes:", paths["routes"])
print("config:", paths["config"])
assert os.path.exists(paths["net"])
assert os.path.exists(paths["config"])

mgr = get_manager("smoke")
snap = connect(mgr, density="low", gui=False)
print("connected:", snap.get("connected"))
print("tls mapped:", len(mgr.junction_tls), "/", 8)
for jid, tls in sorted(mgr.junction_tls.items()):
    print(f"  {jid} -> {tls}")
assert snap.get("connected")
assert len(mgr.junction_tls) == 8

snap0 = mgr.collect_metrics()
for _ in range(30):
    snap = mgr.step(1)
print("after 30 steps: vehicles =", snap.get("total_vehicles"),
      "moving =", snap.get("moving"), "waiting =", snap.get("waiting"))

msg = mgr.apply_signal("gandhipuram", "EW")
print("apply EW:", msg)
msg = mgr.apply_signal("gandhipuram", "NS")
print("apply NS:", msg)
snap = mgr.collect_metrics()
print("override stored:", mgr.overrides.get("gandhipuram"))

msg = mgr.set_green_duration("gandhipuram", 45)
print("set_green_duration:", msg)

snap = mgr.collect_metrics()
if snap.get("queue_by_junction"):
    jid = sorted(snap["queue_by_junction"])[0]
else:
    jid = "gandhipuram"
edge = f"E_{jid}_gandhipuram" if jid != "gandhipuram" else "E_gandhipuram_race_course"
msg = mgr.set_road_closed(edge, True)
print("close:", msg)
msg = mgr.set_road_closed(edge, False)
print("reopen:", msg)

mgr.stop()
print("stopped, running =", mgr.running)
print("SUMO SMOKE OK")