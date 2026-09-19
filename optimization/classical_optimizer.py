# optimization/classical_optimizer.py
# Classical optimization: exhaustive search (n≤8) + simulated annealing fallback.

import numpy as np
import time
from typing import Dict, List, Tuple
from simulation.junction import Junction
from optimization.qubo_model import build_qubo, evaluate, decode_plan


def _exhaustive(Q: np.ndarray) -> Tuple[np.ndarray, float]:
    n = Q.shape[0]
    best_x, best_e = np.zeros(n), evaluate(np.zeros(n), Q)
    for k in range(2 ** n):
        x = np.array([(k >> b) & 1 for b in range(n)], dtype=float)
        e = evaluate(x, Q)
        if e < best_e:
            best_e, best_x = e, x.copy()
    return best_x, best_e


def _simulated_annealing(Q: np.ndarray, seed: int = 0) -> Tuple[np.ndarray, float]:
    rng = np.random.default_rng(seed)
    n   = Q.shape[0]
    x   = rng.integers(0, 2, n).astype(float)
    e   = evaluate(x, Q)
    best_x, best_e = x.copy(), e
    T   = 5.0
    for _ in range(800):
        i    = rng.integers(0, n)
        x[i] = 1 - x[i]
        ne   = evaluate(x, Q)
        if ne < e or rng.random() < np.exp(-(ne - e) / max(T, 1e-9)):
            e = ne
            if e < best_e:
                best_e, best_x = e, x.copy()
        else:
            x[i] = 1 - x[i]
        T *= 0.995
    return best_x, best_e


def classical_optimize(
    junctions: Dict[str, Junction],
    adjacency: List[Tuple[str, str]],
) -> dict:
    """
    Run classical optimizer. Returns result dict with plan, score, runtime.
    """
    t0 = time.time()
    Q, ids = build_qubo(junctions, adjacency)
    n = len(ids)

    if n <= 8:
        x, energy = _exhaustive(Q)
        method = "Exhaustive Search"
    else:
        x, energy = _simulated_annealing(Q)
        method = "Simulated Annealing"

    runtime = time.time() - t0
    plan    = decode_plan(x, ids)

    return {
        "method":   method,
        "plan":     plan,
        "energy":   energy,
        "runtime":  runtime,
        "bitstring": "".join(str(int(b)) for b in x),
        "ids":      ids,
    }
