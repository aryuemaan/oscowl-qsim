import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { FileCode2, RotateCcw } from "lucide-react";
import { api, ApiError } from "./api";
import { AIPanel } from "./components/AIPanel";
import { AIStack } from "./components/AIStack";
import { Benchmarks } from "./components/Benchmarks";
import { CircuitEditor, type EditorHandle } from "./components/CircuitEditor";
import { IssuesList } from "./components/IssuesList";
import { NoisePanel, PRESETS } from "./components/NoisePanel";
import { Results } from "./components/Results";
import { RunPanel, type Stages } from "./components/RunPanel";
import { bytes } from "./format";
import type { AgentResult, Example, Explanation, Health, Issue, Noise, RunOptions, SimResult, ValidateResult } from "./types";

type Page = "workbench" | "benchmarks" | "stack";
const DEFAULT_EXAMPLE = "ansatz_redundant_8";
const IDLE: Stages = { validate: "idle", gemma: "idle", simulate: "idle" };

function toNoise(n: Example["noise"]): Noise {
  return { p1: n.p1, p2: n.p2, amplitude_damping: n.amplitude_damping, readout_p01: n.readout, readout_p10: n.readout };
}

function issuesFrom(err: unknown): Issue[] {
  if (err instanceof ApiError && err.detail && typeof err.detail === "object" && "issues" in err.detail) {
    return (err.detail as { issues: Issue[] }).issues;
  }
  return [];
}

