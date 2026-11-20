import { CircleCheck, CircleX, LoaderCircle, Play } from "lucide-react";
import type { RunOptions } from "../types";

export type StageState = "idle" | "run" | "done" | "fail" | "skip";
export interface Stages {
  validate: StageState;
  gemma: StageState;
  simulate: StageState;
}

function Stage({ label, state }: { label: string; state: StageState }) {
  if (state === "idle") return null;
  const icon = state === "run" ? <LoaderCircle size={13} className="spin" /> : state === "fail" ? <CircleX size={13} /> : <CircleCheck size={13} />;
  return <span className={`stage ${state}`}>{icon}{label}</span>;
}

interface Props {
  options: RunOptions;
  onChange: (o: RunOptions) => void;
  onRun: () => void;
  running: boolean;
  disabled: boolean;
  stages: Stages;
  gemmaLabel: string;
}

export function RunPanel({ options, onChange, onRun, running, disabled, stages, gemmaLabel }: Props) {
  const set = <K extends keyof RunOptions>(k: K, v: RunOptions[K]) => onChange({ ...options, [k]: v });
  return (
    <div className="card">
      <div className="card-body">
        <div className="settings">
          <label className="field">Shots
            <select value={options.shots} onChange={(e) => set("shots", Number(e.target.value))}>
              {[256, 1024, 4096, 8192].map((v) => <option key={v} value={v}>{v}</option>)}
            </select>
          </label>
          <label className="field">Noise trajectories
            <select value={options.trajectories} onChange={(e) => set("trajectories", Number(e.target.value))}>
              {[8, 16, 32, 64, 128].map((v) => <option key={v} value={v}>{v}</option>)}
            </select>
          </label>
          <label className="field">Backend
            <select value={options.backend} onChange={(e) => set("backend", e.target.value as RunOptions["backend"])}>
              <option value="auto">Auto (planner)</option>
              <option value="mps">Tensor network (MPS)</option>
              <option value="statevector">Dense state vector</option>
            </select>
          </label>
          <label className="field">Max bond dimension
            <select value={options.max_bond} onChange={(e) => set("max_bond", Number(e.target.value))}>
              {[8, 16, 32, 64, 128, 256].map((v) => <option key={v} value={v}>{v}</option>)}
            </select>
          </label>
        </div>
        <button className="btn primary big" onClick={onRun} disabled={running || disabled}>
          {running ? <LoaderCircle size={17} className="spin" /> : <Play size={17} />}
          {running ? "Running..." : "Run simulation"}
        </button>
        <div className="pipeline">
          <Stage label="Validate" state={stages.validate} />
          <Stage label={gemmaLabel} state={stages.gemma} />
          <Stage label="Simulate" state={stages.simulate} />
        </div>
      </div>
    </div>
  );
}
