# map/coimbatore_map.py
# Loads the REAL Coimbatore road network via OSMnx.
# Displays actual road geometry on Folium.
# Falls back to a hand-crafted sample network if download fails.
# All TRAFFIC values (density, queue, wait) are SIMULATED.

import networkx as nx
import numpy as np
from typing import Dict, Tuple

from simulation.junction import Junction, Road, DIRECTIONS
from utils.helpers import CBE_LAT, CBE_LON, SPEED_ARTERIAL, SPEED_COLLECTOR

# ── Key Coimbatore junctions (real lat/lon, hand-verified) ───────────────────
FALLBACK_JUNCTIONS = {
    "gandhipuram":    {"name": "Gandhipuram Bus Stand",   "lat": 11.0168, "lon": 76.9558},
    "rs_puram":       {"name": "RS Puram",                "lat": 11.0050, "lon": 76.9559},
    "peelamedu":      {"name": "Peelamedu",               "lat": 11.0274, "lon": 77.0169},
    "singanallur":    {"name": "Singanallur",             "lat": 10.9987, "lon": 77.0169},
    "ukkadam":        {"name": "Ukkadam",                 "lat": 10.9900, "lon": 76.9600},
    "saibaba_colony": {"name": "Saibaba Colony",          "lat": 11.0300, "lon": 76.9700},
    "race_course":    {"name": "Race Course",             "lat": 11.0100, "lon": 76.9650},
    "hopes":          {"name": "Hope College Junction",   "lat": 11.0200, "lon": 76.9450},
}

FALLBACK_EDGES = [
    ("gandhipuram",    "rs_puram",        800,  SPEED_ARTERIAL,  "S"),
    ("gandhipuram",    "saibaba_colony",  1200, SPEED_COLLECTOR, "N"),
    ("gandhipuram",    "race_course",     600,  SPEED_ARTERIAL,  "E"),
    ("rs_puram",       "ukkadam",         900,  SPEED_COLLECTOR, "S"),
    ("rs_puram",       "race_course",     700,  SPEED_ARTERIAL,  "E"),
    ("peelamedu",      "singanallur",     1500, SPEED_ARTERIAL,  "S"),
    ("peelamedu",      "saibaba_colony",  2000, SPEED_COLLECTOR, "W"),
    ("singanallur",    "ukkadam",         1800, SPEED_ARTERIAL,  "W"),
    ("saibaba_colony", "race_course",     800,  SPEED_COLLECTOR, "S"),
    ("race_course",    "hopes",           600,  SPEED_ARTERIAL,  "W"),
    ("hopes",          "gandhipuram",     700,  SPEED_COLLECTOR, "E"),
    ("ukkadam",        "rs_puram",        900,  SPEED_COLLECTOR, "N"),
]


def _make_road(from_j, to_j, length, speed, direction) -> Road:
    capacity = max(20, int(length / 20))
    rng = np.random.default_rng(abs(hash(from_j + to_j)) % 2**31)
    return Road(
        road_id=f"{from_j}_{to_j}",
        from_junction=from_j,
        to_junction=to_j,
        length_m=length,
        capacity=capacity,
        speed_kmph=speed,
        density=float(rng.uniform(0.1, 0.5)),
        queue=0.0,
        direction=direction,
    )


def build_fallback_network() -> Tuple[Dict[str, Junction], nx.DiGraph]:
    junctions: Dict[str, Junction] = {}
    for jid, d in FALLBACK_JUNCTIONS.items():
        rng = np.random.default_rng(abs(hash(jid)) % 2**31)
        junctions[jid] = Junction(
            junction_id=jid, name=d["name"],
            lat=d["lat"], lon=d["lon"],
            demand=float(rng.uniform(0.3, 0.8)),
        )

    G = nx.DiGraph()
    for jid in junctions:
        G.add_node(jid, lat=junctions[jid].lat, lon=junctions[jid].lon)

    for from_j, to_j, length, speed, direction in FALLBACK_EDGES:
        road = _make_road(from_j, to_j, length, speed, direction)
        junctions[from_j].roads_out[road.road_id] = road
        junctions[to_j].roads_in[road.road_id]    = road
        tt = (length / 1000.0) / speed * 3600.0
        G.add_edge(from_j, to_j, weight=1.0, travel_time=tt, road_id=road.road_id)

        rev_dir  = {"N": "S", "S": "N", "E": "W", "W": "E"}.get(direction, direction)
        rev_road = _make_road(to_j, from_j, length, speed, rev_dir)
        junctions[to_j].roads_out[rev_road.road_id]  = rev_road
        junctions[from_j].roads_in[rev_road.road_id] = rev_road
        G.add_edge(to_j, from_j, weight=1.0, travel_time=tt, road_id=rev_road.road_id)

    return junctions, G


# ── OSMnx real network ────────────────────────────────────────────────────────

