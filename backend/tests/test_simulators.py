import numpy as np
import pytest

from app.quantum import NoiseModel, SimOptions, load_qasm, simulate
from app.quantum.mps import MPS
from app.quantum.simulator import compile_ops, run_ops
from app.quantum.statevector import StateVector


def random_qasm(n: int, gates: int, rng) -> str:
    one = ["h", "x", "s", "t", "sx"]
    lines = ['OPENQASM 2.0;', 'include "qelib1.inc";', f"qreg q[{n}];", f"creg c[{n}];"]
    for _ in range(gates):
        if rng.random() < 0.5:
            lines.append(f"{one[rng.integers(5)]} q[{rng.integers(n)}];")
            lines.append(f"ry({rng.uniform(-3, 3):.6f}) q[{rng.integers(n)}];")
        else:
            a, b = rng.choice(n, 2, replace=False)
            lines.append(f"cx q[{a}],q[{b}];" if rng.random() < 0.6 else f"rzz({rng.uniform(-3, 3):.6f}) q[{a}],q[{b}];")
    lines.append("measure q -> c;")
    return "\n".join(lines)


def mps_vector(m: MPS) -> np.ndarray:
    v = np.asarray(m.tensors[0])
    for t in m.tensors[1:]:
        v = np.einsum("...a,asb->...sb", v, np.asarray(t))
    return v.reshape(-1)


@pytest.mark.parametrize("seed", range(6))
def test_mps_matches_statevector(seed):
    rng = np.random.default_rng(seed)
    c = load_qasm(random_qasm(int(rng.integers(3, 8)), 30, rng))
    ops = compile_ops(c)
    sv, mp = StateVector(c.num_qubits), MPS(c.num_qubits, max_bond=256)
    run_ops(sv, ops)
    run_ops(mp, ops)
    assert abs(np.vdot(sv.psi.reshape(-1), mps_vector(mp))) == pytest.approx(1.0, abs=1e-9)
    assert mp.truncation_fidelity == 1.0


def test_truncation_is_reported():
    rng = np.random.default_rng(3)
    c = load_qasm(random_qasm(10, 120, rng))
    mp = MPS(c.num_qubits, max_bond=4)
    run_ops(mp, compile_ops(c))
    assert mp.truncations > 0 and 0 < mp.truncation_fidelity < 1


def test_ghz_100_is_exact_and_small():
    lines = ['OPENQASM 2.0;', 'include "qelib1.inc";', "qreg q[100];", "creg c[100];", "h q[0];"]
    lines += [f"cx q[{i}],q[{i + 1}];" for i in range(99)] + ["measure q -> c;"]
    r = simulate(load_qasm("\n".join(lines)), NoiseModel(), SimOptions(shots=500, seed=1)).result
    assert r["backend"] == "mps"
    assert r["tensor_network"]["max_bond_used"] == 2
    assert r["fidelity"]["truncation"] == 1.0
    assert set(r["counts"]) == {"0" * 100, "1" * 100}
    assert r["memory"]["used_bytes"] < 1_000_000


def test_grover_success_probability():
    src = open("app/examples/grover_3.qasm").read()
    r = simulate(load_qasm(src), NoiseModel(), SimOptions(shots=1000, seed=1)).result
    top = r["outcomes"][0]
    assert top["bitstring"] == "101" and top["ideal"] == pytest.approx(0.78125, abs=1e-9)


def test_depolarizing_matches_theory():
    c = load_qasm('OPENQASM 2.0; include "qelib1.inc"; qreg q[1]; creg c[1]; x q[0]; measure q -> c;')
    r = simulate(c, NoiseModel(p1=0.3), SimOptions(shots=3000, trajectories=3000, seed=11)).result
    assert r["fidelity"]["state"] == pytest.approx(1 - 2 * 0.3 / 3, abs=0.03)


def test_readout_error_rate():
    c = load_qasm('OPENQASM 2.0; include "qelib1.inc"; qreg q[1]; creg c[1]; x q[0]; measure q -> c;')
    r = simulate(c, NoiseModel(readout_p10=0.1), SimOptions(shots=20000, seed=5)).result
    assert r["counts"].get("0", 0) / 20000 == pytest.approx(0.1, abs=0.01)


def test_budget_shares_sum_to_one():
    src = open("app/examples/ansatz_redundant_8.qasm").read()
    r = simulate(load_qasm(src), NoiseModel(p1=0.002, p2=0.02, amplitude_damping=0.005, readout_p01=0.03, readout_p10=0.03),
                 SimOptions(shots=256, seed=2)).result
    assert sum(s["share"] for s in r["budget"]["by_source"]) == pytest.approx(1.0)
    assert r["budget"]["dominant_source"] == "2q depolarizing"
    assert r["budget"]["hotspots"][0]["line"] is not None
