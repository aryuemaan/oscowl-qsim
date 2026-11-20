// Shapes of the JSON returned by the FastAPI backend (see docs/API.md).

export type Severity = "error" | "warning" | "info";

export interface Issue {
  severity: Severity;
  message: string;
  line: number | null;
  rule: string;
  source: string;
}

export interface CircuitStats {
  num_qubits: number;
  num_clbits: number;
  num_gates: number;
  one_qubit_gates: number;
  two_qubit_gates: number;
  depth: number;
  gate_counts: Record<string, number>;
  long_range_gates: number;
  max_interaction_distance: number;
  implicit_measurement: boolean;
  unused_qubits: number[];
}

export interface Plan {
  backend: "statevector" | "mps";
  max_bond: number;
  exact_expected: boolean;
  predicted_max_bond: number;
  statevector_bytes: number;
  mps_bytes_estimate: number;
  hardware: string;
  reason: string;
}

export interface ValidateResult {
  ok: boolean;
  issues: Issue[];
  stats: CircuitStats | null;
  plan: Plan | null;
  ai: { used: boolean; provider?: string; model?: string; summary?: string | null; error?: string | null; latency_ms?: number };
}

export interface Noise {
  p1: number;
  p2: number;
  amplitude_damping: number;
  readout_p01: number;
  readout_p10: number;
}

export interface RunOptions {
  shots: number;
  trajectories: number;
  backend: "auto" | "statevector" | "mps";
  max_bond: number;
  seed: number | null;
}

export interface Hotspot {
  index: number;
  gate: string;
  qubits: number[];
  line: number | null;
  label: string;
  error: number;
  share: number;
  layer: number;
}

export interface Budget {
  esp: number;
  total_weight: number;
  by_source: { source: string; weight: number; share: number }[];
  by_gate_type: { gate: string; weight: number; share: number; count: number }[];
  by_qubit: { qubit: number; weight: number; share: number }[];
  by_layer: { layer: number; weight: number }[];
  hotspots: Hotspot[];
  dominant_source: string | null;
  model_note: string;
}

export interface SimResult {
  backend: "statevector" | "mps";
  array_backend: string;
  plan: Plan;
  seed: number;
  shots: number;
  trajectories: number;
  outcomes: { bitstring: string; noisy: number; ideal: number }[];
  num_outcomes: number;
  counts: Record<string, number>;
  ideal_counts: Record<string, number>;
  fidelity: {
    state: number;
    state_stderr: number;
    hellinger: number | null;
    hellinger_method: string;
    esp: number;
    truncation: number;
    error_bound: number;
  };
  noise: Noise;
  noise_events_mean: number;
  budget: Budget;
  tensor_network: {
    predicted_bonds: number[];
    bond_dims?: number[];
    entropies?: number[];
    max_bond_used: number | null;
    truncations: number;
    discarded_weight: number;
  };
  memory: { used_bytes: number; dense_equivalent_bytes: number };
  timing: { ideal_ms: number; noisy_ms: number; total_ms: number };
  circuit: CircuitStats;
  measurement: { pairs: [number, number][]; num_clbits: number; implicit: boolean; bit_order: string };
  warnings: string[];
}

export interface Explanation {
  source: "gemini" | "offline";
  model: string;
  summary: string;
  intent: string;
  noise_explanation: string;
  key_findings: string[];
  suggestions: string[];
  latency_ms?: number;
  note?: string;
}

export interface AgentStep {
  id: number;
  phase: "validate" | "diagnose" | "propose" | "verify" | "explain";
  title: string;
  status: "ok" | "info" | "warn" | "error" | "accepted" | "rejected";
  detail: string;
  metrics: Record<string, unknown>;
  source: string;
  duration_ms: number;
}

export interface Snapshot {
  state_fidelity: number;
  state_stderr: number;
  hellinger: number | null;
  esp: number;
  gates: number;
  two_qubit_gates: number;
  depth: number;
  hellinger_mitigated?: number;
}

export interface AgentResult {
  ok: boolean;
  steps: AgentStep[];
  accepted: { title: string; verdict: string; source: string }[];
  rejected: { title: string; verdict: string; source: string }[];
  final_qasm: string;
  changed: boolean;
  before: Snapshot | null;
  after: Snapshot | null;
  explanation: { source: string; text: string; model?: string } | null;
  ai_mode: string;
  duration_ms?: number;
}

export interface Example {
  id: string;
  title: string;
  description: string;
  qasm: string;
  noise: { p1: number; p2: number; amplitude_damping: number; readout: number };
}

export interface Health {
  status: string;
  version: string;
  ai: {
    mode: "gemini" | "offline";
    via: string | null;
    flash_model: string;
    reasoning_model: string;
    gemma_provider: string;
    gemma_model: string;
    last_error: string | null;
  };
  array_backends: string[];
  array_backend: string;
  limits: Record<string, number>;
}

export interface Skill {
  name: string;
  description: string;
  path: string;
}

export interface BenchmarkRow {
  method: string;
  circuit: string;
  qubits: number;
  seconds: number | null;
  peak_bytes: number | null;
  state_bytes: number | null;
  max_bond: number | null;
  fidelity_vs_dense: number | null;
  note?: string;
}

export interface BenchmarkFile {
  created: string;
  machine: Record<string, string>;
  rows: BenchmarkRow[];
}
