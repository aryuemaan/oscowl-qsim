"""Gate library: names, arities, unitary matrices and algebraic properties.

Convention for two-qubit matrices: the FIRST qubit listed in the gate call is the
most significant bit of the 4x4 matrix index (|q_first q_second>). So ``cx a, b``
uses control = a and the familiar matrix [[1,0,0,0],[0,1,0,0],[0,0,0,1],[0,0,1,0]].
"""
from __future__ import annotations

import math
from functools import lru_cache

import numpy as np

# name -> (number of qubits, number of parameters)
GATE_SPECS: dict[str, tuple[int, int]] = {
    # one-qubit
    "id": (1, 0), "x": (1, 0), "y": (1, 0), "z": (1, 0), "h": (1, 0),
    "s": (1, 0), "sdg": (1, 0), "t": (1, 0), "tdg": (1, 0),
    "sx": (1, 0), "sxdg": (1, 0),
    "rx": (1, 1), "ry": (1, 1), "rz": (1, 1), "p": (1, 1),
    "u2": (1, 2), "u3": (1, 3),
    # two-qubit
    "cx": (2, 0), "cy": (2, 0), "cz": (2, 0), "ch": (2, 0),
    "crx": (2, 1), "cry": (2, 1), "crz": (2, 1), "cp": (2, 1), "cu3": (2, 3),
    "swap": (2, 0), "iswap": (2, 0), "ecr": (2, 0),
    "rxx": (2, 1), "ryy": (2, 1), "rzz": (2, 1),
    # three-qubit (decomposed into 1- and 2-qubit gates by the parser)
    "ccx": (3, 0), "ccz": (3, 0), "cswap": (3, 0),
}

ALIASES: dict[str, str] = {
    "i": "id", "cnot": "cx", "CX": "cx", "U": "u3", "u": "u3", "u1": "p", "phase": "p",
    "cphase": "cp", "cu1": "cp", "toffoli": "ccx", "fredkin": "cswap",
}

SELF_INVERSE = {"id", "x", "y", "z", "h", "cx", "cy", "cz", "ch", "swap"}
INVERSE_PAIRS = {("s", "sdg"), ("sdg", "s"), ("t", "tdg"), ("tdg", "t"), ("sx", "sxdg"), ("sxdg", "sx")}
# gates whose two qubits can be exchanged without changing the operation
SYMMETRIC_2Q = {"cz", "swap", "cp", "rzz", "rxx", "ryy", "iswap"}
# single-angle rotations that compose additively, with the period after which they
# are the identity (up to a global phase for uncontrolled gates)
ROTATIONS: dict[str, float] = {
    "rx": 2 * math.pi, "ry": 2 * math.pi, "rz": 2 * math.pi, "p": 2 * math.pi,
    "rxx": 2 * math.pi, "ryy": 2 * math.pi, "rzz": 2 * math.pi, "cp": 2 * math.pi,
    "crx": 4 * math.pi, "cry": 4 * math.pi, "crz": 4 * math.pi,
}
# operator Schmidt rank of two-qubit gates: how much a gate can grow an MPS bond
SCHMIDT_RANK: dict[str, int] = {
    "cx": 2, "cy": 2, "cz": 2, "ch": 2, "crx": 2, "cry": 2, "crz": 2, "cp": 2, "cu3": 2,
    "rxx": 2, "ryy": 2, "rzz": 2, "ecr": 2, "swap": 4, "iswap": 4,
}

# Decompositions of three-qubit gates (qelib1.inc definitions). Indices refer to the
# gate's own arguments (0, 1, 2).
DECOMPOSITIONS: dict[str, list[tuple[str, tuple[int, ...]]]] = {
    "ccx": [
        ("h", (2,)), ("cx", (1, 2)), ("tdg", (2,)), ("cx", (0, 2)), ("t", (2,)),
        ("cx", (1, 2)), ("tdg", (2,)), ("cx", (0, 2)), ("t", (1,)), ("t", (2,)),
        ("h", (2,)), ("cx", (0, 1)), ("t", (0,)), ("tdg", (1,)), ("cx", (0, 1)),
    ],
}
DECOMPOSITIONS["ccz"] = [("h", (2,)), *DECOMPOSITIONS["ccx"], ("h", (2,))]
DECOMPOSITIONS["cswap"] = [("cx", (2, 1)), *DECOMPOSITIONS["ccx"], ("cx", (2, 1))]

I2 = np.eye(2, dtype=np.complex128)
X = np.array([[0, 1], [1, 0]], dtype=np.complex128)
Y = np.array([[0, -1j], [1j, 0]], dtype=np.complex128)
Z = np.array([[1, 0], [0, -1]], dtype=np.complex128)
H = np.array([[1, 1], [1, -1]], dtype=np.complex128) / math.sqrt(2)
PAULIS = {"I": I2, "X": X, "Y": Y, "Z": Z}


