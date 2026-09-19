"""app_smoke_test.py — Executes app.py headlessly via Streamlit's AppTest.

Verifies the dashboard script runs end-to-end without raising exceptions, then
drives the control-room widgets (mode toggle, signal desk, vehicle injection)
to prove they are wired to real application state.
"""

import sys
sys.stdout.reconfigure(encoding="utf-8")

from streamlit.testing.v1 import AppTest

FAILURES = []


def check(label: str, condition: bool, detail: str = ""):
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {label}" + (f"  — {detail}" if detail else ""))
    if not condition:
        FAILURES.append(label)


def main() -> int:
    at = AppTest.from_file("app.py", default_timeout=300)
    at.run()

    print("Exceptions raised:", len(at.exception))
    for exc in at.exception:
        print("  EXCEPTION:", exc.value)

    # ── Element inventory (best-effort; unknown types are ignored) ────────────
    for el_type in ("markdown", "dataframe", "button", "slider", "selectbox",
                    "radio", "number_input", "tabs", "warning", "info",
                    "caption", "plotly_chart"):
        try:
            n = len(at.get(el_type))
        except Exception:
            n = "n/a"
        print(f"  {el_type}: {n}")

    if at.session_state.get("network_loaded"):
        print("  map_source:", at.session_state.get("map_source"))
        print("  junctions:", len(at.session_state.get("junctions", {})))

    if at.exception:
        print("APP SMOKE TEST FAILED (script raised exceptions)")
        return 1

    # ── Interactive control-room checks ──────────────────────────────────────
    print("\nInteractive control-room checks:")
    junctions = at.session_state["junctions"]
    jid0 = list(junctions.keys())[0]
    junc0 = junctions[jid0]

    # 1. Mode toggle must reach the engine
    at.radio(key="mode_radio").set_value("manual").run()
    engine = at.session_state["engine"]
    check("mode toggle -> engine", engine.control_mode == "manual",
          f"control_mode={engine.control_mode}")

    # 2. Junction selector drives which junction is controlled
    check("junction selected", at.session_state["selected_jid"] == jid0,
          f"selected={at.session_state['selected_jid']}")

    # 3. Stage a phase in the Operator Signal Desk and commit it
    for key in (f"p_grn_E_{jid0}", f"p_grn_W_{jid0}",
                f"p_red_N_{jid0}", f"p_red_S_{jid0}"):
        at.button(key=key).click().run()
    at.button(key=f"apply_{jid0}").click().run()
    junc0 = at.session_state["junctions"][jid0]
    check("Apply Signal commits phase", set(junc0.active_greens()) == {"E", "W"},
          f"greens={sorted(junc0.active_greens())}")

    # 4. Manual mode must survive simulation steps (no auto re-cycle)
    at.button(key="btn_step10").click().run()
    junc0 = at.session_state["junctions"][jid0]
    check("manual phase held over 10 steps",
          set(junc0.active_greens()) == {"E", "W"},
          f"greens={sorted(junc0.active_greens())}")

    # 5. Vehicle injection reaches the engine
    engine = at.session_state["engine"]
    n_before = len(engine.vehicles)
    at.number_input(key="add_veh_count").set_value(4).run()
    at.selectbox(key="add_veh_jid").set_value(jid0).run()
    at.button(key="btn_add_veh").click().run()
    engine = at.session_state["engine"]
    check("Add Vehicles reaches engine", len(engine.vehicles) == n_before + 4,
          f"{n_before} -> {len(engine.vehicles)}")

    # 6. Traffic-load slider reaches the engine
    at.slider(key="flow_slider").set_value(3.0).run()
    engine = at.session_state["engine"]
    check("density slider reaches engine", abs(engine.demand_multiplier - 3.0) < 1e-6,
          f"demand_multiplier={engine.demand_multiplier}")

    # 7. Quick preset must resolve to one axis only
    at.button(key=f"ns_{jid0}").click().run()
    junc0 = at.session_state["junctions"][jid0]
    greens = set(junc0.active_greens())
    check("NS preset conflict-free",
          bool(greens & {"N", "S"}) and not (greens & {"E", "W"}),
          f"greens={sorted(greens)}")

    # 8. No exceptions during any interaction
    check("no exceptions during interaction", not at.exception,
          f"{len(at.exception)} raised")

    if FAILURES:
        print("\nAPP SMOKE TEST FAILED: " + "; ".join(FAILURES))
        return 1

    print("\nAPP SMOKE TEST PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())