OPENQASM 2.0;
include "qelib1.inc";
// 8-qubit hardware-efficient ansatz exported from a transpiler.
// It contains leftovers a careful engineer would remove: the debug agent finds them.
qreg q[8];
creg c[8];
// layer 1
ry(0.31) q[0];
ry(1.12) q[1];
ry(-0.74) q[2];
ry(0.58) q[3];
ry(1.43) q[4];
ry(-0.27) q[5];
ry(0.89) q[6];
ry(-1.05) q[7];
rz(0.44) q[0];
rz(-0.62) q[1];
rz(0.97) q[2];
rz(-0.18) q[3];
rz(0.35) q[4];
rz(1.21) q[5];
rz(-0.83) q[6];
rz(0.16) q[7];
cx q[0],q[1];
cx q[1],q[2];
cx q[2],q[3];
cx q[2],q[3];
cx q[2],q[3];   // three CX in a row: two of them cancel
cx q[3],q[4];
h q[5];
h q[5];          // double Hadamard
cx q[4],q[5];
cx q[5],q[6];
cx q[6],q[7];
swap q[3],q[4];
swap q[3],q[4];  // swap there and back
rz(0.3) q[1];
rz(-0.3) q[1];   // rotations that cancel
rx(0) q[4];       // zero-angle rotation
// layer 2
ry(0.58) q[0];
ry(1.43) q[1];
ry(-0.27) q[2];
ry(0.89) q[3];
ry(-1.05) q[4];
ry(0.31) q[5];
ry(1.12) q[6];
ry(-0.74) q[7];
rz(0.25) q[2];
rz(0.5) q[2];    // two rotations that should be one
cx q[0],q[1];
cx q[1],q[2];
cx q[2],q[3];
cx q[3],q[4];
cx q[4],q[5];
cx q[5],q[6];
cx q[6],q[7];
cx q[6],q[7];
cx q[6],q[7];    // CX pair that cancels
measure q -> c;
