OPENQASM 2.0;
include "qelib1.inc";
// Bell state: the hello-world of entanglement
qreg q[2];
creg c[2];
h q[0];
cx q[0],q[1];
measure q -> c;
