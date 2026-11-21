import React, { useEffect, useState } from 'react';
import { fetchStaffDepartmentDashboard } from '../services/portalApi';

export const HotelVerificationDashboard: React.FC = () => {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const token = localStorage.getItem('access_token') || sessionStorage.getItem('access_token') || '';
    fetchStaffDepartmentDashboard('HOTEL_VERIFICATION', token)
      .then((res) => {
        setData(res);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, []);

  if (loading) return <div className="p-8 text-gray-400">Loading Hotel Verification Desk...</div>;
  if (error) return <div className="p-8 text-rose-400 bg-rose-950/30 rounded-lg">Error: {error}</div>;

  const metrics = data?.metrics || {};
  const recentApplications = Array.isArray(data?.recent_applications) ? data.recent_applications : [];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-black text-white">Hotel Verification & Compliance Portal</h1>
        <p className="text-sm text-gray-400">Review property ownership documents, check compliance, and approve/reject hotel onboardings.</p>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-gray-950 p-5 rounded-xl border border-gray-800">
          <p className="text-xs uppercase font-semibold text-gray-400">Submitted Applications</p>
          <p className="text-3xl font-black text-amber-400 mt-2">{metrics.pending_verifications || 0}</p>
        </div>

        <div className="bg-gray-950 p-5 rounded-xl border border-gray-800">
          <p className="text-xs uppercase font-semibold text-gray-400">Under Review</p>
          <p className="text-3xl font-black text-blue-400 mt-2">{metrics.under_review_hotels || 0}</p>
        </div>

        <div className="bg-gray-950 p-5 rounded-xl border border-gray-800">
          <p className="text-xs uppercase font-semibold text-gray-400">Approved Hotels</p>
          <p className="text-3xl font-black text-emerald-400 mt-2">{metrics.approved_hotels || 0}</p>
        </div>

        <div className="bg-gray-950 p-5 rounded-xl border border-gray-800">
          <p className="text-xs uppercase font-semibold text-gray-400">Rejected Applications</p>
          <p className="text-3xl font-black text-rose-500 mt-2">{metrics.rejected_hotels || 0}</p>
        </div>
      </div>

      {/* Verification Queue Table */}
      <div className="bg-gray-950 rounded-xl border border-gray-800 overflow-hidden">
        <div className="p-5 border-b border-gray-800">
          <h3 className="text-base font-bold text-white">Hotel Onboarding Queue</h3>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm text-gray-300">
            <thead className="bg-gray-900/60 text-xs uppercase text-gray-400 border-b border-gray-800">
              <tr>
                <th className="px-5 py-3">Property Name</th>
                <th className="px-5 py-3">Location</th>
                <th className="px-5 py-3">Status</th>
                <th className="px-5 py-3">Approval Flag</th>
                <th className="px-5 py-3">Submitted Date</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800/60">
              {recentApplications.map((h: any) => (
                <tr key={h.id} className="hover:bg-gray-900/40">
                  <td className="px-5 py-3 font-semibold text-white">{h.name}</td>
                  <td className="px-5 py-3 text-xs text-gray-400">{h.city}, {h.state}</td>
                  <td className="px-5 py-3">
                    <span className="px-2 py-0.5 text-xs rounded-full bg-cyan-950 text-cyan-300 border border-cyan-800">
                      {h.status}
                    </span>
                  </td>
                  <td className="px-5 py-3">
                    {h.is_approved ? (
                      <span className="text-xs text-emerald-400 font-bold">Approved</span>
                    ) : (
                      <span className="text-xs text-amber-400 font-bold">Pending</span>
                    )}
                  </td>
                  <td className="px-5 py-3 text-xs text-gray-400">{new Date(h.created_at).toLocaleDateString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
