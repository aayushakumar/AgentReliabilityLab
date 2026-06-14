'use client';

import { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { Card, CardHeader, CardTitle, CardBody } from '@/components/Card';
import { StatusBadge } from '@/components/Badge';

export default function PolicyPage() {
  const [events, setEvents] = useState<Record<string, unknown>[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.leaderboard  // reuse fetch
      .list()
      .catch(() => null);
    fetch('/api/policy/events?limit=100')
      .then((r) => r.json())
      .then((d) => setEvents(d.events ?? []))
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  const blocked = events.filter((e: any) => e.action === 'blocked').length;
  const hitl = events.filter((e: any) => e.action === 'hitl').length;
  const allowed = events.filter((e: any) => e.action === 'allowed').length;

  return (
    <div className="space-y-5 max-w-6xl">
      <h1 className="text-2xl font-bold text-gray-100">Policy Events</h1>

      {/* Summary cards */}
      <div className="grid grid-cols-3 gap-4">
        <Card className="p-4">
          <div className="text-xs text-gray-500 uppercase">Blocked</div>
          <div className="text-3xl font-bold text-red-400 mt-1">{blocked}</div>
        </Card>
        <Card className="p-4">
          <div className="text-xs text-gray-500 uppercase">HITL Routed</div>
          <div className="text-3xl font-bold text-amber-400 mt-1">{hitl}</div>
        </Card>
        <Card className="p-4">
          <div className="text-xs text-gray-500 uppercase">Allowed</div>
          <div className="text-3xl font-bold text-emerald-400 mt-1">{allowed}</div>
        </Card>
      </div>

      {/* Events table */}
      <Card>
        <CardHeader><CardTitle>Recent Policy Events</CardTitle></CardHeader>
        <CardBody className="p-0">
          {loading ? (
            <div className="p-8 text-center text-gray-500">Loading…</div>
          ) : events.length === 0 ? (
            <div className="p-8 text-center text-gray-500">No policy events recorded yet.</div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-800 text-xs text-gray-500 uppercase">
                  <th className="text-left px-5 py-2">Run</th>
                  <th className="text-left px-5 py-2">Policy</th>
                  <th className="text-left px-5 py-2">Tool</th>
                  <th className="text-left px-5 py-2">Action</th>
                  <th className="text-left px-5 py-2">Severity</th>
                  <th className="text-left px-5 py-2">Reason</th>
                  <th className="text-right px-5 py-2">Time</th>
                </tr>
              </thead>
              <tbody>
                {events.map((e: any, i) => (
                  <tr key={i} className="border-b border-gray-800 hover:bg-gray-800/40">
                    <td className="px-5 py-2 font-mono text-xs text-brand-400">
                      {e.run_id?.slice(0, 8)}…
                    </td>
                    <td className="px-5 py-2 text-xs text-gray-400">{e.policy_name}</td>
                    <td className="px-5 py-2 font-mono text-xs text-gray-300">{e.tool_name ?? '—'}</td>
                    <td className="px-5 py-2"><StatusBadge status={e.action} /></td>
                    <td className="px-5 py-2">
                      <span className={`text-xs ${
                        e.severity === 'critical' ? 'text-red-400' :
                        e.severity === 'high' ? 'text-orange-400' :
                        e.severity === 'medium' ? 'text-amber-400' : 'text-gray-400'
                      }`}>{e.severity}</span>
                    </td>
                    <td className="px-5 py-2 text-xs text-gray-400 max-w-xs truncate">{e.reason}</td>
                    <td className="px-5 py-2 text-right text-xs text-gray-500">
                      {e.created_at ? new Date(e.created_at).toLocaleTimeString() : '—'}
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
