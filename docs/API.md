# REST API

Interactive documentation is at **http://localhost:8000/api/docs** while the backend is running.
All bodies are JSON. Probabilities are 0–1.

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Version, AI mode, models, limits |
| GET | `/api/examples` | Demo circuits (with QASM and suggested noise) |
| GET | `/api/noise-presets` | ideal / low / nisq / harsh |
| GET | `/api/skills` | Agent Skills catalog |
| POST | `/api/validate` | `{qasm, use_ai}` returns issues (with line numbers), stats and plan |
| POST | `/api/simulate` | `{qasm, noise, options}` returns the full simulation result |
| POST | `/api/explain` | `{qasm, noise, options, simulation?}` returns a plain-English explanation |
| POST | `/api/agent/debug` | `{qasm, noise, options}` returns the agent trace, verified fixes and fixed QASM |
| GET | `/api/benchmarks/latest` | Latest benchmark results |

### Noise object
```json
{"p1": 0.002, "p2": 0.02, "amplitude_damping": 0.005, "readout_p01": 0.03, "readout_p10": 0.03}
```

### Options object
```json
{"shots": 1024, "trajectories": 32, "backend": "auto", "max_bond": 64, "seed": 7}
```
`backend` is `auto` (planner), `statevector` or `mps`.

### Example (Git Bash)
```bash
curl -s localhost:8000/api/simulate -H "Content-Type: application/json" -d '{
  "qasm": "OPENQASM 2.0; include \"qelib1.inc\"; qreg q[2]; creg c[2]; h q[0]; cx q[0],q[1]; measure q -> c;",
  "noise": {"p2": 0.02, "readout_p01": 0.02, "readout_p10": 0.02},
  "options": {"shots": 1000, "seed": 1}
}'
```

### Key result fields (`/api/simulate`)
- `fidelity.state` / `state_stderr`: trajectory estimate of ⟨ψ_ideal|ρ|ψ_ideal⟩
- `fidelity.hellinger`: output-distribution fidelity against exact ideal probabilities (`null` if outcomes are too spread)
- `fidelity.esp`: first-order estimated success probability; `fidelity.truncation`: MPS truncation fidelity (1 = exact)
- `budget.by_source`, `by_gate_type`, `by_qubit`, `hotspots[]` (with `line`)
- `outcomes[]` (top outcomes with noisy and ideal probability), `counts`, `ideal_counts` (Qiskit bit order)
- `tensor_network.bond_dims`, `entropies`, `max_bond_used`; `memory.used_bytes` vs `dense_equivalent_bytes`
- `plan.backend`, `plan.reason`, `plan.hardware`

Errors: `422` with `detail.issues[]` for circuits with errors; `400` for limits (for example, too many qubits for the dense backend).
