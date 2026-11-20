"""Benchmark: dense state-vector simulation vs Q-Sim's MPS tensor network.

Measures wall-clock time and peak memory (traced by Python's tracemalloc, which
also sees NumPy buffers) for the ideal simulation of two circuit families:

  * GHZ chain       - low entanglement (bond dimension 2): MPS scales linearly
  * Brickwork, 4 layers of ry + CX - moderate entanglement (bond dimension <= 16)

For every size where both run, the MPS state is checked against the dense one
(|<dense|mps>|^2 should be 1). Results go to benchmarks/results/latest.json
(shown in the web app's Benchmarks tab), a CSV, and a PNG chart if matplotlib
is installed.

Usage (repo root, backend venv active):
    python benchmarks/benchmark.py              # full run (~1-3 min)
    python benchmarks/benchmark.py --quick      # fast smoke run
    python benchmarks/benchmark.py --max-dense 26 --max-mps 200
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import gc
import json
import math
import platform
import sys
import time
import tracemalloc
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.quantum.circuit import Circuit, Gate  # noqa: E402
from app.quantum.mps import MPS  # noqa: E402
from app.quantum.simulator import compile_ops, run_ops  # noqa: E402
from app.quantum.statevector import StateVector  # noqa: E402

OUT = ROOT / "benchmarks" / "results"


def ghz(n: int) -> Circuit:
    return Circuit(n, [Gate("h", (0,))] + [Gate("cx", (i, i + 1)) for i in range(n - 1)])


def brickwork(n: int, layers: int = 4) -> Circuit:
    gates = []
    for layer in range(layers):
        gates += [Gate("ry", (i,), (0.7 * math.sin(1.3 * i + layer) + 0.2,)) for i in range(n)]
        gates += [Gate("cx", (i, i + 1)) for i in range(layer % 2, n - 1, 2)]
        gates += [Gate("cx", (i, i + 1)) for i in range(1 - layer % 2, n - 1, 2)]
    return Circuit(n, gates)


def measure(fn):
    gc.collect()
    tracemalloc.start()
    t0 = time.perf_counter()
    state = fn()
    secs = time.perf_counter() - t0
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return state, secs, peak


def to_dense(m: MPS) -> np.ndarray:
    v = np.asarray(m.tensors[0])
    for t in m.tensors[1:]:
        v = np.einsum("...a,asb->...sb", v, np.asarray(t))
    return v.reshape(-1)


def run_family(name: str, make, sizes_dense, sizes_mps, max_bond: int, rows: list) -> None:
    dense_states = {}
    for n in sizes_dense:
        c = make(n)
        ops = compile_ops(c)

        def go():
            s = StateVector(n, max_qubits=64)
            run_ops(s, ops)
            return s

        try:
            s, secs, peak = measure(go)
        except MemoryError as exc:
            rows.append(dict(method="statevector", circuit=name, qubits=n, seconds=None, peak_bytes=None,
                             state_bytes=16 * 2**n, max_bond=None, fidelity_vs_dense=None, note=str(exc)[:80]))
            break
        if n <= 20:
            dense_states[n] = s.psi.reshape(-1).copy()
        rows.append(dict(method="statevector", circuit=name, qubits=n, seconds=secs, peak_bytes=peak,
                         state_bytes=s.memory_bytes(), max_bond=None, fidelity_vs_dense=None))
        print(f"  dense  {name:10s} n={n:3d}  {secs * 1000:9.1f} ms  peak {peak / 2**20:9.1f} MiB", flush=True)
        del s
    for n in sizes_mps:
        c = make(n)
        ops = compile_ops(c)

        def go():
            m = MPS(n, max_bond=max_bond)
            run_ops(m, ops)
            return m

        m, secs, peak = measure(go)
        fid = None
        if n in dense_states:
            fid = float(abs(np.vdot(dense_states[n], to_dense(m))) ** 2)
        rows.append(dict(method="mps", circuit=name, qubits=n, seconds=secs, peak_bytes=peak, state_bytes=m.memory_bytes(),
                         max_bond=m.max_bond_used, fidelity_vs_dense=fid,
                         note="exact" if m.truncation_fidelity == 1.0 else f"truncation fidelity {m.truncation_fidelity:.6f}"))
        print(f"  mps    {name:10s} n={n:3d}  {secs * 1000:9.1f} ms  peak {peak / 2**20:9.1f} MiB  chi={m.max_bond_used}"
              + (f"  fidelity vs dense {fid:.10f}" if fid is not None else ""), flush=True)


def plot(rows: list, path: Path) -> None:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not installed: skipping PNG chart")
        return
    circuits = sorted({r["circuit"] for r in rows})
    fig, axes = plt.subplots(len(circuits), 2, figsize=(11, 3.6 * len(circuits)))
    axes = np.atleast_2d(axes)
    for i, c in enumerate(circuits):
        for j, (key, label) in enumerate((("seconds", "time (s)"), ("peak_bytes", "peak memory (bytes)"))):
            ax = axes[i, j]
            for method, color in (("statevector", "#9a9aae"), ("mps", "#5b3cc4")):
                pts = [(r["qubits"], r[key]) for r in rows if r["circuit"] == c and r["method"] == method and r[key]]
                if pts:
                    ax.plot(*zip(*pts), marker="o", color=color, label="dense state vector" if method == "statevector" else "Q-Sim MPS")
            ax.set_yscale("log")
            ax.set_xlabel("qubits")
            ax.set_ylabel(label)
            ax.set_title(f"{c}: {label}")
            ax.grid(alpha=0.3)
            ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    print(f"chart: {path}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="small sizes only")
    ap.add_argument("--max-dense", type=int, default=24, help="largest dense simulation (24 = 256 MiB state)")
    ap.add_argument("--max-mps", type=int, default=128)
    ap.add_argument("--max-bond", type=int, default=64)
    args = ap.parse_args()
    top_dense = 16 if args.quick else args.max_dense
    top_mps = 32 if args.quick else args.max_mps
    dense_sizes = list(range(4, top_dense + 1, 2))
    mps_sizes = sorted(set(list(range(4, min(top_mps, 32) + 1, 4)) + [n for n in (48, 64, 96, 128, 160, 200) if n <= top_mps]))
    rows: list[dict] = []
    print("GHZ chain")
    run_family("GHZ chain", ghz, dense_sizes, mps_sizes, args.max_bond, rows)
    print("Brickwork (4 layers)")
    run_family("Brickwork (4 layers)", brickwork, dense_sizes, [n for n in mps_sizes if n <= 100], args.max_bond, rows)

    OUT.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    meta = {"platform": f"{platform.system()} {platform.release()}", "cpu": platform.processor() or platform.machine(),
            "python": platform.python_version(), "numpy": np.__version__}
    doc = {"created": dt.datetime.now().isoformat(timespec="seconds"), "machine": meta, "rows": rows}
    (OUT / "latest.json").write_text(json.dumps(doc, indent=1), encoding="utf-8")
    with open(OUT / f"run_{stamp}.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["circuit", "method", "qubits", "seconds", "peak_bytes", "state_bytes", "max_bond", "fidelity_vs_dense", "note"])
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) for k in w.fieldnames})
    plot(rows, OUT / "benchmark.png")
    print(f"results: {OUT / 'latest.json'}")


if __name__ == "__main__":
    main()
