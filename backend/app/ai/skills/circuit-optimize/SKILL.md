---
name: circuit-optimize
description: Propose an equivalent rewrite of a quantum circuit that uses fewer noisy gates. Use inside the debug agent loop; every proposal is verified by simulation before it is accepted.
---

# Circuit optimisation (semantics-preserving)

Goal: produce a circuit that prepares **the same quantum state** (global phase allowed) with fewer
two-qubit gates, lower depth, or fewer long-range interactions.

Safe rewrite rules:
- Cancel adjacent inverse pairs: H H, X X, CX CX (same control/target), S Sdg, T Tdg, SWAP SWAP.
- Merge consecutive rotations about the same axis on the same qubit; drop zero-angle rotations.
- Commute single-qubit Z-rotations through CX controls, and X-rotations through CX targets, to expose cancellations.
- A CX ladder that prepares a GHZ state can be rearranged, but the final state must be identical.

Hard constraints:
- Same number of qubits and the same `measure` mapping (qubit -> classical bit).
- Use only standard qelib1.inc gates. No mid-circuit measurement, no classical control.
- If you are not confident a rewrite is equivalent, return `"rewritten_qasm": null`.

Output JSON: `{"diagnosis": str, "rationale": str, "rewritten_qasm": str|null}`.
The simulator will reject any rewrite whose ideal state overlap with the original is below 0.999.