export default function App() {
  const [page, setPage] = useState<Page>("workbench");
  const [health, setHealth] = useState<Health | null>(null);
  const [backendDown, setBackendDown] = useState(false);
  const [examples, setExamples] = useState<Example[]>([]);
  const [exampleId, setExampleId] = useState(DEFAULT_EXAMPLE);
  const [qasm, setQasm] = useState("");
  const [noise, setNoise] = useState<Noise>(PRESETS.NISQ);
  const [options, setOptions] = useState<RunOptions>({ shots: 1024, trajectories: 64, backend: "auto", max_bond: 64, seed: null });
  const [validation, setValidation] = useState<ValidateResult | null>(null);
  const [aiIssues, setAiIssues] = useState<Issue[]>([]);
  const [result, setResult] = useState<SimResult | null>(null);
  const [explanation, setExplanation] = useState<Explanation | null>(null);
  const [agent, setAgent] = useState<AgentResult | null>(null);
  const [stages, setStages] = useState<Stages>(IDLE);
  const [busy, setBusy] = useState({ run: false, explain: false, debug: false });
  const [error, setError] = useState<string | null>(null);
  const [aiError, setAiError] = useState<string | null>(null);
  const [focusLine, setFocusLine] = useState<number | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const editor = useRef<EditorHandle>(null);

  // initial load
  useEffect(() => {
    api.health().then(setHealth).catch(() => setBackendDown(true));
    api.examples().then((ex) => {
      setExamples(ex);
      const first = ex.find((e) => e.id === DEFAULT_EXAMPLE) ?? ex[0];
      if (first) { setQasm(first.qasm); setNoise(toNoise(first.noise)); }
    }).catch(() => setBackendDown(true));
  }, []);

  // live validation (deterministic, no AI) while typing
  useEffect(() => {
    if (!qasm) return;
    const t = setTimeout(() => {
      api.validate(qasm).then((v) => { setValidation(v); setAiIssues([]); }).catch(() => undefined);
    }, 350);
    return () => clearTimeout(t);
  }, [qasm]);

  const issues = useMemo(() => [...(validation?.issues ?? []), ...aiIssues], [validation, aiIssues]);
  const hasErrors = issues.some((i) => i.severity === "error");
  const gemmaOn = !!health && health.ai.gemma_provider !== "off";

  const loadExample = (id: string) => {
    const ex = examples.find((e) => e.id === id);
    if (!ex) return;
    setExampleId(id);
    setQasm(ex.qasm);
    setNoise(toNoise(ex.noise));
    setResult(null); setExplanation(null); setAgent(null); setStages(IDLE); setError(null); setFocusLine(null); setNotice(null);
  };

  const jump = useCallback((line: number) => { setFocusLine(line); editor.current?.focusLine(line); }, []);

  const run = async () => {
    setBusy((b) => ({ ...b, run: true })); setError(null); setNotice(null);
    setExplanation(null); setAgent(null); setAiError(null);
    setStages({ validate: "run", gemma: "idle", simulate: "idle" });
    try {
      const v = await api.validate(qasm);
      setValidation(v);
      if (!v.ok) { setStages({ validate: "fail", gemma: "idle", simulate: "idle" }); return; }
      let st: Stages = { validate: "done", gemma: gemmaOn ? "run" : "skip", simulate: gemmaOn ? "idle" : "run" };
      setStages(st);
      if (gemmaOn) {
        const g = await api.validate(qasm, true);
        setAiIssues(g.issues.filter((i) => i.source === "gemma"));
        st = { ...st, gemma: g.ai.used ? "done" : "skip", simulate: "run" };
        setStages(st);
      }
      const r = await api.simulate(qasm, noise, options);
      setResult(r);
      setStages({ ...st, simulate: "done" });
    } catch (e) {
      setStages((s) => ({ ...s, simulate: "fail" }));
      const extra = issuesFrom(e);
      if (extra.length) setValidation((v) => (v ? { ...v, ok: false, issues: extra } : v));
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy((b) => ({ ...b, run: false }));
    }
  };

  const explain = async () => {
    if (!result) return;
    setBusy((b) => ({ ...b, explain: true })); setAiError(null);
    try { setExplanation(await api.explain(qasm, noise, options, result)); }
    catch (e) { setAiError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy((b) => ({ ...b, explain: false })); }
  };

  const debug = async () => {
    setBusy((b) => ({ ...b, debug: true })); setAiError(null);
    try { setAgent(await api.debug(qasm, noise, options)); }
    catch (e) { setAiError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy((b) => ({ ...b, debug: false })); }
  };

  const applyFix = (fixed: string) => {
    setQasm(fixed);
    setResult(null); setExplanation(null); setStages(IDLE); setFocusLine(null);
    setNotice("Fixed circuit loaded into the editor. Press Run simulation to see the new results.");
  };

  const st = validation?.stats;
  const ai = health?.ai;
  return (
    <>
      <header className="header">
        <div className="brand">
          <img src="/favicon.svg" width={26} height={26} alt="" />
          <span>OSCOWL Q-Sim <small>tensor-network quantum debugger</small></span>
        </div>
        <nav className="nav">
          {([["workbench", "Workbench"], ["benchmarks", "Benchmarks"], ["stack", "AI stack"]] as [Page, string][]).map(([k, label]) => (
            <button key={k} className={page === k ? "active" : ""} onClick={() => setPage(k)}>{label}</button>
          ))}
        </nav>
        <div className="spacer" />
        {backendDown && <span className="pill" style={{ color: "var(--bad)" }}><span className="dot" />Backend not reachable on :8000</span>}
        {ai && (
          <>
            <span className={`pill ${ai.mode === "gemini" ? "on" : ""}`} title={ai.last_error ?? ""}>
              <span className="dot" />{ai.mode === "gemini" ? `Gemini: ${ai.flash_model} · ${ai.reasoning_model}` : "AI: offline rules"}
            </span>
            <span className={`pill ${ai.gemma_provider !== "off" ? "on" : ""}`}><span className="dot" />Gemma: {ai.gemma_provider === "off" ? "off" : ai.gemma_model}</span>
          </>
        )}
      </header>

      <main className="page">
        {page === "benchmarks" && <Benchmarks />}
        {page === "stack" && <AIStack health={health} />}
        {page === "workbench" && (
          <div className="workbench">
            <div className="stack">
              <div className="card">
                <div className="card-head">
                  <h2><FileCode2 size={16} /> Circuit</h2>
                  <div className="grow" />
                  <select value={exampleId} onChange={(e) => loadExample(e.target.value)} aria-label="Example circuits" style={{ maxWidth: 260 }}>
                    {examples.map((e) => <option key={e.id} value={e.id}>{e.title}</option>)}
                  </select>
                  <button className="btn" title="Reload example" onClick={() => loadExample(exampleId)}><RotateCcw size={15} /></button>
                </div>
                <div className="card-body small muted" style={{ paddingTop: 10, paddingBottom: 10 }}>
                  {examples.find((e) => e.id === exampleId)?.description ?? "Paste OpenQASM 2.0 or 3.0. Qiskit users: qiskit.qasm2.dumps(circuit)."}
                </div>
                <CircuitEditor ref={editor} value={qasm} onChange={(v) => { setQasm(v); setFocusLine(null); }} issues={issues} focusLine={focusLine} />
                {st && (
                  <div className="statsbar">
                    <span><b>{st.num_qubits}</b> qubits</span><span><b>{st.num_gates}</b> gates</span>
                    <span><b>{st.two_qubit_gates}</b> two-qubit</span><span>depth <b>{st.depth}</b></span>
                    {validation?.plan && <span>planner: <b>{validation.plan.backend === "mps" ? "tensor network" : "dense"}</b>
                      {validation.plan.backend === "mps" ? ` (bond ≤ ${validation.plan.predicted_max_bond > 1e6 ? "1e6+" : validation.plan.predicted_max_bond.toLocaleString()})` : ` (${bytes(validation.plan.statevector_bytes)})`}</span>}
                  </div>
                )}
                <IssuesList issues={issues} onJump={jump} />
              </div>
            </div>

            <div className="stack">
              <NoisePanel noise={noise} onChange={setNoise} />
              <RunPanel options={options} onChange={setOptions} onRun={run} running={busy.run} disabled={!qasm || hasErrors || backendDown}
                stages={stages} gemmaLabel={gemmaOn ? "Gemma pre-check" : "Gemma pre-check (off)"} />
              {error && <div className="error-box">{error}</div>}
              {notice && <div className="note">{notice}</div>}
              <Results result={result} onJump={jump} />
              <AIPanel explanation={explanation} agent={agent} explaining={busy.explain} debugging={busy.debug}
                canExplain={!!result} canDebug={!!qasm && !hasErrors && !backendDown} onExplain={explain} onDebug={debug}
                onApply={applyFix} error={aiError} />
            </div>
          </div>
        )}
      </main>
    </>
  );
}
