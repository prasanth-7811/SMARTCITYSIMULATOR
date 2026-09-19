# COIMBATORE SMART TRAFFIC CONTROL SYSTEM
## Quantum-Enhanced Adaptive Urban Traffic Optimization

> **Simulation Prototype** — Does NOT control real traffic signals.
> All traffic values are synthetically generated for demonstration purposes.

---

## 1. Project Overview
An interactive smart-city traffic control dashboard built for Coimbatore, Tamil Nadu.
Users can view the real road network, manually control simulated traffic signals,
run traffic simulations, and compare classical vs quantum optimization results.

## 2. Problem Statement
Urban traffic congestion causes delays, fuel waste, and emergency vehicle delays.
Fixed-time signals cannot adapt to real-time conditions.
This prototype demonstrates how adaptive signal control and quantum optimization
could improve traffic flow — using a simulation environment.

## 3. Main Features
- Real Coimbatore road map (OSMnx) with offline fallback
- **MANUAL / AUTOMATIC control modes** with a live mode indicator
- **On-map live signal indicators** (N S E W per junction, no click required)
- **Operator Signal Desk**: per-direction RED/GREEN, staged durations, atomic
  "Apply Signal" with automatic conflict resolution
- Manual signal control (N/S/E/W per junction)
- Live traffic simulation with queue and density tracking
- **Traffic density control** (arrival-rate multiplier) and **operator vehicle injection**
- Classical optimizer (exhaustive search / simulated annealing)
- Quantum optimizer (QAOA via Qiskit Aer)
- Before/after comparison charts
- Scenario lab: Heavy Traffic, Road Closure, Large Event, Emergency Vehicle
- KPI dashboard: vehicles, wait time, queue, congestion

## 4. System Architecture
```
Streamlit Dashboard (app.py)
    ├── map/coimbatore_map.py       ← OSMnx + fallback network
    ├── simulation/traffic_engine.py ← Core simulation loop
    ├── simulation/junction.py      ← Junction & road models
    ├── simulation/scenarios.py     ← Scenario appliers
    ├── optimization/qubo_model.py  ← QUBO formulation
    ├── optimization/classical_optimizer.py
    ├── optimization/quantum_optimizer.py ← QAOA (Qiskit Aer)
    ├── dashboard/controls.py       ← Folium map builder
    ├── dashboard/metrics.py        ← KPI cards
    ├── dashboard/charts.py         ← Plotly charts
    └── utils/helpers.py            ← Constants & utilities
```

## 5. How the Traffic Simulation Works
- Each junction has N/S/E/W signal states
- Vehicles arrive via Poisson process (seeded, deterministic)
- Vehicles move when their direction signal is green
- Queue builds when signal is red; clears at saturation flow rate
- Density = queue / road capacity (0–1)
- Simulation advances in 10-second steps

## 5b. Control Modes (MANUAL vs AUTOMATIC)

| Mode | Who owns the signals | Behaviour |
|---|---|---|
| **AUTOMATIC** | The engine | When a green timer expires the engine cycles N/S ↔ E/W automatically. Optimizer plans applied here persist until the next cycle. |
| **MANUAL** | The operator | Signals change **only** when you change them. The engine still ages the green timers (for display) but never switches a phase. |

The active mode is shown in the header badge, in the sidebar, and in the map legend.
Manual mode is never silently overridden — pressing **Apply Classical/Quantum Plan**
in manual mode still works, but displays an explicit warning that it replaced your phases.

### Operator Signal Desk
Select a junction, then stage each of the four directions and press **Apply Signal**:
- **RED / GREEN** per direction stages the wanted state (yellow = pending change)
- **Duration (s)** sets the green time for that direction (10–90 s)
- **Apply Signal** commits all four directions atomically via
  `TrafficEngine.apply_junction_signals()`
- **Reload From Live** discards staged edits

Conflicts are impossible: requesting both axes green is auto-resolved by
`Junction.resolve_phase()` — the larger request wins (ties favour N/S) and a
warning is shown. Durations for red directions are stored and used the next
time that direction receives green.

## 6. How QUBO/QAOA Works
- Decision variable: x_i = 1 → junction i uses NS-green, 0 → EW-green
- Objective: minimise weighted queue imbalance + adjacency conflict penalty
- QAOA circuit: p=1 layers, COBYLA parameter optimisation, 256 shots
- Runs on Qiskit Aer (classical simulator of quantum circuits)
- NOT running on real quantum hardware

## 7. Classical vs Quantum Comparison
- Same QUBO objective function used for both
- Classical: exhaustive search (n≤8) or simulated annealing
- Quantum: QAOA with Qiskit Aer
- Results show actual measured QUBO energy and runtime
- No improvements are hardcoded or fabricated

