---
name: resource-sizing
description: Choose the simulation backend, MPS bond dimension and Google Cloud hardware for a circuit. Use before launching a large or batch simulation.
---

# Resource sizing

Decision rules used by Q-Sim's planner (`app/quantum/planner.py`):

| Situation | Backend | Hardware |
|---|---|---|
| n <= 16 qubits | dense state vector (exact) | Cloud Run CPU |
| n > 16, predicted bond dimension <= cap | MPS, exact | Cloud Run CPU |
| predicted bond > cap, cap <= 128 | MPS, truncated with error bound | Cloud Run CPU |
| cap 129-512 | MPS | GKE GPU node (NVIDIA L4) with `ARRAY_BACKEND=jax` |
| cap > 512 or many noise trajectories | MPS batch job | GKE TPU / large GPU node |

Bond-dimension bound per cut = product of operator Schmidt ranks of the two-qubit gates crossing it
(2 for CX-like gates, 4 for SWAP), capped at 2^min(left, right).
Memory per MPS ~ 32 * n * chi^2 bytes. Dense memory = 16 * 2^n bytes.
Always report the truncation fidelity: when it is below 0.999, recommend a larger cap.
