'use client';

import { useEffect, useState } from 'react';
import { api, HITLCheckpoint } from '@/lib/api';
import { StatusBadge } from '@/components/Badge';
import { Card, CardHeader, CardTitle, CardBody } from '@/components/Card';

export default function HITLPage() {
  const [checkpoints, setCheckpoints] = useState<HITLCheckpoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [deciding, setDeciding] = useState<string | null>(null);

  const load = () =>
    api.hitl.all().then((r) => setCheckpoints(r.checkpoints)).catch(console.error).finally(() => setLoading(false));

  useEffect(() => { load(); }, []);

  const decide = async (id: string, decision: 'approve' | 'reject') => {
    setDeciding(id);
    try {
      await api.hitl.decide(id, decision);
      await load();
    } catch (e) {
      console.error(e);
    } finally {
      setDeciding(null);
    }
  };

  const pending = checkpoints.filter((c) => c.decision === 'pending');
  const decided = checkpoints.filter((c) => c.decision !== 'pending');

  return (
    <div className="space-y-5 max-w-5xl">
      <div>
        <h1 className="text-2xl font-bold text-gray-100">Human-in-the-Loop</h1>
        <p className="text-sm text-gray-400 mt-1">
          High-risk tool calls awaiting human approval before execution.
        </p>
      </div>

      {/* Pending */}
      <Card>
        <CardHeader>
          <CardTitle>
            Pending Approvals
            {pending.length > 0 && (
              <span className="ml-2 bg-amber-700 text-amber-200 text-xs px-2 py-0.5 rounded-full">
                {pending.length}
              </span>
            )}
          </CardTitle>
        </CardHeader>
        <CardBody>
          {loading ? (
            <div className="text-gray-500 text-sm">Loading…</div>
          ) : pending.length === 0 ? (
            <div className="text-gray-500 text-sm">No pending approvals.</div>
          ) : (
            <div className="space-y-4">
              {pending.map((cp) => (
                <div key={cp.checkpoint_id} className="bg-gray-800 rounded-xl p-4 border border-amber-800">
                  <div className="flex items-start justify-between gap-4">
                    <div className="space-y-2 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-mono text-amber-400">{cp.tool_name}</span>
                        <span className="text-xs bg-red-900 text-red-300 px-2 py-0.5 rounded-full">
                          risk: {(cp.risk_score * 100).toFixed(0)}%
                        </span>
                      </div>
                      <p className="text-sm text-gray-300">{cp.reason}</p>
                      <pre className="bg-gray-900 rounded p-2 text-xs text-gray-300 overflow-x-auto max-h-24">
                        {JSON.stringify(cp.tool_input, null, 2)}
                      </pre>
                      <p className="text-xs text-gray-500">Run: {cp.run_id}</p>
                    </div>
                    <div className="flex gap-2 shrink-0">
                      <button
                        onClick={() => decide(cp.checkpoint_id, 'approve')}
                        disabled={deciding === cp.checkpoint_id}
                        className="px-3 py-1.5 bg-emerald-700 hover:bg-emerald-600 text-white text-xs rounded-lg transition-colors disabled:opacity-50"
                      >
                        Approve
                      </button>
                      <button
                        onClick={() => decide(cp.checkpoint_id, 'reject')}
                        disabled={deciding === cp.checkpoint_id}
                        className="px-3 py-1.5 bg-red-700 hover:bg-red-600 text-white text-xs rounded-lg transition-colors disabled:opacity-50"
                      >
                        Reject
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardBody>
      </Card>

      {/* History */}
      {decided.length > 0 && (
        <Card>
          <CardHeader><CardTitle>Decision History</CardTitle></CardHeader>
          <CardBody className="p-0">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-800 text-xs text-gray-500 uppercase">
                  <th className="text-left px-5 py-2">Tool</th>
                  <th className="text-left px-5 py-2">Risk</th>
                  <th className="text-left px-5 py-2">Decision</th>
                  <th className="text-left px-5 py-2">By</th>
                  <th className="text-right px-5 py-2">Time</th>
                </tr>
              </thead>
              <tbody>
                {decided.map((cp) => (
                  <tr key={cp.checkpoint_id} className="border-b border-gray-800">
                    <td className="px-5 py-2 font-mono text-xs text-gray-300">{cp.tool_name}</td>
                    <td className="px-5 py-2 text-xs text-gray-400">{(cp.risk_score * 100).toFixed(0)}%</td>
                    <td className="px-5 py-2"><StatusBadge status={cp.decision} /></td>
                    <td className="px-5 py-2 text-xs text-gray-400">{cp.decided_by ?? '—'}</td>
                    <td className="px-5 py-2 text-right text-xs text-gray-500">
                      {cp.decided_at ? new Date(cp.decided_at).toLocaleString() : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardBody>
        </Card>
      )}
    </div>
  );
}
