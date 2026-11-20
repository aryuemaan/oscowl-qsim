"""OpenQASM 2.0 / 3.0 parser (the subset used by Qiskit, Cirq and most tutorials).

Supported: registers (qreg/creg, qubit/bit), the standard gate library, user
``gate`` definitions (macro-expanded), register broadcasting, parameter
expressions (pi, + - * / ^, sin/cos/...), barriers, and terminal measurements in
both 2.0 (``measure q -> c``) and 3.0 (``c = measure q``) syntax.

Not supported in this MVP (reported as clear errors): mid-circuit measurement,
reset, classical control (if/for/while), gate modifiers (ctrl @, inv @), and
parameter inputs. Errors carry the source line so the UI can highlight them.
"""
from __future__ import annotations

import ast
import difflib
import math
import operator
import re
from dataclasses import asdict, dataclass

from .circuit import Circuit, Gate
from .gates import DECOMPOSITIONS, GATE_SPECS, canonical_name


@dataclass
class Issue:
    severity: str  # "error" | "warning" | "info"
    message: str
    line: int | None = None
    rule: str = "syntax"
    source: str = "parser"

    def to_dict(self) -> dict:
        return asdict(self)


class QasmError(ValueError):
    def __init__(self, issues: list[Issue]):
        self.issues = issues
        errors = [i for i in issues if i.severity == "error"]
        first = errors[0] if errors else issues[0]
        where = f"line {first.line}: " if first.line else ""
        super().__init__(f"{where}{first.message}" + (f" (+{len(errors) - 1} more)" if len(errors) > 1 else ""))


# ----------------------------------------------------------------- expressions
_BINOPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
           ast.Div: operator.truediv, ast.Pow: operator.pow, ast.Mod: operator.mod}
_FUNCS = {"sin": math.sin, "cos": math.cos, "tan": math.tan, "exp": math.exp, "ln": math.log,
          "log": math.log, "sqrt": math.sqrt, "asin": math.asin, "acos": math.acos,
          "atan": math.atan, "arcsin": math.asin, "arccos": math.acos, "arctan": math.atan}
_CONSTS = {"pi": math.pi, "tau": 2 * math.pi, "euler": math.e, "e": math.e}


def eval_expr(text: str, env: dict[str, float] | None = None) -> float:
    """Safely evaluate a QASM parameter expression such as ``-3*pi/4``."""
    env = env or {}
    src = text.strip().replace("π", "pi").replace("τ", "tau").replace("^", "**")
    if not src:
        raise ValueError("empty expression")
    node = ast.parse(src, mode="eval").body

    def ev(n: ast.AST) -> float:
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
            return float(n.value)
        if isinstance(n, ast.Name):
            if n.id in env:
                return float(env[n.id])
            if n.id in _CONSTS:
                return _CONSTS[n.id]
            raise ValueError(f"unknown symbol '{n.id}'")
        if isinstance(n, ast.BinOp) and type(n.op) in _BINOPS:
            return _BINOPS[type(n.op)](ev(n.left), ev(n.right))
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.USub, ast.UAdd)):
            v = ev(n.operand)
            return -v if isinstance(n.op, ast.USub) else v
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in _FUNCS and len(n.args) == 1:
            return _FUNCS[n.func.id](ev(n.args[0]))
        raise ValueError("unsupported expression")

    return ev(node)


# ----------------------------------------------------------------- lexing
def _strip_comments(text: str) -> str:
    out, i, n = [], 0, len(text)
    while i < n:
        if text.startswith("//", i):
            j = text.find("\n", i)
            i = n if j == -1 else j
            continue
        if text.startswith("/*", i):
            j = text.find("*/", i + 2)
            end = n if j == -1 else j + 2
            out.append("\n" * text.count("\n", i, end))
            i = end
            continue
        out.append(text[i])
        i += 1
    return "".join(out)


