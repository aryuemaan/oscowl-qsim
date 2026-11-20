"""Matrix-product-state (MPS) simulator: the tensor-network core of Q-Sim.

The n-qubit state is stored as a chain of tensors A[i] with shape
(chi_left, 2, chi_right). Memory grows with the bond dimension chi, not with 2^n,
so structured / low-entanglement circuits with 100+ qubits fit in megabytes.

Accuracy is controlled by ``max_bond``. Every SVD truncation records the discarded
weight, and ``truncation_fidelity`` (product of 1 - discarded weight) is reported
with each result as the error bound. When no truncation happens the simulation is
exact.

The array library is pluggable (NumPy by default, JAX for GPU/TPU via ``xp``).
"""
from __future__ import annotations

import math

import numpy as np

from .gates import flip_two_qubit, gate_matrix

SWAP = gate_matrix("swap")


class MPS:
    kind = "mps"

    def __init__(self, num_qubits: int, max_bond: int = 64, cutoff: float = 1e-14, xp=np):
        self.n = num_qubits
        self.max_bond = int(max_bond)
        self.cutoff = cutoff
        self.xp = xp
        zero = np.zeros((1, 2, 1), dtype=np.complex128)
        zero[0, 0, 0] = 1.0
        self.tensors = [xp.asarray(zero) for _ in range(num_qubits)]
        self.center = 0
        self.truncation_fidelity = 1.0
        self.discarded_weight = 0.0
        self.truncations = 0
        self.max_bond_used = 1

    # --------------------------------------------------------------- canonical form
    def _move_center(self, target: int) -> None:
        xp, T = self.xp, self.tensors
        while self.center < target:
            i = self.center
            a, d, b = T[i].shape
            q, r = xp.linalg.qr(T[i].reshape(a * d, b))
            k = q.shape[1]
            T[i] = q.reshape(a, d, k)
            T[i + 1] = xp.einsum("kb,bdc->kdc", r, T[i + 1])
            self.center += 1
        while self.center > target:
            i = self.center
            a, d, b = T[i].shape
            q, r = xp.linalg.qr(T[i].reshape(a, d * b).T)
            k = q.shape[1]
            T[i] = q.T.reshape(k, d, b)
            T[i - 1] = xp.einsum("xda,ka->xdk", T[i - 1], r)
            self.center -= 1

    # --------------------------------------------------------------- gates
    def apply_1q(self, u: np.ndarray, q: int) -> None:
        self.tensors[q] = self.xp.einsum("st,atb->asb", self.xp.asarray(u), self.tensors[q])

    def apply_local(self, k: np.ndarray, q: int) -> None:
        """Apply a non-unitary 2x2 operator (noise Kraus operator) and renormalise."""
        self._move_center(q)
        t = self.xp.einsum("st,atb->asb", self.xp.asarray(k), self.tensors[q])
        norm = float(self.xp.linalg.norm(t))
        self.tensors[q] = t / norm if norm > 0 else t

    def prob_one(self, q: int) -> float:
        self._move_center(q)
        t = self.tensors[q]
        num = float(self.xp.sum(self.xp.abs(t[:, 1, :]) ** 2))
        den = float(self.xp.sum(self.xp.abs(t) ** 2))
        return num / den if den > 0 else 0.0

    def apply_2q(self, u4: np.ndarray, qa: int, qb: int) -> None:
        """Apply a 4x4 gate whose first qubit is ``qa``. Distant qubits are routed with SWAPs."""
        if qa == qb:
            raise ValueError("two-qubit gate on a single qubit")
        if abs(qa - qb) == 1:
            self._apply_adjacent(u4 if qa < qb else flip_two_qubit(u4), min(qa, qb))
            return
        if qa < qb:
            for k in range(qb, qa + 1, -1):
                self._apply_adjacent(SWAP, k - 1)
            self._apply_adjacent(u4, qa)
            for k in range(qa + 1, qb):
                self._apply_adjacent(SWAP, k)
        else:
            for k in range(qb, qa - 1):
                self._apply_adjacent(SWAP, k)
            self._apply_adjacent(flip_two_qubit(u4), qa - 1)
            for k in range(qa - 2, qb - 1, -1):
                self._apply_adjacent(SWAP, k)

    def _apply_adjacent(self, u4: np.ndarray, i: int) -> None:
        xp, T = self.xp, self.tensors
        self._move_center(i)
        theta = xp.einsum("asb,btc->astc", T[i], T[i + 1])
        theta = xp.einsum("xyst,astc->axyc", xp.asarray(u4).reshape(2, 2, 2, 2), theta)
        a, _, _, c = theta.shape
        u, s, vh = xp.linalg.svd(theta.reshape(a * 2, 2 * c), full_matrices=False)
        s_np = np.asarray(s, dtype=float)
        total = float(np.sum(s_np**2))
        keep = int(np.sum(s_np**2 > self.cutoff * total)) if total > 0 else 1
        keep = max(1, min(keep, self.max_bond))
        discarded = float(np.sum(s_np[keep:] ** 2) / total) if total > 0 else 0.0
        if discarded > 1e-12:  # below this it is floating-point noise, not a real truncation
            self.truncations += 1
            self.discarded_weight += discarded
            self.truncation_fidelity *= 1.0 - discarded
        s = s[:keep]
        s = s / xp.linalg.norm(s)
        T[i] = u[:, :keep].reshape(a, 2, keep)
        T[i + 1] = (s[:, None] * vh[:keep, :]).reshape(keep, 2, c)
        self.center = i + 1
        self.max_bond_used = max(self.max_bond_used, keep)

    # --------------------------------------------------------------- readout
    def _numpy_tensors_right_canonical(self) -> list[np.ndarray]:
        self._move_center(0)
        return [np.asarray(t) for t in self.tensors]

    def sample(self, shots: int, rng: np.random.Generator) -> np.ndarray:
        """Exact sequential sampling of all qubits, vectorised over shots."""
        T = self._numpy_tensors_right_canonical()
        bits = np.zeros((shots, self.n), dtype=np.uint8)
        env = np.ones((shots, 1), dtype=np.complex128)
        rows = np.arange(shots)
        for i, a in enumerate(T):
            v = np.einsum("na,asb->nsb", env, a)
            p = np.sum(np.abs(v) ** 2, axis=2)
            tot = p.sum(axis=1)
            tot[tot == 0] = 1.0
            choice = (rng.random(shots) < p[:, 1] / tot).astype(np.uint8)
            bits[:, i] = choice
            env = v[rows, choice, :]
            env /= np.sqrt(np.maximum(p[rows, choice], 1e-300))[:, None]
        return bits

    def probabilities_for(self, bits: np.ndarray, qubits: list[int]) -> np.ndarray | None:
        """Probability of each row of ``bits``. Cheap when all qubits are measured."""
        T = self._numpy_tensors_right_canonical()
        rows = bits.shape[0]
        if sorted(qubits) == list(range(self.n)):
            full = np.zeros((rows, self.n), dtype=int)
            full[:, qubits] = bits
            vec = np.ones((rows, 1), dtype=np.complex128)
            for i, a in enumerate(T):
                sel = a.transpose(1, 0, 2)[full[:, i]]  # (rows, chi_l, chi_r)
                vec = np.einsum("na,nab->nb", vec, sel)
            return np.abs(vec[:, 0]) ** 2
        if rows > 256:
            return None  # partial-measurement marginals are O(chi^3) per string; skip for big sets
        pos = {q: k for k, q in enumerate(qubits)}
        out = np.zeros(rows)
        for r in range(rows):
            env = np.ones((1, 1), dtype=np.complex128)
            for i, a in enumerate(T):
                if i in pos:
                    m = a[:, int(bits[r, pos[i]]), :]
                    env = m.conj().T @ env @ m
                else:
                    env = sum(a[:, s, :].conj().T @ env @ a[:, s, :] for s in (0, 1))
            out[r] = float(np.real(env[0, 0]))
        return out

    def overlap(self, other: "MPS") -> complex:
        env = np.ones((1, 1), dtype=np.complex128)
        for a, b in zip(self.tensors, other.tensors):
            env = np.einsum("ab,asc,bsd->cd", env, np.asarray(a).conj(), np.asarray(b))
        return complex(env[0, 0])

    def bond_dims(self) -> list[int]:
        return [int(t.shape[2]) for t in self.tensors[:-1]]

    def entanglement_entropies(self) -> list[float]:
        """Von Neumann entropy (bits) across every cut. Uses a copy; the state is unchanged."""
        T = [np.asarray(t) for t in self.tensors]
        # right-canonicalise the copy
        for i in range(self.n - 1, 0, -1):
            a, d, b = T[i].shape
            q, r = np.linalg.qr(T[i].reshape(a, d * b).T)
            T[i] = q.T.reshape(q.shape[1], d, b)
            T[i - 1] = np.einsum("xda,ka->xdk", T[i - 1], r)
        out = []
        for i in range(self.n - 1):
            a, d, b = T[i].shape
            u, s, vh = np.linalg.svd(T[i].reshape(a * d, b), full_matrices=False)
            p = (s**2) / max(np.sum(s**2), 1e-300)
            p = p[p > 1e-16]
            out.append(float(-np.sum(p * np.log2(p))))
            T[i] = u.reshape(a, d, -1)
            T[i + 1] = np.einsum("k,kb,bdc->kdc", s, vh, T[i + 1])
        return out

    def copy(self) -> "MPS":
        new = object.__new__(MPS)
        new.__dict__.update(self.__dict__)
        new.tensors = list(self.tensors)  # arrays are never mutated in place
        return new

    # --------------------------------------------------------------- info
    def memory_bytes(self) -> int:
        return int(sum(math.prod(t.shape) * 16 for t in self.tensors))

    def info(self) -> dict:
        return {
            "kind": self.kind,
            "memory_bytes": self.memory_bytes(),
            "truncation_fidelity": self.truncation_fidelity,
            "discarded_weight": self.discarded_weight,
            "max_bond_used": self.max_bond_used,
            "truncations": self.truncations,
        }
