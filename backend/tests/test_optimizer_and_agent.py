import pytest

from app.ai.agent import run_debug_agent
from app.ai.llm import AIClient
from app.config import Settings
from app.quantum import NoiseModel, SimOptions, load_qasm, simulate, state_overlap
from app.quantum.mitigation import hellinger_fidelity, mitigate_readout
from app.quantum.optimizer import simplify

NISQ = NoiseModel(p1=0.002, p2=0.02, amplitude_damping=0.005, readout_p01=0.03, readout_p10=0.03)


def test_cascading_cancellation():
    c = load_qasm('OPENQASM 2.0; include "qelib1.inc"; qreg q[2]; h q[0]; x q[0]; cx q[0],q[1]; cx q[0],q[1]; x q[0]; h q[0]; rz(0.2) q[1]; rz(-0.2) q[1];')
    new, changes = simplify(c)
    assert new.gates == [] and len(changes) == 4


def test_simplify_preserves_state():
    src = open("app/examples/qft_roundtrip_6.qasm").read()
    c = load_qasm(src)
    new, _ = simplify(c)
    a, b = simulate(c, NoiseModel(), SimOptions(seed=1)), simulate(new, NoiseModel(), SimOptions(seed=1))
    assert state_overlap(a.ideal_state, b.ideal_state) == pytest.approx(1.0, abs=1e-9)
    assert len(new.gates) < len(c.gates) // 5


def test_readout_mitigation_improves_fidelity():
    src = open("app/examples/ghz_12.qasm").read()
    noise = NoiseModel(readout_p01=0.04, readout_p10=0.04)
    run = simulate(load_qasm(src), noise, SimOptions(shots=4000, seed=3))
    ideal = {"0" * 12: 0.5, "1" * 12: 0.5}
    counts = run.result["counts"]
    raw = hellinger_fidelity({k: v / 4000 for k, v in counts.items()}, ideal, normalize_q=False)
    mit = mitigate_readout(counts, 0.04, 0.04)
    assert hellinger_fidelity(mit, ideal, normalize_q=False) > raw + 0.1


def test_agent_offline_finds_and_verifies_fix():
    settings = Settings(qsim_ai_mode="offline", gemini_api_key="")
    src = open("app/examples/ansatz_redundant_8.qasm").read()
    out = run_debug_agent(src, NISQ, SimOptions(shots=512, trajectories=32, seed=7), settings, AIClient(settings))
    assert out["ok"] and out["changed"]
    assert out["accepted"][0]["title"] == "Remove redundant gates"
    assert out["after"]["two_qubit_gates"] < out["before"]["two_qubit_gates"]
    assert out["after"]["esp"] > out["before"]["esp"]
    assert load_qasm(out["final_qasm"]).num_qubits == 8
    phases = [s["phase"] for s in out["steps"]]
    assert phases[0] == "validate" and "verify" in phases and phases[-1] == "explain"


def test_agent_reports_validation_errors():
    settings = Settings(qsim_ai_mode="offline", gemini_api_key="")
    out = run_debug_agent(open("app/examples/broken.qasm").read(), NISQ, SimOptions(), settings, AIClient(settings))
    assert not out["ok"] and out["steps"][0]["status"] == "error"