# Named key junctions in Coimbatore with real coordinates
NAMED_JUNCTIONS = {
    "gandhipuram":    {"name": "Gandhipuram",          "lat": 11.0168, "lon": 76.9558},
    "rs_puram":       {"name": "RS Puram",             "lat": 11.0050, "lon": 76.9559},
    "peelamedu":      {"name": "Peelamedu",            "lat": 11.0274, "lon": 77.0169},
    "singanallur":    {"name": "Singanallur",          "lat": 10.9987, "lon": 77.0169},
    "ukkadam":        {"name": "Ukkadam",              "lat": 10.9900, "lon": 76.9600},
    "saibaba_colony": {"name": "Saibaba Colony",       "lat": 11.0300, "lon": 76.9700},
    "race_course":    {"name": "Race Course",          "lat": 11.0100, "lon": 76.9650},
    "hopes":          {"name": "Hope College",         "lat": 11.0200, "lon": 76.9450},
    "townhall":       {"name": "Town Hall",            "lat": 11.0130, "lon": 76.9600},
    "ganapathy":      {"name": "Ganapathy",            "lat": 11.0350, "lon": 76.9650},
    "vadavalli":      {"name": "Vadavalli",            "lat": 11.0200, "lon": 76.9100},
    "kuniyamuthur":   {"name": "Kuniyamuthur",         "lat": 10.9800, "lon": 76.9500},
}


def load_coimbatore_network() -> Tuple[Dict[str, Junction], nx.DiGraph, str, object]:
    """
    Download real Coimbatore road network via OSMnx.
    Returns (junctions, graph, source_label, osm_graph_or_None).
    osm_graph is the raw OSMnx graph — used by the map to draw real road geometry.
    """
    try:
        import osmnx as ox
        ox.settings.timeout = 30
        ox.settings.log_console = False

        # Download a 3km radius around Coimbatore city centre
        G_osm = ox.graph_from_point(
            (CBE_LAT, CBE_LON),
            dist=3000,
            network_type="drive",
            simplify=True,
        )

        nodes_gdf, edges_gdf = ox.graph_to_gdfs(G_osm)

        # ── Pick the nearest OSMnx node to each named junction ───────────────
        junctions: Dict[str, Junction] = {}
        osm_id_to_jid: Dict[int, str] = {}

        for jid, info in NAMED_JUNCTIONS.items():
            nearest = ox.distance.nearest_nodes(G_osm, info["lon"], info["lat"])
            node_data = G_osm.nodes[nearest]
            junctions[jid] = Junction(
                junction_id=jid,
                name=info["name"],
                lat=float(node_data["y"]),
                lon=float(node_data["x"]),
                demand=float(np.random.default_rng(abs(hash(jid)) % 2**31).uniform(0.3, 0.8)),
            )
            osm_id_to_jid[nearest] = jid

        # ── Build routing graph between named junctions ───────────────────────
        G = nx.DiGraph()
        for jid, junc in junctions.items():
            G.add_node(jid, lat=junc.lat, lon=junc.lon)

        rng = np.random.default_rng(42)
        jid_list = list(junctions.keys())
        osm_ids  = {jid: ox.distance.nearest_nodes(G_osm, junctions[jid].lon, junctions[jid].lat)
                    for jid in jid_list}

        for i, jid_u in enumerate(jid_list):
            for jid_v in jid_list[i+1:]:
                try:
                    path_len = nx.shortest_path_length(
                        G_osm, osm_ids[jid_u], osm_ids[jid_v], weight="length"
                    )
                    if path_len > 6000:   # skip very distant pairs
                        continue
                    speed  = SPEED_ARTERIAL
                    tt     = (path_len / 1000.0) / speed * 3600.0
                    direction = _bearing_to_dir(junctions[jid_u], junctions[jid_v])
                    rev_dir   = {"N":"S","S":"N","E":"W","W":"E"}.get(direction, direction)

                    road_fwd = Road(
                        road_id=f"{jid_u}_{jid_v}",
                        from_junction=jid_u, to_junction=jid_v,
                        length_m=path_len, capacity=max(20, int(path_len/20)),
                        speed_kmph=speed,
                        density=float(rng.uniform(0.1, 0.6)),
                        queue=0.0, direction=direction,
                    )
                    road_rev = Road(
                        road_id=f"{jid_v}_{jid_u}",
                        from_junction=jid_v, to_junction=jid_u,
                        length_m=path_len, capacity=max(20, int(path_len/20)),
                        speed_kmph=speed,
                        density=float(rng.uniform(0.1, 0.6)),
                        queue=0.0, direction=rev_dir,
                    )
                    junctions[jid_u].roads_out[road_fwd.road_id] = road_fwd
                    junctions[jid_v].roads_in[road_fwd.road_id]  = road_fwd
                    junctions[jid_v].roads_out[road_rev.road_id] = road_rev
                    junctions[jid_u].roads_in[road_rev.road_id]  = road_rev

                    G.add_edge(jid_u, jid_v, weight=1.0, travel_time=tt,
                               road_id=road_fwd.road_id)
                    G.add_edge(jid_v, jid_u, weight=1.0, travel_time=tt,
                               road_id=road_rev.road_id)
                except Exception:
                    continue

        if len(G.edges) < 4:
            raise ValueError("Too few edges in real network")

        return junctions, G, "OpenStreetMap — Real Coimbatore Road Network", G_osm

    except Exception as e:
        junctions, G = build_fallback_network()
        return junctions, G, f"Fallback network (OSMnx error: {str(e)[:80]})", None


def _bearing_to_dir(from_j: Junction, to_j: Junction) -> str:
    """Approximate compass direction from one junction to another."""
    dlat = to_j.lat - from_j.lat
    dlon = to_j.lon - from_j.lon
    if abs(dlat) >= abs(dlon):
        return "N" if dlat > 0 else "S"
    else:
        return "E" if dlon > 0 else "W"
