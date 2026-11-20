OPENQASM 2.0;
include "qelib1.inc";
// This circuit has mistakes on purpose. Validation explains each one.
qreg q[3];
creg c[3];
h q[0];
cx q[0],q[3];
hadamard q[1];
rz q[2];
measure q -> c;
