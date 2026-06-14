'use client';

import { useEffect, useState } from 'react';
import { api, LeaderboardEntry } from '@/lib/api';
import { Card, CardHeader, CardTitle, CardBody } from '@/components/Card';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell,
} from 'recharts';

const BENCH_COLORS: Record<string, string> = {
  sql_agent: '#0ea5e9',
  enterprise_rag: '#8b5cf6',
  github_security: '#f59e0b',
};

export default function LeaderboardPage() {
  const [entries, setEntries] = useState<LeaderboardEntry[]>([]);
  const [metrics, setMetrics] = useState<Record<string, number>>({});
  const [benchmark, setBenchmark] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    Promise.all([
      api.leaderboard.list(benchmark || undefined),
      api.leaderboard.metrics(benchmark || undefined),
    ])
      .then(([lb, m]) => {
        setEntries(lb.leaderboard);
        setMetrics(m.metric_averages);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [benchmark]);

  const chartData = Object.entries(metrics).map(([k, v]) => ({
    name: k.replace(/_/g, ' '),
    value: v,
    color: v >= 0.7 ? '#10b981' : v >= 0.4 ? '#f59e0b' : '#ef4444',
  }));

  return (
    <div className="space-y-5 max-w-6xl">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-100">Leaderboard</h1>
        <select
          className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-gray-200"
          value={benchmark}
          onChange={(e) => setBenchmark(e.target.value)}
        >
          <option value="">All benchmarks</option>
          <option value="sql_agent">SQL Agent</option>
          <option value="enterprise_rag">Enterprise RAG</option>
          <option value="github_security">GitHub Security</option>
        </select>
      </div>

      {/* Metric averages chart */}
      {chartData.length > 0 && (
        <Card>
          <CardHeader><CardTitle>Average Metric Scores</CardTitle></CardHeader>
          <CardBody>
            <ResponsiveContainer width="100%" height={180}>
              <BarChart data={chartData} barSize={32}>
                <XAxis dataKey="name" tick={{ fill: '#9ca3af', fontSize: 11 }} />
                <YAxis domain={[0, 1]} tick={{ fill: '#9ca3af', fontSize: 11 }} tickFormatter={(v) => `${(v * 100).toFixed(0)}%`} />
                <Tooltip
                  contentStyle={{ background: '#111827', border: '1px solid #374151' }}
                  formatter={(v: number) => [`${(v * 100).toFixed(1)}%`, 'Score']}
                />
                <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                  {chartData.map((d, i) => <Cell key={i} fill={d.color} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </CardBody>
        </Card>
      )}

      {/* Leaderboard table */}
      <Card>
        <CardHeader><CardTitle>Model × Framework Rankings</CardTitle></CardHeader>
        <CardBody className="p-0">
          {loading ? (
            <div className="p-8 text-center text-gray-500">Loading…</div>
          ) : entries.length === 0 ? (
            <div className="p-8 text-center text-gray-500">
              No completed runs yet. Run a benchmark to populate the leaderboard.
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-800 text-xs text-gray-500 uppercase">
                  <th className="text-left px-5 py-3">#</th>
                  <th className="text-left px-5 py-3">Model</th>
                  <th className="text-left px-5 py-3">Framework</th>
                  <th className="text-left px-5 py-3">Benchmark</th>
                  <th className="text-right px-5 py-3">Runs</th>
                  <th className="text-right px-5 py-3">Avg Latency</th>
                  <th className="text-right px-5 py-3">Avg Tokens</th>
                </tr>
              </thead>
              <tbody>
                {entries.map((e, i) => (
                  <tr key={i} className="border-b border-gray-800 hover:bg-gray-800/40">
                    <td className="px-5 py-3 text-gray-500">{i + 1}</td>
                    <td className="px-5 py-3 font-mono text-xs text-gray-200">{e.model_name}</td>
                    <td className="px-5 py-3 text-gray-400">{e.framework}</td>
                    <td className="px-5 py-3">
                      <span
                        className="text-xs px-2 py-0.5 rounded-full"
                        style={{
                          background: BENCH_COLORS[e.benchmark] + '33',
                          color: BENCH_COLORS[e.benchmark],
                        }}
                      >
                        {e.benchmark.replace('_', ' ')}
                      </span>
                    </td>
                    <td className="px-5 py-3 text-right text-gray-400">{e.total_runs}</td>
                    <td className="px-5 py-3 text-right text-gray-400 font-mono text-xs">
                      {Math.round(e.avg_latency_ms)}ms
                    </td>
                    <td className="px-5 py-3 text-right text-gray-400 font-mono text-xs">
                      {Math.round(e.avg_tokens)}
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
