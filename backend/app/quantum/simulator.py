"""Simulation engine: ideal run, noisy trajectories, metrics and error budget."""
from __future__ import annotations

import math
import time
from collections import Counter
from dataclasses import dataclass, field

import numpy as np

from .arrays import get_array_module
from .budget import error_budget
from .circuit import Circuit
from .gates import gate_matrix
from .mitigation import hellinger_fidelity
from .mps import MPS
from .noise import NoiseModel, TrajectoryNoise, apply_readout_error
from .planner import Plan, plan_resources
from .statevector import StateVector


@dataclass
class SimOptions:
    shots: int = 1024
    trajectories: int = 16
    backend: str = "auto"  # auto | statevector | mps
    max_bond: int = 64
    seed: int | None = None
    array_backend: str = "numpy"
    sv_auto_max: int = 16
    sv_hard_max: int = 24
    time_budget_s: float = 90.0
    chart_outcomes: int = 24


@dataclass
class SimulationRun:
    """Everything the agent needs to reuse: the plan, the ideal state and the JSON result."""

    circuit: Circuit
    plan: Plan
    ideal_state: object
    result: dict = field(default_factory=dict)


# ------------------------------------------------------------------ helpers
def compile_ops(circuit: Circuit) -> list[tuple[int, np.ndarray, tuple[int, ...]]]:
    return [(g.arity, gate_matrix(g.name, g.params), g.qubits) for g in circuit.gates]


def new_state(plan: Plan, n: int, opts: SimOptions):
    if plan.backend == "statevector":
        return StateVector(n, max_qubits=opts.sv_hard_max)
    return MPS(n, max_bond=plan.max_bond, xp=get_array_module(opts.array_backend))


def run_ops(state, ops, noise: TrajectoryNoise | None = None) -> None:
    for arity, u, qs in ops:
        if arity == 1:
            state.apply_1q(u, qs[0])
        else:
            state.apply_2q(u, qs[0], qs[1])
        if noise is not None:
            noise.after_gate(state, qs)


def bits_to_strings(bits: np.ndarray, pairs: list[tuple[int, int]], n_cl: int) -> list[str]:
    """Map qubit bits to classical-register strings in Qiskit order (c[n-1] ... c[0])."""
    cl = np.zeros((bits.shape[0], n_cl), dtype=np.uint8)
    for q, c in pairs:
        cl[:, c] = bits[:, q]
    arr = (cl[:, ::-1] + ord("0")).astype(np.uint8)
    return [row.tobytes().decode() for row in arr]


def ideal_probabilities(state, outcomes: list[str], pairs: list[tuple[int, int]], n_cl: int) -> dict[str, float] | None:
    """Exact ideal probability of each observed classical outcome (None if too expensive)."""
    if not outcomes:
        return {}
    first_clbit: dict[int, int] = {}
    for q, c in pairs:
        first_clbit.setdefault(q, c)
    qubits = list(first_clbit)
    bits = np.array([[int(s[n_cl - 1 - first_clbit[q]]) for q in qubits] for s in outcomes], dtype=np.uint8)
    probs = state.probabilities_for(bits, qubits)
    if probs is None:
        return None
    return {s: float(p) for s, p in zip(outcomes, probs)}


def _split(total: int, parts: int) -> list[int]:
    base, extra = divmod(total, parts)
    return [base + (1 if i < extra else 0) for i in range(parts)]


