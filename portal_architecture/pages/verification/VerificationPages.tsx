import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  fetchStaffVerifications,
  fetchStaffVerificationDetail,
  approveStaffHotel,
  rejectStaffHotel,
  fetchStaffVerificationHistory,
  fetchStaffHotelDocuments
} from '../../services/portalApi';

function getToken(): string {
  return localStorage.getItem('access_token') || sessionStorage.getItem('access_token') || '';
}

// 1. Pending Hotel Applications Queue Page
export const VerificationPendingPage: React.FC = () => {
  const [hotels, setHotels] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState<{ id: number; action: 'approve' | 'reject' } | null>(null);
  const navigate = useNavigate();

  const loadData = () => {
    setLoading(true);
    setError(null);
    fetchStaffVerifications({}, getToken())
      .then((res) => {
        const list = Array.isArray(res?.verifications)
          ? res.verifications
          : Array.isArray(res)
            ? res
            : Array.isArray(res?.results)
              ? res.results
              : [];
        setHotels(list);
        setLoading(false);
      })
      .catch((err: any) => {
        setError(err.message || 'Failed to load pending verifications');
        setLoading(false);
      });
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleApprove = async (id: number) => {
    if (actionLoading !== null) return;
    if (!window.confirm(`Approve hotel #${id} for public booking?`)) return;
    setActionLoading({ id, action: 'approve' });
    try {
      await approveStaffHotel(id, getToken());
      alert('Hotel approved successfully!');
      loadData();
    } catch (e: any) {
      alert(e.message || 'Approval failed');
    } finally {
      setActionLoading(null);
    }
  };

  const handleReject = async (id: number) => {
    if (actionLoading !== null) return;
    const reason = window.prompt('Please enter mandatory rejection reason:');
    if (!reason || !reason.trim()) return;
    setActionLoading({ id, action: 'reject' });
    try {
      await rejectStaffHotel(id, reason.trim(), getToken());
      alert('Hotel application rejected.');
      loadData();
    } catch (e: any) {
      alert(e.message || 'Rejection failed');
    } finally {
      setActionLoading(null);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-black text-white">Pending Hotel Applications</h1>
        <p className="text-sm text-gray-400">Review onboarding properties, inspect documents, and grant live booking status.</p>
      </div>

      {error && (
        <div className="p-4 bg-rose-950/40 border border-rose-800 rounded-xl text-rose-300 text-sm">
          {error}
        </div>
      )}

      <div className="bg-gray-950 rounded-xl border border-gray-800 overflow-hidden">
        {loading ? (
          <div className="p-8 text-center text-gray-500">Loading hotel submissions...</div>
        ) : hotels.length === 0 ? (
          <div className="p-8 text-center text-gray-500">No pending hotel applications awaiting verification.</div>
        ) : (
          <table className="w-full text-left text-sm text-gray-300">
            <thead className="bg-gray-900/60 text-xs uppercase text-gray-400 border-b border-gray-800">
              <tr>
                <th className="px-5 py-3">Property</th>
                <th className="px-5 py-3">Location</th>
                <th className="px-5 py-3">Host</th>
                <th className="px-5 py-3">Documents</th>
                <th className="px-5 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800/60">
              {hotels.map((h) => {
                const isThisRowAction = actionLoading?.id === h.id;
                return (
                  <tr key={h.id} className="hover:bg-gray-900/40">
                    <td className="px-5 py-3 font-semibold text-white">{h.name}</td>
                    <td className="px-5 py-3 text-xs text-gray-400">{h.city}, {h.state}</td>
                    <td className="px-5 py-3 text-xs text-gray-300">{h.owner_name}</td>
                    <td className="px-5 py-3 text-xs text-cyan-400 font-bold">{h.documents_count || 0} Docs</td>
                    <td className="px-5 py-3 text-right space-x-2">
                      <button
                        disabled={isThisRowAction}
                        onClick={() => handleApprove(h.id)}
                        className="px-2.5 py-1 text-xs bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white rounded font-medium transition"
                      >
                        {isThisRowAction && actionLoading?.action === 'approve' ? 'Approving...' : 'Approve'}
                      </button>
                      <button
                        disabled={isThisRowAction}
                        onClick={() => handleReject(h.id)}
                        className="px-2.5 py-1 text-xs bg-rose-600 hover:bg-rose-700 disabled:opacity-50 text-white rounded font-medium transition"
                      >
                        {isThisRowAction && actionLoading?.action === 'reject' ? 'Rejecting...' : 'Reject'}
                      </button>
                      <button
                        onClick={() => navigate(`/staff/verification/${h.id}`)}
                        className="px-2.5 py-1 text-xs bg-gray-800 hover:bg-gray-700 text-gray-200 rounded"
                      >
                        Review
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

// 2. Hotel Documents Directory Page
export const VerificationDocumentsPage: React.FC = () => {
  const [docs, setDocs] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    fetchStaffHotelDocuments({}, getToken())
      .then((res) => {
        const list = Array.isArray(res?.documents)
          ? res.documents
          : Array.isArray(res)
            ? res
            : [];
        setDocs(list);
        setLoading(false);
      })
      .catch((err: any) => {
        setError(err.message || 'Failed to load documents');
        setLoading(false);
      });
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-black text-white">Hotel Compliance Documents</h1>
        <p className="text-sm text-gray-400">Trade licenses, property ownership deeds, PAN, and GST certificates.</p>
      </div>

      {error && (
        <div className="p-4 bg-rose-950/40 border border-rose-800 rounded-xl text-rose-300 text-sm">
          {error}
        </div>
      )}

      <div className="bg-gray-950 rounded-xl border border-gray-800 overflow-hidden">
        {loading ? (
          <div className="p-8 text-center text-gray-500">Loading documents...</div>
        ) : docs.length === 0 ? (
          <div className="p-8 text-center text-gray-500">No verification documents on file.</div>
        ) : (
          <table className="w-full text-left text-sm text-gray-300">
            <thead className="bg-gray-900/60 text-xs uppercase text-gray-400 border-b border-gray-800">
              <tr>
                <th className="px-5 py-3">Hotel</th>
                <th className="px-5 py-3">Owner</th>
                <th className="px-5 py-3">Document Type</th>
                <th className="px-5 py-3">Status</th>
                <th className="px-5 py-3 text-right">View</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800/60">
              {docs.map((d) => (
                <tr key={d.id} className="hover:bg-gray-900/40">
                  <td className="px-5 py-3 font-semibold text-white">{d.hotel_name}</td>
                  <td className="px-5 py-3 text-gray-400 text-xs">{d.owner_name}</td>
                  <td className="px-5 py-3 text-cyan-300 text-xs font-mono">{d.document_type_label || d.document_type}</td>
                  <td className="px-5 py-3">
                    <span className="px-2 py-0.5 text-xs rounded-full bg-cyan-950 text-cyan-300 border border-cyan-800">
                      {d.status}
                    </span>
                  </td>
                  <td className="px-5 py-3 text-right">
                    {d.document_url ? (
                      <a
                        href={d.document_url}
                        target="_blank"
                        rel="noreferrer"
                        className="px-2.5 py-1 text-xs bg-cyan-800 hover:bg-cyan-700 text-cyan-100 rounded"
                      >
                        Open File
                      </a>
                    ) : (
                      <span className="text-xs text-gray-500">No URL</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
};

// 3. Hotel Verification Detail & Inspection Page
export const VerificationDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const [hotel, setHotel] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState<'approve' | 'reject' | null>(null);
  const [statusMsg, setStatusMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  const loadData = () => {
    if (id) {
      setLoading(true);
      setError(null);
      fetchStaffVerificationDetail(id, getToken())
        .then((res) => {
          setHotel(res.hotel || res.data || res);
          setLoading(false);
        })
        .catch((err: any) => {
          setError(err.message || 'Failed to load verification detail');
          setLoading(false);
        });
    }
  };

  useEffect(() => {
    loadData();
  }, [id]);

  const handleApprove = async () => {
    if (!id || isSubmitting) return;
    if (!window.confirm(`Approve property '${hotel.name}'?`)) return;
    setIsSubmitting('approve');
    setStatusMsg(null);
    try {
      await approveStaffHotel(id, getToken());
      setStatusMsg({ type: 'success', text: 'Hotel approved for public booking.' });
      loadData();
    } catch (e: any) {
      setStatusMsg({ type: 'error', text: e.message || 'Approval failed' });
    } finally {
      setIsSubmitting(null);
    }
  };

  const handleReject = async () => {
    if (!id || isSubmitting) return;
    const reason = window.prompt('Enter mandatory rejection reason:');
    if (!reason || !reason.trim()) return;
    setIsSubmitting('reject');
    setStatusMsg(null);
    try {
      await rejectStaffHotel(id, reason.trim(), getToken());
      setStatusMsg({ type: 'success', text: 'Hotel application rejected.' });
      loadData();
    } catch (e: any) {
      setStatusMsg({ type: 'error', text: e.message || 'Rejection failed' });
    } finally {
      setIsSubmitting(null);
    }
  };

  if (loading) return <div className="p-8 text-gray-400">Loading hotel verification file...</div>;
  if (error || !hotel) return <div className="p-8 text-rose-400">{error || 'Hotel not found.'}</div>;

  return (
    <div className="space-y-6 max-w-4xl">
      <div>
        <h1 className="text-2xl font-black text-white">{hotel.name}</h1>
        <p className="text-sm text-gray-400">{hotel.address}, {hotel.city}, {hotel.state}</p>
      </div>

      {statusMsg && (
        <div className={`p-4 rounded-xl text-sm border ${
          statusMsg.type === 'success'
            ? 'bg-emerald-950/40 border-emerald-800 text-emerald-300'
            : 'bg-rose-950/40 border-rose-800 text-rose-300'
        }`}>
          {statusMsg.text}
        </div>
      )}

      <div className="grid grid-cols-2 gap-4 bg-gray-950 p-6 rounded-xl border border-gray-800">
        <div>
          <p className="text-xs text-gray-400">Property Type</p>
          <p className="text-base font-bold text-white mt-1">{hotel.property_type}</p>
        </div>
        <div>
          <p className="text-xs text-gray-400">Verification Status</p>
          <span className="inline-block mt-1 px-3 py-1 text-xs rounded-full bg-cyan-950 text-cyan-300 border border-cyan-800">
            {hotel.status}
          </span>
        </div>
        <div>
          <p className="text-xs text-gray-400">Host Owner</p>
          <p className="text-sm font-semibold text-white mt-1">{hotel.owner?.name || hotel.owner_name}</p>
          <p className="text-xs text-gray-400">{hotel.owner?.email || hotel.owner?.phone || 'N/A'}</p>
        </div>
        <div>
          <p className="text-xs text-gray-400">Approval Flag</p>
          <p className="text-sm font-bold text-emerald-400 mt-1">{hotel.is_approved ? 'Live (Approved)' : 'Pending Review'}</p>
        </div>
      </div>

      {/* Action Buttons */}
      <div className="flex gap-4">
        <button
          onClick={handleApprove}
          disabled={isSubmitting !== null}
          className="px-6 py-2.5 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white rounded-lg font-bold text-sm transition"
        >
          {isSubmitting === 'approve' ? 'Approving...' : 'Approve Property'}
        </button>
        <button
          onClick={handleReject}
          disabled={isSubmitting !== null}
          className="px-6 py-2.5 bg-rose-600 hover:bg-rose-700 disabled:opacity-50 text-white rounded-lg font-bold text-sm transition"
        >
          {isSubmitting === 'reject' ? 'Rejecting...' : 'Reject Application'}
        </button>
      </div>
    </div>
  );
};

// 4. Verification Review Page
export const VerificationReviewPage: React.FC = () => {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-black text-white">Verification Compliance Review</h1>
        <p className="text-sm text-gray-400">Audit checklist for government compliance, safety protocols, and property registration.</p>
      </div>
      <div className="bg-gray-950 p-6 rounded-xl border border-gray-800 text-sm text-gray-400">
        All partner properties must fulfill safety inspections, valid trade licenses, and PAN/GST verification before onboarding.
      </div>
    </div>
  );
};

// 5. Authorized Verification Actions Page
export const VerificationActionsPage: React.FC = () => {
  const [hotelId, setHotelId] = useState('');
  const [reason, setReason] = useState('');
  const [msg, setMsg] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState<'approve' | 'reject' | null>(null);

  const handleApprove = async () => {
    if (!hotelId.trim()) {
      setMsg('❌ Please enter a Hotel ID.');
      return;
    }
    setMsg(null);
    setIsSubmitting('approve');
    try {
      const res = await approveStaffHotel(hotelId.trim(), getToken());
      setMsg(`✅ ${res.message || 'Hotel approved successfully.'}`);
    } catch (e: any) {
      setMsg(`❌ ${e.message}`);
    } finally {
      setIsSubmitting(null);
    }
  };

  const handleReject = async () => {
    if (!hotelId.trim()) {
      setMsg('❌ Please enter a Hotel ID.');
      return;
    }
    if (!reason.trim()) {
      setMsg('❌ Mandatory rejection reason is required.');
      return;
    }
    setMsg(null);
    setIsSubmitting('reject');
    try {
      const res = await rejectStaffHotel(hotelId.trim(), reason.trim(), getToken());
      setMsg(`⚠️ ${res.message || 'Hotel rejected.'}`);
    } catch (e: any) {
      setMsg(`❌ ${e.message}`);
    } finally {
      setIsSubmitting(null);
    }
  };

  return (
    <div className="space-y-6 max-w-xl">
      <div>
        <h1 className="text-2xl font-black text-white">Approve / Reject Operational Terminal</h1>
        <p className="text-sm text-gray-400">Direct compliance action console for hotel onboarding decisions.</p>
      </div>

      <div className="bg-gray-950 p-6 rounded-xl border border-gray-800 space-y-4">
        <div>
          <label className="text-xs font-semibold text-gray-300 uppercase">Hotel ID</label>
          <input
            type="number"
            className="w-full mt-1 bg-gray-900 border border-gray-800 rounded-lg px-4 py-2 text-white text-sm"
            placeholder="e.g. 1"
            value={hotelId}
            onChange={(e) => setHotelId(e.target.value)}
          />
        </div>
        <div>
          <label className="text-xs font-semibold text-gray-300 uppercase">Rejection Reason (if rejecting)</label>
          <input
            type="text"
            className="w-full mt-1 bg-gray-900 border border-gray-800 rounded-lg px-4 py-2 text-white text-sm"
            placeholder="Reason for rejection (mandatory for reject action)"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
        </div>
        <div className="flex gap-3">
          <button
            onClick={handleApprove}
            disabled={isSubmitting !== null || !hotelId.trim()}
            className="flex-1 py-2.5 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white rounded-lg text-sm font-bold transition"
          >
            {isSubmitting === 'approve' ? 'Approving...' : 'Approve Hotel'}
          </button>
          <button
            onClick={handleReject}
            disabled={isSubmitting !== null || !hotelId.trim()}
            className="flex-1 py-2.5 bg-rose-600 hover:bg-rose-700 disabled:opacity-50 text-white rounded-lg text-sm font-bold transition"
          >
            {isSubmitting === 'reject' ? 'Rejecting...' : 'Reject Hotel'}
          </button>
        </div>
        {msg && <div className="p-3 bg-gray-900 border border-gray-800 rounded text-sm text-gray-200">{msg}</div>}
      </div>
    </div>
  );
};

// 6. Verification History Page
export const VerificationHistoryPage: React.FC = () => {
  const [history, setHistory] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    fetchStaffVerificationHistory(getToken())
      .then((res) => {
        const list = Array.isArray(res?.history)
          ? res.history
          : Array.isArray(res)
            ? res
            : [];
        setHistory(list);
        setLoading(false);
      })
      .catch((err: any) => {
        setError(err.message || 'Failed to load verification history');
        setLoading(false);
      });
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-black text-white">Verification History</h1>
        <p className="text-sm text-gray-400">Archive of approved and rejected hotel onboarding applications.</p>
      </div>

      {error && (
        <div className="p-4 bg-rose-950/40 border border-rose-800 rounded-xl text-rose-300 text-sm">
          {error}
        </div>
      )}

      <div className="bg-gray-950 rounded-xl border border-gray-800 overflow-hidden">
        {loading ? (
          <div className="p-8 text-center text-gray-500">Loading history...</div>
        ) : history.length === 0 ? (
          <div className="p-8 text-center text-gray-500">No verification history records found.</div>
        ) : (
          <table className="w-full text-left text-sm text-gray-300">
            <thead className="bg-gray-900/60 text-xs uppercase text-gray-400 border-b border-gray-800">
              <tr>
                <th className="px-5 py-3">Property</th>
                <th className="px-5 py-3">Location</th>
                <th className="px-5 py-3">Host</th>
                <th className="px-5 py-3">Decision</th>
                <th className="px-5 py-3">Remarks / Reason</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800/60">
              {history.map((h) => (
                <tr key={h.id} className="hover:bg-gray-900/40">
                  <td className="px-5 py-3 font-semibold text-white">{h.name}</td>
                  <td className="px-5 py-3 text-xs text-gray-400">{h.city}, {h.state}</td>
                  <td className="px-5 py-3 text-xs text-gray-300">{h.owner_name}</td>
                  <td className="px-5 py-3">
                    <span
                      className={`px-2 py-0.5 text-xs rounded-full font-bold ${
                        h.is_approved
                          ? 'bg-emerald-950 text-emerald-300 border border-emerald-800'
                          : 'bg-rose-950 text-rose-300 border border-rose-800'
                      }`}
                    >
                      {h.status}
                    </span>
                  </td>
                  <td className="px-5 py-3 text-xs text-gray-400">{h.rejection_reason || 'Verified & Compliant'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
};
