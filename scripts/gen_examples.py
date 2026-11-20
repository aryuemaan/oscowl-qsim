"""Regenerate the example circuits in backend/app/examples/.

Usage (from the repo root):  python scripts/gen_examples.py
"""
from __future__ import annotations

import json
import math
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "backend" / "app" / "examples"
HEADER = 'OPENQASM 2.0;\ninclude "qelib1.inc";\n'


def ghz(n: int) -> str:
    lines = [HEADER + f"// {n}-qubit GHZ state: (|00..0> + |11..1>)/sqrt(2)", f"qreg q[{n}];", f"creg c[{n}];", "h q[0];"]
    lines += [f"cx q[{i}],q[{i + 1}];" for i in range(n - 1)]
    lines.append("measure q -> c;")
    return "\n".join(lines) + "\n"


def qft_roundtrip(n: int, x: str) -> str:
    lines = [HEADER + f"// Prepare |{x}>, apply the QFT, then the inverse QFT.",
             "// Ideal output is the input bitstring; noise blurs it.", f"qreg q[{n}];", f"creg c[{n}];"]
    lines += [f"x q[{i}];" for i, b in enumerate(reversed(x)) if b == "1"]
    fwd = []
    for j in range(n):
        fwd.append(("h", (j,), None))
        for k in range(j + 1, n):
            fwd.append(("cp", (k, j), math.pi / 2 ** (k - j)))
    for i in range(n // 2):
        fwd.append(("swap", (i, n - 1 - i), None))

    def emit(gate, qs, angle):
        args = ",".join(f"q[{q}]" for q in qs)
        return f"{gate}({angle:.12f}) {args};" if angle is not None else f"{gate} {args};"

    lines.append("// QFT")
    lines += [emit(*g) for g in fwd]
    lines.append("// inverse QFT")
    lines += [emit(g, qs, -a if a is not None else None) for g, qs, a in reversed(fwd)]
    lines.append("measure q -> c;")
    return "\n".join(lines) + "\n"


def redundant_ansatz() -> str:
    n = 8
    th = [0.31, 1.12, -0.74, 0.58, 1.43, -0.27, 0.89, -1.05]
    ph = [0.44, -0.62, 0.97, -0.18, 0.35, 1.21, -0.83, 0.16]
    l = [HEADER + "// 8-qubit hardware-efficient ansatz exported from a transpiler.",
         "// It contains leftovers a careful engineer would remove: the debug agent finds them.",
         f"qreg q[{n}];", f"creg c[{n}];", "// layer 1"]
    l += [f"ry({th[i]}) q[{i}];" for i in range(n)]
    l += [f"rz({ph[i]}) q[{i}];" for i in range(n)]
    l += ["cx q[0],q[1];", "cx q[1],q[2];",
          "cx q[2],q[3];", "cx q[2],q[3];", "cx q[2],q[3];   // three CX in a row: two of them cancel",
          "cx q[3],q[4];", "h q[5];", "h q[5];          // double Hadamard",
          "cx q[4],q[5];", "cx q[5],q[6];", "cx q[6],q[7];",
          "swap q[3],q[4];", "swap q[3],q[4];  // swap there and back",
          "rz(0.3) q[1];", "rz(-0.3) q[1];   // rotations that cancel",
          "rx(0) q[4];       // zero-angle rotation",
          "// layer 2"]
    l += [f"ry({th[(i + 3) % n]}) q[{i}];" for i in range(n)]
    l += ["rz(0.25) q[2];", "rz(0.5) q[2];    // two rotations that should be one"]
    l += [f"cx q[{i}],q[{i + 1}];" for i in range(n - 1)]
    l += ["cx q[6],q[7];", "cx q[6],q[7];    // CX pair that cancels", "measure q -> c;"]
    return "\n".join(l) + "\n"


def hea(n: int, layers: int) -> str:
    l = [HEADER + f"// {n}-qubit hardware-efficient ansatz, {layers} layers (linear entanglement).",
         "// Dense simulation would need 16 * 2^n bytes; the MPS backend handles it exactly.",
         f"qreg q[{n}];", f"creg c[{n}];"]
    for layer in range(layers):
        l += [f"ry({round(0.7 * math.sin(1.3 * i + layer) + 0.2, 4)}) q[{i}];" for i in range(n)]
        l += [f"cx q[{i}],q[{i + 1}];" for i in range(layer % 2, n - 1, 2)]
        l += [f"cx q[{i}],q[{i + 1}];" for i in range(1 - layer % 2, n - 1, 2)]
    l.append("measure q -> c;")
    return "\n".join(l) + "\n"


BELL = HEADER + "// Bell state: the hello-world of entanglement\nqreg q[2];\ncreg c[2];\nh q[0];\ncx q[0],q[1];\nmeasure q -> c;\n"

GROVER = HEADER + """// 3-qubit Grover search, one iteration, marked state |101> (q2 q1 q0)
// Ideal success probability is 78%.
qreg q[3];
creg c[3];
h q[0]; h q[1]; h q[2];
// oracle: phase-flip |101>
x q[1];
h q[2]; ccx q[0],q[1],q[2]; h q[2];
x q[1];
// diffuser
h q[0]; h q[1]; h q[2];
x q[0]; x q[1]; x q[2];
h q[2]; ccx q[0],q[1],q[2]; h q[2];
x q[0]; x q[1]; x q[2];
h q[0]; h q[1]; h q[2];
measure q -> c;
"""

BROKEN = HEADER + """// This circuit has mistakes on purpose. Validation explains each one.
qreg q[3];
creg c[3];
h q[0];
cx q[0],q[3];
hadamard q[1];
rz q[2];
measure q -> c;
"""

NISQ = {"p1": 0.002, "p2": 0.02, "amplitude_damping": 0.005, "readout": 0.03}
LOW = {"p1": 0.0005, "p2": 0.005, "amplitude_damping": 0.001, "readout": 0.01}

EXAMPLES = [
    ("ansatz_redundant_8", "Ansatz with leftovers (8q)", "Hero demo: run the debug agent to find and remove redundant gates, then see the verified fidelity gain.", redundant_ansatz(), NISQ),
    ("ghz_100", "GHZ state (100q)", "Structured, low-entanglement circuit: exact on the MPS backend with bond dimension 2 (dense would need 2x10^31 bytes).", ghz(100), LOW),
    ("hea_32", "Variational ansatz (32q)", "Hardware-efficient ansatz with linear entanglement: exact MPS run where dense simulation needs 64 GiB.", hea(32, 4), LOW),
    ("grover_3", "Grover search (3q)", "One Grover iteration marking |101>; uses Toffoli gates (decomposed into CX + T).", GROVER, NISQ),
    ("qft_roundtrip_6", "QFT round trip (6q)", "QFT followed by its inverse: long-range gates exercise MPS routing; the agent spots the redundancy.", qft_roundtrip(6, "101101"), NISQ),
    ("ghz_12", "GHZ state (12q)", "Classic entangled benchmark; exact dense simulation.", ghz(12), NISQ),
    ("bell", "Bell state (2q)", "The hello-world of entanglement.", BELL, NISQ),
    ("broken", "Broken circuit (validation)", "Contains an out-of-range qubit, a misspelt gate and a missing parameter.", BROKEN, NISQ),
]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = []
    for ex_id, title, desc, qasm, noise in EXAMPLES:
        (OUT / f"{ex_id}.qasm").write_text(qasm, encoding="utf-8", newline="\n")
        manifest.append({"id": ex_id, "title": title, "description": desc, "file": f"{ex_id}.qasm", "noise": noise})
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {len(manifest)} examples to {OUT}")


if __name__ == "__main__":
    main()
