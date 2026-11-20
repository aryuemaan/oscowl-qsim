import { useState } from "react";
import {
  Bot, CircleCheck, CircleX, FileCode2, Info, LoaderCircle, Search, ShieldCheck, Sparkles, Stethoscope, TriangleAlert, WandSparkles,
} from "lucide-react";
import { ms, pct } from "../format";
import type { AgentResult, AgentStep, Explanation, Snapshot } from "../types";

interface Props {
  explanation: Explanation | null;
  agent: AgentResult | null;
  explaining: boolean;
  debugging: boolean;
  canExplain: boolean;
  canDebug: boolean;
  onExplain: () => void;
  onDebug: () => void;
  onApply: (qasm: string) => void;
  error: string | null;
}

export function AIPanel(p: Props) {
  const [view, setView] = useState<"explain" | "agent">("explain");
  const showAgent = view === "agent";
  return (
    <div className="card">
      <div className="card-head">
        <h2><Sparkles size={16} /> AI debugger</h2>
        <div className="grow" />
        <button className="btn soft" onClick={() => { setView("explain"); p.onExplain(); }} disabled={!p.canExplain || p.explaining}>
          {p.explaining ? <LoaderCircle size={15} className="spin" /> : <Search size={15} />} Explain results
        </button>
        <button className="btn primary" onClick={() => { setView("agent"); p.onDebug(); }} disabled={!p.canDebug || p.debugging}>
          {p.debugging ? <LoaderCircle size={15} className="spin" /> : <WandSparkles size={15} />} Run debug agent
        </button>
      </div>
      <div className="tabs">
        <button className={!showAgent ? "active" : ""} onClick={() => setView("explain")}>Explanation</button>
        <button className={showAgent ? "active" : ""} onClick={() => setView("agent")}>Debug agent</button>
      </div>
      <div className="card-body">
        {p.error && <div className="error-box" style={{ marginBottom: 12 }}>{p.error}</div>}
        {!showAgent ? <ExplanationView e={p.explanation} busy={p.explaining} /> : <AgentView a={p.agent} busy={p.debugging} onApply={p.onApply} />}
      </div>
    </div>
  );
}

function SourceBadge({ source, model }: { source: string; model?: string }) {
  const online = source === "gemini" || source === "gemma";
  return <span className={`pill ${online ? "on" : ""}`}><span className="dot" />{online ? `${model ?? source}` : "Offline rules"}</span>;
}

function ExplanationView({ e, busy }: { e: Explanation | null; busy: boolean }) {
  if (busy) return <div className="empty"><LoaderCircle className="spin" size={18} /> Analysing the error budget...</div>;
  if (!e) return <div className="empty">Run a simulation, then press <b>Explain results</b> for a plain-English diagnosis.</div>;
  return (
    <div className="stack" style={{ gap: 12 }}>
      <div className="row"><span className="chip">{e.intent}</span><SourceBadge source={e.source} model={e.model} />
        {e.latency_ms ? <span className="small muted">{ms(e.latency_ms)}</span> : null}</div>
      <div style={{ fontSize: 15, fontWeight: 550 }}>{e.summary}</div>
      <div>{e.noise_explanation}</div>
      <div className="grid2">
        <div><div className="chart-title">Key findings</div><ul className="tight">{e.key_findings.map((x, i) => <li key={i}>{x}</li>)}</ul></div>
        <div><div className="chart-title">Suggested fixes</div><ul className="tight">{e.suggestions.map((x, i) => <li key={i}>{x}</li>)}</ul></div>
      </div>
      {e.note && <div className="small muted">{e.note}</div>}
    </div>
  );
}

const PHASE_ICON = { validate: ShieldCheck, diagnose: Stethoscope, propose: Bot, verify: ShieldCheck, explain: Sparkles };

function StepRow({ s }: { s: AgentStep }) {
  const Icon = s.status === "accepted" ? CircleCheck : s.status === "rejected" || s.status === "error" ? CircleX
    : s.status === "warn" ? TriangleAlert : PHASE_ICON[s.phase] ?? Info;
  return (
    <div className={`step ${s.status}`}>
      <div className="icon"><Icon size={15} /></div>
      <div>
        <div className="title">{s.title}
          {(s.status === "accepted" || s.status === "rejected" || s.status === "error") && <span className={`chip ${s.status}`}>{s.status}</span>}
          <span className="chip">{s.phase}</span>
          <span className="small muted">{s.source}{s.duration_ms > 1 ? ` · ${ms(s.duration_ms)}` : ""}</span>
        </div>
        <div className="detail">{s.detail}</div>
      </div>
    </div>
  );
}

function Delta({ label, a, b, fmt, higherIsBetter }: { label: string; a: number; b: number; fmt: (x: number) => string; higherIsBetter: boolean }) {
  const better = higherIsBetter ? b > a : b < a;
  const same = Math.abs(b - a) < 1e-12;
  return (
    <div className="metric">
      <div className="k">{label}</div>
      <div className="v">{fmt(b)}</div>
      <div className={`s ${same ? "" : better ? "up" : "down"}`}>was {fmt(a)}</div>
    </div>
  );
}

function Comparison({ before, after }: { before: Snapshot; after: Snapshot }) {
  return (
    <div className="compare">
      <Delta label="State fidelity" a={before.state_fidelity} b={after.state_fidelity} fmt={(x) => pct(x)} higherIsBetter />
      <Delta label="Est. success" a={before.esp} b={after.esp} fmt={(x) => pct(x)} higherIsBetter />
      <Delta label="Two-qubit gates" a={before.two_qubit_gates} b={after.two_qubit_gates} fmt={(x) => String(x)} higherIsBetter={false} />
      <Delta label="Depth" a={before.depth} b={after.depth} fmt={(x) => String(x)} higherIsBetter={false} />
    </div>
  );
}

function AgentView({ a, busy, onApply }: { a: AgentResult | null; busy: boolean; onApply: (q: string) => void }) {
  if (busy) return <div className="empty"><LoaderCircle className="spin" size={18} /> Diagnosing, proposing fixes and verifying each one by simulation...</div>;
  if (!a) return <div className="empty">The agent validates the circuit, diagnoses the noise, proposes fixes and <b>accepts only those that simulation proves</b> are equivalent and better.</div>;
  return (
    <div className="stack" style={{ gap: 12 }}>
      {a.before && a.after && <Comparison before={a.before} after={a.after} />}
      {a.after?.hellinger_mitigated !== undefined && (
        <div className="note">Readout mitigation raises output fidelity to <b>{pct(a.after.hellinger_mitigated)}</b> (from {pct(a.after.hellinger)}).</div>
      )}
      {a.explanation && <div className="note"><b>Summary: </b>{a.explanation.text}</div>}
      {a.changed && (
        <div className="row">
          <button className="btn primary" onClick={() => onApply(a.final_qasm)}><FileCode2 size={15} /> Load fixed circuit into editor</button>
          <span className="small muted">{a.accepted.length} verified fix(es) · {a.rejected.length} rejected · {a.duration_ms ? ms(a.duration_ms) : ""}</span>
        </div>
      )}
      <div className="timeline">{a.steps.map((s) => <StepRow key={s.id} s={s} />)}</div>
    </div>
  );
}
