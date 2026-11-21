import React, { useEffect, useState } from 'react';
import { fetchAdminDashboard } from '../services/portalApi';

export const AdminDashboard: React.FC = () => {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const token = localStorage.getItem('access_token') || sessionStorage.getItem('access_token') || '';
    fetchAdminDashboard(token)
      .then((res) => {
        setData(res.overview || {});
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, []);

  if (loading) return <div className="p-8 text-slate-400">Loading Administrative Oversight Metrics...</div>;
  if (error) return <div className="p-8 text-rose-400 bg-rose-950/30 rounded-lg">Error: {error}</div>;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-black text-white">Administrator Platform Oversight</h1>
        <p className="text-sm text-slate-400">Full system governance across staff, hotels, bookings, and financial flows.</p>
      </div>

      {/* KPI Oversight Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-slate-950 p-5 rounded-xl border border-slate-800">
          <p className="text-xs uppercase font-semibold text-slate-400">Total Staff Accounts</p>
          <p className="text-3xl font-black text-white mt-2">{data?.staff?.total || 0}</p>
          <p className="text-xs text-emerald-400 mt-1">{data?.staff?.active || 0} active employees</p>
        </div>

        <div className="bg-slate-950 p-5 rounded-xl border border-slate-800">
          <p className="text-xs uppercase font-semibold text-slate-400">Registered Properties</p>
          <p className="text-3xl font-black text-white mt-2">{data?.hotels?.total || 0}</p>
          <p className="text-xs text-amber-400 mt-1">{data?.hotels?.pending || 0} pending review</p>
        </div>

        <div className="bg-slate-950 p-5 rounded-xl border border-slate-800">
          <p className="text-xs uppercase font-semibold text-slate-400">All-Time Bookings</p>
          <p className="text-3xl font-black text-white mt-2">{data?.bookings?.total || 0}</p>
          <p className="text-xs text-blue-400 mt-1">{data?.bookings?.confirmed || 0} confirmed</p>
        </div>

        <div className="bg-slate-950 p-5 rounded-xl border border-slate-800">
          <p className="text-xs uppercase font-semibold text-slate-400">Processed Payments Volume</p>
          <p className="text-3xl font-black text-emerald-400 mt-2">
            ₹{Number(data?.financials?.total_revenue || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
          </p>
          <p className="text-xs text-slate-400 mt-1">{data?.financials?.payments_count || 0} total transactions</p>
        </div>
      </div>

      {/* Secondary Governance Panels */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-6">
        <div className="bg-slate-950 p-5 rounded-xl border border-slate-800">
          <h3 className="text-sm font-bold text-slate-200">Refunds Oversight</h3>
          <div className="mt-4 space-y-2 text-sm">
            <div className="flex justify-between py-1 border-b border-slate-800/60">
              <span className="text-slate-400">Pending Approvals</span>
              <span className="font-semibold text-amber-400">{data?.financials?.pending_refunds || 0}</span>
            </div>
            <div className="flex justify-between py-1">
              <span className="text-slate-400">Completed Refunds</span>
              <span className="font-semibold text-emerald-400">{data?.financials?.processed_refunds || 0}</span>
            </div>
          </div>
        </div>

        <div className="bg-slate-950 p-5 rounded-xl border border-slate-800">
          <h3 className="text-sm font-bold text-slate-200">Host Payouts Oversight</h3>
          <div className="mt-4 space-y-2 text-sm">
            <div className="flex justify-between py-1 border-b border-slate-800/60">
              <span className="text-slate-400">Pending Requests</span>
              <span className="font-semibold text-amber-400">{data?.financials?.pending_payouts || 0}</span>
            </div>
            <div className="flex justify-between py-1">
              <span className="text-slate-400">Settled Transfers</span>
              <span className="font-semibold text-emerald-400">{data?.financials?.completed_payouts || 0}</span>
            </div>
          </div>
        </div>

        <div className="bg-slate-950 p-5 rounded-xl border border-slate-800">
          <h3 className="text-sm font-bold text-slate-200">Support Oversight</h3>
          <div className="mt-4 space-y-2 text-sm">
            <div className="flex justify-between py-1 border-b border-slate-800/60">
              <span className="text-slate-400">Open Tickets</span>
              <span className="font-semibold text-rose-400">{data?.support?.open_tickets || 0}</span>
            </div>
            <div className="flex justify-between py-1">
              <span className="text-slate-400">In Progress</span>
              <span className="font-semibold text-blue-400">{data?.support?.in_progress_tickets || 0}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
