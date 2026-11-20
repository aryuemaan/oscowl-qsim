"""Semantics-preserving circuit simplification (the debug agent's deterministic fixes).

One stack-based pass that, per qubit, looks at the most recent surviving gate:
  * cancels adjacent inverse pairs (H H, CX CX, S Sdg, SWAP SWAP, ...)
  * merges consecutive rotations about the same axis (rz(a) rz(b) -> rz(a+b))
  * drops identities (id, zero-angle rotations)
Cancellations cascade, e.g. ``H X X H`` disappears completely. The result is
always equivalent to the input up to a global phase; the agent still verifies
that by simulation before accepting it.
"""
from __future__ import annotations

import math

from .circuit import Circuit, Gate
from .gates import INVERSE_PAIRS, ROTATIONS, SELF_INVERSE, SYMMETRIC_2Q

ANGLE_TOL = 1e-9


def _same_qubits(a: Gate, b: Gate) -> bool:
    if a.qubits == b.qubits:
        return True
    return a.arity == 2 and a.name == b.name and a.name in SYMMETRIC_2Q and set(a.qubits) == set(b.qubits)


def _is_identity(g: Gate) -> bool:
    if g.name == "id":
        return True
    if g.name in ROTATIONS:
        period = ROTATIONS[g.name]
        r = math.remainder(g.params[0], period)
        return abs(r) < ANGLE_TOL
    if g.name == "u3":
        return abs(math.remainder(g.params[0], 4 * math.pi)) < ANGLE_TOL and abs(math.remainder(g.params[1] + g.params[2], 2 * math.pi)) < ANGLE_TOL
    return False


def _cancels(prev: Gate, g: Gate) -> bool:
    if not _same_qubits(prev, g):
        return False
    if prev.name == g.name and g.name in SELF_INVERSE:
        return True
    return (prev.name, g.name) in INVERSE_PAIRS


def simplify(circuit: Circuit) -> tuple[Circuit, list[dict]]:
    """Return (simplified circuit, list of human-readable changes)."""
    out: list[Gate | None] = []
    stacks: list[list[int]] = [[] for _ in range(circuit.num_qubits)]
    changes: list[dict] = []

    def top(g: Gate) -> int | None:
        tops = {stacks[q][-1] if stacks[q] else None for q in g.qubits}
        if len(tops) != 1:
            return None
        t = tops.pop()
        return t if t is not None and set(out[t].qubits) == set(g.qubits) else None  # type: ignore[union-attr]

    def pop(idx: int) -> None:
        for q in out[idx].qubits:  # type: ignore[union-attr]
            stacks[q].pop()
        out[idx] = None

    for g in circuit.gates:
        if _is_identity(g):
            changes.append({"kind": "remove_identity", "lines": [g.line], "two_qubit": g.arity == 2,
                            "description": f"Removed {g.label()} (does nothing)",
                            "finding": f"{g.label()} does nothing"})
            continue
        t = top(g)
        if t is not None:
            prev = out[t]
            assert prev is not None
            if _cancels(prev, g):
                pop(t)
                changes.append({"kind": "cancel_pair", "lines": [prev.line, g.line], "two_qubit": g.arity == 2,
                                "description": f"Cancelled {prev.label()} with {g.label()} (they undo each other)",
                                "finding": f"{prev.label()} and {g.label()} undo each other"})
                continue
            if prev.name == g.name and g.name in ROTATIONS and _same_qubits(prev, g):
                merged = Gate(g.name, prev.qubits, (prev.params[0] + g.params[0],), prev.line)
                pop(t)
                if _is_identity(merged):
                    changes.append({"kind": "cancel_pair", "lines": [prev.line, g.line], "two_qubit": g.arity == 2,
                                    "description": f"Cancelled {prev.label()} with {g.label()} (angles sum to zero)",
                                    "finding": f"{prev.label()} and {g.label()} cancel (angles sum to zero)"})
                    continue
                changes.append({"kind": "merge_rotation", "lines": [prev.line, g.line], "two_qubit": g.arity == 2,
                                "description": f"Merged {prev.label()} and {g.label()} into one {g.name}",
                                "finding": f"{prev.label()} and {g.label()} can be merged into one {g.name}"})
                g = merged
        out.append(g)
        for q in g.qubits:
            stacks[q].append(len(out) - 1)

    gates = [g for g in out if g is not None]
    return circuit.with_gates(gates), changes


def simplification_summary(before: Circuit, after: Circuit) -> dict:
    return {
        "gates_before": len(before.gates), "gates_after": len(after.gates),
        "two_qubit_before": before.two_qubit_count(), "two_qubit_after": after.two_qubit_count(),
        "depth_before": before.depth(), "depth_after": after.depth(),
    }
