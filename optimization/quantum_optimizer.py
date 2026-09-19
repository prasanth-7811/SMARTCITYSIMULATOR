# optimization/quantum_optimizer.py
# QAOA-based quantum optimizer using Qiskit Aer.
# Honest fallback to classical if Qiskit is unavailable.
# Never claims quantum superiority without measured evidence.

import numpy as np
import time
import warnings
warnings.filterwarnings("ignore")

from typing import Dict, List, Tuple
from simulation.junction import Junction
from optimization.qubo_model import build_qubo, evaluate, decode_plan
from optimization.classical_optimizer import _simulated_annealing

# ── Qiskit availability ───────────────────────────────────────────────────────
QUANTUM_AVAILABLE = False
try:
    from qiskit import QuantumCircuit
    from qiskit.circuit import Parameter
    from qiskit_aer import AerSimulator
    QUANTUM_AVAILABLE = True
except Exception:
    pass


def _build_qaoa_circuit(Q: np.ndarray, p: int = 1):
    """Build p-layer QAOA circuit for QUBO Q."""
    if not QUANTUM_AVAILABLE:
        return None
    n      = Q.shape[0]
    gammas = [Parameter(f"g{k}") for k in range(p)]
    betas  = [Parameter(f"b{k}") for k in range(p)]
    qc     = QuantumCircuit(n)
    qc.h(range(n))
    for layer in range(p):
        for i in range(n):
            if Q[i, i] != 0:
                qc.rz(2 * gammas[layer] * Q[i, i], i)
        for i in range(n):
            for j in range(i + 1, n):
                if Q[i, j] != 0:
                    qc.cx(i, j)
                    qc.rz(2 * gammas[layer] * Q[i, j], j)
                    qc.cx(i, j)
        for i in range(n):
            qc.rx(2 * betas[layer], i)
    qc.measure_all()
    return qc


def _run_qaoa(Q: np.ndarray, shots: int = 512, p: int = 1) -> Tuple[np.ndarray, float, str]:
    if not QUANTUM_AVAILABLE:
        x, e = _simulated_annealing(Q)
        return x, e, "Classical SA (Qiskit unavailable)"

    qc        = _build_qaoa_circuit(Q, p)
    n         = Q.shape[0]
    simulator = AerSimulator()
    sorted_params = sorted(qc.parameters, key=lambda pr: pr.name)

    def objective(params):
        b_vals = params[:p]
        g_vals = params[p:]
        pdict  = {sorted_params[k]: b_vals[k] for k in range(p)}
        pdict.update({sorted_params[p + k]: g_vals[k] for k in range(p)})
        bound  = qc.assign_parameters(pdict)
        counts = simulator.run(bound, shots=shots).result().get_counts()
        total, norm = 0.0, 0
        for bitstr, cnt in counts.items():
            xv = np.array([int(b) for b in reversed(bitstr[:n])], dtype=float)
            total += cnt * evaluate(xv, Q)
            norm  += cnt
        return total / max(norm, 1)

    from scipy.optimize import minimize
    rng = np.random.default_rng(0)
    x0  = rng.uniform(0, np.pi, 2 * p)
    try:
        res        = minimize(objective, x0, method="COBYLA",
                              options={"maxiter": 80, "rhobeg": 0.5})
        opt_params = res.x
    except Exception:
        opt_params = x0

    b_vals = opt_params[:p]
    g_vals = opt_params[p:]
    pdict  = {sorted_params[k]: b_vals[k] for k in range(p)}
    pdict.update({sorted_params[p + k]: g_vals[k] for k in range(p)})
    bound  = qc.assign_parameters(pdict)
    counts = simulator.run(bound, shots=shots).result().get_counts()

    best_x, best_e = None, np.inf
    for bitstr, _ in counts.items():
        xv = np.array([int(b) for b in reversed(bitstr[:n])], dtype=float)
        e  = evaluate(xv, Q)
        if e < best_e:
            best_e, best_x = e, xv

    if best_x is None:
        x, e = _simulated_annealing(Q)
        return x, e, "Classical SA (QAOA sampling failed)"

    return best_x, best_e, "QAOA (Qiskit Aer — classical simulator)"


def quantum_optimize(
    junctions: Dict[str, Junction],
    adjacency: List[Tuple[str, str]],
) -> dict:
    """Run QAOA optimizer. Returns result dict."""
    t0     = time.time()
    Q, ids = build_qubo(junctions, adjacency)

    # Keep problem small: use at most 6 junctions for QAOA
    if len(ids) > 6:
        ids_sub = ids[:6]
        junc_sub = {jid: junctions[jid] for jid in ids_sub}
        adj_sub  = [(u, v) for u, v in adjacency if u in ids_sub and v in ids_sub]
        Q, ids_used = build_qubo(junc_sub, adj_sub)
    else:
        ids_used = ids

    try:
        x, energy, method = _run_qaoa(Q, shots=256, p=1)
    except Exception as ex:
        x, energy = _simulated_annealing(Q)
        method = f"Classical SA (QAOA error: {str(ex)[:40]})"

    runtime = time.time() - t0
    plan    = decode_plan(x, ids_used)

    # Fill remaining junctions with default plan
    for jid in ids:
        if jid not in plan:
            plan[jid] = {"greens": ["N", "S"], "durations": {"N": 30, "S": 30}}

    return {
        "method":    method,
        "plan":      plan,
        "energy":    energy,
        "runtime":   runtime,
        "bitstring": "".join(str(int(b)) for b in x),
        "ids":       ids_used,
        "quantum_available": QUANTUM_AVAILABLE,
        "note": ("Running on Qiskit Aer classical simulator — not real quantum hardware."
                 if QUANTUM_AVAILABLE else
                 "Qiskit Aer not available. Used classical simulated annealing as fallback."),
    }
