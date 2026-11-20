"""Noise models, applied with quantum trajectories (Monte-Carlo wavefunction).

Each trajectory is a pure state; averaging many trajectories reproduces the
density-matrix result. This works for both the dense and the MPS backend and
keeps MPS memory small.

Channels (applied after every gate, on the qubits the gate touched):
  * depolarizing_1q  p1: with probability p1 a random Pauli (X, Y or Z) hits the qubit
  * depolarizing_2q  p2: with probability p2 a random non-identity two-qubit Pauli hits the pair
  * amplitude_damping gamma: energy relaxation |1> -> |0> with probability gamma
  * readout error p01 / p10: each measured bit flips 0->1 / 1->0 with that probability
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass

import numpy as np

from .gates import I2, X, Y, Z

PAULI_LIST = [X, Y, Z]
TWO_Q_PAULIS = [(a, b) for a in range(4) for b in range(4) if (a, b) != (0, 0)]
_P4 = [I2, X, Y, Z]


@dataclass
class NoiseModel:
    p1: float = 0.0
    p2: float = 0.0
    amplitude_damping: float = 0.0
    readout_p01: float = 0.0
    readout_p10: float = 0.0

    def is_ideal(self) -> bool:
        return max(self.p1, self.p2, self.amplitude_damping, self.readout_p01, self.readout_p10) == 0.0

    def has_gate_noise(self) -> bool:
        return max(self.p1, self.p2, self.amplitude_damping) > 0.0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict | None) -> "NoiseModel":
        d = dict(d or {})
        if "readout" in d:  # convenience: one symmetric readout error
            r = float(d.pop("readout") or 0.0)
            d.setdefault("readout_p01", r)
            d.setdefault("readout_p10", r)
        return cls(**{k: float(v) for k, v in d.items() if k in cls.__dataclass_fields__})


PRESETS: dict[str, NoiseModel] = {
    "ideal": NoiseModel(),
    "low": NoiseModel(p1=0.0005, p2=0.005, amplitude_damping=0.001, readout_p01=0.01, readout_p10=0.01),
    "nisq": NoiseModel(p1=0.002, p2=0.02, amplitude_damping=0.005, readout_p01=0.03, readout_p10=0.03),
    "harsh": NoiseModel(p1=0.01, p2=0.05, amplitude_damping=0.02, readout_p01=0.06, readout_p10=0.06),
}


class TrajectoryNoise:
    """Applies stochastic noise events to a state during one trajectory."""

    def __init__(self, model: NoiseModel, rng: np.random.Generator):
        self.m = model
        self.rng = rng
        self.events = 0
        if model.amplitude_damping > 0:
            g = model.amplitude_damping
            self.k0 = np.array([[1, 0], [0, math.sqrt(1 - g)]], dtype=np.complex128)
            self.k1 = np.array([[0, 1], [0, 0]], dtype=np.complex128)  # sqrt(g) dropped: renormalised

    def after_gate(self, state, qubits: tuple[int, ...]) -> None:
        m, rng = self.m, self.rng
        if len(qubits) == 1 and m.p1 > 0 and rng.random() < m.p1:
            state.apply_1q(PAULI_LIST[rng.integers(3)], qubits[0])
            self.events += 1
        elif len(qubits) == 2 and m.p2 > 0 and rng.random() < m.p2:
            a, b = TWO_Q_PAULIS[rng.integers(15)]
            if a:
                state.apply_1q(_P4[a], qubits[0])
            if b:
                state.apply_1q(_P4[b], qubits[1])
            self.events += 1
        if m.amplitude_damping > 0:
            for q in qubits:
                p_jump = m.amplitude_damping * state.prob_one(q)
                if p_jump > 0 and rng.random() < p_jump:
                    state.apply_local(self.k1, q)
                    self.events += 1
                else:
                    state.apply_local(self.k0, q)


def apply_readout_error(bits: np.ndarray, model: NoiseModel, rng: np.random.Generator) -> np.ndarray:
    """Flip measured bits according to the readout error rates."""
    if model.readout_p01 == 0 and model.readout_p10 == 0:
        return bits
    r = rng.random(bits.shape)
    flip = np.where(bits == 0, r < model.readout_p01, r < model.readout_p10)
    return (bits ^ flip.astype(np.uint8)).astype(np.uint8)
