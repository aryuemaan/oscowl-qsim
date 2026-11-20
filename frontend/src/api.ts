import type {
  AgentResult, BenchmarkFile, Example, Explanation, Health, Noise, RunOptions, SimResult, Skill, ValidateResult,
} from "./types";

// Same origin in production (FastAPI serves the app); Vite proxies /api in development.
const BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "";

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, message: string, detail: unknown) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

async function request<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}/api${path}`, {
    method: body === undefined ? "GET" : "POST",
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    let detail: unknown = null;
    try {
      detail = (await res.json()).detail;
    } catch {
      /* not JSON */
    }
    const msg =
      typeof detail === "string" ? detail
      : detail && typeof detail === "object" && "message" in detail ? String((detail as { message: string }).message)
      : `Request failed (${res.status})`;
    throw new ApiError(res.status, msg, detail);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => request<Health>("/health"),
  examples: () => request<Example[]>("/examples"),
  skills: () => request<Skill[]>("/skills"),
  benchmarks: () => request<BenchmarkFile>("/benchmarks/latest"),
  validate: (qasm: string, use_ai = false) => request<ValidateResult>("/validate", { qasm, use_ai }),
  simulate: (qasm: string, noise: Noise, options: RunOptions) => request<SimResult>("/simulate", { qasm, noise, options }),
  explain: (qasm: string, noise: Noise, options: RunOptions, simulation: SimResult) =>
    request<Explanation>("/explain", { qasm, noise, options, simulation }),
  debug: (qasm: string, noise: Noise, options: RunOptions) => request<AgentResult>("/agent/debug", { qasm, noise, options }),
};
