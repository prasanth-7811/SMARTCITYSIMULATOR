# dashboard/metrics.py — KPI card rendering helpers.

import streamlit as st
from utils.helpers import density_color, congestion_label, format_seconds


def kpi_card(label: str, value: str, color: str = "#00c8ff", icon: str = ""):
    st.markdown(
        f"""
        <div style="
            background:linear-gradient(135deg,rgba(0,200,255,.07),rgba(100,0,255,.07));
            border:1px solid rgba(0,200,255,.2);border-radius:10px;
            padding:14px 16px;text-align:center;margin:4px 0;">
          <div style="font-size:.7rem;color:#7a8fbb;text-transform:uppercase;letter-spacing:1px;">{icon} {label}</div>
          <div style="font-size:1.8rem;font-weight:700;color:{color};font-family:monospace;">{value}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def kpi_cards_row(metrics: dict):
    """Render a 5-card KPI row with vehicle-specific metrics."""
    k1, k2, k3, k4, k5 = st.columns(5)
    with k1: kpi_card("Active Junctions", str(metrics["active_junctions"]), "#00c8ff", "🚦")
    with k2: kpi_card("Total Vehicles",   str(metrics["total_vehicles"]),   "#00ff88", "🚗")
    with k3: kpi_card("Moving",           str(metrics.get("vehicles_moving", 0)), "#00cc44", "▶")
    with k4: kpi_card("Stopped",          str(metrics.get("vehicles_stopped", 0)), "#ff2222", "⏸")
    with k5:
        cong = metrics["congestion_pct"]
        color = "#00cc44" if cong < 30 else ("#ffaa00" if cong < 65 else "#ff2222")
        kpi_card("Congestion", f"{cong:.0f}%", color, "📊")


def signal_badge(direction: str, is_green: bool, duration: float = 0) -> str:
    color  = "#00cc44" if is_green else "#ff2222"
    state  = "GREEN" if is_green else "RED"
    label  = f"{direction}: {state}"
    if is_green and duration > 0:
        label += f" ({duration:.0f}s)"
    return (
        f"<span style='background:{color};color:#fff;padding:3px 10px;"
        f"border-radius:12px;font-size:.75rem;font-weight:700;margin:2px'>{label}</span>"
    )


def render_signal_panel(junction, warnings: list):
    """Render the current signal state for a junction."""
    st.markdown("**Current Signal States**")
    badges = ""
    for d, sig in junction.signals.items():
        badges += signal_badge(d, sig.is_green, sig.green_duration if sig.is_green else 0)
    st.markdown(badges, unsafe_allow_html=True)
    if warnings:
        for w in warnings:
            st.warning(w)


def mode_badge(mode: str) -> str:
    """Return an HTML badge showing the active control mode."""
    is_auto = str(mode).lower() == "auto"
    color = "#00c8ff" if is_auto else "#ffaa00"
    icon  = "🤖" if is_auto else ""
    label = "AUTOMATIC MODE" if is_auto else "MANUAL MODE"
    hint  = "engine cycles phases" if is_auto else "operator owns the signals"
    return (
        f"<span style='background:rgba(0,0,0,.25);border:1px solid {color};"
        f"color:{color};padding:3px 12px;border-radius:12px;font-size:.72rem;"
        f"font-weight:700;letter-spacing:1px;margin-right:8px'>{icon} {label}</span>"
        f"<span style='color:#7a8fbb;font-size:.72rem'>{hint}</span>"
    )


def current_phase_label(junction) -> str:
    """Describe a junction's live phase, e.g. 'NS GREEN' / 'EW GREEN' / 'ALL RED'."""
    greens = set(junction.active_greens())
    if {"N", "S"} & greens and {"E", "W"} & greens:
        return "CONFLICT"
    if {"N", "S"} & greens:
        return "NS GREEN"
    if {"E", "W"} & greens:
        return "EW GREEN"
    return "ALL RED"


def render_junction_info(junction, engine=None):
    """Render the identity + live state block for the selected junction."""
    greens = junction.active_greens() or ["none"]
    phase  = current_phase_label(junction)
    phase_color = (
        "#ff2222" if phase in ("ALL RED", "CONFLICT")
        else ("#00c8ff" if phase == "NS GREEN" else "#00ff88")
    )

    st.markdown(
        f"<div style='background:rgba(0,200,255,.05);border:1px solid "
        f"rgba(0,200,255,.18);border-radius:10px;padding:10px 14px;margin:6px 0'>"
        f"<div style='font-size:1.05rem;font-weight:700;color:#dde6ff'>{junction.name}</div>"
        f"<div style='font-size:.7rem;color:#7a8fbb;font-family:monospace'>"
        f"{junction.junction_id}</div>"
        f"<div style='margin-top:6px;font-size:.78rem;color:#c0d0ff'>"
        f"📍 {junction.lat:.4f}, {junction.lon:.4f}<br>"
        f"🛣 {len(junction.roads_in)} incoming &nbsp;|&nbsp; "
        f"{len(junction.roads_out)} outgoing<br>"
        f" Active greens: <b>{', '.join(greens)}</b><br>"
        f" Phase: <b style='color:{phase_color}'>{phase}</b><br>"
        f"📥 Demand: <b>{junction.demand:.2f}</b> veh/step &nbsp;|&nbsp; "
        f"{'⛔ BLOCKED' if junction.is_blocked else '✅ Open'}"
        f"</div></div>",
        unsafe_allow_html=True,
    )

    # Live simulated traffic at this junction
    c1, c2, c3 = st.columns(3)
    c1.metric("Avg Density", f"{junction.avg_density():.0%}")
    c2.metric("Total Queue", f"{junction.total_queue():.1f}")
    c3.metric("Queueing Roads", str(sum(1 for r in junction.roads_in.values() if r.queue > 0)))

    if engine is not None:
        st.caption(
            f"Control mode: **{engine.control_mode.upper()}** "
            f"&nbsp;|&nbsp; Traffic load ×{engine.demand_multiplier:.1f} "
            f"&nbsp;|&nbsp; — simulated values"
        )


def render_road_metrics(junction):
    """Show queue and density for each incoming road."""
    import pandas as pd
    rows = []
    for rid, road in junction.roads_in.items():
        rows.append({
            "Road": f"{road.from_junction} → {road.to_junction}",
            "Dir": road.direction,
            "Queue": f"{road.queue:.1f}",
            "Density": f"{road.density:.0%}",
            "Status": congestion_label(road.density),
            "Speed (km/h)": f"{road.congested_speed():.0f}",
        })
    if rows:
        import pandas as pd
        st.dataframe(pd.DataFrame(rows), width='stretch', hide_index=True)
    else:
        st.info("No incoming roads for this junction.")