## 8. Folder Structure
```
coimbatore-smart-traffic/
├── app.py
├── requirements.txt
├── README.md
├── smoke_test.py          ← verifies all modules + core logic
├── app_smoke_test.py      ← headless end-to-end dashboard test
├── map_test.py            ← OSMnx network + map rendering test
├── simulation/
│   ├── traffic_engine.py
│   ├── junction.py
│   ├── vehicle.py
│   ├── ambulance.py
│   └── scenarios.py
├── optimization/
│   ├── classical_optimizer.py
│   ├── quantum_optimizer.py
│   └── qubo_model.py
├── map/
│   └── coimbatore_map.py
├── dashboard/
│   ├── controls.py
│   ├── metrics.py
│   └── charts.py
└── utils/
    └── helpers.py
```

## 9. Windows Installation

### Prerequisites
- Python 3.10, 3.11 or 3.12 (3.12 verified working)
- VS Code with Python extension

### Setup
```
cd c:\Users\hp\OneDrive\Desktop\coimbatore-smart-traffic
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

## 10. Run the Application
```
venv\Scripts\activate
streamlit run app.py
```
Open http://localhost:8501 in your browser.

### Verify the Installation
Run these from the project root with the venv active:

```
python smoke_test.py        # module imports + simulation + optimizers
python map_test.py          # OSMnx real network + Folium map render
python app_smoke_test.py    # headless end-to-end dashboard run
```

Expected key output:
- `Quantum available: True` (if Qiskit is installed)
- `source: OpenStreetMap — Real Coimbatore Road Network`
- `map_source: OpenStreetMap — Real Coimbatore Road Network`
- `ALL SMOKE TESTS PASSED` / `MAP OK` / `APP SMOKE TEST PASSED`

`smoke_test.py` also exercises the control-room APIs: control-mode switching,
manual-mode phase retention, automatic phase cycling, conflict resolution,
atomic signal apply, vehicle injection, and the signal → queue linkage.

### Control Room Walkthrough

1. **Check the mode** — the header badge shows `AUTOMATIC MODE` or `MANUAL MODE`.
   Switch it in the sidebar under **🎚 CONTROL MODE**.
2. **Pick a junction** — use *Select Junction* in the control panel, or click a
   marker on the map. The selected junction is highlighted blue.
3. **Read the map** — each junction shows a `N S E W` badge; letters are green or
   red according to the live (simulated) signal state. Road colours show density.
4. **Control the signals** — in the *Operator Signal Desk*, press **RED**/**GREEN**
   for any direction, set **Duration (s)**, then press **✅ Apply Signal**.
   Conflicting N/S + E/W requests are auto-resolved with a warning.
5. **Watch the traffic react** — queues drain on green and build on red; the KPI
   cards and the history chart update every simulation step.
6. **Load the network** — use **🚗 TRAFFIC LOAD** to scale the arrival rate
   (0.1× – 5×) or inject vehicles at a specific junction.
7. **Run the sim** — **▶ Start** / **⏸ Pause** / **🔄 Reset**, or single-step.
8. **Compare optimizers** — run the classical and/or QAOA optimizer, then apply a
   plan from the 📋 Signal Plans tab to see before/after KPIs.


## 11. Troubleshooting

| Error | Fix |
|---|---|
| `ModuleNotFoundError: osmnx` | `pip install osmnx` |
| `ModuleNotFoundError: qiskit_aer` | `pip install qiskit-aer` |
| Map shows fallback network | No internet / OSMnx timeout — fallback works fine |
| Fallback says `scikit-learn must be installed as an optional dependency` | `pip install scikit-learn` — required by osmnx 2.x for `nearest_nodes` on unprojected graphs |
| QAOA shows "SA fallback" | Qiskit not installed — `pip install qiskit qiskit-aer` |
| `streamlit_folium` not found | `pip install streamlit-folium` |

## 12. Known Limitations
- **This prototype does NOT control actual Coimbatore traffic lights** — everything is simulated
- QAOA runs on a classical simulator (Qiskit Aer), not real quantum hardware
- OSMnx requires internet; fallback network used offline
- Simulation is synthetic — not connected to real Coimbatore sensors
- QAOA with p=1 on small problems may not outperform classical methods
- Manual control is **per junction**; there is no network-wide green-wave coordination
- Green duration is a fixed timer — no yellow or all-red clearance interval is modelled
- In MANUAL mode a phase is held indefinitely; there is no automatic fail-safe reversion
- Vehicles are aggregated per road (queue-based), not individually tracked metre-by-metre

## 13. Future Improvements
- Connect to real traffic sensor APIs
- Add SUMO integration for microscopic simulation
- Increase QAOA circuit depth (p > 1)
- Add pedestrian and cyclist modelling
- Deploy on cloud with real-time data feeds
