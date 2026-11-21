import React, { useEffect, useState } from 'react';
import { fetchStaffDepartmentDashboard } from '../services/portalApi';

export const ReservationDashboard: React.FC = () => {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const token = localStorage.getItem('access_token') || sessionStorage.getItem('access_token') || '';
    fetchStaffDepartmentDashboard('RESERVATION', token)
      .then((res) => {
        setData(res);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, []);

  if (loading) return <div className="p-8 text-gray-400">Loading Reservation Operations Dashboard...</div>;
  if (error) return <div className="p-8 text-rose-400 bg-rose-950/30 rounded-lg">Error: {error}</div>;

  const metrics = data?.metrics || {};
  const recentBookings = Array.isArray(data?.recent_bookings) ? data.recent_bookings : [];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-black text-white">Reservation Management Portal</h1>
        <p className="text-sm text-gray-400">Real-time room occupancy, check-in flows, and guest bookings.</p>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-gray-950 p-5 rounded-xl border border-gray-800">
          <p className="text-xs uppercase font-semibold text-gray-400">Total Bookings</p>
          <p className="text-3xl font-black text-white mt-2">{metrics.total_bookings || 0}</p>
        </div>

        <div className="bg-gray-950 p-5 rounded-xl border border-gray-800">
          <p className="text-xs uppercase font-semibold text-gray-400">Confirmed Stays</p>
          <p className="text-3xl font-black text-emerald-400 mt-2">{metrics.confirmed_bookings || 0}</p>
        </div>

        <div className="bg-gray-950 p-5 rounded-xl border border-gray-800">
          <p className="text-xs uppercase font-semibold text-gray-400">Today's Check-ins</p>
          <p className="text-3xl font-black text-blue-400 mt-2">{metrics.upcoming_checkins_today || 0}</p>
        </div>

        <div className="bg-gray-950 p-5 rounded-xl border border-gray-800">
          <p className="text-xs uppercase font-semibold text-gray-400">Today's Check-outs</p>
          <p className="text-3xl font-black text-amber-400 mt-2">{metrics.upcoming_checkouts_today || 0}</p>
        </div>
      </div>

      {/* Recent Bookings Queue */}
      <div className="bg-gray-950 rounded-xl border border-gray-800 overflow-hidden">
        <div className="p-5 border-b border-gray-800">
          <h3 className="text-base font-bold text-white">Recent Guest Reservations</h3>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm text-gray-300">
            <thead className="bg-gray-900/60 text-xs uppercase text-gray-400 border-b border-gray-800">
              <tr>
                <th className="px-5 py-3">Booking ID</th>
                <th className="px-5 py-3">Guest Name</th>
                <th className="px-5 py-3">Phone</th>
                <th className="px-5 py-3">Dates</th>
                <th className="px-5 py-3">Amount</th>
                <th className="px-5 py-3">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800/60">
              {recentBookings.map((bk: any) => (
                <tr key={bk.id} className="hover:bg-gray-900/40">
                  <td className="px-5 py-3 font-mono text-xs text-blue-400">{bk.booking_id}</td>
                  <td className="px-5 py-3 font-semibold text-white">{bk.guest_name}</td>
                  <td className="px-5 py-3 text-gray-400">{bk.guest_phone}</td>
                  <td className="px-5 py-3 text-xs">{bk.check_in} → {bk.check_out}</td>
                  <td className="px-5 py-3 font-semibold text-emerald-400">₹{bk.total_amount}</td>
                  <td className="px-5 py-3">
                    <span className="px-2 py-0.5 text-xs rounded-full bg-blue-900/40 text-blue-300 border border-blue-800">
                      {bk.booking_status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
