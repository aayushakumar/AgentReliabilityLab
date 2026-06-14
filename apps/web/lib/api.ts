/**
 * API client — all requests go through Next.js rewrites to the FastAPI backend.
 */

const API_BASE = '/api';

export async function fetchJSON<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  });
  if (!res.ok) {
    const text = await res.text().catch(() => 'Unknown error');
    throw new Error(`API error ${res.status}: ${text}`);
  }
  return res.json();
}

// ─────────────────────────── Types ────────────────────────────────────────

export interface Run {
  run_id: string;
  agent_type: string;
  benchmark: string;
  task_id: string;
  model_name: string;
  framework: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'hitl_waiting';
  created_at: string;
  completed_at: string | null;
  total_steps: number;
  total_tokens: number;
  total_cost_usd: number;
  total_latency_ms: number;
  eval_scores: Record<string, number>;
  policy_violations: Array<Record<string, string>>;
  hitl_required: boolean;
  tags: Record<string, string>;
  spans?: Span[];
}

export interface Span {
  span_id: string;
  parent_span_id: string | null;
  name: string;
  kind: string;
  start_time: string;
  end_time: string | null;
  duration_ms: number;
  input_payload: Record<string, unknown>;
  output_payload: Record<string, unknown>;
  status: string;
  error_message: string | null;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
}

export interface RunsResponse {
  items: Run[];
  total: number;
  limit: number;
  offset: number;
}

export interface LeaderboardEntry {
  model_name: string;
  model_provider: string;
  framework: string;
  benchmark: string;
  total_runs: number;
  avg_latency_ms: number;
  avg_tokens: number;
  avg_cost_usd: number;
}

export interface HITLCheckpoint {
  checkpoint_id: string;
  run_id: string;
  span_id: string | null;
  tool_name: string;
  tool_input: Record<string, unknown>;
  risk_score: number;
  reason: string;
  decision: 'pending' | 'approve' | 'reject' | 'timeout';
  decided_by: string | null;
  decided_at: string | null;
  created_at: string;
}

// ─────────────────────────── API Calls ────────────────────────────────────

export const api = {
  runs: {
    list: (params?: { agent_type?: string; benchmark?: string; status?: string; limit?: number; offset?: number }) => {
      const q = new URLSearchParams();
      if (params?.agent_type) q.set('agent_type', params.agent_type);
      if (params?.benchmark) q.set('benchmark', params.benchmark);
      if (params?.status) q.set('status', params.status);
      if (params?.limit) q.set('limit', String(params.limit));
      if (params?.offset) q.set('offset', String(params.offset));
      return fetchJSON<RunsResponse>(`/runs/?${q}`);
    },
    get: (runId: string) => fetchJSON<Run>(`/runs/${runId}`),
    delete: (runId: string) =>
      fetchJSON<{ deleted: string }>(`/runs/${runId}`, { method: 'DELETE' }),
  },
  traces: {
    spans: (runId: string) => fetchJSON<{ run_id: string; trace_id: string; spans: Span[] }>(`/traces/${runId}/spans`),
    policyEvents: (runId: string) => fetchJSON<{ events: unknown[] }>(`/traces/${runId}/policy-events`),
  },
  leaderboard: {
    list: (benchmark?: string) => {
      const q = benchmark ? `?benchmark=${benchmark}` : '';
      return fetchJSON<{ leaderboard: LeaderboardEntry[] }>(`/leaderboard/${q}`);
    },
    metrics: (benchmark?: string) => {
      const q = benchmark ? `?benchmark=${benchmark}` : '';
      return fetchJSON<{ metric_averages: Record<string, number> }>(`/leaderboard/metrics${q}`);
    },
  },
  hitl: {
    pending: () => fetchJSON<{ checkpoints: HITLCheckpoint[] }>('/hitl/pending'),
    all: () => fetchJSON<{ checkpoints: HITLCheckpoint[] }>('/hitl/all'),
    decide: (checkpointId: string, decision: 'approve' | 'reject') =>
      fetchJSON(`/hitl/${checkpointId}/decide`, {
        method: 'POST',
        body: JSON.stringify({ decision }),
      }),
  },
  evals: {
    trigger: (req: { benchmark: string; max_tasks?: number; model_provider?: string }) =>
      fetchJSON('/evals/benchmark', { method: 'POST', body: JSON.stringify(req) }),
  },
  replay: {
    trigger: (req: { run_id: string; model_provider?: string; model_name?: string }) =>
      fetchJSON('/replay/', { method: 'POST', body: JSON.stringify(req) }),
    diff: (runIdA: string, runIdB: string) =>
      fetchJSON(`/replay/diff/${runIdA}/${runIdB}`),
  },
  stats: () => fetchJSON<{ total_runs: number }>('/stats'),
};
