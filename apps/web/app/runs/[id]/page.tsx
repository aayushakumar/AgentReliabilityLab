'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { api, Run, Span } from '@/lib/api';
import { StatusBadge } from '@/components/Badge';
import { Card, CardHeader, CardTitle, CardBody } from '@/components/Card';
import { clsx } from 'clsx';

const KIND_COLORS: Record<string, string> = {
  llm_call:     'bg-blue-800 text-blue-200',
  tool_call:    'bg-amber-800 text-amber-200',
  retrieval:    'bg-purple-800 text-purple-200',
  policy_check: 'bg-red-800 text-red-200',
  planner:      'bg-teal-800 text-teal-200',
  final_answer: 'bg-green-800 text-green-200',
  hitl:         'bg-orange-800 text-orange-200',
  internal:     'bg-gray-700 text-gray-300',
};

function SpanRow({ span, depth = 0 }: { span: Span; depth?: number }) {
  const [open, setOpen] = useState(false);
  const dur = span.duration_ms ? `${Math.round(span.duration_ms)}ms` : '—';
  const kindClass = KIND_COLORS[span.kind] ?? KIND_COLORS.internal;

  return (
    <>
      <tr
        className="border-b border-gray-800 hover:bg-gray-800/40 cursor-pointer transition-colors"
        onClick={() => setOpen((o) => !o)}
      >
        <td className="px-4 py-2 font-mono text-xs" style={{ paddingLeft: `${depth * 16 + 16}px` }}>
          <span className="text-gray-400 mr-2">{open ? '▼' : '▶'}</span>
          {span.name}
        </td>
        <td className="px-4 py-2">
          <span className={clsx('text-xs px-2 py-0.5 rounded-full', kindClass)}>{span.kind}</span>
        </td>
        <td className="px-4 py-2 text-right text-xs text-gray-400">{dur}</td>
        <td className="px-4 py-2 text-right">
          <StatusBadge status={span.status} />
        </td>
        <td className="px-4 py-2 text-right text-xs text-gray-500">{span.total_tokens || '—'}</td>
      </tr>
      {open && (
        <tr className="bg-gray-900/80">
          <td colSpan={5} className="px-6 py-3">
            <div className="grid grid-cols-2 gap-4 text-xs">
              {Object.keys(span.input_payload).length > 0 && (
                <div>
                  <div className="text-gray-500 mb-1 uppercase tracking-wider text-xs">Input</div>
                  <pre className="bg-gray-800 rounded p-2 text-gray-300 overflow-x-auto max-h-40 text-xs">
                    {JSON.stringify(span.input_payload, null, 2)}
                  </pre>
                </div>
              )}
              {Object.keys(span.output_payload).length > 0 && (
                <div>
                  <div className="text-gray-500 mb-1 uppercase tracking-wider text-xs">Output</div>
                  <pre className="bg-gray-800 rounded p-2 text-gray-300 overflow-x-auto max-h-40 text-xs">
                    {JSON.stringify(span.output_payload, null, 2)}
                  </pre>
                </div>
              )}
              {span.error_message && (
                <div className="col-span-2">
                  <div className="text-red-400 mb-1">Error</div>
                  <pre className="bg-red-950 rounded p-2 text-red-300 text-xs">{span.error_message}</pre>
                </div>
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

export default function RunDetailPage() {
  const params = useParams();
  const runId = params.id as string;
  const [run, setRun] = useState<Run | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.runs.get(runId).then(setRun).catch(console.error).finally(() => setLoading(false));
  }, [runId]);

  if (loading) return <div className="text-gray-500 p-8">Loading…</div>;
  if (!run) return <div className="text-red-400 p-8">Run not found.</div>;

  const overallScore = run.eval_scores?.overall;

  return (
    <div className="space-y-5 max-w-6xl">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <div className="text-xs text-gray-500 mb-1">
            <Link href="/runs" className="hover:text-gray-300">Runs</Link> / {runId.slice(0, 8)}…
          </div>
          <h1 className="text-xl font-bold text-gray-100 font-mono">{run.task_id}</h1>
          <p className="text-sm text-gray-400 mt-1">{run.benchmark.replace('_', ' ')} · {run.model_name}</p>
        </div>
        <StatusBadge status={run.status} />
      </div>

      {/* Metrics */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        {[
          { label: 'Overall Score', value: overallScore != null ? `${(overallScore * 100).toFixed(0)}%` : '—', color: overallScore != null && overallScore >= 0.7 ? 'text-emerald-400' : 'text-amber-400' },
          { label: 'Steps', value: run.total_steps, color: 'text-blue-400' },
          { label: 'Latency', value: `${Math.round(run.total_latency_ms)}ms`, color: 'text-purple-400' },
          { label: 'Tokens', value: run.total_tokens, color: 'text-teal-400' },
          { label: 'Policy', value: `${run.policy_violations.length} violations`, color: run.policy_violations.length > 0 ? 'text-red-400' : 'text-gray-500' },
        ].map((m) => (
          <Card key={m.label} className="p-4">
            <div className="text-xs text-gray-500 uppercase tracking-wider">{m.label}</div>
            <div className={`text-xl font-bold mt-1 ${m.color}`}>{m.value}</div>
          </Card>
        ))}
      </div>

      {/* Eval scores */}
      {Object.keys(run.eval_scores).length > 0 && (
        <Card>
          <CardHeader><CardTitle>Evaluation Scores</CardTitle></CardHeader>
          <CardBody>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {Object.entries(run.eval_scores).map(([k, v]) => (
                <div key={k}>
                  <div className="text-xs text-gray-500 mb-1">{k.replace('_', ' ')}</div>
                  <div className="flex items-center gap-2">
                    <div className="flex-1 bg-gray-800 rounded-full h-1.5">
                      <div
                        className="bg-brand-500 h-1.5 rounded-full"
                        style={{ width: `${Math.min(v * 100, 100)}%` }}
                      />
                    </div>
                    <span className="text-xs font-mono text-gray-300">{(v * 100).toFixed(0)}%</span>
                  </div>
                </div>
              ))}
            </div>
          </CardBody>
        </Card>
      )}

      {/* Trace viewer */}
      <Card>
        <CardHeader><CardTitle>Trace — {run.spans?.length ?? 0} spans</CardTitle></CardHeader>
        <CardBody className="p-0">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-800 text-xs text-gray-500 uppercase">
                <th className="text-left px-4 py-2">Span</th>
                <th className="text-left px-4 py-2">Kind</th>
                <th className="text-right px-4 py-2">Duration</th>
                <th className="text-right px-4 py-2">Status</th>
                <th className="text-right px-4 py-2">Tokens</th>
              </tr>
            </thead>
            <tbody>
              {(run.spans ?? []).map((span) => (
                <SpanRow key={span.span_id} span={span} />
              ))}
            </tbody>
          </table>
        </CardBody>
      </Card>

      {/* Policy violations */}
      {run.policy_violations.length > 0 && (
        <Card>
          <CardHeader><CardTitle>Policy Violations</CardTitle></CardHeader>
          <CardBody>
            <div className="space-y-2">
              {run.policy_violations.map((v, i) => (
                <div key={i} className="flex items-start gap-3 bg-red-950/40 border border-red-900 rounded-lg p-3">
                  <span className="text-red-400 text-xs font-mono">[{v.severity}]</span>
                  <div>
                    <div className="text-sm text-red-300">{v.reason}</div>
                    {v.policy_name && <div className="text-xs text-gray-500 mt-0.5">Policy: {v.policy_name}</div>}
                  </div>
                </div>
              ))}
            </div>
          </CardBody>
        </Card>
      )}
    </div>
  );
}
