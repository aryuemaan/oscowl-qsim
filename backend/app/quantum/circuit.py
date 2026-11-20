"""Circuit intermediate representation shared by the parser, simulators, optimizer and AI layer."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field, replace

from .gates import GATE_SPECS


@dataclass(frozen=True)
class Gate:
    """One unitary gate application. ``line`` points back to the QASM source."""

    name: str
    qubits: tuple[int, ...]
    params: tuple[float, ...] = ()
    line: int | None = None

    @property
    def arity(self) -> int:
        return len(self.qubits)

    def label(self) -> str:
        args = ", ".join(f"q[{q}]" for q in self.qubits)
        if self.params:
            ps = ", ".join(f"{p:.4g}" for p in self.params)
            return f"{self.name}({ps}) {args}"
        return f"{self.name} {args}"


@dataclass
class Circuit:
    num_qubits: int
    gates: list[Gate] = field(default_factory=list)
    num_clbits: int = 0
    measurements: list[tuple[int, int]] = field(default_factory=list)  # (qubit, clbit)
    name: str = "circuit"

    # ------------------------------------------------------------------ helpers
    def with_gates(self, gates: list[Gate]) -> "Circuit":
        return replace(self, gates=list(gates), measurements=list(self.measurements))

    def effective_measurements(self) -> tuple[list[tuple[int, int]], int, bool]:
        """Measurements to sample. Circuits without measurements are measured fully.

        Returns (pairs, number_of_clbits, implicit_flag)."""
        if self.measurements:
            n_cl = max(self.num_clbits, max(c for _, c in self.measurements) + 1)
            return list(self.measurements), n_cl, False
        return [(q, q) for q in range(self.num_qubits)], self.num_qubits, True

    def gate_counts(self) -> dict[str, int]:
        return dict(Counter(g.name for g in self.gates).most_common())

    def two_qubit_count(self) -> int:
        return sum(1 for g in self.gates if g.arity == 2)

    def layers(self) -> list[int]:
        """ASAP layer (moment) index of each gate."""
        frontier = [0] * self.num_qubits
        out = []
        for g in self.gates:
            layer = max(frontier[q] for q in g.qubits)
            out.append(layer)
            for q in g.qubits:
                frontier[q] = layer + 1
        return out

    def depth(self) -> int:
        layers = self.layers()
        return (max(layers) + 1) if layers else 0

    def used_qubits(self) -> set[int]:
        used = {q for g in self.gates for q in g.qubits}
        used.update(q for q, _ in self.measurements)
        return used

    def long_range_gates(self) -> list[Gate]:
        return [g for g in self.gates if g.arity == 2 and abs(g.qubits[0] - g.qubits[1]) > 1]

    def stats(self) -> dict:
        _, n_cl, implicit = self.effective_measurements()
        lr = self.long_range_gates()
        return {
            "num_qubits": self.num_qubits,
            "num_clbits": n_cl,
            "num_gates": len(self.gates),
            "one_qubit_gates": sum(1 for g in self.gates if g.arity == 1),
            "two_qubit_gates": self.two_qubit_count(),
            "depth": self.depth(),
            "gate_counts": self.gate_counts(),
            "long_range_gates": len(lr),
            "max_interaction_distance": max((abs(g.qubits[0] - g.qubits[1]) for g in lr), default=1 if self.two_qubit_count() else 0),
            "implicit_measurement": implicit,
            "unused_qubits": sorted(set(range(self.num_qubits)) - self.used_qubits()),
        }

    # ------------------------------------------------------------------ export
    def to_qasm(self) -> str:
        """Serialise to OpenQASM 2.0 with flat registers ``q`` and ``c``."""
        pairs, n_cl, implicit = self.effective_measurements()
        lines = ["OPENQASM 2.0;", 'include "qelib1.inc";', f"qreg q[{self.num_qubits}];", f"creg c[{n_cl}];"]
        for g in self.gates:
            name = {"u3": "u3", "p": "p"}.get(g.name, g.name)
            if g.name not in GATE_SPECS:
                raise ValueError(f"cannot export gate {g.name}")
            args = ",".join(f"q[{q}]" for q in g.qubits)
            if g.params:
                ps = ",".join(_fmt(p) for p in g.params)
                lines.append(f"{name}({ps}) {args};")
            else:
                lines.append(f"{name} {args};")
        if implicit:
            lines.append("measure q -> c;")
        else:
            lines.extend(f"measure q[{q}] -> c[{c}];" for q, c in pairs)
        return "\n".join(lines) + "\n"


def _fmt(x: float) -> str:
    import math

    for k, label in ((1, "pi"), (2, "pi/2"), (4, "pi/4"), (8, "pi/8")):
        if abs(x - math.pi / k) < 1e-12:
            return label
        if abs(x + math.pi / k) < 1e-12:
            return "-" + label
    return repr(float(x))
