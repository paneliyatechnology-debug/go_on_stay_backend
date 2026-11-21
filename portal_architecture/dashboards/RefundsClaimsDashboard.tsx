import React, { useEffect, useState } from 'react';
import { fetchStaffDepartmentDashboard } from '../services/portalApi';

export const RefundsClaimsDashboard: React.FC = () => {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const token = localStorage.getItem('access_token') || sessionStorage.getItem('access_token') || '';
    fetchStaffDepartmentDashboard('REFUNDS_AND_CLAIMS', token)
      .then((res) => {
        setData(res);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, []);

  if (loading) return <div className="p-8 text-gray-400">Loading Refunds & Claims Operations...</div>;
  if (error) return <div className="p-8 text-rose-400 bg-rose-950/30 rounded-lg">Error: {error}</div>;

  const metrics = data?.metrics || {};
  const recentRefunds = Array.isArray(data?.recent_refunds) ? data.recent_refunds : [];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-black text-white">Refunds & Claims Portal</h1>
        <p className="text-sm text-gray-400">Process guest refund claims, audit eligibility, and verify payment returns.</p>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-gray-950 p-5 rounded-xl border border-gray-800">
          <p className="text-xs uppercase font-semibold text-gray-400">Pending Requests</p>
          <p className="text-3xl font-black text-amber-400 mt-2">{metrics.pending_refunds || 0}</p>
          <p className="text-xs text-slate-400 mt-1">₹{Number(metrics.pending_refund_amount || 0).toLocaleString()} pending</p>
        </div>

        <div className="bg-gray-950 p-5 rounded-xl border border-gray-800">
          <p className="text-xs uppercase font-semibold text-gray-400">Processed Refunds</p>
          <p className="text-3xl font-black text-emerald-400 mt-2">{metrics.processed_refunds || 0}</p>
          <p className="text-xs text-emerald-400 mt-1">₹{Number(metrics.total_refunded_amount || 0).toLocaleString()} total</p>
        </div>

        <div className="bg-gray-950 p-5 rounded-xl border border-gray-800">
          <p className="text-xs uppercase font-semibold text-gray-400">Failed / Rejected</p>
          <p className="text-3xl font-black text-rose-500 mt-2">{metrics.failed_refunds || 0}</p>
        </div>

        <div className="bg-gray-950 p-5 rounded-xl border border-gray-800">
          <p className="text-xs uppercase font-semibold text-gray-400">Gateway Status</p>
          <p className="text-xl font-bold text-emerald-400 mt-2">Razorpay Live</p>
          <p className="text-xs text-slate-400 mt-1">Direct reversal & RazorpayX active</p>
        </div>
      </div>

      {/* Recent Refunds Table */}
      <div className="bg-gray-950 rounded-xl border border-gray-800 overflow-hidden">
        <div className="p-5 border-b border-gray-800">
          <h3 className="text-base font-bold text-white">Refund Requests Queue</h3>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm text-gray-300">
            <thead className="bg-gray-900/60 text-xs uppercase text-gray-400 border-b border-gray-800">
              <tr>
                <th className="px-5 py-3">ID</th>
                <th className="px-5 py-3">Booking</th>
                <th className="px-5 py-3">Amount</th>
                <th className="px-5 py-3">Reason</th>
                <th className="px-5 py-3">Status</th>
                <th className="px-5 py-3">Created</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800/60">
              {recentRefunds.map((r: any) => (
                <tr key={r.id} className="hover:bg-gray-900/40">
                  <td className="px-5 py-3 font-mono text-xs text-emerald-400">REF-{r.id}</td>
                  <td className="px-5 py-3 text-xs text-gray-300">Booking #{r.booking_id}</td>
                  <td className="px-5 py-3 font-semibold text-white">₹{r.amount}</td>
                  <td className="px-5 py-3 text-xs text-gray-400">{r.reason || 'N/A'}</td>
                  <td className="px-5 py-3">
                    <span className="px-2 py-0.5 text-xs rounded-full bg-emerald-950 text-emerald-300 border border-emerald-800">
                      {r.status}
                    </span>
                  </td>
                  <td className="px-5 py-3 text-xs text-gray-400">{new Date(r.created_at).toLocaleDateString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
