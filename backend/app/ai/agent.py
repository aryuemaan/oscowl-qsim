"""The Q-Sim debug agent: diagnose -> propose -> verify by simulation -> accept or reject -> explain.

Proposals come from two places:
  1. deterministic rewrites (``quantum.optimizer.simplify``) and readout mitigation, always available;
  2. Gemini (reasoning model) when online: an equivalent rewrite of the circuit.

Nothing is accepted on trust. Every circuit change must (a) prepare the same ideal
state (overlap >= 0.999) and (b) improve the estimated success probability without
lowering the simulated fidelity beyond statistical noise. Readout mitigation must
improve the output-distribution fidelity against exact ideal probabilities.
"""
from __future__ import annotations

import math
import time

from ..config import Settings
from ..quantum.circuit import Circuit
from ..quantum.mitigation import hellinger_fidelity, mitigate_readout
from ..quantum.noise import NoiseModel
from ..quantum.optimizer import simplification_summary, simplify
from ..quantum.qasm_parser import parse_qasm
from ..quantum.simulator import SimOptions, SimulationRun, ideal_probabilities, simulate, state_overlap
from .explainer import offline_explanation
from .llm import AIClient
from .skills import skill_prompt
from .validator import validate

EQUIV_TOL = 1e-3


class Trace:
    def __init__(self) -> None:
        self.steps: list[dict] = []

    def add(self, phase: str, title: str, status: str, detail: str = "", metrics: dict | None = None,
            source: str = "simulator", t0: float | None = None) -> dict:
        step = {"id": len(self.steps) + 1, "phase": phase, "title": title, "status": status, "detail": detail,
                "metrics": metrics or {}, "source": source,
                "duration_ms": (time.perf_counter() - t0) * 1000 if t0 else 0.0}
        self.steps.append(step)
        return step


def _snapshot(run: SimulationRun) -> dict:
    f, c = run.result["fidelity"], run.circuit
    return {"state_fidelity": f["state"], "state_stderr": f["state_stderr"], "hellinger": f["hellinger"],
            "esp": f["esp"], "gates": len(c.gates), "two_qubit_gates": c.two_qubit_count(), "depth": c.depth()}


def _verify_circuit(base: SimulationRun, cand: Circuit, noise: NoiseModel, opts: SimOptions) -> tuple[bool, str, SimulationRun | None, dict]:
    if cand.num_qubits != base.circuit.num_qubits:
        return False, "Rejected: the rewrite changes the number of qubits.", None, {}
    if cand.effective_measurements()[0] != base.circuit.effective_measurements()[0]:
        return False, "Rejected: the rewrite changes which qubits are measured into which bits.", None, {}
    run = simulate(cand, noise, opts)
    if run.plan.backend != base.plan.backend:
        return False, "Rejected: rewrite needs a different backend; cannot compare states.", None, {}
    overlap = state_overlap(base.ideal_state, run.ideal_state)
    before, after = _snapshot(base), _snapshot(run)
    metrics = {"ideal_overlap": overlap, "before": before, "after": after}
    if overlap < 1 - EQUIV_TOL:
        return False, f"Rejected: not equivalent (ideal-state overlap {overlap:.4f} < {1 - EQUIV_TOL}).", run, metrics
    noise_band = 2 * math.hypot(before["state_stderr"], after["state_stderr"])
    if after["esp"] <= before["esp"] + 1e-12:
        return False, "Rejected: equivalent, but it does not reduce the expected noise.", run, metrics
    if after["state_fidelity"] < before["state_fidelity"] - noise_band:
        return False, "Rejected: simulated fidelity got worse beyond statistical noise.", run, metrics
    gain = after["state_fidelity"] - before["state_fidelity"]
    return True, (f"Accepted: equivalent (overlap {overlap:.6f}); simulated fidelity {before['state_fidelity']:.3f} -> "
                  f"{after['state_fidelity']:.3f} ({gain:+.3f}), estimated success {before['esp']:.3f} -> {after['esp']:.3f}."), run, metrics


def _gemini_rewrite(qasm: str, run: SimulationRun, applied: list[str], ai: AIClient) -> tuple[dict | None, dict]:
    b = run.result["budget"]
    prompt = (
        "Debug this noisy quantum circuit and propose an equivalent rewrite with less noise exposure.\n"
        f"Noise model: {run.result['noise']}\n"
        f"Error budget by source: {[(s['source'], round(s['share'], 3)) for s in b['by_source']]}\n"
        f"Hotspots: {[(h['label'], h['line']) for h in b['hotspots'][:8]]}\n"
        f"Fixes already applied: {applied or 'none'}\n\n"
        f"```qasm\n{qasm}\n```"
    )
    system = "You are Q-Sim's circuit-debugging agent.\n\n" + skill_prompt("circuit-optimize")
    return ai.generate_json(model=ai.s.gemini_reasoning_model, system=system, prompt=prompt, thinking="medium", max_tokens=8192)


