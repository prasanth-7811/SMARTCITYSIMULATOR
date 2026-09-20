# simulation/sumo_env.py — Author a small synthetic SUMO network.
# 8 named Coimbatore junctions (coords from map.coimbatore_map), ring + chords.
# Clearly labelled SYNTHETIC sample network, not real geometry.
from __future__ import annotations
import math
import os
import re
import subprocess
import xml.etree.ElementTree as ET
from typing import Dict, List, Tuple
from map.coimbatore_map import FALLBACK_JUNCTIONS

SUMO_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sumo")
RING = ["gandhipuram", "race_course", "rs_puram", "ukkadam",
        "singanallur", "peelamedu", "saibaba_colony", "hopes"]
CHORDS = [("gandhipuram", "ukkadam"), ("peelamedu", "race_course")]
DEMAND_VPH = {"low": 60, "medium": 180, "high": 360}

VTYPES = [
    ("car", "passenger", 16.67, 5.0),
    ("moto", "motorcycle", 16.67, 2.5),
    ("truck", "truck", 13.89, 9.0),
    ("bus", "bus", 13.89, 12.0),
    ("cycle", "bicycle", 5.50, 2.0),
]

def _project(lon, lat, lon0, lat0):
    x = (lon - lon0) * 111320.0 * math.cos(math.radians(lat0))
    y = (lat - lat0) * 110540.0
    return x, y


def _junction_centroid():
    lons = [d["lon"] for d in FALLBACK_JUNCTIONS.values()]
    lats = [d["lat"] for d in FALLBACK_JUNCTIONS.values()]
    return sum(lons) / len(lons), sum(lats) / len(lats)


def sumo_to_ll(x, y):
    """Map a SUMO network coordinate (x, y) back to (lat, lon).

    The synthetic net is built by projecting FALLBACK_JUNCTIONS lon/lat into a
    local planar system (see ``_project``); netconvert then shifts all
    coordinates so the minimum becomes zero (the ``netOffset`` in the
    .net.xml header). This inverts both steps so SUMO vehicle positions can be
    overlaid on the real Coimbatore folium map.
    """
    lon0, lat0 = _junction_centroid()
    min_x, min_y = None, None
    for d in FALLBACK_JUNCTIONS.values():
        px, py = _project(d["lon"], d["lat"], lon0, lat0)
        min_x = px if min_x is None else min(min_x, px)
        min_y = py if min_y is None else min(min_y, py)
    off_x, off_y = -min_x, -min_y  # fallback if net file is missing
    try:
        with open(os.path.join(SUMO_DIR, "coimbatore_traffic.net.xml"),
                  "r", encoding="utf-8") as fh:
            head = fh.read(4000)
        m = re.search(r"netOffset=\"(-?[\d.]+),(-?[\d.]+)\"", head)
        if m:
            off_x, off_y = float(m.group(1)), float(m.group(2))
    except OSError:
        pass
    orig_x = float(x) - off_x
    orig_y = float(y) - off_y
    lon = lon0 + orig_x / (111320.0 * math.cos(math.radians(lat0)))
    lat = lat0 + orig_y / 110540.0
    return lat, lon

def directed_edges():
    pairs = []
    n = len(RING)
    for i in range(n):
        a, b = RING[i], RING[(i + 1) % n]
        pairs += [(a, b), (b, a)]
    for a, b in CHORDS:
        pairs += [(a, b), (b, a)]
    return pairs

def _write_nodes(path):
    lons = [d["lon"] for d in FALLBACK_JUNCTIONS.values()]
    lats = [d["lat"] for d in FALLBACK_JUNCTIONS.values()]
    lon0, lat0 = sum(lons) / len(lons), sum(lats) / len(lats)
    root = ET.Element("nodes")
    for jid in RING:
        d = FALLBACK_JUNCTIONS[jid]
        x, y = _project(d["lon"], d["lat"], lon0, lat0)
        ET.SubElement(root, "node", {"id": jid, "x": f"{x:.2f}",
                                     "y": f"{y:.2f}", "type": "traffic_light"})
    ET.ElementTree(root).write(path, encoding="unicode", xml_declaration=True)

def _write_edges(path):
    root = ET.Element("edges")
    for a, b in directed_edges():
        ET.SubElement(root, "edge", {"id": f"E_{a}_{b}", "from": a,
                                     "to": b, "type": "arterial", "numLanes": "1"})
    ET.ElementTree(root).write(path, encoding="unicode", xml_declaration=True)

