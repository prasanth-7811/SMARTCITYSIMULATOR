# dashboard/controls.py
# Compatible with folium 0.20+ and streamlit-folium 0.27+
# Draws real Coimbatore OSMnx road geometry + simulated traffic overlay.
# OSMnx edges are sampled to keep Streamlit rendering fast.

import folium
from typing import Dict, Optional
from simulation.junction import Junction, DIRECTIONS
from utils.helpers import density_color, congestion_label, CBE_LAT, CBE_LON, CBE_ZOOM


def _signal_badge_html(junc) -> str:
    """Compact live signal indicator rendered on the map itself."""
    greens = set(junc.active_greens())
    cells = "".join(
        f"<span style='color:{'#00e05a' if d in greens else '#ff3b3b'};"
        f"font-weight:700;font-size:11px'>{d}</span>"
        for d in DIRECTIONS
    )
    return (
        "<div style='background:rgba(4,10,22,.90);border:1px solid rgba(0,200,255,.5);"
        "border-radius:5px;padding:1px 6px;letter-spacing:3px;text-align:center;"
        "font-family:monospace;white-space:nowrap;box-shadow:0 0 4px rgba(0,0,0,.6)'>"
        f"{cells}</div>"
    )


def build_traffic_map(
    junctions: Dict[str, Junction],
    selected_jid: Optional[str] = None,
    emergency_route: Optional[list] = None,
    osm_graph=None,
    max_osm_edges: int = 800,   # cap for Streamlit performance
    show_signals: bool = True,  # draw live signal indicators on junctions
    control_mode: Optional[str] = None,
) -> folium.Map:
    emergency_route = emergency_route or []

    lats = [j.lat for j in junctions.values()]
    lons = [j.lon for j in junctions.values()]
    centre_lat = sum(lats) / len(lats) if lats else CBE_LAT
    centre_lon = sum(lons) / len(lons) if lons else CBE_LON

    # ── Base map ──────────────────────────────────────────────────────────────
    m = folium.Map(
        location=[centre_lat, centre_lon],
        zoom_start=CBE_ZOOM,
        tiles="OpenStreetMap",
    )

    folium.TileLayer(
        tiles="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
        attr="&copy; OpenStreetMap &copy; CARTO",
        name="Dark Mode",
        max_zoom=19,
    ).add_to(m)

    # ── Real OSMnx road geometry (sampled for performance) ────────────────────
    if osm_graph is not None:
        try:
            real_layer = folium.FeatureGroup(name="Real Roads (OSM)", show=True)
            edges = list(osm_graph.edges(data=True))

            # Sample edges evenly if too many
            if len(edges) > max_osm_edges:
                step = len(edges) // max_osm_edges
                edges = edges[::step]

            for u, v, data in edges:
                nu = osm_graph.nodes[u]
                nv = osm_graph.nodes[v]
                try:
                    if "geometry" in data:
                        coords = [[pt[1], pt[0]] for pt in data["geometry"].coords]
                    else:
                        coords = [
                            [float(nu["y"]), float(nu["x"])],
                            [float(nv["y"]), float(nv["x"])],
                        ]
                    folium.PolyLine(
                        locations=coords,
                        color="#2255aa",
                        weight=1.5,
                        opacity=0.55,
                    ).add_to(real_layer)
                except Exception:
                    continue
            real_layer.add_to(m)
        except Exception:
            pass

    # ── Simulated traffic density overlay ────────────────────────────────────
    traffic_layer = folium.FeatureGroup(name="Simulated Traffic", show=True)
    drawn = set()
    for jid, junc in junctions.items():
        for rid, road in {**junc.roads_in, **junc.roads_out}.items():
            if rid in drawn:
                continue
            drawn.add(rid)
            fj = junctions.get(road.from_junction)
            tj = junctions.get(road.to_junction)
            if fj is None or tj is None:
                continue
            is_emerg = (road.from_junction in emergency_route
                        and road.to_junction in emergency_route)
            color  = "#ff3355" if is_emerg else density_color(road.density)
            weight = 7 if is_emerg else 5
            tip = (
                f"<b>{fj.name} to {tj.name}</b><br>"
                f"Queue: {road.queue:.1f} veh (simulated)<br>"
                f"Density: {road.density:.0%} (simulated)<br>"
                f"Status: {congestion_label(road.density)}"
            )
            folium.PolyLine(
                locations=[[fj.lat, fj.lon], [tj.lat, tj.lon]],
                color=color, weight=weight, opacity=0.85,
                tooltip=folium.Tooltip(tip),
            ).add_to(traffic_layer)
    traffic_layer.add_to(m)

    # ── Junction markers ──────────────────────────────────────────────────────
    junc_layer = folium.FeatureGroup(name="Junctions", show=True)
    for jid, junc in junctions.items():
        is_sel     = (jid == selected_jid)
        is_blocked = junc.is_blocked
        is_emerg   = jid in emergency_route
        d          = junc.avg_density()

        if is_blocked:
            color, icon = "black",  "ban"
        elif is_emerg:
            color, icon = "red",    "plus-sign"
        elif is_sel:
            color, icon = "blue",   "info-sign"
        else:
            color = "green" if d < 0.30 else ("orange" if d < 0.65 else "red")
            icon  = "map-marker"

        greens = junc.active_greens()
        sig_html = "".join(
            f"<tr><td><b>{dr}</b></td>"
            f"<td style='color:{'#009933' if dr in greens else '#cc0000'}'>"
            f"{'GREEN' if dr in greens else 'RED'}</td></tr>"
            for dr in ["N", "S", "E", "W"]
        )
        popup_html = (
            f"<div style='min-width:200px;font-size:13px'>"
            f"<b style='font-size:14px'>{junc.name}</b><br>"
            f"<span style='color:#888;font-size:11px'>{jid}</span><hr>"
            f"<table>{sig_html}</table><hr>"
            f"Density: <b>{d:.0%}</b> <i style='color:#cc6600'>(simulated)</i><br>"
            f"Queue: <b>{junc.total_queue():.1f}</b> veh "
            f"<i style='color:#cc6600'>(simulated)</i><br>"
            f"{'<b style=color:red>BLOCKED</b>' if is_blocked else ''}"
            f"{'<b style=color:red>EMERGENCY</b>' if is_emerg else ''}"
            f"</div>"
        )
        folium.Marker(
            location=[junc.lat, junc.lon],
            popup=folium.Popup(popup_html, max_width=260),
            tooltip=("Selected: " if is_sel else "") + junc.name,
            icon=folium.Icon(color=color, icon_color="white",
                             icon=icon, prefix="glyphicon"),
        ).add_to(junc_layer)

        # Congestion circle
        folium.CircleMarker(
            location=[junc.lat, junc.lon],
            radius=max(8, 8 + junc.total_queue() * 0.3),
            color=density_color(d),
            fill=True,
            fill_color=density_color(d),
            fill_opacity=0.2,
            weight=2,
        ).add_to(junc_layer)

        # Live signal indicator (always visible, not just in the popup)
        if show_signals:
            folium.Marker(
                location=[junc.lat, junc.lon],
                icon=folium.DivIcon(
                    html=_signal_badge_html(junc),
                    icon_size=(62, 18),
                    icon_anchor=(31, 18),
                ),
                tooltip=(
                    f"{junc.name} — active: "
                    f"{', '.join(junc.active_greens()) or 'none'} "
                    f"({'simulated'})"
                ),
            ).add_to(junc_layer)

    junc_layer.add_to(m)

    # ── Legend ────────────────────────────────────────────────────────────────
    mode_line = (
        f'<b>Control</b> <span style="background:'
        f'{"#00c8ff" if str(control_mode).lower() == "auto" else "#ffaa00"};color:#000;'
        f'font-size:10px;padding:1px 6px;border-radius:3px">'
        f'{str(control_mode).upper()}</span><br>'
        if control_mode else ""
    )
    legend = f"""
    <div style="position:fixed;bottom:28px;left:28px;z-index:9999;
         background:rgba(255,255,255,0.93);padding:10px 14px;
         border-radius:8px;font-size:12px;border:1px solid #bbb;
         font-family:sans-serif;line-height:1.9;box-shadow:2px 2px 6px rgba(0,0,0,.2)">
      <b style="font-size:13px">Traffic Density</b>
      <span style="background:#ffaa00;color:#000;font-size:10px;
            padding:1px 6px;border-radius:3px;margin-left:4px">SIMULATED</span><br>
      <span style="color:#00cc44;font-size:16px">&#9644;</span> Smooth (&lt;30%)<br>
      <span style="color:#ffaa00;font-size:16px">&#9644;</span> Moderate (30-65%)<br>
      <span style="color:#ff2222;font-size:16px">&#9644;</span> Heavy (&gt;65%)<br>
      <span style="color:#ff3355;font-size:16px">&#9644;</span> Emergency Route<br>
      <span style="color:#2255aa;font-size:16px">&#9644;</span> Real OSM Roads<br>
      {mode_line}
      <b>Signal indicator</b>: letters are the 4 directions &mdash;
      <span style="color:#00e05a;font-weight:700;font-family:monospace">N</span> =
      <span style="color:#00e05a">GREEN</span>,
      <span style="color:#ff3b3b;font-weight:700;font-family:monospace">S</span> =
      <span style="color:#ff3b3b">RED</span>
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend))
    folium.LayerControl(collapsed=False).add_to(m)
    return m


def save_full_map(
    junctions: Dict[str, Junction],
    osm_graph=None,
    path: str = "coimbatore_full_map.html",
):
    """Save a full-resolution map (all OSMnx edges) as a standalone HTML file."""
    m = build_traffic_map(junctions, osm_graph=osm_graph, max_osm_edges=99999)
    m.save(path)
    return path