def run_debug_agent(qasm: str, noise: NoiseModel, opts: SimOptions, settings: Settings, ai: AIClient) -> dict:
    trace = Trace()
    t_all = time.perf_counter()

    # 1. validate ---------------------------------------------------------
    t0 = time.perf_counter()
    report = validate(qasm, settings, ai, use_ai=True)
    errors = [i for i in report["issues"] if i["severity"] == "error"]
    if errors:
        trace.add("validate", "Validation failed", "error", "; ".join(f"line {e['line']}: {e['message']}" for e in errors[:5]),
                  {"errors": len(errors)}, "parser", t0)
        return {"ok": False, "steps": trace.steps, "accepted": [], "rejected": [], "final_qasm": qasm, "changed": False,
                "before": None, "after": None, "explanation": None, "ai_mode": ai.mode}
    gemma_used = report["ai"].get("used")
    trace.add("validate", "Pre-check passed", "ok",
              (report["ai"].get("summary") or "No syntax errors.") +
              (f" Gemma pre-check ({report['ai'].get('model')})." if gemma_used else " Deterministic lint (Gemma off)."),
              {"warnings": sum(i["severity"] == "warning" for i in report["issues"]),
               "hints": sum(i["severity"] == "info" for i in report["issues"])},
              "gemma" if gemma_used else "rules", t0)
    circuit, _ = parse_qasm(qasm)
    assert circuit is not None

    # 2. diagnose ---------------------------------------------------------
    t0 = time.perf_counter()
    if opts.seed is None:
        opts.seed = 1234
    if circuit.num_qubits <= 16 and len(circuit.gates) <= 300:
        opts.trajectories = max(opts.trajectories, 96)  # tighter fidelity estimates for the before/after comparison
    base = simulate(circuit, noise, opts)
    start = base
    b = base.result["budget"]
    dom = b["by_source"][0] if b["by_source"] else None
    detail = (f"Simulated state fidelity {base.result['fidelity']['state']:.3f} on the {base.plan.backend} backend. "
              + (f"Dominant error source: {dom['source']} ({100 * dom['share']:.0f}% of the budget)." if dom else "No noise configured."))
    trace.add("diagnose", "Baseline simulation", "info", detail,
              {**_snapshot(base), "dominant_source": dom["source"] if dom else None}, "simulator", t0)

    # 3. propose + 4. verify ------------------------------------------------
    accepted: list[dict] = []
    rejected: list[dict] = []
    applied: list[str] = []

    t0 = time.perf_counter()
    simplified, changes = simplify(base.circuit)
    if changes:
        summ = simplification_summary(base.circuit, simplified)
        trace.add("propose", f"Remove {summ['gates_before'] - summ['gates_after']} redundant gates", "info",
                  "; ".join(c["description"] + (f" (lines {', '.join(str(x) for x in c['lines'] if x)})") for c in changes[:6])
                  + (f"; and {len(changes) - 6} more" if len(changes) > 6 else ""),
                  {**summ, "changes": len(changes)}, "rules", t0)
        t0 = time.perf_counter()
        ok, verdict, run, metrics = _verify_circuit(base, simplified, noise, opts)
        fix = {"kind": "circuit", "title": "Remove redundant gates", "source": "rules", "verdict": verdict, "metrics": metrics,
               "changes": changes}
        trace.add("verify", "Verify: remove redundant gates", "accepted" if ok else "rejected", verdict, metrics, "simulator", t0)
        if ok and run is not None:
            accepted.append(fix)
            applied.append("removed redundant gates")
            base = run
        else:
            rejected.append(fix)
    else:
        trace.add("propose", "No redundant gates found", "info", "Deterministic rewrite rules found nothing to remove.", {}, "rules", t0)

    if ai.online and base.circuit.num_qubits <= 40 and len(base.circuit.gates) <= 400:
        t0 = time.perf_counter()
        data, meta = _gemini_rewrite(base.circuit.to_qasm(), base, applied, ai)
        if data is None:
            trace.add("propose", "Gemini rewrite unavailable", "warn", meta.get("error") or "No answer", {}, "gemini", t0)
        elif not data.get("rewritten_qasm"):
            trace.add("propose", "Gemini: no safe rewrite", "info", str(data.get("diagnosis") or data.get("rationale") or "")[:600],
                      {"latency_ms": meta["latency_ms"]}, "gemini", t0)
        else:
            trace.add("propose", "Gemini proposes a rewrite", "info",
                      (str(data.get("diagnosis") or "") + " " + str(data.get("rationale") or ""))[:800],
                      {"model": meta["model"], "latency_ms": meta["latency_ms"]}, "gemini", t0)
            cand, issues = parse_qasm(str(data["rewritten_qasm"]))
            t0 = time.perf_counter()
            fix = {"kind": "circuit", "title": "Gemini rewrite", "source": "gemini", "rationale": data.get("rationale")}
            if cand is None:
                fix["verdict"] = "Rejected: the proposed QASM does not parse (" + "; ".join(i.message for i in issues[:2]) + ")."
                trace.add("verify", "Verify: Gemini rewrite", "rejected", fix["verdict"], {}, "simulator", t0)
                rejected.append(fix)
            else:
                ok, verdict, run, metrics = _verify_circuit(base, cand, noise, opts)
                fix.update(verdict=verdict, metrics=metrics)
                trace.add("verify", "Verify: Gemini rewrite", "accepted" if ok else "rejected", verdict, metrics, "simulator", t0)
                if ok and run is not None:
                    accepted.append(fix)
                    applied.append("Gemini rewrite")
                    base = run
                else:
                    rejected.append(fix)

    # readout mitigation (post-processing)
    ro_share = next((s["share"] for s in base.result["budget"]["by_source"] if s["source"] == "readout"), 0.0)
    mitigated_hellinger = None
    if ro_share >= 0.08 and base.result["fidelity"]["hellinger"] is not None:
        t0 = time.perf_counter()
        trace.add("propose", "Readout-error mitigation", "info",
                  f"Readout is {100 * ro_share:.0f}% of the error budget; invert the readout confusion on observed outcomes.",
                  {"readout_share": ro_share}, "rules", t0)
        t0 = time.perf_counter()
        counts = base.result["counts"]
        mit = mitigate_readout(counts, noise.readout_p01, noise.readout_p10)
        pairs = base.result["measurement"]["pairs"]
        exact = ideal_probabilities(base.ideal_state, list(counts), [tuple(p) for p in pairs], base.result["measurement"]["num_clbits"])
        fix = {"kind": "post_processing", "title": "Readout-error mitigation", "source": "rules"}
        if mit is None or exact is None:
            fix["verdict"] = "Skipped: too many distinct outcomes to mitigate on the observed subspace."
            trace.add("verify", "Verify: readout mitigation", "rejected", fix["verdict"], {}, "simulator", t0)
            rejected.append(fix)
        else:
            shots = sum(counts.values())
            raw = hellinger_fidelity({k: v / shots for k, v in counts.items()}, exact, normalize_q=False)
            new = hellinger_fidelity(mit, exact, normalize_q=False)
            metrics = {"hellinger_before": raw, "hellinger_after": new}
            ok = new > raw + 1e-3
            fix.update(verdict=(f"{'Accepted' if ok else 'Rejected'}: output-distribution fidelity {raw:.3f} -> {new:.3f}."), metrics=metrics)
            trace.add("verify", "Verify: readout mitigation", "accepted" if ok else "rejected", fix["verdict"], metrics, "simulator", t0)
            (accepted if ok else rejected).append(fix)
            if ok:
                mitigated_hellinger = new

    # 5. explain -----------------------------------------------------------
    t0 = time.perf_counter()
    before, after = _snapshot(start), _snapshot(base)
    if mitigated_hellinger is not None:
        after["hellinger_mitigated"] = mitigated_hellinger
    changed = base.circuit is not start.circuit
    final_qasm = base.circuit.to_qasm() if changed else qasm
    explanation = _final_explanation(start, base, accepted, rejected, ai)
    trace.add("explain", "Summary", "ok", explanation["text"], {}, explanation["source"], t0)
    return {
        "ok": True, "steps": trace.steps, "accepted": accepted, "rejected": rejected, "final_qasm": final_qasm,
        "changed": changed, "before": before, "after": after, "explanation": explanation, "ai_mode": ai.mode,
        "duration_ms": (time.perf_counter() - t_all) * 1000,
        "final_explanation": offline_explanation(base.circuit, base.result),
    }


