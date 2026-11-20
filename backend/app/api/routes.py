"""REST API. Interactive docs at /api/docs when the server is running."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, HTTPException

from ..ai.agent import run_debug_agent
from ..ai.explainer import explain
from ..ai.llm import get_ai_client
from ..ai.skills import skill_catalog
from ..ai.validator import lint, validate
from ..config import VERSION, get_settings
from ..quantum import NoiseModel, PRESETS, SimOptions, parse_qasm, simulate
from ..quantum.arrays import available_backends
from ..schemas import ExplainIn, SimulateIn, ValidateIn

router = APIRouter()
EXAMPLES_DIR = Path(__file__).resolve().parents[1] / "examples"


# ------------------------------------------------------------------ helpers
def _options(o, s) -> SimOptions:
    if o.shots > s.max_shots:
        raise HTTPException(400, f"shots must be <= {s.max_shots}")
    if o.trajectories > s.max_trajectories:
        raise HTTPException(400, f"trajectories must be <= {s.max_trajectories}")
    if o.max_bond > s.max_bond_limit:
        raise HTTPException(400, f"max_bond must be <= {s.max_bond_limit} on this server (MAX_BOND_LIMIT)")
    return SimOptions(shots=o.shots, trajectories=o.trajectories, backend=o.backend, max_bond=o.max_bond, seed=o.seed,
                      array_backend=s.array_backend, sv_auto_max=s.sv_auto_max, sv_hard_max=s.sv_hard_max,
                      time_budget_s=s.time_budget_s)


def _circuit(qasm: str):
    s = get_settings()
    circuit, issues = parse_qasm(qasm)
    if circuit is not None:
        issues += [i for i in lint(circuit, s) if i.severity == "error"]
    errors = [i.to_dict() for i in issues if i.severity == "error"]
    if errors:
        raise HTTPException(422, {"message": "The circuit has errors; fix them and run again.", "issues": errors})
    return circuit


def _run(body: SimulateIn):
    s = get_settings()
    circuit = _circuit(body.qasm)
    try:
        return simulate(circuit, NoiseModel(**body.noise.model_dump()), _options(body.options, s))
    except (ValueError, MemoryError) as exc:
        raise HTTPException(400, str(exc)) from exc


@lru_cache
def _manifest() -> list[dict]:
    return json.loads((EXAMPLES_DIR / "manifest.json").read_text(encoding="utf-8"))


# ------------------------------------------------------------------ endpoints
@router.get("/health")
def health() -> dict:
    s = get_settings()
    return {"status": "ok", "version": VERSION, "ai": get_ai_client().status(),
            "array_backends": available_backends(), "array_backend": s.array_backend,
            "limits": {"max_qubits": s.max_qubits, "sv_auto_max": s.sv_auto_max, "sv_hard_max": s.sv_hard_max,
                       "max_bond": s.max_bond_limit, "max_shots": s.max_shots, "max_trajectories": s.max_trajectories}}


@router.get("/examples")
def examples() -> list[dict]:
    return [{**m, "qasm": (EXAMPLES_DIR / m["file"]).read_text(encoding="utf-8")} for m in _manifest()]


@router.get("/noise-presets")
def noise_presets() -> dict:
    return {k: v.to_dict() for k, v in PRESETS.items()}


@router.get("/skills")
def skills() -> list[dict]:
    return skill_catalog()


@router.post("/validate")
def validate_endpoint(body: ValidateIn) -> dict:
    return validate(body.qasm, get_settings(), get_ai_client(), use_ai=body.use_ai)


@router.post("/simulate")
def simulate_endpoint(body: SimulateIn) -> dict:
    return _run(body).result


@router.post("/explain")
def explain_endpoint(body: ExplainIn) -> dict:
    circuit = _circuit(body.qasm)
    sim = body.simulation or _run(body).result
    return explain(circuit, sim, body.qasm, get_ai_client())


@router.post("/agent/debug")
def debug_endpoint(body: SimulateIn) -> dict:
    s = get_settings()
    _circuit(body.qasm)
    try:
        return run_debug_agent(body.qasm, NoiseModel(**body.noise.model_dump()), _options(body.options, s), s, get_ai_client())
    except (ValueError, MemoryError) as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/benchmarks/latest")
def benchmarks_latest() -> dict:
    path = Path(get_settings().benchmark_results)
    if not path.is_file():
        raise HTTPException(404, "No benchmark results yet. Run: python benchmarks/benchmark.py")
    return json.loads(path.read_text(encoding="utf-8"))
