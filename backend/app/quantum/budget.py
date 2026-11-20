"""Noise error budget: where does the fidelity go?

For every gate we estimate the probability that noise corrupts it, turn that
into an additive "weight" w = -ln(1 - e), and aggregate by noise source, gate
type, qubit, circuit layer and individual gate (hotspots, with source lines).
exp(-sum w) is the estimated success probability (ESP), a standard
first-order fidelity estimate that complements the simulated fidelity.
"""
from __future__ import annotations

import math
from collections import defaultdict

from .circuit import Circuit
from .noise import NoiseModel


def _w(p: float) -> float:
    return -math.log(max(1.0 - p, 1e-12)) if p > 0 else 0.0


def error_budget(circuit: Circuit, noise: NoiseModel, top_k: int = 10) -> dict:
    layers = circuit.layers()
    by_source: dict[str, float] = defaultdict(float)
    by_type: dict[str, float] = defaultdict(float)
    by_qubit = [0.0] * circuit.num_qubits
    by_layer = [0.0] * (max(layers) + 1 if layers else 0)
    per_gate = []

    w_ad_qubit = _w(noise.amplitude_damping / 2.0)  # damping hurts only the |1> part: ~half on average
    for idx, g in enumerate(circuit.gates):
        dep = noise.p1 if g.arity == 1 else noise.p2
        w_dep = _w(dep)
        w_ad = w_ad_qubit * g.arity
        w = w_dep + w_ad
        if w <= 0:
            continue
        by_source["1q depolarizing" if g.arity == 1 else "2q depolarizing"] += w_dep
        by_source["amplitude damping"] += w_ad
        by_type[g.name] += w
        for q in g.qubits:
            by_qubit[q] += w / g.arity
        by_layer[layers[idx]] += w
        per_gate.append((w, idx, g))

    pairs, _, _ = circuit.effective_measurements()
    w_ro = _w((noise.readout_p01 + noise.readout_p10) / 2.0)
    for q, _c in pairs:
        by_source["readout"] += w_ro
        by_qubit[q] += w_ro

    total = sum(by_source.values())
    share = (lambda v: v / total) if total > 0 else (lambda v: 0.0)
    per_gate.sort(key=lambda t: (-t[0], t[1]))
    hotspots = [
        {"index": idx, "gate": g.name, "qubits": list(g.qubits), "line": g.line, "label": g.label(),
         "error": 1 - math.exp(-w), "share": share(w), "layer": layers[idx]}
        for w, idx, g in per_gate[:top_k]
    ]
    sources = sorted(({"source": k, "weight": v, "share": share(v)} for k, v in by_source.items() if v > 0),
                     key=lambda d: -d["weight"])
    types = sorted(({"gate": k, "weight": v, "share": share(v), "count": circuit.gate_counts().get(k, 0)}
                    for k, v in by_type.items()), key=lambda d: -d["weight"])
    return {
        "esp": math.exp(-total),
        "total_weight": total,
        "by_source": sources,
        "by_gate_type": types,
        "by_qubit": [{"qubit": q, "weight": v, "share": share(v)} for q, v in enumerate(by_qubit)],
        "by_layer": [{"layer": i, "weight": v} for i, v in enumerate(by_layer)],
        "hotspots": hotspots,
        "dominant_source": sources[0]["source"] if sources else None,
        "model_note": "First-order error budget: each gate's chance of a noise event, aggregated. "
                      "Compare with the simulated fidelity, which includes interference effects.",
    }