# ------------------------------------------------------------------ engine
def simulate(circuit: Circuit, noise: NoiseModel, opts: SimOptions | None = None) -> SimulationRun:
    opts = opts or SimOptions()
    t_start = time.perf_counter()
    warnings: list[str] = []
    seed = opts.seed if opts.seed is not None else int(np.random.SeedSequence().entropy % 2**31)
    rng = np.random.default_rng(seed)
    plan = plan_resources(circuit, opts.backend, opts.max_bond, opts.sv_auto_max, opts.sv_hard_max)
    ops = compile_ops(circuit)
    pairs, n_cl, implicit = circuit.effective_measurements()
    if implicit:
        warnings.append("No measurements in the circuit: all qubits are measured at the end.")
    n = circuit.num_qubits

    # ideal run
    t0 = time.perf_counter()
    ideal = new_state(plan, n, opts)
    run_ops(ideal, ops)
    ideal_ms = (time.perf_counter() - t0) * 1000
    ideal_counts = Counter(bits_to_strings(ideal.sample(opts.shots, rng), pairs, n_cl))
    mem_peak = ideal.memory_bytes()

    # noisy trajectories
    t1 = time.perf_counter()
    fids: list[float] = []
    events: list[int] = []
    if noise.has_gate_noise():
        n_traj = max(1, min(opts.trajectories, opts.shots))
        shares = _split(opts.shots, n_traj)
        chunks = []
        for t in range(n_traj):
            if time.perf_counter() - t1 > opts.time_budget_s and t >= 2:
                warnings.append(f"Time budget reached: used {t} of {n_traj} trajectories "
                                f"({sum(shares[:t])} shots). Lower trajectories or bond dimension for full runs.")
                break
            st = new_state(plan, n, opts)
            tn = TrajectoryNoise(noise, rng)
            run_ops(st, ops, tn)
            fids.append(min(1.0, abs(ideal.overlap(st)) ** 2))
            events.append(tn.events)
            mem_peak = max(mem_peak, st.memory_bytes())
            chunks.append(st.sample(shares[t], rng))
        noisy_bits = np.concatenate(chunks, axis=0)
    else:
        noisy_bits = ideal.sample(opts.shots, rng)
        fids, events = [1.0], [0]
    noisy_bits = apply_readout_error(noisy_bits, noise, rng)
    noisy_ms = (time.perf_counter() - t1) * 1000
    noisy_counts = Counter(bits_to_strings(noisy_bits, pairs, n_cl))

    # metrics
    shots = float(sum(noisy_counts.values()))
    p_noisy = {k: v / shots for k, v in noisy_counts.items()}
    exact = ideal_probabilities(ideal, list(noisy_counts), pairs, n_cl)
    hell: float | None
    if len(noisy_counts) > 0.5 * shots and len(noisy_counts) > 64:
        hell, hell_method = None, "not resolvable: outcomes too spread for this many shots (use state fidelity)"
    elif exact is not None:
        hell, hell_method = hellinger_fidelity(p_noisy, exact, normalize_q=False), "exact ideal probabilities"
    else:
        hell, hell_method = hellinger_fidelity(p_noisy, dict(ideal_counts)), "sampled ideal distribution"
    budget = error_budget(circuit, noise)
    fid_mean = float(np.mean(fids))
    fid_err = float(np.std(fids, ddof=1) / math.sqrt(len(fids))) if len(fids) > 1 else 0.0

    # chart data: union of the most likely noisy and ideal outcomes
    top = [k for k, _ in noisy_counts.most_common(opts.chart_outcomes)]
    for k, _ in ideal_counts.most_common(opts.chart_outcomes):
        if k not in top and len(top) < opts.chart_outcomes * 2:
            top.append(k)
    ideal_shots = float(sum(ideal_counts.values()))
    extra = ideal_probabilities(ideal, [k for k in top if exact is None or k not in exact], pairs, n_cl) or {}
    ideal_p = {**(exact or {}), **extra}
    outcomes = sorted(
        ({"bitstring": k, "noisy": p_noisy.get(k, 0.0),
          "ideal": ideal_p.get(k, ideal_counts.get(k, 0) / ideal_shots)} for k in top),
        key=lambda d: -(d["noisy"] + d["ideal"]))[: opts.chart_outcomes]

    tn_info: dict = {"predicted_bonds": [2 ** v for v in plan.predicted_bonds_log2]}
    if isinstance(ideal, MPS):
        tn_info.update({"bond_dims": ideal.bond_dims(), "entropies": ideal.entanglement_entropies()})
    info = ideal.info()
    if info["truncation_fidelity"] < 0.999:
        warnings.append("Bond dimension cap truncated the state; increase max bond for higher accuracy.")

    result = {
        "backend": plan.backend,
        "array_backend": opts.array_backend,
        "plan": plan.to_dict(),
        "seed": seed,
        "shots": int(shots),
        "trajectories": len(fids) if noise.has_gate_noise() else 0,
        "outcomes": outcomes,
        "num_outcomes": len(noisy_counts),
        "counts": dict(noisy_counts.most_common(256)),
        "ideal_counts": dict(ideal_counts.most_common(256)),
        "fidelity": {
            "state": fid_mean,
            "state_stderr": fid_err,
            "hellinger": hell,
            "hellinger_method": hell_method,
            "esp": budget["esp"],
            "truncation": info["truncation_fidelity"],
            "error_bound": 1.0 - info["truncation_fidelity"],
        },
        "noise": noise.to_dict(),
        "noise_events_mean": float(np.mean(events)) if events else 0.0,
        "budget": budget,
        "tensor_network": {**tn_info, "max_bond_used": info["max_bond_used"], "truncations": info["truncations"],
                           "discarded_weight": info["discarded_weight"]},
        "memory": {"used_bytes": mem_peak, "dense_equivalent_bytes": 16.0 * 2.0**n},
        "timing": {"ideal_ms": ideal_ms, "noisy_ms": noisy_ms, "total_ms": (time.perf_counter() - t_start) * 1000},
        "circuit": circuit.stats(),
        "measurement": {"pairs": pairs, "num_clbits": n_cl, "implicit": implicit,
                        "bit_order": "Qiskit order: leftmost character is the highest classical bit"},
        "warnings": warnings,
    }
    return SimulationRun(circuit=circuit, plan=plan, ideal_state=ideal, result=result)


def state_overlap(a, b) -> float:
    """|<a|b>|^2 between two ideal states produced with the same plan."""
    return float(min(1.0, abs(a.overlap(b)) ** 2))
