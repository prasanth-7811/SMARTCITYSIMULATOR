import sys, os
sys.stdout.reconfigure(encoding="utf-8")

from map.coimbatore_map import load_coimbatore_network
from dashboard.controls import build_traffic_map

j, g, s, o = load_coimbatore_network()
print("source:", s)
print("junctions:", len(j))
print("osm edges:", len(o.edges) if o else 0)

m = build_traffic_map(j, selected_jid=list(j.keys())[0], osm_graph=o)
m.save("test_map.html")

size = os.path.getsize("test_map.html")
html = open("test_map.html", encoding="utf-8").read()
print("file size:", size, "bytes")
print("has OSM tile:", "openstreetmap.org" in html)
print("has markers:", "L.marker" in html)
print("has polylines:", "polyline" in html.lower())
print("centre lat in html:", "11.0" in html)
print("MAP OK")
