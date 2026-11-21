import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  fetchStaffRefunds,
  fetchStaffRefundDetail,
  fetchStaffRefundEligibility,
  processStaffRefund,
  fetchStaffRefundHistory
} from '../../services/portalApi';

function getToken(): string {
  return localStorage.getItem('access_token') || sessionStorage.getItem('access_token') || '';
}

// 1. Refund Requests Queue Page
export const RefundRequestsPage: React.FC = () => {
  const [refunds, setRefunds] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState<number | null>(null);
  const [statusFilter, setStatusFilter] = useState('');
  const navigate = useNavigate();

  const loadData = () => {
    setLoading(true);
    setError(null);
    const params: any = {};
    if (statusFilter) params.status = statusFilter;
    fetchStaffRefunds(params, getToken())
      .then((res) => {
        const list = Array.isArray(res?.refunds)
          ? res.refunds
          : Array.isArray(res)
            ? res
            : Array.isArray(res?.results)
              ? res.results
              : [];
        setRefunds(list);
        setLoading(false);
      })
      .catch((err: any) => {
        setError(err.message || 'Failed to load refund requests');
        setLoading(false);
      });
  };

  useEffect(() => {
    loadData();
  }, [statusFilter]);

  const handleProcess = async (id: number) => {
    if (actionLoading !== null) return;
    if (!window.confirm(`Are you sure you want to process refund #${id}?`)) return;
    setActionLoading(id);
    try {
      await processStaffRefund(id, {}, getToken());
      alert('Refund processed successfully!');
      loadData();
    } catch (e: any) {
      alert(e.message || 'Refund processing failed');
    } finally {
      setActionLoading(null);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-black text-white">Refund Requests Queue</h1>
        <p className="text-sm text-gray-400">Review pending cancellation refunds and execute gateway transactions.</p>
      </div>

      <div className="flex gap-3 bg-gray-950 p-4 rounded-xl border border-gray-800">
        <select
          className="bg-gray-900 border border-gray-800 rounded-lg px-3 py-2 text-sm text-gray-300"
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
        >
          <option value="">All Statuses</option>
          <option value="PENDING">Pending</option>
          <option value="REFUND_PENDING">Refund Pending</option>
          <option value="REFUNDED">Refunded</option>
          <option value="FAILED">Failed</option>
        </select>
        <button
          onClick={loadData}
          disabled={loading}
          className="px-5 py-2 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white rounded-lg text-sm font-semibold transition"
        >
          {loading ? 'Filtering...' : 'Filter'}
        </button>
      </div>

      {error && (
        <div className="p-4 bg-rose-950/40 border border-rose-800 rounded-xl text-rose-300 text-sm">
          {error}
        </div>
      )}

      <div className="bg-gray-950 rounded-xl border border-gray-800 overflow-hidden">
        {loading ? (
          <div className="p-8 text-center text-gray-500">Loading refunds...</div>
        ) : refunds.length === 0 ? (
          <div className="p-8 text-center text-gray-500">No refund requests found.</div>
        ) : (
          <table className="w-full text-left text-sm text-gray-300">
            <thead className="bg-gray-900/60 text-xs uppercase text-gray-400 border-b border-gray-800">
              <tr>
                <th className="px-5 py-3">Refund ID</th>
                <th className="px-5 py-3">Booking ID</th>
                <th className="px-5 py-3">Customer</th>
                <th className="px-5 py-3">Amount</th>
                <th className="px-5 py-3">Status</th>
                <th className="px-5 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800/60">
              {refunds.map((r) => {
                const isProcessingRow = actionLoading === r.id;
                return (
                  <tr key={r.id} className="hover:bg-gray-900/40">
                    <td className="px-5 py-3 font-mono text-xs text-emerald-400">#{r.id}</td>
                    <td className="px-5 py-3 font-mono text-xs text-blue-400">{r.booking_id}</td>
                    <td className="px-5 py-3 font-semibold text-white">{r.customer_name || 'N/A'}</td>
                    <td className="px-5 py-3 font-bold text-emerald-400">₹{r.amount}</td>
                    <td className="px-5 py-3">
                      <span className="px-2 py-0.5 text-xs rounded-full bg-emerald-950 text-emerald-300 border border-emerald-800">
                        {r.status}
                      </span>
                    </td>
                    <td className="px-5 py-3 text-right space-x-2">
                      {r.status !== 'REFUNDED' && (
                        <button
                          disabled={isProcessingRow}
                          onClick={() => handleProcess(r.id)}
                          className="px-2.5 py-1 text-xs bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white rounded font-medium"
                        >
                          {isProcessingRow ? 'Processing...' : 'Process'}
                        </button>
                      )}
                      <button
                        onClick={() => navigate(`/staff/refunds/${r.id}`)}
                        className="px-2.5 py-1 text-xs bg-gray-800 hover:bg-gray-700 text-gray-200 rounded"
                      >
                        Audit
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

// 2. Claims Management Page
export const RefundClaimsPage: React.FC = () => {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-black text-white">Claims Management</h1>
        <p className="text-sm text-gray-400">Review disputed cancellation penalty claims and policy exceptions.</p>
      </div>
      <div className="bg-gray-950 p-6 rounded-xl border border-gray-800 text-sm text-gray-400">
        Customer claims submitted for non-standard refund review are audited against property cancellation terms.
      </div>
    </div>
  );
};

// 3. Refund Detail & Audit Page
export const RefundDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const [refund, setRefund] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [statusMsg, setStatusMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  const loadData = () => {
    if (id) {
      setLoading(true);
      setError(null);
      fetchStaffRefundDetail(id, getToken())
        .then((res) => {
          setRefund(res.refund || res.data || res);
          setLoading(false);
        })
        .catch((err: any) => {
          setError(err.message || 'Failed to load refund details');
          setLoading(false);
        });
    }
  };

  useEffect(() => {
    loadData();
  }, [id]);

  const handleProcess = async () => {
    if (!id || isProcessing) return;
    if (!window.confirm('Confirm executing live refund disbursement?')) return;
    setIsProcessing(true);
    setStatusMsg(null);
    try {
      await processStaffRefund(id, {}, getToken());
      setStatusMsg({ type: 'success', text: 'Refund processed successfully with payment gateway!' });
      loadData();
    } catch (e: any) {
      setStatusMsg({ type: 'error', text: e.message || 'Refund processing failed' });
    } finally {
      setIsProcessing(false);
    }
  };

  if (loading) return <div className="p-8 text-gray-400">Loading refund audit...</div>;
  if (error || !refund) return <div className="p-8 text-rose-400">{error || 'Refund record not found.'}</div>;

  return (
    <div className="space-y-6 max-w-4xl">
      <div>
        <h1 className="text-2xl font-black text-white">Refund Audit #{refund.id}</h1>
        <p className="text-sm text-gray-400">Booking {refund.booking?.booking_id || refund.booking_id || 'N/A'}</p>
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
          <p className="text-xs text-gray-400">Refund Amount</p>
          <p className="text-2xl font-bold text-emerald-400">₹{refund.amount}</p>
        </div>
        <div>
          <p className="text-xs text-gray-400">Status</p>
          <span className="inline-block mt-1 px-3 py-1 text-xs rounded-full bg-emerald-950 text-emerald-300 border border-emerald-800">
            {refund.status}
          </span>
        </div>
        <div>
          <p className="text-xs text-gray-400">Payment ID</p>
          <p className="text-xs font-mono text-gray-200 mt-1">{refund.razorpay_payment_id || 'N/A'}</p>
        </div>
        <div>
          <p className="text-xs text-gray-400">Refund Mode</p>
          <p className="text-sm text-gray-200">{refund.refund_mode || 'GATEWAY'}</p>
        </div>
      </div>

      {refund.status !== 'REFUNDED' && (
        <button
          onClick={handleProcess}
          disabled={isProcessing}
          className="px-6 py-2.5 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white rounded-lg font-bold text-sm transition"
        >
          {isProcessing ? 'Executing Live Refund...' : 'Execute Live Refund'}
        </button>
      )}
    </div>
  );
};

// 4. Refund Eligibility Page
export const RefundEligibilityPage: React.FC = () => {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-black text-white">Refund Eligibility Calculator</h1>
        <p className="text-sm text-gray-400">Inspect automated policy eligibility calculation based on check-in lead times.</p>
      </div>
      <div className="bg-gray-950 p-6 rounded-xl border border-gray-800 text-sm text-gray-400">
        Refund calculations automatically evaluate cancellation policy rules: Free Cancellation (100% refund), Moderate (50% penalty), or Non-Refundable.
      </div>
    </div>
  );
};

// 5. Authorized Refund Processing Page
export const RefundProcessPage: React.FC = () => {
  const [refundId, setRefundId] = useState('');
  const [msg, setMsg] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async () => {
    if (!refundId.trim()) {
      setMsg('❌ Please enter a Refund Record ID.');
      return;
    }
    setMsg(null);
    setIsSubmitting(true);
    try {
      const res = await processStaffRefund(refundId.trim(), {}, getToken());
      setMsg(`✅ ${res.message || 'Refund executed successfully.'}`);
    } catch (e: any) {
      setMsg(`❌ ${e.message}`);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="space-y-6 max-w-xl">
      <div>
        <h1 className="text-2xl font-black text-white">Authorized Refund Processing</h1>
        <p className="text-sm text-gray-400">Direct gateway execution terminal for approved refund requests.</p>
      </div>

      <div className="bg-gray-950 p-6 rounded-xl border border-gray-800 space-y-4">
        <div>
          <label className="text-xs font-semibold text-gray-300 uppercase">Refund Record ID</label>
          <input
            type="number"
            className="w-full mt-1 bg-gray-900 border border-gray-800 rounded-lg px-4 py-2 text-white text-sm"
            placeholder="e.g. 1"
            value={refundId}
            onChange={(e) => setRefundId(e.target.value)}
          />
        </div>
        <button
          onClick={handleSubmit}
          disabled={isSubmitting || !refundId.trim()}
          className="w-full py-2.5 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white rounded-lg text-sm font-bold transition"
        >
          {isSubmitting ? 'Processing Refund With Gateway...' : 'Process Refund With Gateway'}
        </button>
        {msg && <div className="p-3 bg-gray-900 border border-gray-800 rounded text-sm text-gray-200">{msg}</div>}
      </div>
    </div>
  );
};

// 6. Refund History Page
export const RefundHistoryPage: React.FC = () => {
  const [history, setHistory] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    fetchStaffRefundHistory(getToken())
      .then((res) => {
        const list = Array.isArray(res?.history)
          ? res.history
          : Array.isArray(res)
            ? res
            : Array.isArray(res?.results)
              ? res.results
              : [];
        setHistory(list);
        setLoading(false);
      })
      .catch((err: any) => {
        setError(err.message || 'Failed to load refund history');
        setLoading(false);
      });
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-black text-white">Refund History</h1>
        <p className="text-sm text-gray-400">Disbursed refunds and payment gateway confirmations.</p>
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
          <div className="p-8 text-center text-gray-500">No processed refund records.</div>
        ) : (
          <table className="w-full text-left text-sm text-gray-300">
            <thead className="bg-gray-900/60 text-xs uppercase text-gray-400 border-b border-gray-800">
              <tr>
                <th className="px-5 py-3">Refund ID</th>
                <th className="px-5 py-3">Booking ID</th>
                <th className="px-5 py-3">Hotel</th>
                <th className="px-5 py-3">Amount</th>
                <th className="px-5 py-3">Gateway ID</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800/60">
              {history.map((h) => (
                <tr key={h.id} className="hover:bg-gray-900/40">
                  <td className="px-5 py-3 font-mono text-xs text-emerald-400">#{h.id}</td>
                  <td className="px-5 py-3 font-mono text-xs text-blue-400">{h.booking_id}</td>
                  <td className="px-5 py-3 text-gray-300 text-xs">{h.hotel_name || 'N/A'}</td>
                  <td className="px-5 py-3 font-bold text-emerald-400">₹{h.amount}</td>
                  <td className="px-5 py-3 font-mono text-xs text-gray-400">{h.razorpay_refund_id || 'N/A'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
};
