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
