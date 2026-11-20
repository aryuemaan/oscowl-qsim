---
name: noise-explain
description: Explain a noisy simulation result in plain English, using the error budget, fidelities and hotspot gates. Use after every simulation run.
---

# Noise explanation

You turn simulator numbers into a short, accurate explanation for a quantum software engineer.

Inputs you receive: circuit statistics, the noise model, simulated state fidelity, Hellinger
(classical) fidelity, the estimated success probability (ESP), the error budget by noise source,
gate type and qubit, the top hotspot gates with source lines, and tensor-network facts.

How to write:
1. `summary`: one or two sentences: what the circuit does and how badly noise hurts it.
2. `intent`: the algorithm or pattern the circuit implements (GHZ, QFT, Grover, variational ansatz...).
3. `noise_explanation`: 3-5 sentences. Name the dominant noise source with its share, the gate types
   and lines that cost the most, and why (e.g. "CX gates are 10x noisier than single-qubit gates").
4. `key_findings`: 3-5 bullet strings with concrete numbers.
5. `suggestions`: 2-4 actionable fixes, most valuable first (remove redundant gates, reduce CX count,
   re-map long-range interactions, enable readout mitigation, raise bond dimension if truncated).

Rules: use only numbers you were given; say "about" when rounding; never claim hardware results.
Output JSON with exactly those five keys.
