'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { api, Run } from '@/lib/api';
import { StatusBadge } from '@/components/Badge';
import { Card, CardHeader, CardTitle, CardBody } from '@/components/Card';

function formatMs(ms: number) {
  return ms < 1000 ? `${Math.round(ms)}ms` : `${(ms / 1000).toFixed(1)}s`;
}

export default function RunsPage() {
  const [runs, setRuns] = useState<Run[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState({ benchmark: '', status: '' });

  const load = () => {
    setLoading(true);
    api.runs
      .list({
        benchmark: filter.benchmark || undefined,
        status: filter.status || undefined,
        limit: 100,
      })
      .then((r) => {
        setRuns(r.items);
        setTotal(r.total);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  };

  useEffect(load, [filter]);

  return (
    <div className="space-y-5 max-w-7xl">
      <h1 className="text-2xl font-bold text-gray-100">Runs</h1>

      {/* Filters */}
      <div className="flex gap-3 flex-wrap">
        <select
          className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-gray-200 focus:outline-none"
          value={filter.benchmark}
          onChange={(e) => setFilter((f) => ({ ...f, benchmark: e.target.value }))}
        >
          <option value="">All benchmarks</option>
          <option value="sql_agent">SQL Agent</option>
          <option value="enterprise_rag">Enterprise RAG</option>
          <option value="github_security">GitHub Security</option>
        </select>
        <select
          className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-gray-200 focus:outline-none"
          value={filter.status}
          onChange={(e) => setFilter((f) => ({ ...f, status: e.target.value }))}
        >
          <option value="">All statuses</option>
          <option value="completed">Completed</option>
          <option value="failed">Failed</option>
          <option value="running">Running</option>
          <option value="pending">Pending</option>
        </select>
        <span className="text-sm text-gray-500 self-center">
          {total} run{total !== 1 ? 's' : ''}
        </span>
      </div>

      <Card>
        <CardBody className="p-0">
          {loading ? (
            <div className="p-8 text-center text-gray-500">Loading…</div>
          ) : runs.length === 0 ? (
            <div className="p-8 text-center text-gray-500">
              No runs found. Run a benchmark to get started.
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-800 text-xs text-gray-500 uppercase tracking-wider">
                  <th className="text-left px-5 py-3">Run ID</th>
                  <th className="text-left px-5 py-3">Task</th>
                  <th className="text-left px-5 py-3">Benchmark</th>
                  <th className="text-left px-5 py-3">Model</th>
                  <th className="text-left px-5 py-3">Status</th>
                  <th className="text-right px-5 py-3">Score</th>
                  <th className="text-right px-5 py-3">Steps</th>
                  <th className="text-right px-5 py-3">Latency</th>
                  <th className="text-right px-5 py-3">Policy</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((run) => (
                  <tr
                    key={run.run_id}
                    className="border-b border-gray-800 hover:bg-gray-800/60 transition-colors"
                  >
                    <td className="px-5 py-3">
                      <Link
                        href={`/runs/${run.run_id}`}
                        className="text-brand-400 hover:underline font-mono text-xs"
                      >
                        {run.run_id.slice(0, 8)}…
                      </Link>
                    </td>
                    <td className="px-5 py-3 font-mono text-xs text-gray-300">{run.task_id}</td>
                    <td className="px-5 py-3 text-gray-400">{run.benchmark.replace('_', ' ')}</td>
                    <td className="px-5 py-3 font-mono text-xs text-gray-400">{run.model_name}</td>
                    <td className="px-5 py-3"><StatusBadge status={run.status} /></td>
                    <td className="px-5 py-3 text-right font-mono text-xs">
                      {run.eval_scores?.overall != null
                        ? `${(run.eval_scores.overall * 100).toFixed(0)}%`
                        : '—'}
                    </td>
                    <td className="px-5 py-3 text-right text-gray-400 text-xs">{run.total_steps}</td>
                    <td className="px-5 py-3 text-right text-gray-400 text-xs">{formatMs(run.total_latency_ms)}</td>
                    <td className="px-5 py-3 text-right">
                      {run.policy_violations.length > 0 ? (
                        <span className="text-red-400 text-xs">
                          {run.policy_violations.length} violation{run.policy_violations.length !== 1 ? 's' : ''}
                        </span>
                      ) : (
                        <span className="text-gray-600 text-xs">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardBody>
      </Card>
    </div>
  );
}
