# optimization/qubo_model.py
# QUBO formulation for traffic signal phase selection.
#
# Decision variable: x_i ∈ {0,1}
#   x_i = 1  →  junction i uses NS-green phase
#   x_i = 0  →  junction i uses EW-green phase
#
# Objective (minimise):
#   Σ_i  (queue_ew_i - queue_ns_i) * x_i          ← serve heavier direction
#   + λ  Σ_{(i,j)∈E}  x_i * x_j                  ← penalise adjacent same-phase
#   + μ  Σ_i  density_i * (1 - x_i)               ← penalise high-density EW roads

import numpy as np
from typing import Dict, List, Tuple
from simulation.junction import Junction

LAMBDA = 1.2   # adjacency conflict penalty
MU     = 0.5   # density penalty weight


def build_qubo(
    junctions: Dict[str, Junction],
    adjacency: List[Tuple[str, str]],
) -> Tuple[np.ndarray, List[str]]:
    """
    Build the QUBO matrix Q and return (Q, ordered junction id list).
    Minimise  x^T Q x.
    """
    ids = sorted(junctions.keys())
    n   = len(ids)
    idx = {jid: i for i, jid in enumerate(ids)}
    Q   = np.zeros((n, n))

    for jid in ids:
        junc = junctions[jid]
        i    = idx[jid]
        q_ns = sum(r.queue for d, r in junc.roads_in.items() if r.direction in ("N", "S"))
        q_ew = sum(r.queue for d, r in junc.roads_in.items() if r.direction in ("E", "W"))
        d_ew = np.mean([r.density for r in junc.roads_in.values()
                        if r.direction in ("E", "W")] or [0.0])
        # Diagonal: prefer NS-green when NS queue > EW queue
        Q[i, i] += (q_ew - q_ns)
        # Density penalty for choosing EW (x=0 means EW; penalise via -x term)
        Q[i, i] -= MU * d_ew

    # Off-diagonal: adjacent junctions should not both be NS-green
    for u, v in adjacency:
        if u in idx and v in idx:
            i, j = idx[u], idx[v]
            Q[i, j] += LAMBDA
            Q[j, i] += LAMBDA

    return Q, ids


def evaluate(x: np.ndarray, Q: np.ndarray) -> float:
    return float(x @ Q @ x)


def decode_plan(x: np.ndarray, ids: List[str]) -> Dict[str, Dict]:
    """Convert bitstring to signal plan dict."""
    plan = {}
    for i, jid in enumerate(ids):
        if int(x[i]) == 1:
            plan[jid] = {"greens": ["N", "S"], "durations": {"N": 35, "S": 35}}
        else:
            plan[jid] = {"greens": ["E", "W"], "durations": {"E": 35, "W": 35}}
    return plan
