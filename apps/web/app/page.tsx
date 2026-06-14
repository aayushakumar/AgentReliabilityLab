'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { api, Run } from '@/lib/api';
import { StatusBadge } from '@/components/Badge';
import { Card, CardHeader, CardTitle, CardBody, StatCard } from '@/components/Card';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell,
} from 'recharts';

function formatMs(ms: number) {
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function formatScore(s: number) {
  return (s * 100).toFixed(0) + '%';
}

const BENCH_COLORS: Record<string, string> = {
  sql_agent: '#0ea5e9',
  enterprise_rag: '#8b5cf6',
  github_security: '#f59e0b',
};

export default function OverviewPage() {
  const [runs, setRuns] = useState<Run[]>([]);
  const [stats, setStats] = useState<{ total_runs: number } | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([api.runs.list({ limit: 50 }), api.stats()])
      .then(([r, s]) => {
        setRuns(r.items);
        setStats(s);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  const completed = runs.filter((r) => r.status === 'completed');
  const failed = runs.filter((r) => r.status === 'failed');
  const avgScore = completed.length
    ? completed.reduce((a, r) => a + (r.eval_scores?.overall ?? 0), 0) / completed.length
    : 0;
  const avgLatency = completed.length
    ? completed.reduce((a, r) => a + r.total_latency_ms, 0) / completed.length
    : 0;

  // Score distribution per benchmark
  const benchData = ['sql_agent', 'enterprise_rag', 'github_security'].map((b) => {
    const bRuns = completed.filter((r) => r.benchmark === b);
    return {
      name: b.replace('_', ' '),
      score: bRuns.length
        ? bRuns.reduce((a, r) => a + (r.eval_scores?.overall ?? 0), 0) / bRuns.length
        : 0,
      count: bRuns.length,
      color: BENCH_COLORS[b],
    };
  });

  if (loading) {
    return (
      <div className="flex items-center justify-center h-48 text-gray-500">
        Loading…
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-6xl">
      <div>
        <h1 className="text-2xl font-bold text-gray-100">Overview</h1>
        <p className="text-sm text-gray-400 mt-1">
          Evaluation & observability for AI agents
        </p>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Total Runs" value={stats?.total_runs ?? 0} />
        <StatCard
          label="Avg Score"
          value={formatScore(avgScore)}
          color={avgScore > 0.7 ? 'text-emerald-400' : 'text-amber-400'}
        />
        <StatCard label="Avg Latency" value={formatMs(avgLatency)} color="text-purple-400" />
        <StatCard
          label="Failed Runs"
          value={failed.length}
          color={failed.length > 0 ? 'text-red-400' : 'text-gray-400'}
        />
      </div>

      {/* Benchmark chart */}
      <Card>
        <CardHeader>
          <CardTitle>Average Score by Benchmark</CardTitle>
        </CardHeader>
        <CardBody>
          {benchData.every((b) => b.count === 0) ? (
            <p className="text-gray-500 text-sm">
              No completed runs yet. Run a benchmark to see results.
            </p>
          ) : (
            <ResponsiveContainer width="100%" height={180}>
              <BarChart data={benchData} barSize={40}>
                <XAxis dataKey="name" tick={{ fill: '#9ca3af', fontSize: 12 }} />
                <YAxis domain={[0, 1]} tick={{ fill: '#9ca3af', fontSize: 12 }} tickFormatter={(v) => `${(v * 100).toFixed(0)}%`} />
                <Tooltip
                  contentStyle={{ background: '#111827', border: '1px solid #374151' }}
                  formatter={(v: number) => [formatScore(v), 'Avg Score']}
                />
                <Bar dataKey="score" radius={[4, 4, 0, 0]}>
                  {benchData.map((b, i) => (
                    <Cell key={i} fill={b.color} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </CardBody>
      </Card>

      {/* Recent runs */}
      <Card>
        <CardHeader className="flex items-center justify-between">
          <CardTitle>Recent Runs</CardTitle>
          <Link href="/runs" className="text-xs text-brand-500 hover:underline">
            View all →
          </Link>
        </CardHeader>
        <CardBody className="p-0">
          {runs.length === 0 ? (
            <div className="p-5 text-gray-500 text-sm">No runs yet.</div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-800 text-xs text-gray-500 uppercase">
                  <th className="text-left px-5 py-2">Task</th>
                  <th className="text-left px-5 py-2">Benchmark</th>
                  <th className="text-left px-5 py-2">Model</th>
                  <th className="text-left px-5 py-2">Status</th>
                  <th className="text-right px-5 py-2">Score</th>
                  <th className="text-right px-5 py-2">Latency</th>
                </tr>
              </thead>
              <tbody>
                {runs.slice(0, 10).map((run) => (
                  <tr
                    key={run.run_id}
                    className="border-b border-gray-800 hover:bg-gray-800 transition-colors"
                  >
                    <td className="px-5 py-3">
                      <Link
                        href={`/runs/${run.run_id}`}
                        className="text-brand-400 hover:underline font-mono text-xs"
                      >
                        {run.task_id}
                      </Link>
                    </td>
                    <td className="px-5 py-3 text-gray-400">{run.benchmark.replace('_', ' ')}</td>
                    <td className="px-5 py-3 text-gray-400 font-mono text-xs">{run.model_name}</td>
                    <td className="px-5 py-3">
                      <StatusBadge status={run.status} />
                    </td>
                    <td className="px-5 py-3 text-right font-mono text-xs">
                      {run.eval_scores?.overall != null
                        ? formatScore(run.eval_scores.overall)
                        : '—'}
                    </td>
                    <td className="px-5 py-3 text-right text-gray-400 text-xs">
                      {formatMs(run.total_latency_ms)}
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
