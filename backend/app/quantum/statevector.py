"""Dense state-vector simulator.

Exact, simple, and the baseline we benchmark against: memory is 16 * 2^n bytes,
so it is only practical up to ~25-30 qubits on a laptop.
"""
from __future__ import annotations

import numpy as np


class StateVector:
    kind = "statevector"

    def __init__(self, num_qubits: int, max_qubits: int = 26):
        if num_qubits > max_qubits:
            need = 16 * 2**num_qubits / 2**30
            raise MemoryError(f"Dense simulation of {num_qubits} qubits needs {need:,.0f} GiB; use the MPS backend")
        self.n = num_qubits
        psi = np.zeros(2**num_qubits, dtype=np.complex128)
        psi[0] = 1.0
        self.psi = psi.reshape((2,) * num_qubits) if num_qubits else psi

    # --------------------------------------------------------------- gates
    def apply_1q(self, u: np.ndarray, q: int) -> None:
        self.psi = np.moveaxis(np.tensordot(u, self.psi, axes=([1], [q])), 0, q)

    def apply_2q(self, u4: np.ndarray, qa: int, qb: int) -> None:
        u = u4.reshape(2, 2, 2, 2)
        out = np.tensordot(u, self.psi, axes=([2, 3], [qa, qb]))
        self.psi = np.moveaxis(out, [0, 1], [qa, qb])

    def apply_local(self, k: np.ndarray, q: int) -> None:
        """Apply a (possibly non-unitary) 2x2 operator and renormalise."""
        self.apply_1q(k, q)
        norm = np.linalg.norm(self.psi)
        if norm > 0:
            self.psi = self.psi / norm

    def prob_one(self, q: int) -> float:
        sl = [slice(None)] * self.n
        sl[q] = 1
        return float(np.sum(np.abs(self.psi[tuple(sl)]) ** 2))

    # --------------------------------------------------------------- readout
    def sample(self, shots: int, rng: np.random.Generator) -> np.ndarray:
        """Return a (shots, n) uint8 array of measured bits (column = qubit)."""
        p = np.abs(self.psi.reshape(-1)) ** 2
        cdf = np.cumsum(p)
        idx = np.searchsorted(cdf, rng.random(shots) * cdf[-1], side="right")
        idx = np.minimum(idx, p.size - 1)
        shifts = np.arange(self.n - 1, -1, -1)
        return ((idx[:, None] >> shifts[None, :]) & 1).astype(np.uint8)

    def probabilities_for(self, bits: np.ndarray, qubits: list[int]) -> np.ndarray:
        """Exact probability of each row of ``bits`` (values for ``qubits``), marginalising the rest."""
        probs = np.abs(self.psi) ** 2
        others = tuple(q for q in range(self.n) if q not in qubits)
        marg = probs.sum(axis=others) if others else probs
        order = sorted(qubits)
        marg = np.transpose(marg, [order.index(q) for q in qubits]) if order != list(qubits) else marg
        return np.asarray([marg[tuple(row)] for row in bits.astype(int)], dtype=float)

    def overlap(self, other: "StateVector") -> complex:
        return complex(np.vdot(self.psi.reshape(-1), other.psi.reshape(-1)))

    def copy(self) -> "StateVector":
        new = object.__new__(StateVector)
        new.n, new.psi = self.n, self.psi.copy()
        return new

    # --------------------------------------------------------------- info
    def memory_bytes(self) -> int:
        return int(self.psi.nbytes)

    def info(self) -> dict:
        return {"kind": self.kind, "memory_bytes": self.memory_bytes(), "truncation_fidelity": 1.0,
                "discarded_weight": 0.0, "max_bond_used": None, "truncations": 0}
