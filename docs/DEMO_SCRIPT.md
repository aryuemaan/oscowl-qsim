# 2-minute demo script

**Setup before you start:** backend and frontend running (`bash scripts/dev.sh`), browser at
http://localhost:5173 (or your Cloud Run URL), default example **Ansatz with leftovers (8q)**
loaded, and the NISQ noise preset selected. With a Gemini key the pills show the model names;
without one the demo still works in offline mode.

---

**0:00 – 0:15 · Hook**
> "Every run on a real quantum computer costs money and queue time, and many runs fail because of
> noise nobody can see. OSCOWL Q-Sim lets you find and fix those failures on classical cloud
> hardware first."

**0:15 – 0:40 · Simulate and see where fidelity goes**
- Click **Run simulation**. Point at the pipeline: *Validate → Gemma pre-check → Simulate*.
- Overview: "State fidelity is only about 40–60%, and here is the honest error bar."
- Open **Noise impact**: "Two-qubit gates cause most of the error. These are the exact lines."
  Click a hotspot; the editor jumps to the line.

**0:40 – 1:10 · The debug agent**
- Click **Run debug agent**. Walk down the timeline:
  > "It diagnoses, proposes fixes, and accepts only what simulation proves: the new circuit is
  > equivalent, with overlap 1.000000, and better. Twelve redundant gates are gone, two-qubit gates
  > drop from 20 to 14, and fidelity goes up. It also rejected a fix that didn't help. Gemini
  > proposes; physics decides."
- Click **Load fixed circuit into editor**.

**1:10 – 1:35 · Scale with tensor networks**
- Choose **GHZ state (100q)** → Run → **Tensor network** tab.
  > "100 qubits. A dense simulator would need 2×10³¹ bytes. We use about 12 kilobytes at bond
  > dimension 2, and the result is exact. We say clearly that this works for structured circuits;
  > the error bound is always shown."
- Open the **Benchmarks** tab:
  > "At 24 qubits, the dense simulator takes about 40 seconds and 768 MB. Our MPS takes about 50
  > milliseconds and under 1 MB, with identical results."

**1:35 – 2:00 · Google stack and close**
- Open the **AI stack** tab:
  > "Gemma 4 pre-checks, Gemini 3.8 Flash explains, Gemini 4 Argon proposes rewrites, and Agent
  > Skills package our quantum know-how. It ships as one container on Cloud Run, and heavy jobs go to
  > GKE GPUs and TPUs through JAX."
- Close: **"Debug the quantum future on today's hardware. Thank you."**

---

**Backup plan:** if Wi-Fi or the API key fails, set `QSIM_AI_MODE=offline` and restart. Every step
above still works with the rule-based fallbacks, and the timeline labels them as "rules".
