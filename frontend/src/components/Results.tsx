import { useState } from "react";
import { BarChart3 } from "lucide-react";
import {
  Bar, BarChart, CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { bytes, ms, pct, shortBits } from "../format";
import type { SimResult } from "../types";

const ACCENT = "#5b3cc4";
const ACCENT_MID = "#b9adeb";
const AXIS = { fontSize: 11, fill: "#5f5f73" };

type Tab = "overview" | "outcomes" | "noise" | "tn";

export function Results({ result, onJump }: { result: SimResult | null; onJump: (line: number) => void }) {
  const [tab, setTab] = useState<Tab>("overview");
  return (
    <div className="card">
      <div className="card-head"><h2><BarChart3 size={16} /> Results</h2></div>
      {!result ? (
        <div className="empty">Pick an example or paste a circuit, then press <b>Run simulation</b>.</div>
      ) : (
        <>
          <div className="tabs">
            {([["overview", "Overview"], ["outcomes", "Measured outcomes"], ["noise", "Noise impact"], ["tn", "Tensor network"]] as [Tab, string][]).map(([k, label]) => (
              <button key={k} className={tab === k ? "active" : ""} onClick={() => setTab(k)}>{label}</button>
            ))}
          </div>
          <div className="card-body">
            {tab === "overview" && <Overview r={result} />}
            {tab === "outcomes" && <Outcomes r={result} />}
            {tab === "noise" && <NoiseImpact r={result} onJump={onJump} />}
            {tab === "tn" && <TensorNetwork r={result} />}
          </div>
        </>
      )}
    </div>
  );
}

function Overview({ r }: { r: SimResult }) {
  const f = r.fidelity;
  return (
    <div className="stack" style={{ gap: 14 }}>
      <div className="metrics">
        <div className="metric"><div className="k">State fidelity</div><div className="v">{pct(f.state)}</div>
          <div className="s">± {pct(f.state_stderr)} over {r.trajectories || 1} trajectories</div></div>
        <div className="metric"><div className="k">Output fidelity (Hellinger)</div><div className="v">{pct(f.hellinger)}</div>
          <div className="s" title={f.hellinger_method}>{f.hellinger === null ? "outcomes too spread" : "vs exact ideal distribution"}</div></div>
        <div className="metric"><div className="k">Est. success probability</div><div className="v">{pct(f.esp)}</div>
          <div className="s">first-order error budget</div></div>
        <div className="metric"><div className="k">Simulation error bound</div><div className="v">{f.error_bound < 1e-12 ? "exact" : pct(f.error_bound, 3)}</div>
          <div className="s">{r.backend === "mps" ? "from MPS truncation" : "dense simulation"}</div></div>
      </div>
      <div className="note">{r.plan.reason}</div>
      <dl className="kv">
        <dt>Backend</dt><dd>{r.backend === "mps" ? `Tensor network (MPS), max bond ${r.tensor_network.max_bond_used} of ${r.plan.max_bond}` : "Dense state vector"} · {r.array_backend}</dd>
        <dt>Memory used</dt><dd><b>{bytes(r.memory.used_bytes)}</b> <span className="muted">vs {bytes(r.memory.dense_equivalent_bytes)} for a dense state vector</span></dd>
        <dt>Run time</dt><dd>{ms(r.timing.total_ms)} <span className="muted">(ideal {ms(r.timing.ideal_ms)}, noisy {ms(r.timing.noisy_ms)})</span></dd>
        <dt>Circuit</dt><dd>{r.circuit.num_qubits} qubits · {r.circuit.num_gates} gates ({r.circuit.two_qubit_gates} two-qubit) · depth {r.circuit.depth}</dd>
        <dt>Suggested hardware</dt><dd>{r.plan.hardware}</dd>
        <dt>Shots / seed</dt><dd>{r.shots} shots · seed {r.seed} · {r.num_outcomes} distinct outcomes</dd>
      </dl>
      {r.warnings.map((w, i) => <div key={i} className="note warn">{w}</div>)}
    </div>
  );
}

function Outcomes({ r }: { r: SimResult }) {
  const data = r.outcomes.slice(0, 16).map((o) => ({ name: shortBits(o.bitstring), full: o.bitstring, Noisy: o.noisy, Ideal: o.ideal }));
  return (
    <div>
      <div className="chart-title">Most likely outcomes: noisy simulation vs ideal</div>
      <ResponsiveContainer width="100%" height={300}>
        <BarChart data={data} margin={{ top: 8, right: 8, bottom: 40, left: 0 }}>
          <CartesianGrid vertical={false} stroke="#eee" />
          <XAxis dataKey="name" tick={AXIS} angle={-35} textAnchor="end" interval={0} height={60} />
          <YAxis tick={AXIS} tickFormatter={(v) => `${Math.round(v * 100)}%`} />
          <Tooltip formatter={(v) => pct(Number(v), 2)} labelFormatter={(_, p) => (p?.[0]?.payload?.full as string) ?? ""} />
          <Legend wrapperStyle={{ fontSize: 12 }} verticalAlign="top" />
          <Bar dataKey="Ideal" fill={ACCENT_MID} radius={[3, 3, 0, 0]} />
          <Bar dataKey="Noisy" fill={ACCENT} radius={[3, 3, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
      <div className="small muted">{r.measurement.bit_order}. {r.num_outcomes} distinct noisy outcomes in {r.shots} shots.</div>
    </div>
  );
}

function NoiseImpact({ r, onJump }: { r: SimResult; onJump: (line: number) => void }) {
  const b = r.budget;
  if (!b.by_source.length) return <div className="empty">No noise configured: choose a noise preset to see where fidelity is lost.</div>;
  const sources = b.by_source.map((s) => ({ name: s.source, share: s.share }));
  const types = b.by_gate_type.slice(0, 8).map((t) => ({ name: `${t.gate} ×${t.count}`, share: t.share }));
  return (
    <div className="stack" style={{ gap: 14 }}>
      <div className="grid2">
        <div>
          <div className="chart-title">Error budget by noise source</div>
          <ResponsiveContainer width="100%" height={170}>
            <BarChart data={sources} layout="vertical" margin={{ left: 10, right: 30 }}>
              <XAxis type="number" tick={AXIS} tickFormatter={(v) => `${Math.round(v * 100)}%`} domain={[0, 1]} />
              <YAxis type="category" dataKey="name" tick={AXIS} width={120} />
              <Tooltip formatter={(v) => pct(Number(v))} />
              <Bar dataKey="share" fill={ACCENT} radius={[0, 3, 3, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
        <div>
          <div className="chart-title">Error budget by gate type</div>
          <ResponsiveContainer width="100%" height={170}>
            <BarChart data={types} layout="vertical" margin={{ left: 10, right: 30 }}>
              <XAxis type="number" tick={AXIS} tickFormatter={(v) => `${Math.round(v * 100)}%`} domain={[0, 1]} />
              <YAxis type="category" dataKey="name" tick={AXIS} width={80} />
              <Tooltip formatter={(v) => pct(Number(v))} />
              <Bar dataKey="share" fill={ACCENT_MID} radius={[0, 3, 3, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
      <div>
        <div className="chart-title">Hotspot gates (click to jump to the line)</div>
        <table className="simple">
          <thead><tr><th>Line</th><th>Gate</th><th>Error chance</th><th style={{ width: "35%" }}>Share of budget</th></tr></thead>
          <tbody>
            {b.hotspots.slice(0, 8).map((h) => (
              <tr key={h.index} className="click" onClick={() => h.line && onJump(h.line)}>
                <td className="mono">{h.line ?? "-"}</td>
                <td className="mono">{h.label}</td>
                <td>{pct(h.error, 2)}</td>
                <td><div className="row" style={{ gap: 8, flexWrap: "nowrap" }}>
                  <div className="bar" style={{ width: `${Math.max(4, h.share * 300)}%`, maxWidth: "80%" }} />{pct(h.share)}</div></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="small muted">{b.model_note} Average noise events per trajectory: {r.noise_events_mean.toFixed(2)}.</div>
    </div>
  );
}

function TensorNetwork({ r }: { r: SimResult }) {
  const tn = r.tensor_network;
  if (r.backend !== "mps" || !tn.bond_dims) {
    return (
      <div className="stack" style={{ gap: 10 }}>
        <div className="note">This run used the exact dense state vector ({bytes(r.memory.used_bytes)}). Switch the backend to
          <b> Tensor network (MPS)</b> to see bond dimensions and entanglement per cut.</div>
        <div className="small muted">Planner prediction: max bond dimension {r.plan.predicted_max_bond.toLocaleString()} for this circuit.</div>
      </div>
    );
  }
  const data = tn.bond_dims.map((d, i) => ({ cut: `${i}|${i + 1}`, Bond: d, Entropy: tn.entropies?.[i] ?? 0 }));
  return (
    <div className="stack" style={{ gap: 10 }}>
      <div className="chart-title">Bond dimension and entanglement entropy across each cut of the qubit chain</div>
      <ResponsiveContainer width="100%" height={280}>
        <ComposedChart data={data} margin={{ top: 8, right: 8, bottom: 8, left: 0 }}>
          <CartesianGrid vertical={false} stroke="#eee" />
          <XAxis dataKey="cut" tick={AXIS} interval="preserveStartEnd" />
          <YAxis yAxisId="l" tick={AXIS} allowDecimals={false} domain={[0, (m: number) => Math.ceil(m * 1.3) || 1]} />
          <YAxis yAxisId="r" orientation="right" tick={AXIS} domain={[0, (m: number) => Math.max(1, Math.ceil(m * 1.3 * 10) / 10)]} />
          <Tooltip />
          <Legend wrapperStyle={{ fontSize: 12 }} verticalAlign="top" />
          <Bar yAxisId="l" dataKey="Bond" fill={ACCENT_MID} name="Bond dimension" />
          <Line yAxisId="r" dataKey="Entropy" stroke={ACCENT} dot={false} strokeWidth={2} name="Entropy (bits)" />
        </ComposedChart>
      </ResponsiveContainer>
      <dl className="kv">
        <dt>Max bond used</dt><dd>{tn.max_bond_used} (cap {r.plan.max_bond}, predicted bound {r.plan.predicted_max_bond.toLocaleString()})</dd>
        <dt>Truncations</dt><dd>{tn.truncations} · discarded weight {tn.discarded_weight.toExponential(2)}</dd>
        <dt>Truncation fidelity</dt><dd>{r.fidelity.truncation.toFixed(6)}</dd>
      </dl>
    </div>
  );
}
