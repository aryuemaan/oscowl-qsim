"""Q-Sim debug agent for Google's Agent Development Kit (ADK).

The same tools the web app uses, exposed to an ADK ``Agent`` so the debugger can
run in ``adk web`` locally or be deployed to Gemini Enterprise Agent Platform.

Run locally (from the backend/ folder, with GEMINI_API_KEY or GOOGLE_API_KEY set):
    pip install google-adk
    adk web adk_agents
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # make `app` importable

from google.adk.agents import Agent  # noqa: E402

from app.ai.skills import load_skills, skill_prompt  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.quantum import NoiseModel, SimOptions, load_qasm, simulate, state_overlap  # noqa: E402
from app.quantum.optimizer import simplification_summary, simplify  # noqa: E402
from app.quantum.qasm_parser import parse_qasm  # noqa: E402

_S = get_settings()


def _noise(p1: float, p2: float, amplitude_damping: float, readout: float) -> NoiseModel:
    return NoiseModel.from_dict({"p1": p1, "p2": p2, "amplitude_damping": amplitude_damping, "readout": readout})


def validate_circuit(qasm: str) -> dict:
    """Parse an OpenQASM circuit and report syntax errors with line numbers plus basic statistics."""
    circuit, issues = parse_qasm(qasm)
    return {"ok": circuit is not None, "issues": [i.to_dict() for i in issues],
            "stats": circuit.stats() if circuit else None}


def simulate_circuit(qasm: str, p1: float = 0.002, p2: float = 0.02, amplitude_damping: float = 0.005,
                     readout: float = 0.03, shots: int = 1024) -> dict:
    """Simulate a circuit under noise. Returns fidelities, the error budget and the top measured outcomes."""
    run = simulate(load_qasm(qasm), _noise(p1, p2, amplitude_damping, readout),
                   SimOptions(shots=shots, trajectories=16, seed=1234, sv_auto_max=_S.sv_auto_max))
    r = run.result
    return {"backend": r["backend"], "fidelity": r["fidelity"], "error_budget": r["budget"]["by_source"],
            "hotspots": r["budget"]["hotspots"][:8], "top_outcomes": r["outcomes"][:8]}


def propose_simplification(qasm: str) -> dict:
    """Apply safe rewrite rules (cancel inverse pairs, merge rotations, drop identities). Returns new QASM."""
    circuit = load_qasm(qasm)
    new, changes = simplify(circuit)
    return {"changes": [c["description"] for c in changes], "summary": simplification_summary(circuit, new),
            "qasm": new.to_qasm()}


def verify_fix(original_qasm: str, candidate_qasm: str, p1: float = 0.002, p2: float = 0.02,
               amplitude_damping: float = 0.005, readout: float = 0.03) -> dict:
    """Check that a candidate circuit is equivalent to the original and compare their noisy fidelity."""
    noise = _noise(p1, p2, amplitude_damping, readout)
    opts = SimOptions(shots=1024, trajectories=16, seed=1234, sv_auto_max=_S.sv_auto_max)
    a, b = simulate(load_qasm(original_qasm), noise, opts), simulate(load_qasm(candidate_qasm), noise, opts)
    overlap = state_overlap(a.ideal_state, b.ideal_state) if a.plan.backend == b.plan.backend else None
    return {"ideal_state_overlap": overlap, "equivalent": overlap is not None and overlap >= 0.999,
            "fidelity_before": a.result["fidelity"], "fidelity_after": b.result["fidelity"]}


root_agent = Agent(
    name="qsim_debugger",
    model=_S.gemini_reasoning_model,
    description="Debugs noisy quantum circuits: simulates them, explains where fidelity is lost and verifies fixes.",
    instruction=(
        "You are OSCOWL Q-Sim's quantum circuit debugger. Workflow: validate_circuit -> simulate_circuit -> "
        "explain the dominant noise sources and hotspot lines -> propose_simplification (and your own rewrite if "
        "useful) -> verify_fix. Only recommend fixes that verify_fix marks as equivalent and that raise fidelity.\n\n"
        "Available skills: " + "; ".join(f"{s.name}: {s.description}" for s in load_skills().values()) + "\n\n"
        + skill_prompt("noise-explain", "circuit-optimize")
    ),
    tools=[validate_circuit, simulate_circuit, propose_simplification, verify_fix],
)