def _final_explanation(start: SimulationRun, end: SimulationRun, accepted: list[dict], rejected: list[dict], ai: AIClient) -> dict:
    b, a = _snapshot(start), _snapshot(end)
    if accepted:
        text = (f"Applied {len(accepted)} verified fix(es): " + ", ".join(f["title"] for f in accepted) + ". "
                f"Two-qubit gates {b['two_qubit_gates']} -> {a['two_qubit_gates']}, depth {b['depth']} -> {a['depth']}, "
                f"simulated fidelity {b['state_fidelity']:.3f} -> {a['state_fidelity']:.3f}, "
                f"estimated success {b['esp']:.3f} -> {a['esp']:.3f}.")
    else:
        text = "No fix improved the circuit under this noise model; it is already lean for these errors."
    if rejected:
        text += f" {len(rejected)} proposal(s) were rejected by verification."
    if not ai.online:
        return {"source": "rules", "text": text}
    data, meta = ai.generate_json(
        model=ai.s.gemini_flash_model,
        system="You summarise a quantum-circuit debugging session for an engineer in 2-3 sentences. Use only the numbers given. JSON: {\"text\": str}",
        prompt=text + "\nRejected proposals: " + "; ".join(str(r.get("verdict")) for r in rejected))
    if data and data.get("text"):
        return {"source": "gemini", "text": str(data["text"])[:900], "model": meta["model"]}
    return {"source": "rules", "text": text}
