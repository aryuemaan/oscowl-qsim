import { SlidersHorizontal } from "lucide-react";
import type { Noise } from "../types";

export const PRESETS: Record<string, Noise> = {
  Ideal: { p1: 0, p2: 0, amplitude_damping: 0, readout_p01: 0, readout_p10: 0 },
  Low: { p1: 0.0005, p2: 0.005, amplitude_damping: 0.001, readout_p01: 0.01, readout_p10: 0.01 },
  NISQ: { p1: 0.002, p2: 0.02, amplitude_damping: 0.005, readout_p01: 0.03, readout_p10: 0.03 },
  Harsh: { p1: 0.01, p2: 0.05, amplitude_damping: 0.02, readout_p01: 0.06, readout_p10: 0.06 },
};

const SLIDERS: { key: keyof Noise | "readout"; name: string; max: number; step: number; hint: string }[] = [
  { key: "p1", name: "1-qubit depolarizing", max: 0.02, step: 0.0005, hint: "Chance a single-qubit gate is hit by a random Pauli error" },
  { key: "p2", name: "2-qubit depolarizing", max: 0.1, step: 0.001, hint: "Chance a two-qubit gate (CX, CZ, SWAP...) is corrupted" },
  { key: "amplitude_damping", name: "Amplitude damping (T1)", max: 0.05, step: 0.001, hint: "Energy relaxation |1> to |0> per gate per qubit" },
  { key: "readout", name: "Readout error", max: 0.1, step: 0.002, hint: "Chance a measured bit is reported flipped" },
];

export function NoisePanel({ noise, onChange }: { noise: Noise; onChange: (n: Noise) => void }) {
  const active = Object.entries(PRESETS).find(([, p]) => JSON.stringify(p) === JSON.stringify(noise))?.[0];
  const get = (k: string) => (k === "readout" ? noise.readout_p01 : noise[k as keyof Noise]);
  const set = (k: string, v: number) =>
    onChange(k === "readout" ? { ...noise, readout_p01: v, readout_p10: v } : { ...noise, [k]: v });
  return (
    <div className="card">
      <div className="card-head">
        <h2><SlidersHorizontal size={16} /> Noise profile</h2>
        <div className="grow" />
        <div className="segmented">
          {Object.keys(PRESETS).map((name) => (
            <button key={name} className={active === name ? "active" : ""} onClick={() => onChange(PRESETS[name])}>{name}</button>
          ))}
        </div>
      </div>
      <div className="card-body grid2" style={{ gap: "0 24px" }}>
        {SLIDERS.map((s) => (
          <div className="slider" key={s.key}>
            <span className="name">{s.name}</span>
            <span className="val">{(100 * get(s.key)).toFixed(s.max <= 0.02 ? 2 : 1)}%</span>
            <input type="range" min={0} max={s.max} step={s.step} value={get(s.key)}
              onChange={(e) => set(s.key, Number(e.target.value))} aria-label={s.name} />
            <span className="hint">{s.hint}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
