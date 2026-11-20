"""Minimal Python client for the OSCOWL Q-Sim API (no dependencies beyond the standard library).

    from oscowl_client import QSim
    qs = QSim("http://localhost:8000")          # or your Cloud Run URL
    result = qs.simulate(qasm_text, noise={"p2": 0.02, "readout": 0.03})
    print(result["fidelity"])

Qiskit users: pass a QuantumCircuit directly; it is converted with qiskit.qasm2.dumps.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any


def to_qasm(circuit: Any) -> str:
    """Accept QASM text or a Qiskit QuantumCircuit (bind parameters first)."""
    if isinstance(circuit, str):
        return circuit
    try:
        from qiskit import qasm2
    except ImportError as exc:  # pragma: no cover
        raise TypeError("Pass OpenQASM text, or install qiskit to pass a QuantumCircuit") from exc
    return qasm2.dumps(circuit)


def _noise(noise: dict | None) -> dict:
    n = dict(noise or {})
    if "readout" in n:
        r = n.pop("readout")
        n.setdefault("readout_p01", r)
        n.setdefault("readout_p10", r)
    return n


class QSim:
    def __init__(self, base_url: str = "http://localhost:8000", timeout: float = 300):
        self.base = base_url.rstrip("/")
        self.timeout = timeout

    def _call(self, path: str, body: dict | None = None) -> Any:
        req = urllib.request.Request(
            f"{self.base}/api{path}",
            data=None if body is None else json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
            method="GET" if body is None else "POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as err:
            raise RuntimeError(f"{err.code}: {err.read().decode(errors='replace')}") from None

    def health(self) -> dict:
        return self._call("/health")

    def validate(self, circuit: Any, use_ai: bool = False) -> dict:
        return self._call("/validate", {"qasm": to_qasm(circuit), "use_ai": use_ai})

    def simulate(self, circuit: Any, noise: dict | None = None, **options: Any) -> dict:
        return self._call("/simulate", {"qasm": to_qasm(circuit), "noise": _noise(noise), "options": options})

    def explain(self, circuit: Any, noise: dict | None = None, **options: Any) -> dict:
        return self._call("/explain", {"qasm": to_qasm(circuit), "noise": _noise(noise), "options": options})

    def debug(self, circuit: Any, noise: dict | None = None, **options: Any) -> dict:
        return self._call("/agent/debug", {"qasm": to_qasm(circuit), "noise": _noise(noise), "options": options})


if __name__ == "__main__":
    qs = QSim()
    bell = 'OPENQASM 2.0; include "qelib1.inc"; qreg q[2]; creg c[2]; h q[0]; cx q[0],q[1]; measure q -> c;'
    r = qs.simulate(bell, noise={"p2": 0.02, "readout": 0.02}, shots=1000, seed=1)
    print("backend:", r["backend"], "| state fidelity:", round(r["fidelity"]["state"], 3))
    print("counts:", r["counts"])
