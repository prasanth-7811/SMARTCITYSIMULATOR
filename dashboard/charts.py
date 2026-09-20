# dashboard/charts.py — Plotly chart builders.

import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import numpy as np
from typing import List
from simulation.traffic_engine import SimSnapshot

DARK = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color="#c0d0ff", family="Inter, sans-serif"),
    margin=dict(l=30, r=20, t=36, b=30),
)


def _dk(fig):
    fig.update_layout(**DARK)
    fig.update_xaxes(gridcolor="rgba(0,200,255,.08)", zerolinecolor="rgba(0,200,255,.15)")
    fig.update_yaxes(gridcolor="rgba(0,200,255,.08)", zerolinecolor="rgba(0,200,255,.15)")
    return fig


def history_chart(history: List[SimSnapshot]) -> go.Figure:
    if not history:
        fig = go.Figure()
        fig.update_layout(**DARK, title="No simulation history yet.")
        return fig
    df = pd.DataFrame([
        {"step": h.step, "avg_wait": h.avg_wait, "total_queue": h.total_queue,
         "vehicles": h.total_vehicles, "congestion_pct": h.congestion_pct}
        for h in history
    ])
    fig = make_subplots(rows=1, cols=3,
                        subplot_titles=["Avg Wait (s)", "Total Queue",
                                        "Congestion (% roads >65%)"])
    fig.add_trace(go.Scatter(x=df["step"], y=df["avg_wait"],
        mode="lines", name="Avg Wait",
        line=dict(color="#00c8ff", width=2),
        fill="tozeroy", fillcolor="rgba(0,200,255,.07)"), row=1, col=1)
    fig.add_trace(go.Scatter(x=df["step"], y=df["total_queue"],
        mode="lines", name="Total Queue",
        line=dict(color="#ff6600", width=2),
        fill="tozeroy", fillcolor="rgba(255,102,0,.07)"), row=1, col=2)
    fig.add_trace(go.Scatter(x=df["step"], y=df["congestion_pct"],
        mode="lines", name="Congestion",
        line=dict(color="#ff2222", width=2),
        fill="tozeroy", fillcolor="rgba(255,34,34,.07)"), row=1, col=3)
    fig.update_layout(**DARK, height=260, showlegend=False,
                      title="Simulation History (simulated values)")
    fig.update_yaxes(rangemode="tozero")
    return _dk(fig)


def sumo_history_chart(history: List[dict]) -> go.Figure:
    """Time-series for live SUMO/TraCI snapshots (dicts from SumoTraciManager)."""
    if not history:
        fig = go.Figure()
        fig.update_layout(**DARK, title="No SUMO history yet.")
        return fig
    df = pd.DataFrame([
        {"step": h.get("step", 0),
         "vehicles": h.get("total_vehicles", 0),
         "moving": h.get("moving", 0),
         "waiting": h.get("waiting", 0),
         "avg_speed": h.get("avg_speed", 0.0),
         "avg_wait": h.get("avg_wait", 0.0)}
        for h in history
    ])
    fig = make_subplots(rows=1, cols=3,
                        subplot_titles=["Vehicles on Network",
                                        "Moving / Waiting",
                                        "Avg Speed (m/s)"])
    fig.add_trace(go.Scatter(x=df["step"], y=df["vehicles"],
        mode="lines", name="Vehicles",
        line=dict(color="#00c8ff", width=2),
        fill="tozeroy", fillcolor="rgba(0,200,255,.07)"), row=1, col=1)
    fig.add_trace(go.Scatter(x=df["step"], y=df["moving"],
        mode="lines", name="Moving",
        line=dict(color="#00ff88", width=2)), row=1, col=2)
    fig.add_trace(go.Scatter(x=df["step"], y=df["waiting"],
        mode="lines", name="Waiting",
        line=dict(color="#ff6600", width=2)), row=1, col=2)
    fig.add_trace(go.Scatter(x=df["step"], y=df["avg_speed"],
        mode="lines", name="Avg Speed",
        line=dict(color="#00e5a0", width=2),
        fill="tozeroy", fillcolor="rgba(0,229,160,.07)"), row=1, col=3)
    fig.update_layout(**DARK, height=260, showlegend=False,
                      title="SUMO Live Simulation History (TraCI)")
    fig.update_yaxes(rangemode="tozero")
    return _dk(fig)


def comparison_chart(before: dict, after_classical: dict, after_quantum: dict) -> go.Figure:
    metrics = ["avg_wait", "total_queue", "avg_density"]
    labels  = ["Avg Wait (s)", "Total Queue", "Avg Density"]
    methods = ["Before", "Classical", "Quantum"]
    colors  = ["#7a8fbb", "#ffb300", "#00c8ff"]

    fig = make_subplots(rows=1, cols=3, subplot_titles=labels)
    for col_i, (metric, label) in enumerate(zip(metrics, labels), 1):
        vals = [
            before.get(metric, 0),
            after_classical.get(metric, 0),
            after_quantum.get(metric, 0),
        ]
        for method, val, color in zip(methods, vals, colors):
            fig.add_trace(go.Bar(
                x=[method], y=[val],
                name=method,
                marker_color=color,
                showlegend=(col_i == 1),
            ), row=1, col=col_i)
    fig.update_layout(**DARK, height=300, barmode="group",
                      title="Before vs After Optimization (measured from simulation)")
    return _dk(fig)


