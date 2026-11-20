"""Plain-English explanation of a simulation: Gemini Flash when online, rules when offline."""
from __future__ import annotations

import json
import math

from ..quantum.circuit import Circuit
from .llm import AIClient
from .skills import skill_prompt


# ------------------------------------------------------------------ intent detection
def detect_intent(c: Circuit) -> tuple[str, str]:
    names = c.gate_counts()
    n = c.num_qubits
    only = set(names)
    cx_chain = all(g.name == "cx" for g in c.gates[1:]) and c.gates[:1] and c.gates[0].name == "h"
    if cx_chain and len(c.gates) == n:
        if n == 2:
            return "Bell state", "prepares a Bell pair, the simplest entangled state of two qubits"
        return "GHZ state", f"prepares a {n}-qubit GHZ state: all qubits 0 or all 1 with equal probability"
    if "cp" in only and names.get("h", 0) >= n:
        return "QFT-based", "applies a quantum Fourier transform (Hadamards plus controlled phase rotations)"
    if names.get("t", 0) + names.get("tdg", 0) >= 7 and names.get("h", 0) >= n:
        return "Grover / oracle circuit", "looks like amplitude amplification: Hadamard layers around Toffoli-based oracles"
    rot = sum(names.get(k, 0) for k in ("rx", "ry", "rz", "u3"))
    if rot >= n and names.get("cx", 0) + names.get("cz", 0) >= n - 1:
        return "Variational ansatz", "is a parameterised (variational) ansatz: rotation layers with entangling CX layers"
    return "General circuit", f"is a general {n}-qubit circuit with {len(c.gates)} gates"


def _pct(x: float) -> str:
    return f"{100 * x:.0f}%" if x >= 0.095 else f"{100 * x:.1f}%"


def _lines(hotspots: list[dict], k: int = 4) -> str:
    ls = sorted({h["line"] for h in hotspots if h.get("line")})[:k]
    return ", ".join(str(x) for x in ls)


# ------------------------------------------------------------------ offline explanation
def offline_explanation(c: Circuit, sim: dict) -> dict:
    label, sentence = detect_intent(c)
    st, f, b = sim["circuit"], sim["fidelity"], sim["budget"]
    sources = b["by_source"]
    findings, suggestions = [], []
    hell = f.get("hellinger")
    quality = "barely affected by" if f["state"] > 0.95 else "noticeably affected by" if f["state"] > 0.7 else "heavily degraded by"
    summary = (f"This circuit {sentence}. With the selected noise it is {quality} errors: "
               f"simulated state fidelity is about {_pct(f['state'])}.")
    if not sources:
        expl = "No noise is configured, so the result is the ideal output of the circuit."
    else:
        top = sources[0]
        expl = (f"The dominant error source is {top['source']}, about {_pct(top['share'])} of the estimated error budget. ")
        if b["by_gate_type"]:
            gt = b["by_gate_type"][0]
            expl += (f"{gt['gate'].upper()} gates ({gt['count']} of them) cost the most, {_pct(gt['share'])} of the budget")
            ln = _lines(b["hotspots"])
            expl += f", with the worst hotspots at lines {ln}. " if ln else ". "
        if any(s["source"] == "readout" and s["share"] > 0.15 for s in sources):
            expl += "Readout errors are a large share, so post-processing mitigation can recover part of the signal. "
        expl += (f"The first-order estimate of success probability is {_pct(f['esp'])}; the trajectory simulation, "
                 "which includes interference between errors, gives the state fidelity above.")
    findings.append(f"{st['num_qubits']} qubits, {st['num_gates']} gates ({st['two_qubit_gates']} two-qubit), depth {st['depth']}")
    findings.append(f"State fidelity {f['state']:.3f} +/- {f['state_stderr']:.3f}; estimated success probability {f['esp']:.3f}")
    if hell is not None:
        findings.append(f"Output-distribution (Hellinger) fidelity {hell:.3f}")
    plan = sim["plan"]
    if sim["backend"] == "mps":
        dense = sim["memory"]["dense_equivalent_bytes"]
        findings.append(f"Tensor-network run used {_bytes(sim['memory']['used_bytes'])} instead of {_bytes(dense)} for a dense state; "
                        f"max bond dimension {sim['tensor_network']['max_bond_used']}")
    if f["truncation"] < 0.999:
        findings.append(f"Truncation fidelity {f['truncation']:.4f}: results are approximate")
        suggestions.append(f"Raise the max bond dimension above {plan['max_bond']} to reduce truncation error.")
    two_q_share = sum(s["share"] for s in sources if s["source"] == "2q depolarizing")
    if st["two_qubit_gates"] and two_q_share > 0.4:
        suggestions.append(f"Two-qubit gates drive {_pct(two_q_share)} of the error: run the debug agent to remove redundant CX/SWAP gates.")
    if st["long_range_gates"]:
        suggestions.append(f"{st['long_range_gates']} long-range two-qubit gates add routing SWAPs; re-map qubits so interacting pairs are neighbours.")
    concentrated = sim["num_outcomes"] <= 0.25 * max(sim["shots"], 1)
    if concentrated and any(s["source"] == "readout" and s["share"] > 0.15 for s in sources):
        suggestions.append("Enable readout-error mitigation (the agent verifies the gain on the output distribution).")
    if any(s["source"] == "amplitude damping" and s["share"] > 0.25 for s in sources):
        suggestions.append("Amplitude damping is significant: shorten depth so qubits spend less time excited.")
    if not suggestions:
        suggestions.append("The circuit is already efficient for this noise level; try a noisier preset to stress-test it.")
    return {"source": "offline", "model": "rules", "summary": summary, "intent": label,
            "noise_explanation": expl.strip(), "key_findings": findings, "suggestions": suggestions[:4]}