def _statements(text: str) -> tuple[list[tuple[str, int]], tuple[str, int] | None]:
    """Split source into (statement, line) pairs. ``{...}`` blocks end a statement."""
    stmts: list[tuple[str, int]] = []
    buf: list[str] = []
    line, start, depth = 1, None, 0
    for ch in text:
        if ch == "\n":
            line += 1
        if start is None and not ch.isspace():
            start = line
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                buf.append(ch)
                stmts.append(("".join(buf).strip(), start or line))
                buf, start = [], None
                continue
        elif ch == ";" and depth == 0:
            stmts.append(("".join(buf).strip(), start or line))
            buf, start = [], None
            continue
        buf.append(ch)
    rest = "".join(buf).strip()
    return stmts, ((rest, start or line) if rest else None)


def _split_top(text: str, sep: str = ",") -> list[str]:
    parts, depth, cur = [], 0, []
    for ch in text:
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        if ch == sep and depth == 0:
            parts.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    if "".join(cur).strip():
        parts.append("".join(cur).strip())
    return parts


_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_ARG = re.compile(r"([A-Za-z_]\w*)\s*(?:\[\s*(\d+)\s*\])?")
_HINTS = {"hadamard": "h", "not": "x", "cnot": "cx", "toffoli": "ccx", "phase": "p", "measure_all": "measure q -> c"}
_UNSUPPORTED = {
    "reset": "reset is not supported yet (terminal measurements only)",
    "if": "classical control (if) is not supported yet",
    "for": "loops are not supported yet; unroll the loop",
    "while": "loops are not supported yet; unroll the loop",
    "def": "subroutines (def) are not supported yet; use a 'gate' definition",
    "opaque": "opaque gates cannot be simulated",
    "input": "parameter inputs are not supported; bind parameters before exporting (e.g. qc.assign_parameters)",
    "output": "output declarations are not supported",
    "delay": "delay instructions are ignored by this simulator; remove them",
    "box": "box blocks are not supported",
    "defcal": "pulse-level calibrations are not supported",
    "cal": "pulse-level calibrations are not supported",
    "extern": "extern functions are not supported",
}
_CLASSICAL_DECL = {"const", "float", "int", "uint", "angle", "bool", "duration", "stretch", "complex", "array", "let"}


def _split_call(s: str) -> tuple[str, str | None, str]:
    m = _IDENT.match(s)
    if not m:
        raise ValueError(f"cannot read statement '{s[:40]}'")
    name, rest = m.group(0), s[m.end():].lstrip()
    params = None
    if rest.startswith("("):
        depth = 0
        for i, ch in enumerate(rest):
            depth += ch == "("
            depth -= ch == ")"
            if depth == 0:
                params, rest = rest[1:i], rest[i + 1:]
                break
        else:
            raise ValueError("unbalanced parentheses in gate parameters")
    return name, params, rest.strip()