def density_bar_chart(junctions: dict) -> go.Figure:
    names, densities, colors_list = [], [], []
    for jid, junc in junctions.items():
        d = junc.avg_density()
        names.append(junc.name[:18])
        densities.append(d)
        colors_list.append(
            "#00cc44" if d < 0.30 else ("#ffaa00" if d < 0.65 else "#ff2222")
        )
    fig = go.Figure(go.Bar(
        x=names, y=densities,
        marker_color=colors_list,
        text=[f"{d:.0%}" for d in densities],
        textposition="outside",
    ))
    fig.update_layout(**DARK, height=260, title="Junction Avg Density (Simulated)",
                      yaxis=dict(range=[0, 1.1], tickformat=".0%"))
    return _dk(fig)


def queue_chart(junctions: dict) -> go.Figure:
    names, queues = [], []
    for jid, junc in junctions.items():
        names.append(junc.name[:18])
        queues.append(junc.total_queue())
    fig = go.Figure(go.Bar(
        x=names, y=queues,
        marker_color="#6400ff",
        text=[f"{q:.0f}" for q in queues],
        textposition="outside",
    ))
    fig.update_layout(**DARK, height=260, title="Total Queue per Junction (Simulated)")
    return _dk(fig)


def optimizer_comparison_chart(classical_result: dict, quantum_result: dict) -> go.Figure:
    methods = [classical_result.get("method", "Classical"),
               quantum_result.get("method", "Quantum")]
    energies = [classical_result.get("energy", 0), quantum_result.get("energy", 0)]
    runtimes = [classical_result.get("runtime", 0), quantum_result.get("runtime", 0)]

    fig = make_subplots(rows=1, cols=2,
                        subplot_titles=["QUBO Objective Score (lower=better)", "Solver Runtime (s)"])
    fig.add_trace(go.Bar(x=methods, y=energies,
        marker_color=["#ffb300", "#00c8ff"], showlegend=False), row=1, col=1)
    fig.add_trace(go.Bar(x=methods, y=runtimes,
        marker_color=["#ffb300", "#00c8ff"], showlegend=False), row=1, col=2)
    fig.update_layout(**DARK, height=280,
                      title="Classical vs Quantum Optimizer Comparison (actual measured values)")
    return _dk(fig)


def vehicle_road_chart(junctions: dict) -> go.Figure:
    names, queues = [], []
    for jid, junc in junctions.items():
        for rid, road in {**junc.roads_in, **junc.roads_out}.items():
            label = f"{road.from_junction[:8]}→{road.to_junction[:8]}"
            names.append(label)
            queues.append(road.queue)
    fig = go.Figure(go.Bar(
        x=names, y=queues,
        marker_color="#6400ff",
        text=[f"{q:.0f}" for q in queues],
        textposition="outside",
    ))
    fig.update_layout(**DARK, height=260, title="Vehicle Queue per Road (simulated)",
                      xaxis=dict(tickangle=-45),
                      yaxis=dict(title="Vehicles"))
    return _dk(fig)


def junction_congestion_chart(junctions: dict) -> go.Figure:
    """Show congestion level (avg density) for each junction."""
    names, densities, colors_list, queues = [], [], [], []
    for jid, junc in junctions.items():
        d = junc.avg_density()
        q = junc.total_queue()
        names.append(junc.name[:20])
        densities.append(d)
        queues.append(q)
        colors_list.append(
            "#00cc44" if d < 0.30 else ("#ffaa00" if d < 0.65 else "#ff2222")
        )

    fig = make_subplots(
        rows=1, cols=2,
        subplot_titles=["Junction Density (Simulated)", "Junction Queue (Simulated)"],
        specs=[[{"type": "bar"}, {"type": "bar"}]],
    )

    fig.add_trace(go.Bar(
        x=names, y=densities,
        marker_color=colors_list,
        text=[f"{d:.0%}" for d in densities],
        textposition="outside",
    ), row=1, col=1)

    fig.add_trace(go.Bar(
        x=names, y=queues,
        marker_color="#6400ff",
        text=[f"{q:.0f}" for q in queues],
        textposition="outside",
    ), row=1, col=2)

    fig.update_layout(**DARK, height=280,
                      yaxis1=dict(range=[0, 1.1], tickformat=".0%"),
                      yaxis2=dict(title="Vehicles"),
                      showlegend=False)
    return _dk(fig)
