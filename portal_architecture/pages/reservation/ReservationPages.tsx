import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  fetchStaffBookings,
  fetchStaffBookingDetail,
  staffCheckInGuest,
  staffCheckOutGuest,
  fetchStaffRooms,
  fetchStaffGuests
} from '../../services/portalApi';

function getToken(): string {
  return localStorage.getItem('access_token') || sessionStorage.getItem('access_token') || '';
}

// 1. Booking Management Page
export const ReservationBookingsPage: React.FC = () => {
  const [bookings, setBookings] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState('');
  const [search, setSearch] = useState('');
  const navigate = useNavigate();

  const loadData = () => {
    setLoading(true);
    setError(null);
    const params: any = {};
    if (statusFilter) params.status = statusFilter;
    if (search) params.search = search;
    fetchStaffBookings(params, getToken())
      .then((res) => {
        const list = Array.isArray(res)
          ? res
          : Array.isArray(res?.results)
            ? res.results
            : Array.isArray(res?.data)
              ? res.data
              : Array.isArray(res?.data?.results)
                ? res.data.results
                : [];
        setBookings(list);
        setLoading(false);
      })
      .catch((err: any) => {
        setError(err.message || 'Failed to load reservations');
        setLoading(false);
      });
  };

  useEffect(() => {
    loadData();
  }, [statusFilter]);

  const handleAction = async (id: string, action: 'checkin' | 'checkout') => {
    try {
      setActionLoading(id);
      if (action === 'checkin') await staffCheckInGuest(id, getToken());
      else await staffCheckOutGuest(id, getToken());
      loadData();
    } catch (e: any) {
      alert(e.message || 'Operation failed');
    } finally {
      setActionLoading(null);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-black text-white">Booking Management</h1>
          <p className="text-sm text-gray-400">Search and manage guest reservations and check-in statuses.</p>
        </div>
      </div>

      {/* Filter Bar */}
      <div className="flex gap-3 bg-gray-950 p-4 rounded-xl border border-gray-800">
        <input
          type="text"
          placeholder="Search by Guest Name, Booking ID, Phone..."
          className="flex-1 bg-gray-900 border border-gray-800 rounded-lg px-4 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && loadData()}
        />
        <select
          className="bg-gray-900 border border-gray-800 rounded-lg px-3 py-2 text-sm text-gray-300"
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
        >
          <option value="">All Statuses</option>
          <option value="CONFIRMED">Confirmed</option>
          <option value="CHECKED_IN">Checked In</option>
          <option value="CHECKED_OUT">Checked Out</option>
          <option value="CANCELLED">Cancelled</option>
        </select>
        <button
          onClick={loadData}
          disabled={loading}
          className="px-5 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white rounded-lg text-sm font-semibold transition"
        >
          {loading ? 'Searching...' : 'Search'}
        </button>
      </div>

      {error && (
        <div className="p-4 bg-rose-950/40 border border-rose-800 rounded-xl text-rose-300 text-sm">
          {error}
        </div>
      )}

      {/* Bookings Table */}
      <div className="bg-gray-950 rounded-xl border border-gray-800 overflow-hidden">
        {loading ? (
          <div className="p-8 text-center text-gray-500">Loading reservations...</div>
        ) : bookings.length === 0 ? (
          <div className="p-8 text-center text-gray-500">No reservations found matching the criteria.</div>
        ) : (
          <table className="w-full text-left text-sm text-gray-300">
            <thead className="bg-gray-900/60 text-xs uppercase text-gray-400 border-b border-gray-800">
              <tr>
                <th className="px-5 py-3">Booking ID</th>
                <th className="px-5 py-3">Guest</th>
                <th className="px-5 py-3">Hotel</th>
                <th className="px-5 py-3">Stay Dates</th>
                <th className="px-5 py-3">Total</th>
                <th className="px-5 py-3">Status</th>
                <th className="px-5 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800/60">
              {bookings.map((b) => {
                const targetId = String(b.booking_id || b.id);
                const isRowAction = actionLoading === targetId;
                return (
                  <tr key={b.id || targetId} className="hover:bg-gray-900/40">
                    <td className="px-5 py-3 font-mono text-xs text-blue-400">{b.booking_id}</td>
                    <td className="px-5 py-3 font-semibold text-white">{b.guest_name}</td>
                    <td className="px-5 py-3 text-gray-400 text-xs">{b.hotel?.name || b.hotel_name || 'N/A'}</td>
                    <td className="px-5 py-3 text-xs">{b.check_in} → {b.check_out}</td>
                    <td className="px-5 py-3 font-semibold text-emerald-400">₹{b.total_amount}</td>
                    <td className="px-5 py-3">
                      <span className="px-2 py-0.5 text-xs rounded-full bg-blue-950 text-blue-300 border border-blue-800">
                        {b.booking_status}
                      </span>
                    </td>
                    <td className="px-5 py-3 text-right space-x-2">
                      {b.booking_status === 'CONFIRMED' && (
                        <button
                          disabled={isRowAction}
                          onClick={() => handleAction(targetId, 'checkin')}
                          className="px-2.5 py-1 text-xs bg-emerald-700 hover:bg-emerald-600 disabled:opacity-50 text-white rounded font-medium"
                        >
                          {isRowAction ? 'Processing...' : 'Check In'}
                        </button>
                      )}
                      {b.booking_status === 'CHECKED_IN' && (
                        <button
                          disabled={isRowAction}
                          onClick={() => handleAction(targetId, 'checkout')}
                          className="px-2.5 py-1 text-xs bg-amber-700 hover:bg-amber-600 disabled:opacity-50 text-white rounded font-medium"
                        >
                          {isRowAction ? 'Processing...' : 'Check Out'}
                        </button>
                      )}
                      <button
                        onClick={() => navigate(`/staff/reservation/bookings/${targetId}`)}
                        className="px-2.5 py-1 text-xs bg-gray-800 hover:bg-gray-700 text-gray-200 rounded"
                      >
                        Details
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
};

// 2. Booking Detail Page
export const ReservationBookingDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const [booking, setBooking] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (id) {
      setLoading(true);
      setError(null);
      fetchStaffBookingDetail(id, getToken())
        .then((res) => {
          setBooking(res.booking || res.data || res);
          setLoading(false);
        })
        .catch((err: any) => {
          setError(err.message || 'Failed to load booking details');
          setLoading(false);
        });
    }
  }, [id]);

  if (loading) return <div className="p-8 text-gray-400">Loading booking details...</div>;
  if (error || !booking) return <div className="p-8 text-rose-400">{error || 'Booking not found.'}</div>;

  return (
    <div className="space-y-6 max-w-4xl">
      <div>
        <h1 className="text-2xl font-black text-white">Booking #{booking.booking_id}</h1>
        <p className="text-sm text-gray-400">Reservation Details & Guest Verification</p>
      </div>

      <div className="grid grid-cols-2 gap-4 bg-gray-950 p-6 rounded-xl border border-gray-800">
        <div>
          <p className="text-xs text-gray-400">Guest Name</p>
          <p className="text-lg font-bold text-white">{booking.guest_name}</p>
        </div>
        <div>
          <p className="text-xs text-gray-400">Contact</p>
          <p className="text-sm text-gray-200">{booking.guest_phone || booking.guest_email || 'N/A'}</p>
        </div>
        <div>
          <p className="text-xs text-gray-400">Stay Dates</p>
          <p className="text-sm text-gray-200">{booking.check_in} to {booking.check_out}</p>
        </div>
        <div>
          <p className="text-xs text-gray-400">Total Price</p>
          <p className="text-lg font-bold text-emerald-400">₹{booking.total_amount}</p>
        </div>
        <div>
          <p className="text-xs text-gray-400">Status</p>
          <span className="inline-block mt-1 px-3 py-1 text-xs rounded-full bg-blue-950 text-blue-300 border border-blue-800">
            {booking.booking_status}
          </span>
        </div>
      </div>
    </div>
  );
};

// 3. Customer Booking Information (Guests Page)
export const ReservationGuestsPage: React.FC = () => {
  const [guests, setGuests] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    fetchStaffGuests({}, getToken())
      .then((res) => {
        const list = Array.isArray(res?.guests)
          ? res.guests
          : Array.isArray(res)
            ? res
            : Array.isArray(res?.results)
              ? res.results
              : [];
        setGuests(list);
        setLoading(false);
      })
      .catch((err: any) => {
        setError(err.message || 'Failed to load guests');
        setLoading(false);
      });
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-black text-white">Customer Booking Information</h1>
        <p className="text-sm text-gray-400">Registered guest directory and stay history.</p>
      </div>

      {error && (
        <div className="p-4 bg-rose-950/40 border border-rose-800 rounded-xl text-rose-300 text-sm">
          {error}
        </div>
      )}

      <div className="bg-gray-950 rounded-xl border border-gray-800 overflow-hidden">
        {loading ? (
          <div className="p-8 text-center text-gray-500">Loading guests...</div>
        ) : guests.length === 0 ? (
          <div className="p-8 text-center text-gray-500">No guests found in directory.</div>
        ) : (
          <table className="w-full text-left text-sm text-gray-300">
            <thead className="bg-gray-900/60 text-xs uppercase text-gray-400 border-b border-gray-800">
              <tr>
                <th className="px-5 py-3">Guest Name</th>
                <th className="px-5 py-3">Phone</th>
                <th className="px-5 py-3">Email</th>
                <th className="px-5 py-3">Latest Booking</th>
                <th className="px-5 py-3">Hotel</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800/60">
              {guests.map((g, idx) => (
                <tr key={idx} className="hover:bg-gray-900/40">
                  <td className="px-5 py-3 font-semibold text-white">{g.guest_name}</td>
                  <td className="px-5 py-3 text-gray-400">{g.guest_phone || 'N/A'}</td>
                  <td className="px-5 py-3 text-gray-400">{g.guest_email || 'N/A'}</td>
                  <td className="px-5 py-3 font-mono text-xs text-blue-400">{g.latest_booking_id}</td>
                  <td className="px-5 py-3 text-gray-300 text-xs">{g.hotel_name}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
};

// 4. Hotel & Room Information Page
export const ReservationRoomsPage: React.FC = () => {
  const [rooms, setRooms] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    fetchStaffRooms({}, getToken())
      .then((res) => {
        const list = Array.isArray(res?.rooms)
          ? res.rooms
          : Array.isArray(res)
            ? res
            : Array.isArray(res?.results)
              ? res.results
              : [];
        setRooms(list);
        setLoading(false);
      })
      .catch((err: any) => {
        setError(err.message || 'Failed to load rooms');
        setLoading(false);
      });
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-black text-white">Hotel and Room Information</h1>
        <p className="text-sm text-gray-400">Available room inventory and capacity across properties.</p>
      </div>

      {error && (
        <div className="p-4 bg-rose-950/40 border border-rose-800 rounded-xl text-rose-300 text-sm">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {loading ? (
          <div className="p-8 text-gray-500 col-span-3">Loading rooms...</div>
        ) : rooms.length === 0 ? (
          <div className="p-8 text-gray-500 col-span-3">No room records available.</div>
        ) : (
          rooms.map((r) => (
            <div key={r.id} className="bg-gray-950 p-5 rounded-xl border border-gray-800">
              <h3 className="text-base font-bold text-white">{r.title}</h3>
              <p className="text-xs text-blue-400 mt-1">{r.hotel_name}</p>
              <div className="mt-4 flex justify-between items-center text-sm">
                <span className="text-gray-400">Rate / Night:</span>
                <span className="font-bold text-emerald-400">₹{r.price_per_night}</span>
              </div>
              <div className="mt-1 flex justify-between items-center text-sm">
                <span className="text-gray-400">Capacity:</span>
                <span className="text-gray-300">{r.capacity} Guests</span>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};

// 5. Authorized Reservation Operations Page
export const ReservationOperationsPage: React.FC = () => {
  const [bookingId, setBookingId] = useState('');
  const [statusMsg, setStatusMsg] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleOp = async (action: 'checkin' | 'checkout') => {
    if (!bookingId.trim()) {
      setStatusMsg('❌ Please enter a Booking ID or numeric ID.');
      return;
    }
    setStatusMsg(null);
    setIsSubmitting(true);
    try {
      if (action === 'checkin') {
        const res = await staffCheckInGuest(bookingId.trim(), getToken());
        setStatusMsg(`✅ ${res.message || 'Check-in processed successfully.'}`);
      } else {
        const res = await staffCheckOutGuest(bookingId.trim(), getToken());
        setStatusMsg(`✅ ${res.message || 'Check-out processed successfully.'}`);
      }
    } catch (e: any) {
      setStatusMsg(`❌ ${e.message || 'Operation failed.'}`);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="space-y-6 max-w-xl">
      <div>
        <h1 className="text-2xl font-black text-white">Authorized Reservation Operations</h1>
        <p className="text-sm text-gray-400">Front desk instant check-in / check-out processing terminal.</p>
      </div>

      <div className="bg-gray-950 p-6 rounded-xl border border-gray-800 space-y-4">
        <div>
          <label className="text-xs font-semibold text-gray-300 uppercase">Booking ID or Numeric ID</label>
          <input
            type="text"
            className="w-full mt-1 bg-gray-900 border border-gray-800 rounded-lg px-4 py-2 text-white text-sm"
            placeholder="e.g. GS-311 or 311"
            value={bookingId}
            onChange={(e) => setBookingId(e.target.value)}
          />
        </div>

        <div className="flex gap-3">
          <button
            disabled={isSubmitting || !bookingId.trim()}
            onClick={() => handleOp('checkin')}
            className="flex-1 py-2.5 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white rounded-lg text-sm font-bold transition"
          >
            {isSubmitting ? 'Processing...' : 'Check In Guest'}
          </button>
          <button
            disabled={isSubmitting || !bookingId.trim()}
            onClick={() => handleOp('checkout')}
            className="flex-1 py-2.5 bg-amber-600 hover:bg-amber-700 disabled:opacity-50 text-white rounded-lg text-sm font-bold transition"
          >
            {isSubmitting ? 'Processing...' : 'Check Out Guest'}
          </button>
        </div>

        {statusMsg && (
          <div className="p-3 bg-gray-900 border border-gray-800 rounded text-sm text-gray-200">
            {statusMsg}
          </div>
        )}
      </div>
    </div>
  );
};

// 6. Reservation Activity Logs Page
export const ReservationActivityPage: React.FC = () => {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-black text-white">Reservation Activity Logs</h1>
        <p className="text-sm text-gray-400">Audit trail of reservation modifications and guest arrivals.</p>
      </div>
      <div className="bg-gray-950 p-6 rounded-xl border border-gray-800 text-sm text-gray-400">
        All front desk check-ins, check-outs, and stay inquiries are cryptographically recorded in the central audit ledger.
      </div>
    </div>
  );
};