def _bytes(x: float) -> str:
    units = ["B", "KiB", "MiB", "GiB", "TiB", "PiB", "EiB"]
    if x < 1024:
        return f"{x:.0f} B"
    k = min(int(math.log(x, 1024)), len(units) - 1)
    if k == len(units) - 1 and x / 1024**k > 1e4:
        return f"{x:.1e} bytes"
    return f"{x / 1024**k:,.1f} {units[k]}"


# ------------------------------------------------------------------ Gemini explanation
def _facts(c: Circuit, sim: dict, qasm: str) -> str:
    facts = {
        "circuit": sim["circuit"], "noise": sim["noise"], "backend": sim["backend"], "plan": sim["plan"],
        "fidelity": sim["fidelity"], "error_budget_by_source": sim["budget"]["by_source"],
        "error_budget_by_gate_type": sim["budget"]["by_gate_type"][:6],
        "hotspots": [{k: h[k] for k in ("label", "line", "share")} for h in sim["budget"]["hotspots"][:8]],
        "tensor_network": {k: sim["tensor_network"].get(k) for k in ("max_bond_used", "truncations")},
        "memory": sim["memory"], "warnings": sim["warnings"],
        "top_outcomes": sim["outcomes"][:6],
    }
    head = "\n".join(qasm.strip().splitlines()[:80])
    return f"Simulation facts (JSON):\n{json.dumps(facts, default=float)}\n\nCircuit (first 80 lines):\n```qasm\n{head}\n```"


def explain(c: Circuit, sim: dict, qasm: str, ai: AIClient) -> dict:
    fallback = offline_explanation(c, sim)
    if not ai.online:
        return {**fallback, "latency_ms": 0.0, "note": "Offline mode: set GEMINI_API_KEY for Gemini explanations."}
    system = "You are Q-Sim's noise analyst.\n\n" + skill_prompt("noise-explain")
    data, meta = ai.generate_json(model=ai.s.gemini_flash_model, system=system, prompt=_facts(c, sim, qasm))
    if not data:
        return {**fallback, "latency_ms": meta["latency_ms"], "note": f"Gemini unavailable ({meta['error']}); showing rule-based explanation."}
    def _list(v):
        return [str(x) for x in v][:5] if isinstance(v, list) else fallback["key_findings"]
    return {
        "source": "gemini", "model": meta["model"], "latency_ms": meta["latency_ms"], "cached": meta["cached"],
        "summary": str(data.get("summary") or fallback["summary"]),
        "intent": str(data.get("intent") or fallback["intent"]),
        "noise_explanation": str(data.get("noise_explanation") or fallback["noise_explanation"]),
        "key_findings": _list(data.get("key_findings")),
        "suggestions": _list(data.get("suggestions")) if data.get("suggestions") else fallback["suggestions"],
    }
