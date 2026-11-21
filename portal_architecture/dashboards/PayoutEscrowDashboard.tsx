import React, { useEffect, useState } from 'react';
import { fetchStaffDepartmentDashboard } from '../services/portalApi';

export const PayoutEscrowDashboard: React.FC = () => {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const token = localStorage.getItem('access_token') || sessionStorage.getItem('access_token') || '';
    fetchStaffDepartmentDashboard('PAYOUT_AND_ESCROW', token)
      .then((res) => {
        setData(res);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, []);

  if (loading) return <div className="p-8 text-gray-400">Loading Payout & Escrow Operations...</div>;
  if (error) return <div className="p-8 text-rose-400 bg-rose-950/30 rounded-lg">Error: {error}</div>;

  const metrics = data?.metrics || {};
  const recentPayouts = Array.isArray(data?.recent_payouts) ? data.recent_payouts : [];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-black text-white">Payout & Escrow Management Portal</h1>
        <p className="text-sm text-gray-400">Oversee host settlements, verify 7-day escrow maturities, and execute bank transfers.</p>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-gray-950 p-5 rounded-xl border border-gray-800">
          <p className="text-xs uppercase font-semibold text-gray-400">Escrow On-Hold</p>
          <p className="text-3xl font-black text-amber-400 mt-2">
            ₹{Number(metrics.total_escrow_holding || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
          </p>
          <p className="text-xs text-gray-400 mt-1">7-day guest stay hold</p>
        </div>

        <div className="bg-gray-950 p-5 rounded-xl border border-gray-800">
          <p className="text-xs uppercase font-semibold text-gray-400">Eligible For Transfer</p>
          <p className="text-3xl font-black text-blue-400 mt-2">{metrics.eligible_payouts || 0}</p>
          <p className="text-xs text-blue-400 mt-1">Check-out passed & no dispute</p>
        </div>

        <div className="bg-gray-950 p-5 rounded-xl border border-gray-800">
          <p className="text-xs uppercase font-semibold text-gray-400">Pending Review</p>
          <p className="text-3xl font-black text-white mt-2">{metrics.pending_payouts || 0}</p>
        </div>

        <div className="bg-gray-950 p-5 rounded-xl border border-gray-800">
          <p className="text-xs uppercase font-semibold text-gray-400">Total Settled Volume</p>
          <p className="text-3xl font-black text-emerald-400 mt-2">
            ₹{Number(metrics.total_paid_out || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
          </p>
          <p className="text-xs text-emerald-400 mt-1">{metrics.completed_payouts || 0} batches completed</p>
        </div>
      </div>

      {/* Recent Payout Transfers */}
      <div className="bg-gray-950 rounded-xl border border-gray-800 overflow-hidden">
        <div className="p-5 border-b border-gray-800">
          <h3 className="text-base font-bold text-white">Recent Host Payout Batches</h3>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm text-gray-300">
            <thead className="bg-gray-900/60 text-xs uppercase text-gray-400 border-b border-gray-800">
              <tr>
                <th className="px-5 py-3">Payout ID</th>
                <th className="px-5 py-3">Host ID</th>
                <th className="px-5 py-3">Amount</th>
                <th className="px-5 py-3">Status</th>
                <th className="px-5 py-3">Date</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800/60">
              {recentPayouts.map((p: any) => (
                <tr key={p.id} className="hover:bg-gray-900/40">
                  <td className="px-5 py-3 font-mono text-xs text-amber-400">{p.payout_id}</td>
                  <td className="px-5 py-3 text-xs text-gray-300">Host #{p.host_id}</td>
                  <td className="px-5 py-3 font-semibold text-white">₹{p.amount}</td>
                  <td className="px-5 py-3">
                    <span className="px-2 py-0.5 text-xs rounded-full bg-amber-950 text-amber-300 border border-amber-800">
                      {p.status}
                    </span>
                  </td>
                  <td className="px-5 py-3 text-xs text-gray-400">{new Date(p.created_at).toLocaleDateString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