def _write_types(path):
    root = ET.Element("types")
    ET.SubElement(root, "type", {"id": "arterial", "numLanes": "1",
                                 "speed": "13.89", "priority": "3"})
    ET.ElementTree(root).write(path, encoding="unicode", xml_declaration=True)


def _routes_list():
    routes = []
    n = len(RING)
    for i in range(n):
        chain = [RING[(i + k) % n] for k in range(4)]
        rid = f"R_cw_{i}"
        routes.append((rid, [f"E_{chain[k]}_{chain[k+1]}" for k in range(3)]))
    for i in range(n):
        chain = [RING[(i - k) % n] for k in range(4)]
        rid = f"R_ccw_{i}"
        routes.append((rid, [f"E_{chain[k]}_{chain[k+1]}" for k in range(3)]))
    for k, (a, b) in enumerate(CHORDS):
        routes.append((f"R_ch_{k}a", [f"E_{a}_{b}"]))
        routes.append((f"R_ch_{k}b", [f"E_{b}_{a}"]))
    return routes

def write_routes(path, density="medium"):
    vph = DEMAND_VPH.get(density, DEMAND_VPH["medium"])
    root = ET.Element("routes")
    for vid, vclass, vmax, length in VTYPES:
        ET.SubElement(root, "vType", {"id": vid, "vClass": vclass,
            "accel": "2.6", "decel": "4.5", "sigma": "0.5",
            "length": str(length), "maxSpeed": str(vmax)})
    type_ids = [t[0] for t in VTYPES]
    for i, (rid, edges) in enumerate(_routes_list()):
        ET.SubElement(root, "route", {"id": rid, "edges": " ".join(edges)})
        ET.SubElement(root, "flow", {"id": f"F_{rid}", "route": rid,
            "begin": "0", "end": "3600", "vehsPerHour": str(vph),
            "type": type_ids[i % len(type_ids)]})
    ET.ElementTree(root).write(path, encoding="unicode", xml_declaration=True)

def write_config(path, net_file, route_file):
    root = ET.Element("configuration")
    inp = ET.SubElement(root, "input")
    ET.SubElement(inp, "net-file", {"value": os.path.basename(net_file)})
    ET.SubElement(inp, "route-files", {"value": os.path.basename(route_file)})
    t = ET.SubElement(root, "time")
    ET.SubElement(t, "begin", {"value": "0"})
    proc = ET.SubElement(root, "processing")
    ET.SubElement(proc, "time-to-teleport", {"value": "-1"})
    ET.SubElement(proc, "ignore-route-errors", {"value": "true"})
    ET.ElementTree(root).write(path, encoding="unicode", xml_declaration=True)


def find_binary(name):
    import shutil as _sh
    return _sh.which(name)

def build_network(density="medium"):
    os.makedirs(SUMO_DIR, exist_ok=True)
    nodes = os.path.join(SUMO_DIR, "coimbatore_nodes.nod.xml")
    edges = os.path.join(SUMO_DIR, "coimbatore_edges.edg.xml")
    types = os.path.join(SUMO_DIR, "coimbatore_types.typ.xml")
    net = os.path.join(SUMO_DIR, "coimbatore_traffic.net.xml")
    routes = os.path.join(SUMO_DIR, "routes.rou.xml")
    cfg = os.path.join(SUMO_DIR, "coimbatore_sumo.sumocfg")
    _write_nodes(nodes)
    _write_edges(edges)
    _write_types(types)
    netconvert = find_binary("netconvert")
    if not netconvert:
        raise FileNotFoundError(
            "netconvert not found. Install SUMO (pip install eclipse-sumo) "
            "and ensure venv Scripts is on PATH.")
    res = subprocess.run([netconvert, "--node-files", nodes, "--edge-files",
                   edges, "--type-files", types, "--output-file", net,
                   "--no-turnarounds", "--no-warnings"],
                  capture_output=True, text=True, timeout=120)
    if res.returncode != 0 or not os.path.exists(net):
        raise RuntimeError(f"netconvert failed: {res.stderr[:500]}")
    write_routes(routes, density)
    write_config(cfg, net, routes)
    return {"nodes": nodes, "edges": edges, "types": types,
            "net": net, "routes": routes, "config": cfg}
