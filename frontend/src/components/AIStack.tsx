import { useEffect, useState } from "react";
import { Layers } from "lucide-react";
import { api } from "../api";
import type { Health, Skill } from "../types";

export function AIStack({ health }: { health: Health | null }) {
  const [skills, setSkills] = useState<Skill[]>([]);
  useEffect(() => { api.skills().then(setSkills).catch(() => setSkills([])); }, []);
  const ai = health?.ai;
  const rows = [
    ["Gemma 4 (pre-check)", !ai ? "-" : ai.gemma_provider === "off" ? `${ai.gemma_model} (off: needs GEMINI_API_KEY or Ollama)` : `${ai.gemma_model} via ${ai.gemma_provider}`, "Fast syntax and logic check before any compute starts"],
    ["Gemini Flash (explainer)", ai?.flash_model ?? "-", "Turns the error budget into a plain-English diagnosis"],
    ["Gemini reasoning (debugger)", ai?.reasoning_model ?? "-", "Proposes equivalent rewrites; every one is verified by simulation"],
    ["Tensor-network core", health ? `MPS on ${health.array_backend} (${health.array_backends.join(", ")} available)` : "-", "JAX/XLA on Cloud TPU/GPU for large jobs"],
  ];
  return (
    <div className="stack">
      <div className="card">
        <div className="card-head"><h2><Layers size={16} /> AI stack in this deployment</h2><div className="grow" />
          <span className={`pill ${ai?.mode === "gemini" ? "on" : ""}`}><span className="dot" />{ai?.mode === "gemini" ? `Gemini via ${ai.via}` : "Offline mode"}</span></div>
        <div className="card-body">
          {ai?.mode !== "gemini" && (
            <div className="note warn" style={{ marginBottom: 12 }}>
              No Gemini credentials found, so explanations and fixes use built-in rules. Add <code>GEMINI_API_KEY</code> to <code>.env</code> and
              restart the backend to switch on Gemini and Gemma (see docs/GOOGLE_AI_SETUP.md).
            </div>
          )}
          {ai?.last_error && <div className="note bad" style={{ marginBottom: 12 }}>Last AI error: {ai.last_error}</div>}
          <table className="simple">
            <thead><tr><th>Component</th><th>Model / engine</th><th>Job</th></tr></thead>
            <tbody>{rows.map((r) => <tr key={r[0]}><td><b>{r[0]}</b></td><td className="mono">{r[1]}</td><td>{r[2]}</td></tr>)}</tbody>
          </table>
        </div>
      </div>
      <div className="card">
        <div className="card-head"><h2>Agent Skills</h2><span className="small muted">Open Agent Skills format; loaded into prompts only when a task needs them</span></div>
        <div className="card-body grid2">
          {skills.map((s) => (
            <div className="skill" key={s.name}><code>{s.name}</code><div style={{ marginTop: 4 }}>{s.description}</div>
              <div className="small muted" style={{ marginTop: 4 }}>backend/{s.path}</div></div>
          ))}
        </div>
      </div>
    </div>
  );
}
