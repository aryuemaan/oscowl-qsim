from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
NOISE = {"p1": 0.002, "p2": 0.02, "amplitude_damping": 0.005, "readout_p01": 0.03, "readout_p10": 0.03}


def test_health_and_examples():
    h = client.get("/api/health").json()
    assert h["status"] == "ok" and h["ai"]["mode"] == "offline"
    ex = client.get("/api/examples").json()
    assert {"ghz_100", "ansatz_redundant_8", "broken"} <= {e["id"] for e in ex}
    assert len(client.get("/api/skills").json()) == 4


def test_validate_reports_errors_with_lines():
    broken = next(e for e in client.get("/api/examples").json() if e["id"] == "broken")
    r = client.post("/api/validate", json={"qasm": broken["qasm"]}).json()
    assert r["ok"] is False
    assert {i["line"] for i in r["issues"] if i["severity"] == "error"} == {7, 8, 9}


def test_simulate_and_explain():
    bell = next(e for e in client.get("/api/examples").json() if e["id"] == "bell")
    sim = client.post("/api/simulate", json={"qasm": bell["qasm"], "noise": NOISE, "options": {"shots": 500, "seed": 1}})
    assert sim.status_code == 200
    body = sim.json()
    assert body["backend"] == "statevector" and 0 < body["fidelity"]["state"] <= 1
    exp = client.post("/api/explain", json={"qasm": bell["qasm"], "noise": NOISE, "simulation": body}).json()
    assert exp["intent"] == "Bell state" and exp["source"] == "offline"


def test_simulate_rejects_bad_circuit_and_limits():
    r = client.post("/api/simulate", json={"qasm": "qreg q[2]; hadamard q[0];"})
    assert r.status_code == 422 and r.json()["detail"]["issues"]
    r = client.post("/api/simulate", json={"qasm": "qreg q[30]; h q;", "options": {"backend": "statevector"}})
    assert r.status_code == 400


def test_agent_endpoint():
    src = next(e for e in client.get("/api/examples").json() if e["id"] == "ansatz_redundant_8")["qasm"]
    r = client.post("/api/agent/debug", json={"qasm": src, "noise": NOISE, "options": {"shots": 256, "trajectories": 16, "seed": 3}})
    assert r.status_code == 200 and r.json()["changed"] is True
