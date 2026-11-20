"""Batch worker for large simulations (GKE GPU/TPU jobs or local runs).

Usage:
    python -m app.worker --spec job.json [--out result.json]
    python -m app.worker --spec gs://bucket/jobs/job.json --out gs://bucket/results/job.json

Spec format:
    {"qasm": "..."} or {"qasm_path": "app/examples/ghz_100.qasm"},
    "noise": {"p1": 0.001, "p2": 0.01, "amplitude_damping": 0.002, "readout": 0.02},
    "options": {"shots": 4096, "trajectories": 64, "backend": "mps", "max_bond": 512}

Set ARRAY_BACKEND=jax on accelerator nodes to run the MPS contractions with JAX.
gs:// paths need `pip install google-cloud-storage` and default credentials.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from .config import get_settings
from .quantum import NoiseModel, SimOptions, load_qasm, simulate

log = logging.getLogger("qsim.worker")


def _read(uri: str) -> str:
    if uri.startswith("gs://"):
        from google.cloud import storage  # optional dependency

        bucket, _, name = uri[5:].partition("/")
        return storage.Client().bucket(bucket).blob(name).download_as_text()
    return Path(uri).read_text(encoding="utf-8")


def _write(uri: str, text: str) -> None:
    if uri.startswith("gs://"):
        from google.cloud import storage

        bucket, _, name = uri[5:].partition("/")
        storage.Client().bucket(bucket).blob(name).upload_from_string(text, content_type="application/json")
    else:
        Path(uri).write_text(text, encoding="utf-8")


def run_spec(spec: dict) -> dict:
    s = get_settings()
    qasm = spec.get("qasm") or _read(spec["qasm_path"])
    o = spec.get("options", {})
    opts = SimOptions(shots=int(o.get("shots", 1024)), trajectories=int(o.get("trajectories", 16)),
                      backend=o.get("backend", "auto"), max_bond=int(o.get("max_bond", 64)), seed=o.get("seed"),
                      array_backend=s.array_backend, sv_auto_max=s.sv_auto_max, sv_hard_max=s.sv_hard_max,
                      time_budget_s=float(o.get("time_budget_s", 3600)))
    return simulate(load_qasm(qasm), NoiseModel.from_dict(spec.get("noise")), opts).result


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="Run a Q-Sim simulation job")
    ap.add_argument("--spec", required=True, help="Path or gs:// URI of the job spec JSON")
    ap.add_argument("--out", help="Path or gs:// URI for the result JSON (default: print a summary)")
    args = ap.parse_args(argv)
    result = run_spec(json.loads(_read(args.spec)))
    f = result["fidelity"]
    log.info("backend=%s fidelity=%.4f esp=%.4f truncation=%.6f time=%.0f ms memory=%d bytes",
             result["backend"], f["state"], f["esp"], f["truncation"], result["timing"]["total_ms"], result["memory"]["used_bytes"])
    text = json.dumps(result, default=float)
    if args.out:
        _write(args.out, text)
        log.info("wrote %s", args.out)
    else:
        print(json.dumps({k: result[k] for k in ("backend", "fidelity", "timing", "memory", "plan")}, indent=2, default=float))
    return 0


if __name__ == "__main__":
    sys.exit(main())
