import math

import pytest

from app.quantum import QasmError, load_qasm, parse_qasm
from app.quantum.qasm_parser import eval_expr


def test_expressions():
    assert eval_expr("pi/2") == pytest.approx(math.pi / 2)
    assert eval_expr("-3*pi/4 + 2^2") == pytest.approx(-3 * math.pi / 4 + 4)
    assert eval_expr("sin(theta)", {"theta": 0.5}) == pytest.approx(math.sin(0.5))


def test_qasm2_with_broadcast_and_definitions():
    c = load_qasm("""OPENQASM 2.0; include "qelib1.inc";
    gate mygate(a) x, y { rz(a/2) x; cx x, y; }
    qreg q[3]; creg c[3];
    h q;            // broadcast to all qubits
    mygate(pi) q[0], q[2];
    measure q -> c;""")
    assert c.num_qubits == 3
    assert [g.name for g in c.gates] == ["h", "h", "h", "rz", "cx"]
    assert c.gates[3].params[0] == pytest.approx(math.pi / 2)
    assert c.measurements == [(0, 0), (1, 1), (2, 2)]


def test_qasm3_syntax():
    c = load_qasm("""OPENQASM 3.0; include "stdgates.inc";
    qubit[2] q; bit[2] b;
    h q[0]; cx q[0], q[1];
    b = measure q;""")
    assert c.num_qubits == 2 and c.measurements == [(0, 0), (1, 1)]


def test_multiple_registers_flatten():
    c = load_qasm('OPENQASM 2.0; include "qelib1.inc"; qreg a[2]; qreg b[2]; creg m[1]; cx a[1], b[0]; measure b[1] -> m[0];')
    assert c.gates[0].qubits == (1, 2)
    assert c.measurements == [(3, 0)]


def test_toffoli_is_decomposed():
    c = load_qasm('OPENQASM 2.0; include "qelib1.inc"; qreg q[3]; ccx q[0], q[1], q[2];')
    assert all(g.arity <= 2 for g in c.gates) and len(c.gates) == 15


def test_errors_have_lines_and_hints():
    _, issues = parse_qasm('OPENQASM 2.0;\ninclude "qelib1.inc";\nqreg q[2];\nhadamard q[0];\ncx q[0], q[2];\nrz q[1];\n')
    errors = {i.line: i.message for i in issues if i.severity == "error"}
    assert "Did you mean 'h'" in errors[4]
    assert "out of range" in errors[5]
    assert "parameter" in errors[6]


def test_mid_circuit_measurement_rejected():
    with pytest.raises(QasmError):
        load_qasm('OPENQASM 2.0; include "qelib1.inc"; qreg q[1]; creg c[1]; measure q[0] -> c[0]; x q[0];')


def test_roundtrip_to_qasm():
    src = 'OPENQASM 2.0; include "qelib1.inc"; qreg q[2]; creg c[2]; h q[0]; rz(0.25) q[1]; cx q[0],q[1]; measure q -> c;'
    c = load_qasm(src)
    c2 = load_qasm(c.to_qasm())
    assert [(g.name, g.qubits, g.params) for g in c.gates] == [(g.name, g.qubits, g.params) for g in c2.gates]