def canonical_name(name: str) -> str:
    """Map aliases (CX, cnot, u1, ...) to the canonical lower-case gate name."""
    if name in ALIASES:
        return ALIASES[name]
    low = name.lower()
    return ALIASES.get(low, low)


def is_supported(name: str) -> bool:
    return canonical_name(name) in GATE_SPECS


def _u3(theta: float, phi: float, lam: float) -> np.ndarray:
    c, s = math.cos(theta / 2), math.sin(theta / 2)
    return np.array(
        [[c, -np.exp(1j * lam) * s], [np.exp(1j * phi) * s, np.exp(1j * (phi + lam)) * c]],
        dtype=np.complex128,
    )


def _controlled(u: np.ndarray) -> np.ndarray:
    m = np.eye(4, dtype=np.complex128)
    m[2:, 2:] = u
    return m


def _one_qubit(name: str, p: tuple[float, ...]) -> np.ndarray:
    if name == "id":
        return I2.copy()
    if name == "x":
        return X.copy()
    if name == "y":
        return Y.copy()
    if name == "z":
        return Z.copy()
    if name == "h":
        return H.copy()
    if name == "s":
        return np.diag([1, 1j]).astype(np.complex128)
    if name == "sdg":
        return np.diag([1, -1j]).astype(np.complex128)
    if name == "t":
        return np.diag([1, np.exp(1j * math.pi / 4)]).astype(np.complex128)
    if name == "tdg":
        return np.diag([1, np.exp(-1j * math.pi / 4)]).astype(np.complex128)
    if name == "sx":
        return 0.5 * np.array([[1 + 1j, 1 - 1j], [1 - 1j, 1 + 1j]], dtype=np.complex128)
    if name == "sxdg":
        return 0.5 * np.array([[1 - 1j, 1 + 1j], [1 + 1j, 1 - 1j]], dtype=np.complex128)
    if name == "rx":
        c, s = math.cos(p[0] / 2), math.sin(p[0] / 2)
        return np.array([[c, -1j * s], [-1j * s, c]], dtype=np.complex128)
    if name == "ry":
        c, s = math.cos(p[0] / 2), math.sin(p[0] / 2)
        return np.array([[c, -s], [s, c]], dtype=np.complex128)
    if name == "rz":
        return np.diag([np.exp(-0.5j * p[0]), np.exp(0.5j * p[0])]).astype(np.complex128)
    if name == "p":
        return np.diag([1, np.exp(1j * p[0])]).astype(np.complex128)
    if name == "u2":
        return _u3(math.pi / 2, p[0], p[1])
    if name == "u3":
        return _u3(p[0], p[1], p[2])
    raise KeyError(name)


def _two_qubit(name: str, p: tuple[float, ...]) -> np.ndarray:
    if name == "cx":
        return _controlled(X)
    if name == "cy":
        return _controlled(Y)
    if name == "cz":
        return _controlled(Z)
    if name == "ch":
        return _controlled(H)
    if name in ("crx", "cry", "crz"):
        return _controlled(_one_qubit(name[1:], p))
    if name == "cp":
        return np.diag([1, 1, 1, np.exp(1j * p[0])]).astype(np.complex128)
    if name == "cu3":
        return _controlled(_u3(*p))
    if name == "swap":
        return np.array([[1, 0, 0, 0], [0, 0, 1, 0], [0, 1, 0, 0], [0, 0, 0, 1]], dtype=np.complex128)
    if name == "iswap":
        return np.array([[1, 0, 0, 0], [0, 0, 1j, 0], [0, 1j, 0, 0], [0, 0, 0, 1]], dtype=np.complex128)
    if name == "ecr":
        return np.array(
            [[0, 1, 0, 1j], [1, 0, -1j, 0], [0, 1j, 0, 1], [-1j, 0, 1, 0]], dtype=np.complex128
        ) / math.sqrt(2)
    if name in ("rxx", "ryy", "rzz"):
        pauli = {"rxx": X, "ryy": Y, "rzz": Z}[name]
        pp = np.kron(pauli, pauli)
        return math.cos(p[0] / 2) * np.eye(4, dtype=np.complex128) - 1j * math.sin(p[0] / 2) * pp
    raise KeyError(name)


@lru_cache(maxsize=4096)
def _matrix_cached(name: str, params: tuple[float, ...]) -> np.ndarray:
    arity = GATE_SPECS[name][0]
    m = _one_qubit(name, params) if arity == 1 else _two_qubit(name, params)
    m.setflags(write=False)
    return m


def gate_matrix(name: str, params: tuple[float, ...] = ()) -> np.ndarray:
    """Unitary matrix (2x2 or 4x4) for a canonical 1- or 2-qubit gate."""
    name = canonical_name(name)
    return _matrix_cached(name, tuple(float(x) for x in params))


def flip_two_qubit(u: np.ndarray) -> np.ndarray:
    """Re-express a 4x4 gate with its two qubits exchanged."""
    return u.reshape(2, 2, 2, 2).transpose(1, 0, 3, 2).reshape(4, 4)
