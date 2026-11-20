import { useEffect, useState } from "react";
import { Gauge } from "lucide-react";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api";
import { bytes, ms } from "../format";
import type { BenchmarkFile } from "../types";

const AXIS = { fontSize: 11, fill: "#5f5f73" };

function series(rows: BenchmarkFile["rows"], circuit: string, key: "seconds" | "peak_bytes") {
  const qubits = [...new Set(rows.filter((r) => r.circuit === circuit).map((r) => r.qubits))].sort((a, b) => a - b);
  return qubits.map((q) => {
    const sv = rows.find((r) => r.circuit === circuit && r.qubits === q && r.method === "statevector");
    const mps = rows.find((r) => r.circuit === circuit && r.qubits === q && r.method === "mps");
    return { qubits: q, "Dense state vector": sv?.[key] ?? null, "Q-Sim MPS": mps?.[key] ?? null };
  });
}

export function Benchmarks() {
  const [data, setData] = useState<BenchmarkFile | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { api.benchmarks().then(setData).catch((e) => setError(e.message)); }, []);

  if (error) {
    return (
      <div className="card"><div className="card-body">
        <div className="note warn">{error}</div>
        <p>Generate real numbers on your machine (takes a minute or two):</p>
        <pre className="mono">python benchmarks/benchmark.py</pre>
      </div></div>
    );
  }
  if (!data) return <div className="card"><div className="empty">Loading benchmark results...</div></div>;
  const circuits = [...new Set(data.rows.map((r) => r.circuit))];
  return (
    <div className="stack">
      <div className="card"><div className="card-head"><h2><Gauge size={16} /> Benchmark: dense state vector vs Q-Sim MPS</h2></div>
        <div className="card-body small muted">
          Measured {new Date(data.created).toLocaleString()} on {data.machine.platform} ({data.machine.cpu}, Python {data.machine.python}).
          Time is wall-clock for the ideal simulation; memory is the peak allocation traced by Python. Dense runs stop where memory would exceed the limit.
        </div>
      </div>
      {circuits.map((c) => (
        <div className="card" key={c}>
          <div className="card-head"><h2>{c}</h2></div>
          <div className="card-body grid2">
            {(["seconds", "peak_bytes"] as const).map((k) => (
              <div key={k}>
                <div className="chart-title">{k === "seconds" ? "Run time (log scale)" : "Peak memory (log scale)"} vs qubits</div>
                <ResponsiveContainer width="100%" height={240}>
                  <LineChart data={series(data.rows, c, k)} margin={{ top: 8, right: 12, bottom: 8, left: 8 }}>
                    <CartesianGrid stroke="#eee" />
                    <XAxis dataKey="qubits" type="number" domain={[0, "dataMax"]} tick={AXIS} />
                    <YAxis scale="log" domain={["auto", "auto"]} tick={AXIS} width={70} allowDataOverflow
                      tickFormatter={(v) => (k === "seconds" ? ms(v * 1000) : bytes(v))} />
                    <Tooltip formatter={(v) => (k === "seconds" ? ms(Number(v) * 1000) : bytes(Number(v)))} />
                    <Legend wrapperStyle={{ fontSize: 12 }} verticalAlign="top" />
                    <Line dataKey="Dense state vector" stroke="#9a9aae" strokeWidth={2} connectNulls dot={{ r: 2 }} />
                    <Line dataKey="Q-Sim MPS" stroke="#5b3cc4" strokeWidth={2} connectNulls dot={{ r: 2 }} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            ))}
          </div>
        </div>
      ))}
      <div className="card"><div className="card-head"><h2>All measurements</h2></div>
        <div className="card-body" style={{ overflowX: "auto" }}>
          <table className="simple">
            <thead><tr><th>Circuit</th><th>Method</th><th>Qubits</th><th>Time</th><th>Peak memory</th><th>State size</th><th>Max bond</th><th>Fidelity vs dense</th><th>Note</th></tr></thead>
            <tbody>{data.rows.map((r, i) => (
              <tr key={i}><td>{r.circuit}</td><td>{r.method}</td><td>{r.qubits}</td>
                <td>{r.seconds === null ? "-" : ms(r.seconds * 1000)}</td><td>{bytes(r.peak_bytes)}</td><td>{bytes(r.state_bytes)}</td>
                <td>{r.max_bond ?? "-"}</td><td>{r.fidelity_vs_dense === null ? "-" : r.fidelity_vs_dense.toFixed(8)}</td>
                <td className="muted">{r.note ?? ""}</td></tr>))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
