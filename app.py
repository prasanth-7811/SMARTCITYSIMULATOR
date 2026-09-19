"""
app.py — COIMBATORE SMART TRAFFIC CONTROL SYSTEM
Quantum-Enhanced Adaptive Urban Traffic Optimization

This is a simulation and decision-support prototype.
It does NOT control actual Coimbatore traffic lights.
All traffic values are SIMULATED.
"""
import streamlit as st
import pandas as pd
from streamlit_folium import st_folium

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Coimbatore Smart Traffic",
    page_icon="🚦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Inter:wght@300;400;600;700&display=swap');
html,body,[class*="css"]{background:#080e1c;color:#dde6ff;font-family:'Inter',sans-serif;}
.main{background:#080e1c;}
h1,h2,h3{font-family:'Share Tech Mono',monospace;}
.sim-banner{
  background:rgba(255,170,0,.15);border:1px solid rgba(255,170,0,.4);
  color:#ffaa00;padding:6px 14px;border-radius:6px;font-size:.8rem;
  font-weight:600;letter-spacing:.5px;margin-bottom:8px;
}
.section-header{
  font-family:'Share Tech Mono',monospace;color:#00c8ff;
  font-size:1rem;border-bottom:1px solid rgba(0,200,255,.2);
  padding-bottom:4px;margin:12px 0 8px 0;
}
div[data-testid="stSidebar"]{background:#060c1a;border-right:1px solid rgba(0,200,255,.12);}
.stButton>button{
  background:linear-gradient(135deg,#003a99,#6400ff);color:#fff;
  border:none;border-radius:8px;font-size:.8rem;padding:8px 14px;width:100%;
}
.stButton>button:hover{background:linear-gradient(135deg,#0055dd,#9900ff);}
.green-btn>button{background:linear-gradient(135deg,#006622,#00cc44)!important;}
.red-btn>button{background:linear-gradient(135deg,#660000,#cc0000)!important;}
</style>
""", unsafe_allow_html=True)

# ── Imports ───────────────────────────────────────────────────────────────────
from map.coimbatore_map import load_coimbatore_network
from simulation.traffic_engine import TrafficEngine, CONTROL_AUTO, CONTROL_MANUAL
from simulation.scenarios import apply_scenario, SCENARIOS
from optimization.classical_optimizer import classical_optimize
from optimization.quantum_optimizer import quantum_optimize, QUANTUM_AVAILABLE
from dashboard.controls import build_traffic_map
from simulation.ambulance import AmbulanceService
from dashboard.metrics import (
    kpi_cards_row, render_signal_panel, render_road_metrics,
    mode_badge, render_junction_info, current_phase_label,
)
from dashboard.charts import (
    history_chart, comparison_chart, density_bar_chart,
    queue_chart, optimizer_comparison_chart, vehicle_road_chart,
)
from simulation.junction import DIRECTIONS
from utils.helpers import MIN_GREEN, MAX_GREEN

# ── Session state bootstrap ───────────────────────────────────────────────────
@st.cache_resource(show_spinner="Loading Coimbatore road network…")
def _load_network():
    return load_coimbatore_network()   # returns (junctions, graph, source, osm_graph)


def _init_engine(junctions, graph):
    return TrafficEngine(junctions, graph)


def _get_adjacency(junctions):
    adj = []
    for jid, junc in junctions.items():
        for rid, road in junc.roads_out.items():
            if road.to_junction in junctions:
                adj.append((jid, road.to_junction))
    return list(set(adj))


if "network_loaded" not in st.session_state:
    junctions, graph, source, osm_graph = _load_network()
    st.session_state.junctions     = junctions
    st.session_state.graph         = graph
    st.session_state.map_source    = source
    st.session_state.osm_graph     = osm_graph
    st.session_state.engine        = _init_engine(junctions, graph)
    st.session_state.network_loaded = True
    st.session_state.selected_jid  = list(junctions.keys())[0]
    st.session_state.signal_warnings = []
    st.session_state.classical_result = None
    st.session_state.quantum_result   = None
    st.session_state.before_metrics   = None
    st.session_state.after_classical  = None
    st.session_state.after_quantum    = None
    st.session_state.emergency_route  = []
    st.session_state.scenario         = "normal"
    st.session_state.ambulance_svc    = AmbulanceService(junctions, graph)
    st.session_state.amb_msg          = None
    st.session_state.control_mode     = CONTROL_AUTO
    st.session_state.control_msg      = None

junctions = st.session_state.junctions
graph     = st.session_state.graph
engine    = st.session_state.engine
adjacency = _get_adjacency(junctions)

# Ensure ambulance_svc exists even if session was already initialised before this feature was added
if "ambulance_svc" not in st.session_state:
    st.session_state.ambulance_svc = AmbulanceService(junctions, graph)

# Same guard for the control-mode keys added by the control-room upgrade
if "control_mode" not in st.session_state:
    st.session_state.control_mode = engine.control_mode
if "control_msg" not in st.session_state:
    st.session_state.control_msg = None

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown(
    "<h1 style='color:#00c8ff;font-size:1.6rem;margin:0'>🚦 COIMBATORE SMART TRAFFIC CONTROL SYSTEM</h1>",
    unsafe_allow_html=True,
)
st.markdown(
    "<div class='sim-banner'>⚠ SIMULATION PROTOTYPE — Does NOT control real traffic signals. "
    "All traffic values are SIMULATED for demonstration purposes.</div>",
    unsafe_allow_html=True,
)
st.caption(f"Map source: {st.session_state.map_source}")
st.markdown(
    f"<div style='margin:4px 0 10px 0'>{mode_badge(engine.control_mode)}</div>",
    unsafe_allow_html=True,
)

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("<div class='section-header'>🎮 SIMULATION CONTROLS</div>", unsafe_allow_html=True)

    col_s1, col_s2, col_s3 = st.columns(3)
    with col_s1:
        if st.button("▶ Start", key="btn_run"):
            engine.paused = False
            st.rerun()
    with col_s2:
        if st.button("⏸ Pause", key="btn_pause"):
            engine.paused = True
            st.rerun()
    with col_s3:
        if st.button("🔄 Reset", key="btn_reset"):
            engine.reset()
            st.session_state.classical_result = None
            st.session_state.quantum_result   = None
            st.session_state.before_metrics   = None
            st.session_state.after_classical  = None
            st.session_state.after_quantum    = None
            st.session_state.emergency_route  = []
            st.session_state.signal_warnings  = []
            st.session_state.control_msg      = None
            st.rerun()

    st.caption("🟢 Simulation running" if not engine.paused else "⏸ Simulation paused")

    col_m1, col_m2 = st.columns(2)
    with col_m1:
        if st.button("⏭ Step", key="btn_step"):
            engine.force_step()
            st.rerun()
    with col_m2:
        if st.button("⏭⏭ Step × 10", key="btn_step10"):
            for _ in range(10):
                engine.force_step()
            st.rerun()

    # ── Control mode (MANUAL vs AUTOMATIC) ────────────────────────────────────
    st.markdown("---")
    st.markdown("<div class='section-header'>🎚 CONTROL MODE</div>", unsafe_allow_html=True)

    if "mode_radio" not in st.session_state:
        st.session_state.mode_radio = st.session_state.control_mode

    mode_choice = st.radio(
        "Signal ownership",
        [CONTROL_AUTO, CONTROL_MANUAL],
        format_func=lambda m: "🤖 AUTOMATIC" if m == CONTROL_AUTO else "🕹 MANUAL",
        horizontal=True,
        key="mode_radio",
        help="AUTOMATIC: the engine cycles N/S ↔ E/W when green time expires.\n\n"
             "MANUAL: signals change only when you change them — the engine "
             "never overrides your phase.",
    )
    if engine.control_mode != mode_choice:
        engine.set_control_mode(mode_choice)
    st.session_state.control_mode = engine.control_mode

    if engine.is_manual():
        st.warning("MANUAL — engine will NOT auto-cycle signals.")
    else:
        st.info("AUTOMATIC — phases cycle when green time expires.")

    # ── Traffic load / operator vehicle injection ─────────────────────────────
    st.markdown("---")
    st.markdown("<div class='section-header'>🚗 TRAFFIC LOAD</div>", unsafe_allow_html=True)

    if "flow_slider" not in st.session_state:
        st.session_state.flow_slider = float(engine.demand_multiplier)

    # Density presets
    col_dp1, col_dp2, col_dp3, col_dp4 = st.columns(4)
    with col_dp1:
        if st.button("🟢 Low", key="preset_low"):
            engine.set_demand_multiplier(0.5)
            st.session_state.flow_slider = 0.5
            st.rerun()
    with col_dp2:
        if st.button("🟡 Med", key="preset_med"):
            engine.set_demand_multiplier(1.5)
            st.session_state.flow_slider = 1.5
            st.rerun()
    with col_dp3:
        if st.button("🟠 High", key="preset_high"):
            engine.set_demand_multiplier(3.0)
            st.session_state.flow_slider = 3.0
            st.rerun()
    with col_dp4:
        st.caption("")

    flow = st.slider(
        "Traffic density multiplier",
        min_value=0.1, max_value=5.0, step=0.1,
        key="flow_slider",
        help="Scales the Poisson arrival rate at every junction (1.0 = baseline).",
    )
    if abs(engine.demand_multiplier - flow) > 1e-9:
        engine.set_demand_multiplier(flow)

    # Simulation speed
    sim_speed = st.selectbox(
        "Sim speed", ["1x", "2x", "5x", "10x"],
        key="sim_speed", index=0,
    )
    speed_map = {"1x": 1, "2x": 2, "5x": 5, "10x": 10}

    add_count = st.number_input(
        "Vehicles to inject", min_value=1, max_value=100, value=5, step=1,
        key="add_veh_count",
    )
    add_jid = st.selectbox(
        "Inject at junction", list(junctions.keys()),
        format_func=lambda k: junctions[k].name, key="add_veh_jid",
    )
    if st.button("➕ Add Vehicles", key="btn_add_veh"):
        n = engine.add_vehicles(add_jid, int(add_count))
        st.session_state.control_msg = (
            "ok", f"Added {n} vehicle(s) at {junctions[add_jid].name}."
        )
        st.rerun()

    if st.session_state.get("control_msg"):
        _kind, _msg = st.session_state.control_msg
        (st.success if _kind == "ok" else st.warning)(_msg)

    st.markdown("---")
    st.markdown("<div class='section-header'>🎬 SCENARIO</div>", unsafe_allow_html=True)
    scenario_key = st.selectbox(
        "Select Scenario",
        list(SCENARIOS.keys()),
        format_func=lambda k: SCENARIOS[k]["label"],
        index=list(SCENARIOS.keys()).index(st.session_state.scenario),
    )
    target_jid_scenario = st.selectbox(
        "Target Junction (for closure/emergency)",
        list(junctions.keys()),
        format_func=lambda k: junctions[k].name,
    )
    if st.button("▶ Apply Scenario", key="btn_apply_scn"):
        st.session_state.scenario = scenario_key
        apply_scenario(engine, scenario_key, target_jid_scenario)
        # Keep the traffic-load slider in sync with the scenario preset
        st.session_state.flow_slider = float(engine.demand_multiplier)
        st.session_state.control_msg = (
            "ok", f"Scenario '{SCENARIOS[scenario_key]['label']}' applied "
                  f"(load ×{engine.demand_multiplier:.1f})."
        )
        if scenario_key == "emergency":
            import networkx as nx
            jids = list(junctions.keys())
            dest = jids[-1] if jids[-1] != target_jid_scenario else jids[0]
            try:
                st.session_state.emergency_route = nx.shortest_path(
                    graph, target_jid_scenario, dest, weight="travel_time"
                )
            except Exception:
                st.session_state.emergency_route = [target_jid_scenario]
        else:
            st.session_state.emergency_route = []
        st.rerun()

    st.caption(SCENARIOS.get(scenario_key, {}).get("desc", ""))

    # ── Road Closure ──────────────────────────────────────────────
    st.markdown("---")
    st.markdown("<div class='section-header'>⛔ ROAD CLOSURE</div>", unsafe_allow_html=True)
    closure_jid = st.selectbox(
        "Select junction to close",
        list(junctions.keys()),
        format_func=lambda k: junctions[k].name,
        key="closure_jid",
    )
    if st.button("🔒 Close Road", key="btn_close_road"):
        engine.close_road(closure_jid)
        st.session_state.control_msg = (
            "warn", f"⛔ {junctions[closure_jid].name} is CLOSED — traffic rerouted (simulated)"
        )
        st.rerun()
    if st.button("🔓 Open Road", key="btn_open_road"):
        engine.open_road(closure_jid)
        st.session_state.control_msg = (
            "ok", f"✅ {junctions[closure_jid].name} is now OPEN"
        )
        st.rerun()
    if st.session_state.get("control_msg"):
        _kind, _msg = st.session_state.control_msg
        (st.success if _kind == "ok" else st.warning)(_msg)

    st.markdown("---")
    st.markdown("<div class='section-header'>🔬 OPTIMIZER</div>", unsafe_allow_html=True)
    q_status = "🟢 Qiskit Aer available" if QUANTUM_AVAILABLE else "🔴 Qiskit unavailable — SA fallback"
    st.caption(q_status)

    if st.button("⚙ Run Classical Optimizer"):
        st.session_state.before_metrics  = engine.current_metrics()
        st.session_state.classical_result = classical_optimize(junctions, adjacency)
        st.rerun()

    if st.button("⚛ Run Quantum Optimizer (QAOA)"):
        st.session_state.before_metrics = engine.current_metrics()
        st.session_state.quantum_result  = quantum_optimize(junctions, adjacency)
        st.rerun()

    if st.session_state.classical_result and st.button("✅ Apply Classical Plan", key="btn_apply_classical"):
        engine.apply_signal_plan(st.session_state.classical_result["plan"])
        for _ in range(5):
            engine.force_step()
        st.session_state.after_classical = engine.current_metrics()
        st.session_state.control_msg = (
            "warn",
            "Classical plan applied to all junctions"
            + (" — this overrode your MANUAL phases." if engine.is_manual()
               else " (AUTOMATIC mode).")
            + " The engine will resume auto-cycling; re-apply manual "
              "signals if you need to keep them."
        )
        st.rerun()

    if st.session_state.quantum_result and st.button("✅ Apply Quantum Plan", key="btn_apply_quantum"):
        engine.apply_signal_plan(st.session_state.quantum_result["plan"])
        for _ in range(5):
            engine.force_step()
        st.session_state.after_quantum = engine.current_metrics()
        st.session_state.control_msg = (
            "warn",
            "Quantum plan applied to all junctions"
            + (" — this overrode your MANUAL phases." if engine.is_manual()
               else " (AUTOMATIC mode).")
            + " The engine will resume auto-cycling; re-apply manual "
              "signals if you need to keep them."
        )
        st.rerun()

    # ── What-If Simulator ──────────────────────────────────────
    st.markdown("---")
    st.markdown("<div class='section-header'>🔮 WHAT-IF SIMULATOR</div>", unsafe_allow_html=True)
    st.caption("Test a scenario, compare with current state. Runs 20 sim steps.")

    wf_density = st.slider("What-if density multiplier", 0.1, 5.0, 1.0, 0.1, key="wf_density")
    wf_steps = st.selectbox("What-if steps", [10, 20, 50, 100], key="wf_steps")
    jid0 = list(junctions.keys())[0]
    wf_jid = st.selectbox("What-if junction", list(junctions.keys()), key="wf_jid")
    wf_grn = st.slider("What-if green duration (s)", 10, 90, 30, 5, key="wf_grn")

    if st.button("🔮 Run What-If", key="btn_whatif"):
        # Snapshot current metrics
        before = engine.current_metrics()
        # Temporarily apply changes
        orig_mult = engine._demand_multiplier
        orig_grn = junctions[wf_jid].signals["N"].green_duration
        engine.set_demand_multiplier(wf_density)
        junctions[wf_jid].signals["N"].green_duration = wf_grn
        junctions[wf_jid].signals["S"].green_duration = wf_grn
        for _ in range(int(wf_steps)):
            engine.force_step()
        after = engine.current_metrics()
        # Restore
        engine.set_demand_multiplier(orig_mult)
        junctions[wf_jid].signals["N"].green_duration = orig_grn
        junctions[wf_jid].signals["S"].green_duration = orig_grn
        st.session_state.wf_before = before
        st.session_state.wf_after = after
        st.rerun()

    if st.session_state.get("wf_before") and st.session_state.get("wf_after"):
        b = st.session_state.wf_before
        a = st.session_state.wf_after
        wf_data = [
            {"Metric": "Total Vehicles", "Before": b["total_vehicles"], "After": a["total_vehicles"],
             "Diff": a["total_vehicles"] - b["total_vehicles"]},
            {"Metric": "Avg Wait (s)", "Before": round(b["avg_wait"], 1), "After": round(a["avg_wait"], 1),
             "Diff": round(a["avg_wait"] - b["avg_wait"], 1)},
            {"Metric": "Total Queue", "Before": round(b["total_queue"], 1), "After": round(a["total_queue"], 1),
             "Diff": round(a["total_queue"] - b["total_queue"], 1)},
            {"Metric": "Congestion %", "Before": round(b["congestion_pct"], 1), "After": round(a["congestion_pct"], 1),
             "Diff": round(a["congestion_pct"] - b["congestion_pct"], 1)},
            {"Metric": "Vehicles Moving", "Before": b.get("vehicles_moving", 0), "After": a.get("vehicles_moving", 0),
             "Diff": a.get("vehicles_moving", 0) - b.get("vehicles_moving", 0)},
            {"Metric": "Vehicles Stopped", "Before": b.get("vehicles_stopped", 0), "After": a.get("vehicles_stopped", 0),
             "Diff": a.get("vehicles_stopped", 0) - b.get("vehicles_stopped", 0)},
        ]
        st.dataframe(pd.DataFrame(wf_data), use_container_width=True, hide_index=True)
        st.caption("⚠ WHAT-IF results are SIMULATED projections, not real-time Coimbatore data.")

# ── Auto-step when running ────────────────────────────────────────────────────
if not engine.paused:
    engine.step_sim()

# ── KPI Row ───────────────────────────────────────────────────────────────────
metrics = engine.current_metrics()
kpi_cards_row(metrics)

st.markdown("---")

# ── Main layout: Map | Junction Control ──────────────────────────────────────
col_map, col_ctrl = st.columns([3, 2])

with col_map:
    st.markdown("<div class='section-header'>🗺 COIMBATORE TRAFFIC MAP (Simulated)</div>",
                unsafe_allow_html=True)

    # Build map — use cached version to avoid re-downloading OSMnx on every rerun
    @st.cache_data(show_spinner=False, ttl=30)
    def _cached_map(
        sel_jid, emerg_route_tuple, step,
        densities_tuple, queues_tuple,
        signal_tuple, mode,
        vehicles=None,
    ):
        """Re-build map only when traffic OR signal state actually changes."""
        return build_traffic_map(
            junctions,
            selected_jid=sel_jid,
            emergency_route=list(emerg_route_tuple),
            osm_graph=st.session_state.get("osm_graph"),
            show_signals=True,
            control_mode=mode,
            vehicles=vehicles,
        )

    # Create a hashable summary of current traffic + signal state.
    # The signal snapshot is essential: without it the map would not refresh
    # when the operator changes a signal while the simulation is paused.
    density_snapshot = tuple(
        round(j.avg_density(), 2) for j in junctions.values()
    )
    queue_snapshot = tuple(
        round(j.total_queue(), 1) for j in junctions.values()
    )
    signal_snapshot = tuple(
        tuple(1 if j.signals[d].is_green else 0 for d in ("N", "S", "E", "W"))
        for j in junctions.values()
    )

    veh_snapshot = tuple(
        (v.current_junction, v.vehicle_id) for v in engine.vehicles
    )
    traffic_map = _cached_map(
        st.session_state.selected_jid,
        tuple(st.session_state.emergency_route),
        engine.step,
        density_snapshot,
        queue_snapshot,
        signal_snapshot,
        engine.control_mode,
        vehicles=veh_snapshot,
    )

    st_folium(
        traffic_map,
        width="100%",
        height=500,
        key=f"main_map_{engine.step}_{engine.control_mode}_{hash(signal_snapshot)}",
    )

    st.markdown(
        "🟢 Smooth &nbsp;|&nbsp; 🟡 Moderate &nbsp;|&nbsp; 🔴 Heavy &nbsp;|&nbsp; "
        "🔵 Selected &nbsp;|&nbsp; ⛔ Blocked &nbsp;|&nbsp; 🚑 Emergency &nbsp;|&nbsp; "
        "**N S E W** = live signal state (simulated)",
        unsafe_allow_html=True,
    )

    # Full-resolution standalone map
    if st.button("🗺 Save Full Map as HTML", key="save_map"):
        from dashboard.controls import save_full_map
        path = save_full_map(
            junctions,
            osm_graph=st.session_state.get("osm_graph"),
            path="coimbatore_full_map.html",
        )
        st.success(f"Full map saved to: {path} — open it in your browser for all {len(st.session_state.get('osm_graph').edges) if st.session_state.get('osm_graph') else 0} real OSM roads.")

with col_ctrl:
    st.markdown("<div class='section-header'>🎛 JUNCTION CONTROL PANEL</div>",
                unsafe_allow_html=True)

    # Junction selector
    selected_jid = st.selectbox(
        "Select Junction",
        list(junctions.keys()),
        format_func=lambda k: junctions[k].name,
        index=list(junctions.keys()).index(st.session_state.selected_jid),
        key="junction_selector",
    )
    st.session_state.selected_jid = selected_jid
    junc = junctions[selected_jid]

    # Junction identity + richer live state (control-room info block)
    render_junction_info(junc, engine)

    # Signal state display
    render_signal_panel(junc, st.session_state.signal_warnings)
    st.session_state.signal_warnings = []

    st.markdown("**Manual Signal Control**")
    st.caption("⚠ Conflicting directions will be auto-resolved (N/S vs E/W groups).")

    for direction in ["N", "S", "E", "W"]:
        sig = junc.signals[direction]
        with st.expander(f"Direction {direction} — {'🟢 GREEN' if sig.is_green else '🔴 RED'}", expanded=False):
            c1, c2 = st.columns(2)
            with c1:
                st.markdown('<div class="green-btn">', unsafe_allow_html=True)
                if st.button(f"Set {direction} GREEN", key=f"green_{direction}_{selected_jid}"):
                    dur = st.session_state.get(f"dur_{direction}_{selected_jid}", DEFAULT_GREEN := 30)
                    warns = engine.set_junction_signal(selected_jid, direction, True, dur)
                    st.session_state.signal_warnings = warns
                    st.rerun()
                st.markdown('</div>', unsafe_allow_html=True)
            with c2:
                st.markdown('<div class="red-btn">', unsafe_allow_html=True)
                if st.button(f"Set {direction} RED", key=f"red_{direction}_{selected_jid}"):
                    warns = engine.set_junction_signal(selected_jid, direction, False)
                    st.session_state.signal_warnings = warns
                    st.rerun()
                st.markdown('</div>', unsafe_allow_html=True)

            dur_val = st.slider(
                f"Green Duration (s)",
                min_value=10, max_value=90,
                value=int(sig.green_duration),
                key=f"dur_{direction}_{selected_jid}",
            )
            if dur_val != int(sig.green_duration):
                sig.green_duration = float(dur_val)

    # Quick phase buttons
    st.markdown("**Quick Phase Presets**")
    qc1, qc2 = st.columns(2)
    with qc1:
        if st.button("🟢 NS Phase", key=f"ns_{selected_jid}"):
            junc.apply_phase(["N", "S"], {"N": 35, "S": 35})
            st.rerun()
    with qc2:
        if st.button("🟢 EW Phase", key=f"ew_{selected_jid}"):
            junc.apply_phase(["E", "W"], {"E": 35, "W": 35})
            st.rerun()

    # ── Deferred operator signal desk (atomic, conflict-safe apply) ──────────
    st.markdown("**Signal Desk — Stage Then Apply**")
    st.caption("Stage each direction below, then press ✅ Apply Signal to commit all "
               "four at once. N/S and E/W can never be green together — conflicts "
               "are auto-resolved.")

    pend_key = f"pending_{selected_jid}"
    pdur_key = f"pending_dur_{selected_jid}"
    if st.session_state.get("pending_jid") != selected_jid or pend_key not in st.session_state:
        st.session_state.pending_jid = selected_jid
        st.session_state[pend_key] = {d: junc.signals[d].is_green for d in DIRECTIONS}
        st.session_state[pdur_key] = {d: float(junc.signals[d].green_duration) for d in DIRECTIONS}

    pending = st.session_state[pend_key]
    pdur    = st.session_state[pdur_key]

    for d in DIRECTIONS:
        sig  = junc.signals[d]
        want = pending[d]
        staged = ""
        if want != sig.is_green:
            staged = " &nbsp;→&nbsp; staged GREEN" if want else " &nbsp;→&nbsp; staged RED"
        st.markdown(
            f"<div style='margin-top:6px;font-size:.82rem'>"
            f"<b>{d}</b> — live {'GREEN' if sig.is_green else 'RED'}"
            f"<span style='color:#ffaa00'>{staged}</span></div>",
            unsafe_allow_html=True,
        )
        b1, b2, b3 = st.columns([1, 1, 1.5])
        with b1:
            st.markdown('<div class="red-btn">', unsafe_allow_html=True)
            if st.button("RED", key=f"p_red_{d}_{selected_jid}"):
                pending[d] = False
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)
        with b2:
            st.markdown('<div class="green-btn">', unsafe_allow_html=True)
            if st.button("GREEN", key=f"p_grn_{d}_{selected_jid}"):
                pending[d] = True
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)
        with b3:
            pdur[d] = float(st.number_input(
                "Duration (s)", min_value=MIN_GREEN, max_value=MAX_GREEN,
                value=int(pdur[d]), step=5, key=f"p_dur_{d}_{selected_jid}",
            ))

    st.markdown("")
    ap1, ap2 = st.columns(2)
    with ap1:
        if st.button("✅ Apply Signal", key=f"apply_{selected_jid}"):
            warns = engine.apply_junction_signals(selected_jid, pending, pdur)
            st.session_state.signal_warnings = warns
            st.rerun()
    with ap2:
        if st.button("Reload From Live", key=f"reload_{selected_jid}"):
            st.session_state[pend_key] = {d: junc.signals[d].is_green for d in DIRECTIONS}
            st.session_state[pdur_key] = {d: float(junc.signals[d].green_duration) for d in DIRECTIONS}
            st.rerun()

    if engine.is_manual():
        st.success("MANUAL mode — this phase stays until you change it.")
    else:
        st.info("AUTOMATIC mode — this junction will resume auto-cycling.")

    st.markdown("---")
    st.markdown("**Incoming Road Conditions (Simulated)**")
    render_road_metrics(junc)

# ── Analytics tabs ────────────────────────────────────────────────────────────
st.markdown("---")
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📈 Simulation History",
    "📊 Junction Analytics",
    "⚛ Optimizer Comparison",
    "📋 Signal Plans",
    "🚑 Ambulance Service",
])

with tab1:
    st.plotly_chart(history_chart(engine.history), use_container_width=True)
    if engine.history:
        df_hist = pd.DataFrame([
            {"Step": h.step, "Elapsed (s)": h.elapsed,
             "Vehicles": h.total_vehicles, "Moving": getattr(h, "vehicles_moving", "—"),
             "Avg Wait (s)": f"{h.avg_wait:.1f}",
             "Total Queue": f"{h.total_queue:.1f}", "Congestion %": f"{h.congestion_pct:.0f}%"}
            for h in engine.history[-20:]
        ])
        st.dataframe(df_hist, use_container_width=True, hide_index=True)

with tab2:
    c_d, c_q = st.columns(2)
    with c_d:
        st.plotly_chart(density_bar_chart(junctions), use_container_width=True)
    with c_q:
        st.plotly_chart(queue_chart(junctions), use_container_width=True)

    c_v1, c_v2 = st.columns(2)
    with c_v1:
        st.plotly_chart(vehicle_road_chart(junctions), use_container_width=True)
    with c_v2:
        m = engine.current_metrics()
        st.metric("Vehicles Moving", m.get("vehicles_moving", 0),
                   delta=m.get("vehicles_moving", 0) - engine.history[-1].vehicles_moving if engine.history else 0)
        st.metric("Vehicles Stopped", m.get("vehicles_stopped", 0),
                   delta=0)

    # Full junction table with moving/stopped
    rows = []
    for jid, junc in junctions.items():
        j_veh = sum(1 for v in engine.vehicles if v.current_junction == jid)
        j_moving = sum(1 for v in engine.vehicles
                       if v.current_junction == jid and v.route and not v.is_at_destination())
        rows.append({
            "Junction": junc.name,
            "Vehicles": j_veh,
            "Moving": j_moving,
            "Avg Density": f"{junc.avg_density():.0%}",
            "Total Queue": f"{junc.total_queue():.1f}",
            "Active Greens": ", ".join(junc.active_greens()),
            "Demand": f"{junc.demand:.2f}",
            "Blocked": "⛔" if junc.is_blocked else "✅",
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

with tab3:
    cr = st.session_state.classical_result
    qr = st.session_state.quantum_result

    if cr is None and qr is None:
        st.info("Run Classical and/or Quantum optimizer from the sidebar to see comparison.")
    else:
        if cr:
            st.markdown(f"**Classical:** `{cr['method']}` &nbsp; Energy: `{cr['energy']:.3f}` &nbsp; Runtime: `{cr['runtime']:.4f}s`")
        if qr:
            badge = "⚛" if QUANTUM_AVAILABLE else "⚠"
            st.markdown(f"**Quantum:** `{qr['method']}` &nbsp; Energy: `{qr['energy']:.3f}` &nbsp; Runtime: `{qr['runtime']:.4f}s`")
            st.caption(qr.get("note", ""))

        if cr and qr:
            st.plotly_chart(optimizer_comparison_chart(cr, qr), use_container_width=True)

        # Before / After comparison
        bm = st.session_state.before_metrics
        ac = st.session_state.after_classical
        aq = st.session_state.after_quantum
        if bm and (ac or aq):
            st.markdown("**Before vs After Optimization (measured from simulation)**")
            st.plotly_chart(
                comparison_chart(
                    bm,
                    ac or bm,
                    aq or bm,
                ),
                use_container_width=True,
            )
            comp_rows = []
            for label, d in [("Before", bm), ("After Classical", ac or {}), ("After Quantum", aq or {})]:
                if d:
                    comp_rows.append({
                        "State": label,
                        "Avg Wait (s)": f"{d.get('avg_wait',0):.2f}",
                        "Total Queue": f"{d.get('total_queue',0):.1f}",
                        "Avg Density": f"{d.get('avg_density',0):.0%}",
                        "Vehicles": d.get("total_vehicles", 0),
                    })
            st.dataframe(pd.DataFrame(comp_rows), use_container_width=True, hide_index=True)
            st.caption(
                "Note: QAOA runs on a classical Qiskit Aer simulator — not real quantum hardware. "
                "Results reflect actual measured simulation values. No improvements are hardcoded."
            )

with tab4:
    st.markdown("**Current Signal Plan (all junctions)**")
    plan_rows = []
    for jid, junc in junctions.items():
        greens = junc.active_greens()
        for d, sig in junc.signals.items():
            plan_rows.append({
                "Junction": junc.name,
                "Direction": d,
                "State": "🟢 GREEN" if sig.is_green else "🔴 RED",
                "Green Duration (s)": f"{sig.green_duration:.0f}",
                "Elapsed (s)": f"{sig.elapsed:.0f}",
            })
    st.dataframe(pd.DataFrame(plan_rows), use_container_width=True, hide_index=True)

    if st.session_state.classical_result:
        st.markdown("**Classical Optimizer Signal Plan**")
        plan = st.session_state.classical_result["plan"]
        p_rows = []
        for jid, cfg in plan.items():
            jname = junctions[jid].name if jid in junctions else jid
            p_rows.append({
                "Junction": jname,
                "Green Directions": ", ".join(cfg.get("greens", [])),
                "Durations (s)": str(cfg.get("durations", {})),
            })
        st.dataframe(pd.DataFrame(p_rows), use_container_width=True, hide_index=True)

    if st.session_state.quantum_result:
        st.markdown("**Quantum Optimizer Signal Plan**")
        plan = st.session_state.quantum_result["plan"]
        p_rows = []
        for jid, cfg in plan.items():
            jname = junctions[jid].name if jid in junctions else jid
            p_rows.append({
                "Junction": jname,
                "Green Directions": ", ".join(cfg.get("greens", [])),
                "Durations (s)": str(cfg.get("durations", {})),
                "Bitstring": st.session_state.quantum_result.get("bitstring", ""),
            })
        st.dataframe(pd.DataFrame(p_rows), use_container_width=True, hide_index=True)

with tab5:
    amb_svc: AmbulanceService = st.session_state.ambulance_svc

    # ── Styled ambulance CSS ──────────────────────────────────────────────────
    st.markdown("""
    <style>
    .amb-panel{
      background:rgba(180,0,0,.10);border:1px solid rgba(255,60,60,.35);
      border-radius:12px;padding:18px 22px;margin-bottom:14px;
    }
    .amb-title{
      font-family:'Share Tech Mono',monospace;color:#ff4444;
      font-size:1.25rem;letter-spacing:1px;margin-bottom:4px;
    }
    .amb-sub{color:#ffaaaa;font-size:.82rem;margin-bottom:12px;}
    .lane-free{background:rgba(0,200,80,.15);border:1px solid #00cc44;
      border-radius:6px;padding:4px 10px;color:#00ff88;font-size:.8rem;display:inline-block;margin:2px;}
    .lane-busy{background:rgba(255,100,0,.15);border:1px solid #ff6600;
      border-radius:6px;padding:4px 10px;color:#ffaa44;font-size:.8rem;display:inline-block;margin:2px;}
    .dispatch-btn>button{
      background:linear-gradient(135deg,#aa0000,#ff2222)!important;
      color:#fff!important;font-size:1rem!important;padding:12px 0!important;
      border-radius:10px!important;font-weight:700!important;letter-spacing:.5px!important;
    }
    .dispatch-btn>button:hover{background:linear-gradient(135deg,#cc0000,#ff5555)!important;}
    </style>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div class='amb-panel'>
      <div class='amb-title'>🚑 AMBULANCE EMERGENCY DISPATCH</div>
      <div class='amb-sub'>Select FROM and TO junction — system will find shortest path and clear all signals to GREEN (free lane)</div>
    </div>
    """, unsafe_allow_html=True)

    # ── Dispatch form ─────────────────────────────────────────────────────────
    junc_keys  = list(junctions.keys())
    junc_names = {k: junctions[k].name for k in junc_keys}

    frm_col, arr_col, btn_col = st.columns([2, 2, 1])
    with frm_col:
        st.markdown("**📍 FROM (Ambulance Location)**")
        amb_origin = st.selectbox(
            "From", junc_keys,
            format_func=lambda k: f"📍 {junc_names[k]}",
            key="amb_origin", label_visibility="collapsed",
        )
        st.caption(f"Lat: {junctions[amb_origin].lat:.4f}  Lon: {junctions[amb_origin].lon:.4f}")

    with arr_col:
        st.markdown("**🏥 TO (Hospital / Destination)**")
        dest_opts = [k for k in junc_keys if k != amb_origin]
        amb_dest = st.selectbox(
            "To", dest_opts,
            format_func=lambda k: f"🏥 {junc_names[k]}",
            key="amb_dest", label_visibility="collapsed",
        )
        st.caption(f"Lat: {junctions[amb_dest].lat:.4f}  Lon: {junctions[amb_dest].lon:.4f}")

    with btn_col:
        st.markdown("**&nbsp;**")
        st.markdown('<div class="dispatch-btn">', unsafe_allow_html=True)
        dispatched = st.button("🚑 DISPATCH\nFREE LANE", key="dispatch_btn", use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)
        if dispatched:
            unit = amb_svc.dispatch(amb_origin, amb_dest)
            if unit:
                route_names = " → ".join(junc_names[j] for j in unit.route)
                st.session_state.amb_msg = ("ok",
                    f"🚑 **{unit.unit_id}** dispatched!  "
                    f"Free lane cleared on: {route_names}  |  ETA: {unit.eta_seconds:.0f}s")
                st.session_state.emergency_route = unit.route
            else:
                st.session_state.amb_msg = ("err", "❌ No route found between selected junctions.")
            st.rerun()

    # Feedback banner
    amb_msg = st.session_state.get("amb_msg")
    if amb_msg:
        (st.success if amb_msg[0] == "ok" else st.error)(amb_msg[1])

    st.markdown("---")

    # ── Free lane status per junction ─────────────────────────────────────────
    active_jids = set(amb_svc.all_route_junctions())
    st.markdown("**🛣 Free Lane Status — All Junctions**")
    lane_html = ""
    for jid, junc_obj in junctions.items():
        if jid in active_jids:
            lane_html += f"<span class='lane-free'>🟢 {junc_obj.name} — FREE LANE</span>"
        else:
            lane_html += f"<span class='lane-busy'>🔴 {junc_obj.name} — Normal</span>"
    st.markdown(lane_html, unsafe_allow_html=True)

    st.markdown("---")

    # ── Active units table ────────────────────────────────────────────────────
    if amb_svc.units:
        st.markdown("**Active Ambulance Units**")
        rows = []
        for uid, u in amb_svc.units.items():
            rows.append({
                "Unit ID": uid,
                "From": junc_names.get(u.origin, u.origin),
                "To":   junc_names.get(u.destination, u.destination),
                "Current Junction": junc_names.get(u.current_junction, u.current_junction),
                "Progress": f"{u.progress_pct:.0f}%",
                "Elapsed": f"{u.elapsed:.0f}s",
                "ETA Total": f"{u.eta_seconds:.0f}s",
                "Status": {"en_route": "🚑 En Route", "arrived": "✅ Arrived", "idle": "⏹ Idle"}.get(u.status, u.status),
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        mgmt1, mgmt2, mgmt3 = st.columns(3)
        with mgmt1:
            cancel_uid = st.selectbox("Select unit to cancel", list(amb_svc.units.keys()), key="cancel_sel")
        with mgmt2:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("❌ Cancel & Restore Signals", key="cancel_btn", use_container_width=True):
                amb_svc.cancel(cancel_uid)
                st.session_state.emergency_route = amb_svc.all_route_junctions()
                st.session_state.amb_msg = ("ok", f"Unit {cancel_uid} cancelled. Signals restored.")
                st.rerun()
        with mgmt3:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("🧹 Clear Arrived", key="clear_btn", use_container_width=True):
                amb_svc.clear_arrived()
                st.session_state.emergency_route = amb_svc.all_route_junctions()
                st.rerun()
    else:
        st.info("No ambulances dispatched yet. Fill in FROM / TO above and press 🚑 DISPATCH FREE LANE.")

    st.markdown("---")

    # ── Live route map (always visible) ──────────────────────────────────────
    st.markdown("**🗺 Live Ambulance Route Map**")
    amb_route_map = build_traffic_map(
        junctions,
        selected_jid=None,
        emergency_route=list(active_jids),
        osm_graph=st.session_state.get("osm_graph"),
    )
    st_folium(amb_route_map, width="100%", height=450, key="amb_map")

# ── Auto-refresh when simulation is running ───────────────────────────────────
if not engine.paused:
    import time
    speed_map = {"1x": 1.0, "2x": 0.6, "5x": 0.3, "10x": 0.15}
    time.sleep(speed_map.get(st.session_state.get("sim_speed", "1x"), 0.5))
    st.rerun()
