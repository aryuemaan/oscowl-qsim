"""Circuit validation: parser errors + deterministic lint rules + optional Gemma pre-check."""
from __future__ import annotations

import json

from ..config import Settings
from ..quantum.optimizer import simplify
from ..quantum.planner import plan_resources
from ..quantum.qasm_parser import Issue, parse_qasm
from .llm import AIClient
from .skills import skill_prompt


def lint(circuit, settings: Settings) -> list[Issue]:
    """Rules that catch common, costly mistakes before simulation."""
    issues: list[Issue] = []
    st = circuit.stats()
    if circuit.num_qubits > settings.max_qubits:
        issues.append(Issue("error", f"{circuit.num_qubits} qubits exceeds this server's limit of {settings.max_qubits} (MAX_QUBITS)", None, "limit", "lint"))
    if len(circuit.gates) > settings.max_gates:
        issues.append(Issue("error", f"{len(circuit.gates)} gates exceeds the limit of {settings.max_gates} (MAX_GATES)", None, "limit", "lint"))
    if st["implicit_measurement"]:
        issues.append(Issue("warning", "No measurements: all qubits will be measured at the end", None, "no_measurement", "lint"))
    for q in st["unused_qubits"][:5]:
        issues.append(Issue("info", f"Qubit {q} is declared but never used", None, "unused_qubit", "lint"))
    _, changes = simplify(circuit)
    for ch in changes[:8]:
        lines = [ln for ln in ch["lines"] if ln]
        issues.append(Issue("info", ch["finding"] + ". The debug agent can fix this.",
                            lines[-1] if lines else None, "redundant_gates", "lint"))
    if len(changes) > 8:
        issues.append(Issue("info", f"{len(changes) - 8} more redundant gate patterns found", None, "redundant_gates", "lint"))
    lr = circuit.long_range_gates()
    if lr:
        issues.append(Issue(
            "warning",
            f"{len(lr)} two-qubit gate(s) act on non-neighbouring qubits (max distance {st['max_interaction_distance']}). "
            "On linear hardware and in MPS this adds SWAPs; consider re-mapping qubits.",
            lr[0].line, "long_range", "lint"))
    if circuit.num_qubits > settings.sv_auto_max:
        try:
            plan = plan_resources(circuit, "auto", 64, settings.sv_auto_max, settings.sv_hard_max)
            if not plan.exact_expected and plan.predicted_max_bond > settings.max_bond_limit:
                issues.append(Issue("warning", "Highly entangled for its size: the MPS run will be approximate. "
                                    "Results include a truncation error bound.", None, "entanglement", "lint"))
        except ValueError:
            pass
    return issues


def gemma_precheck(qasm: str, issues: list[Issue], ai: AIClient) -> tuple[list[Issue], dict, str | None]:
    """Ask Gemma for likely logic mistakes. Returns (issues, meta, summary)."""
    known = [f"line {i.line}: {i.message}" for i in issues][:12]
    prompt = (
        "Review this circuit before simulation.\n"
        f"Already reported (do not repeat): {json.dumps(known)}\n\n"
        f"```qasm\n{qasm[:6000]}\n```"
    )
    data, meta = ai.generate_json(model=ai.s.gemma_model, system=skill_prompt("qasm-lint"), prompt=prompt,
                                  max_tokens=1024, gemma=True)
    if not data:
        return [], meta, None
    out = []
    for item in (data.get("issues") or [])[:5]:
        if isinstance(item, dict) and item.get("message"):
            line = item.get("line")
            out.append(Issue("warning" if item.get("severity") == "warning" else "info", str(item["message"])[:300],
                             int(line) if isinstance(line, (int, float)) else None, "ai_hint", "gemma"))
    return out, meta, (str(data.get("summary"))[:400] if data.get("summary") else None)


def validate(qasm: str, settings: Settings, ai: AIClient, use_ai: bool = False) -> dict:
    circuit, issues = parse_qasm(qasm)
    stats, plan = None, None
    if circuit is not None:
        issues += lint(circuit, settings)
        stats = circuit.stats()
        try:
            plan = plan_resources(circuit, "auto", 64, settings.sv_auto_max, settings.sv_hard_max).to_dict()
        except ValueError:
            plan = None
    ai_info: dict = {"used": False, "provider": ai.gemma_provider, "summary": None}
    if use_ai and circuit is not None and ai.gemma_provider != "off":
        extra, meta, summary = gemma_precheck(qasm, issues, ai)
        issues += extra
        ai_info = {"used": meta.get("error") is None, **meta, "summary": summary}
    ok = not any(i.severity == "error" for i in issues)
    order = {"error": 0, "warning": 1, "info": 2}
    issues.sort(key=lambda i: (order[i.severity], i.line or 0))
    return {"ok": ok, "issues": [i.to_dict() for i in issues], "stats": stats, "plan": plan, "ai": ai_info}
