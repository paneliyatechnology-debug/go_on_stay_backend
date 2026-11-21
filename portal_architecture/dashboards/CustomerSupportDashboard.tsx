import React, { useEffect, useState } from 'react';
import { fetchStaffDepartmentDashboard } from '../services/portalApi';

export const CustomerSupportDashboard: React.FC = () => {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const token = localStorage.getItem('access_token') || sessionStorage.getItem('access_token') || '';
    fetchStaffDepartmentDashboard('CUSTOMER_SUPPORT', token)
      .then((res) => {
        setData(res);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, []);

  if (loading) return <div className="p-8 text-gray-400">Loading Support Desk Operations...</div>;
  if (error) return <div className="p-8 text-rose-400 bg-rose-950/30 rounded-lg">Error: {error}</div>;

  const metrics = data?.metrics || {};
  const recentTickets = Array.isArray(data?.recent_tickets) ? data.recent_tickets : [];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-black text-white">Customer Support Portal</h1>
        <p className="text-sm text-gray-400">Manage guest issues, respond to tickets, and track customer satisfaction.</p>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-gray-950 p-5 rounded-xl border border-gray-800">
          <p className="text-xs uppercase font-semibold text-gray-400">Open Tickets</p>
          <p className="text-3xl font-black text-rose-400 mt-2">{metrics.open_tickets || 0}</p>
        </div>

        <div className="bg-gray-950 p-5 rounded-xl border border-gray-800">
          <p className="text-xs uppercase font-semibold text-gray-400">In Progress</p>
          <p className="text-3xl font-black text-amber-400 mt-2">{metrics.in_progress_tickets || 0}</p>
        </div>

        <div className="bg-gray-950 p-5 rounded-xl border border-gray-800">
          <p className="text-xs uppercase font-semibold text-gray-400">Resolved</p>
          <p className="text-3xl font-black text-emerald-400 mt-2">{metrics.resolved_tickets || 0}</p>
        </div>

        <div className="bg-gray-950 p-5 rounded-xl border border-gray-800">
          <p className="text-xs uppercase font-semibold text-gray-400">Urgent Tickets</p>
          <p className="text-3xl font-black text-red-500 mt-2">{metrics.urgent_tickets || 0}</p>
        </div>
      </div>

      {/* Recent Support Tickets Table */}
      <div className="bg-gray-950 rounded-xl border border-gray-800 overflow-hidden">
        <div className="p-5 border-b border-gray-800">
          <h3 className="text-base font-bold text-white">Active Support Ticket Queue</h3>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm text-gray-300">
            <thead className="bg-gray-900/60 text-xs uppercase text-gray-400 border-b border-gray-800">
              <tr>
                <th className="px-5 py-3">Ticket #</th>
                <th className="px-5 py-3">Subject</th>
                <th className="px-5 py-3">Category</th>
                <th className="px-5 py-3">Priority</th>
                <th className="px-5 py-3">Status</th>
                <th className="px-5 py-3">Created</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800/60">
              {recentTickets.map((t: any) => (
                <tr key={t.id} className="hover:bg-gray-900/40">
                  <td className="px-5 py-3 font-mono text-xs text-purple-400">{t.ticket_number}</td>
                  <td className="px-5 py-3 font-semibold text-white">{t.subject}</td>
                  <td className="px-5 py-3 text-xs text-gray-400">{t.category}</td>
                  <td className="px-5 py-3">
                    <span className={`px-2 py-0.5 text-xs rounded-full ${
                      t.priority === 'URGENT' ? 'bg-red-950 text-red-400 border border-red-800' : 'bg-gray-800 text-gray-300'
                    }`}>
                      {t.priority}
                    </span>
                  </td>
                  <td className="px-5 py-3">
                    <span className="px-2 py-0.5 text-xs rounded-full bg-purple-950 text-purple-300 border border-purple-800">
                      {t.status}
                    </span>
                  </td>
                  <td className="px-5 py-3 text-xs text-gray-400">{new Date(t.created_at).toLocaleDateString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
