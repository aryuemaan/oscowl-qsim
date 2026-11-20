"""Resource planner: choose the backend, bond dimension and hardware for a circuit.

The key estimate is an upper bound on the MPS bond dimension at every cut of the
qubit chain: each two-qubit gate spanning a cut can multiply the Schmidt rank
there by at most its operator Schmidt rank (2 for CNOT-like gates, 4 for SWAP),
and no cut can exceed 2^min(left, right). If the bound fits in ``max_bond`` the
MPS simulation is exact; otherwise it is truncated and the error is reported.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass

from .circuit import Circuit
from .gates import SCHMIDT_RANK


@dataclass
class Plan:
    backend: str  # "statevector" | "mps"
    max_bond: int
    exact_expected: bool
    predicted_max_bond: int
    predicted_bonds_log2: list[float]
    statevector_bytes: float
    mps_bytes_estimate: float
    hardware: str
    reason: str

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("predicted_bonds_log2")
        return d


def bond_bounds_log2(circuit: Circuit) -> list[float]:
    n = circuit.num_qubits
    logs = [0.0] * max(n - 1, 0)
    for g in circuit.gates:
        if g.arity != 2:
            continue
        lo, hi = sorted(g.qubits)
        inc = math.log2(SCHMIDT_RANK.get(g.name, 4))
        for c in range(lo, hi):
            logs[c] += inc
    return [min(v, float(min(c + 1, n - c - 1))) for c, v in enumerate(logs)]


def _hardware(backend: str, chi: int, n: int) -> str:
    if backend == "statevector":
        return "CPU (Cloud Run)" if n <= 24 else "GPU (GKE, L4/A100)"
    if chi <= 128:
        return "CPU (Cloud Run)"
    if chi <= 512:
        return "GPU (GKE, NVIDIA L4)"
    return "TPU / large GPU (GKE batch job)"


def plan_resources(circuit: Circuit, backend: str = "auto", max_bond: int = 64,
                   sv_auto_max: int = 20, sv_hard_max: int = 24) -> Plan:
    n = circuit.num_qubits
    logs = bond_bounds_log2(circuit)
    pred_log = max(logs, default=0.0)
    pred_chi = int(min(2 ** min(pred_log, 62), 2**62))
    sv_bytes = 16.0 * 2.0**n

    if backend == "statevector" or (backend == "auto" and n <= sv_auto_max):
        if n > sv_hard_max:
            raise ValueError(
                f"The dense state-vector backend is limited to {sv_hard_max} qubits here "
                f"({n} qubits would need {sv_bytes / 2**30:,.0f} GiB). Use backend 'mps' or 'auto'."
            )
        reason = ("Small circuit: exact dense simulation is fastest." if backend == "auto"
                  else "Dense state-vector backend requested.")
        return Plan("statevector", max_bond, True, pred_chi, logs, sv_bytes, 0.0, _hardware("statevector", 0, n), reason)

    chis = [min(2 ** min(v, 40), max_bond) for v in logs]
    left = [1] + [int(c) for c in chis]
    right = [int(c) for c in chis] + [1]
    mps_bytes = float(sum(16 * 2 * l * r for l, r in zip(left, right)))
    exact = pred_chi <= max_bond
    if exact:
        reason = (f"Tensor network (MPS): predicted bond dimension {pred_chi} fits within {max_bond}, "
                  "so this run is exact.")
    else:
        reason = (f"Tensor network (MPS): entanglement could need bond dimension up to {_fmt_chi(pred_log)}; "
                  f"capped at {max_bond}, so results are approximate with a reported error bound.")
    return Plan("mps", max_bond, exact, pred_chi, logs, sv_bytes, mps_bytes,
                _hardware("mps", min(pred_chi, max_bond), n), reason)


def _fmt_chi(log2v: float) -> str:
    return f"{2 ** log2v:,.0f}" if log2v < 30 else f"2^{log2v:.0f}"