# ----------------------------------------------------------------- parser
class _Parser:
    MAX_EXPANSION_DEPTH = 32

    def __init__(self) -> None:
        self.issues: list[Issue] = []
        self.qregs: dict[str, tuple[int, int]] = {}
        self.cregs: dict[str, tuple[int, int]] = {}
        self.nq = 0
        self.nc = 0
        self.gates: list[Gate] = []
        self.meas: dict[int, tuple[int, int]] = {}  # clbit -> (qubit, line)
        self.measured: set[int] = set()
        self.mid_reported: set[int] = set()
        self.defs: dict[str, tuple[list[str], list[str], list[str], int]] = {}
        self.version: str | None = None

    # issue helpers
    def error(self, msg: str, line: int | None, rule: str = "syntax") -> None:
        self.issues.append(Issue("error", msg, line, rule))

    def warning(self, msg: str, line: int | None, rule: str) -> None:
        self.issues.append(Issue("warning", msg, line, rule))

    def info(self, msg: str, line: int | None, rule: str) -> None:
        self.issues.append(Issue("info", msg, line, rule))

    # registers
    def _declare(self, kind: str, name: str, size: int, line: int) -> None:
        regs = self.qregs if kind == "q" else self.cregs
        if name in self.qregs or name in self.cregs:
            self.error(f"Register '{name}' is declared twice", line, "redeclared")
            return
        if size <= 0:
            self.error(f"Register '{name}' must have at least one bit", line)
            return
        if kind == "q":
            regs[name] = (self.nq, size)
            self.nq += size
        else:
            regs[name] = (self.nc, size)
            self.nc += size

    def _resolve(self, arg: str, line: int, quantum: bool) -> list[int] | None:
        m = _ARG.fullmatch(arg.strip())
        regs = self.qregs if quantum else self.cregs
        kind = "quantum" if quantum else "classical"
        if not m:
            self.error(f"Cannot read {kind} argument '{arg.strip()}'", line)
            return None
        name, idx = m.group(1), m.group(2)
        if name not in regs:
            other = self.cregs if quantum else self.qregs
            if name in other:
                self.error(f"'{name}' is a {'classical' if quantum else 'quantum'} register; expected a {kind} one", line, "wrong_register")
            else:
                self.error(f"Unknown {kind} register '{name}'", line, "undeclared")
            return None
        off, size = regs[name]
        if idx is None:
            return list(range(off, off + size))
        i = int(idx)
        if i >= size:
            self.error(f"Index {name}[{i}] is out of range: '{name}' has {size} {'qubit' if quantum else 'bit'}{'s' if size != 1 else ''}", line, "out_of_range")
            return None
        return [off + i]

    # main entry
    def parse(self, text: str) -> Circuit | None:
        stmts, trailing = _statements(_strip_comments(text))
        for s, line in stmts:
            if s:
                try:
                    self._statement(s, line)
                except ValueError as exc:
                    self.error(str(exc), line)
        if trailing:
            self.error(f"Missing ';' at the end of '{trailing[0][:40]}'", trailing[1])
        if self.version is None and (stmts or trailing):
            self.info("No OPENQASM header found; assuming OpenQASM 2.0", 1, "header")
        if self.nq == 0 and not any(i.severity == "error" for i in self.issues):
            self.error("No qubits declared (add e.g. 'qreg q[2];' or 'qubit[2] q;')", None, "no_qubits")
        if any(i.severity == "error" for i in self.issues):
            return None
        measurements = sorted(((q, c) for c, (q, _) in self.meas.items()), key=lambda qc: qc[1])
        return Circuit(num_qubits=self.nq, gates=self.gates, num_clbits=self.nc, measurements=measurements)

    def _statement(self, s: str, line: int) -> None:
        head = s.split(None, 1)[0] if s.split() else ""
        if s.startswith("OPENQASM"):
            ver = s[len("OPENQASM"):].strip()
            if not re.fullmatch(r"[23](\.\d+)?", ver):
                self.error(f"Unsupported OpenQASM version '{ver}'", line, "header")
            self.version = ver
            return
        if head == "include":
            lib = s[len("include"):].strip().strip('"')
            if lib not in ("qelib1.inc", "stdgates.inc"):
                self.warning(f"Include '{lib}' is not available; only the standard gate library is built in", line, "include")
            return
        if head in ("qreg", "creg"):
            m = re.fullmatch(r"(qreg|creg)\s+([A-Za-z_]\w*)\s*\[\s*(\d+)\s*\]", s)
            if not m:
                raise ValueError(f"Bad register declaration '{s}' (expected e.g. '{head} name[3]')")
            self._declare("q" if head == "qreg" else "c", m.group(2), int(m.group(3)), line)
            return
        m = re.fullmatch(r"(qubit|bit)\s*(?:\[\s*(\d+)\s*\])?\s+([A-Za-z_]\w*)", s)
        if m:
            self._declare("q" if m.group(1) == "qubit" else "c", m.group(3), int(m.group(2) or 1), line)
            return
        if head == "gate":
            self._definition(s, line)
            return
        if "=" in s and re.search(r"\bmeasure\b", s):
            left, right = s.split("=", 1)
            right = right.strip()
            if not right.startswith("measure"):
                raise ValueError("Expected 'bits = measure qubits'")
            self._measure(right[len("measure"):].strip(), left.strip(), line)
            return
        if head == "measure":
            body = s[len("measure"):].strip()
            if "->" in body:
                q, c = (x.strip() for x in body.split("->", 1))
                self._measure(q, c, line)
            else:
                self._measure(body, None, line)
            return
        if head == "barrier":
            for a in _split_top(s[len("barrier"):]):
                self._resolve(a, line, quantum=True)
            return
        if head == "gphase":
            self.info("Global phase (gphase) has no observable effect and is ignored", line, "ignored")
            return
        if head in _UNSUPPORTED:
            self.error(_UNSUPPORTED[head], line, "unsupported")
            return
        if head in _CLASSICAL_DECL:
            self.error("Classical variables are not supported; use literal parameter values", line, "unsupported")
            return
        if "@" in s:
            self.error("Gate modifiers (ctrl @, inv @, pow @) are not supported; use explicit gates", line, "unsupported")
            return
        self._call_statement(s, line)

    # gate definitions
    def _definition(self, s: str, line: int) -> None:
        m = re.fullmatch(r"gate\s+([A-Za-z_]\w*)\s*(?:\(([^)]*)\))?\s*([^{]*)\{(.*)\}", s, re.S)
        if not m:
            raise ValueError("Bad gate definition (expected 'gate name(params) a, b { ... }')")
        name = m.group(1)
        params = [p.strip() for p in (m.group(2) or "").split(",") if p.strip()]
        args = [a.strip() for a in m.group(3).split(",") if a.strip()]
        body = [b.strip() for b in m.group(4).split(";") if b.strip()]
        if not args:
            raise ValueError(f"Gate definition '{name}' has no qubit arguments")
        if canonical_name(name) in GATE_SPECS:
            return  # built-in implementation wins (Qiskit sometimes re-defines standard gates)
        self.defs[name] = (params, args, body, line)

    # measurements
    def _measure(self, qarg: str, carg: str | None, line: int) -> None:
        qs = self._resolve(qarg, line, quantum=True)
        if qs is None:
            return
        if carg is None:
            cs = qs if self.nc >= (max(qs) + 1) else None
            if cs is None:
                self.error("Measurement has no classical target; write 'measure q -> c;' or 'c = measure q;'", line, "measure")
                return
        else:
            cs = self._resolve(carg, line, quantum=False)
            if cs is None:
                return
        if len(qs) != len(cs):
            self.error(f"Measuring {len(qs)} qubit(s) into {len(cs)} bit(s): sizes must match", line, "measure")
            return
        for q, c in zip(qs, cs):
            if c in self.meas:
                self.warning(f"Classical bit {c} is written twice; the last measurement wins", line, "double_write")
            self.meas[c] = (q, line)
            self.measured.add(q)

    # gate calls
    def _call_statement(self, s: str, line: int) -> None:
        name, ptxt, atxt = _split_call(s)
        args = _split_top(atxt) if atxt else []
        if not args:
            raise ValueError(f"Gate '{name}' is missing its qubit arguments")
        try:
            params = [eval_expr(p) for p in _split_top(ptxt)] if ptxt is not None else []
        except (ValueError, SyntaxError, ZeroDivisionError) as exc:
            self.error(f"Cannot evaluate parameter of '{name}': {exc}", line, "parameter")
            return
        lists = [self._resolve(a, line, quantum=True) for a in args]
        if any(x is None for x in lists):
            return
        self._apply(name, params, lists, line, 0)  # type: ignore[arg-type]

    def _apply(self, name: str, params: list[float], lists: list[list[int]], line: int, depth: int) -> None:
        canon = canonical_name(name)
        if canon not in GATE_SPECS and name in self.defs:
            self._expand(name, params, lists, line, depth)
            return
        if canon not in GATE_SPECS:
            pool = list(GATE_SPECS) + list(self.defs)
            hint = _HINTS.get(name.lower()) or next(iter(difflib.get_close_matches(name.lower(), pool, n=1)), None)
            self.error(f"Unknown gate '{name}'" + (f". Did you mean '{hint}'?" if hint else ""), line, "unknown_gate")
            return
        nq, npar = GATE_SPECS[canon]
        if len(lists) != nq:
            self.error(f"'{name}' acts on {nq} qubit(s) but got {len(lists)}", line, "arity")
            return
        if len(params) != npar:
            self.error(f"'{name}' needs {npar} parameter(s) but got {len(params)}", line, "parameter")
            return
        sizes = {len(x) for x in lists if len(x) > 1}
        if len(sizes) > 1:
            self.error("Register arguments of different sizes cannot be broadcast together", line, "broadcast")
            return
        reps = sizes.pop() if sizes else 1
        for r in range(reps):
            qs = tuple(x[r] if len(x) > 1 else x[0] for x in lists)
            if len(set(qs)) != len(qs):
                self.error(f"'{name}' uses the same qubit twice ({', '.join(f'q[{q}]' for q in qs)})", line, "duplicate_qubit")
                return
            for q in qs:
                if q in self.measured and q not in self.mid_reported:
                    self.mid_reported.add(q)
                    self.error(f"Qubit {q} is used after being measured; mid-circuit measurement is not supported yet", line, "mid_circuit_measurement")
            if canon in DECOMPOSITIONS:
                for g, idx in DECOMPOSITIONS[canon]:
                    self.gates.append(Gate(g, tuple(qs[i] for i in idx), (), line))
            else:
                self.gates.append(Gate(canon, qs, tuple(params), line))

    def _expand(self, name: str, params: list[float], lists: list[list[int]], line: int, depth: int) -> None:
        if depth > self.MAX_EXPANSION_DEPTH:
            self.error(f"Gate '{name}' expands too deeply (recursive definition?)", line, "definition")
            return
        pnames, anames, body, _ = self.defs[name]
        if len(params) != len(pnames) or len(lists) != len(anames):
            self.error(f"'{name}' expects {len(pnames)} parameter(s) and {len(anames)} qubit(s)", line, "arity")
            return
        sizes = {len(x) for x in lists if len(x) > 1}
        if len(sizes) > 1:
            self.error("Register arguments of different sizes cannot be broadcast together", line, "broadcast")
            return
        reps = sizes.pop() if sizes else 1
        env = dict(zip(pnames, params))
        for r in range(reps):
            qmap = {a: (x[r] if len(x) > 1 else x[0]) for a, x in zip(anames, lists)}
            for stmt in body:
                inner, ptxt, atxt = _split_call(stmt)
                if inner == "barrier":
                    continue
                try:
                    vals = [eval_expr(p, env) for p in _split_top(ptxt)] if ptxt is not None else []
                except (ValueError, SyntaxError, ZeroDivisionError) as exc:
                    self.error(f"Cannot evaluate parameter inside '{name}': {exc}", line, "parameter")
                    return
                inner_args = _split_top(atxt)
                if any(a not in qmap for a in inner_args):
                    self.error(f"Definition of '{name}' uses an unknown argument", line, "definition")
                    return
                self._apply(inner, vals, [[qmap[a]] for a in inner_args], line, depth + 1)


def parse_qasm(text: str, name: str = "circuit") -> tuple[Circuit | None, list[Issue]]:
    """Parse QASM text. Returns (circuit or None, issues). Never raises on bad input."""
    p = _Parser()
    circuit = p.parse(text or "")
    if circuit is not None:
        circuit.name = name
    return circuit, p.issues


def load_qasm(text: str, name: str = "circuit") -> Circuit:
    """Parse QASM text and raise :class:`QasmError` if it contains errors."""
    circuit, issues = parse_qasm(text, name)
    if circuit is None:
        raise QasmError(issues)
    return circuit
