# Python SDK (single file)

Copy `oscowl_client.py` next to your notebook or script. No extra packages needed.

```python
from oscowl_client import QSim
qs = QSim("http://localhost:8000")
r = qs.simulate(open("my_circuit.qasm").read(), noise={"p2": 0.02, "readout": 0.03}, shots=2048)
print(r["fidelity"], r["budget"]["dominant_source"])
fix = qs.debug(open("my_circuit.qasm").read(), noise={"p2": 0.02})
print(fix["explanation"]["text"])
```

With Qiskit (`pip install qiskit`), pass a `QuantumCircuit` directly; bind any parameters first.
Run `python oscowl_client.py` with the backend running for a quick smoke test.
