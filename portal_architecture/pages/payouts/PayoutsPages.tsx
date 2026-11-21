import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  fetchStaffPayouts,
  fetchStaffPayoutDetail,
  processStaffPayout,
  fetchStaffEscrow,
  fetchStaffSettlements,
  fetchStaffPayoutHistory
} from '../../services/portalApi';

function getToken(): string {
  return localStorage.getItem('access_token') || sessionStorage.getItem('access_token') || '';
}

// 1. Payout Requests Queue Page
export const PayoutRequestsPage: React.FC = () => {
  const [payouts, setPayouts] = useState<any[]>([]);
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
    fetchStaffPayouts(params, getToken())
      .then((res) => {
        const list = Array.isArray(res?.payouts)
          ? res.payouts
          : Array.isArray(res)
            ? res
            : Array.isArray(res?.results)
              ? res.results
              : [];
        setPayouts(list);
        setLoading(false);
      })
      .catch((err: any) => {
        setError(err.message || 'Failed to load payouts');
        setLoading(false);
      });
  };

  useEffect(() => {
    loadData();
  }, [statusFilter]);

  const handleProcess = async (id: number) => {
    if (actionLoading !== null) return;
    if (!window.confirm(`Disburse payout #${id} to hotel host?`)) return;
    setActionLoading(id);
    try {
      await processStaffPayout(id, {}, getToken());
      alert('Payout disbursed successfully!');
      loadData();
    } catch (e: any) {
      alert(e.message || 'Payout disbursement failed');
    } finally {
      setActionLoading(null);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-black text-white">Host Payout Requests</h1>
        <p className="text-sm text-gray-400">Review pending host disbursements and execute bank payouts.</p>
      </div>

      <div className="flex gap-3 bg-gray-950 p-4 rounded-xl border border-gray-800">
        <select
          className="bg-gray-900 border border-gray-800 rounded-lg px-3 py-2 text-sm text-gray-300"
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
        >
          <option value="">All Statuses</option>
          <option value="PENDING">Pending</option>
          <option value="ELIGIBLE">Eligible</option>
          <option value="COMPLETED">Completed</option>
          <option value="FAILED">Failed</option>
        </select>
        <button
          onClick={loadData}
          disabled={loading}
          className="px-5 py-2 bg-amber-600 hover:bg-amber-700 disabled:opacity-50 text-white rounded-lg text-sm font-semibold transition"
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
          <div className="p-8 text-center text-gray-500">Loading payouts...</div>
        ) : payouts.length === 0 ? (
          <div className="p-8 text-center text-gray-500">No payout requests found.</div>
        ) : (
          <table className="w-full text-left text-sm text-gray-300">
            <thead className="bg-gray-900/60 text-xs uppercase text-gray-400 border-b border-gray-800">
              <tr>
                <th className="px-5 py-3">Payout ID</th>
                <th className="px-5 py-3">Host Name</th>
                <th className="px-5 py-3">Amount</th>
                <th className="px-5 py-3">Status</th>
                <th className="px-5 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800/60">
              {payouts.map((p) => {
                const isProcessingRow = actionLoading === p.id;
                return (
                  <tr key={p.id} className="hover:bg-gray-900/40">
                    <td className="px-5 py-3 font-mono text-xs text-amber-400">{p.payout_id || `#${p.id}`}</td>
                    <td className="px-5 py-3 font-semibold text-white">{p.host_name}</td>
                    <td className="px-5 py-3 font-bold text-emerald-400">₹{p.amount}</td>
                    <td className="px-5 py-3">
                      <span className="px-2 py-0.5 text-xs rounded-full bg-amber-950 text-amber-300 border border-amber-800">
                        {p.status}
                      </span>
                    </td>
                    <td className="px-5 py-3 text-right space-x-2">
                      {p.status !== 'COMPLETED' && (
                        <button
                          disabled={isProcessingRow}
                          onClick={() => handleProcess(p.id)}
                          className="px-2.5 py-1 text-xs bg-amber-600 hover:bg-amber-700 disabled:opacity-50 text-white rounded font-medium"
                        >
                          {isProcessingRow ? 'Disbursing...' : 'Disburse'}
                        </button>
                      )}
                      <button
                        onClick={() => navigate(`/staff/payouts/${p.id}`)}
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

// 2. Escrow Management Page (7-Day Holding Rule)
export const PayoutEscrowPage: React.FC = () => {
  const [escrows, setEscrows] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    fetchStaffEscrow(getToken())
      .then((res) => {
        const list = Array.isArray(res?.escrow_holdings)
          ? res.escrow_holdings
          : Array.isArray(res)
            ? res
            : [];
        setEscrows(list);
        setLoading(false);
      })
      .catch((err: any) => {
        setError(err.message || 'Failed to load escrow holdings');
        setLoading(false);
      });
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-black text-white">Escrow Holdings Management</h1>
        <p className="text-sm text-gray-400">Mandatory 7-day holding maturity tracking and guest checkout escrow verification.</p>
      </div>

      {error && (
        <div className="p-4 bg-rose-950/40 border border-rose-800 rounded-xl text-rose-300 text-sm">
          {error}
        </div>
      )}

      <div className="bg-gray-950 rounded-xl border border-gray-800 overflow-hidden">
        {loading ? (
          <div className="p-8 text-center text-gray-500">Loading escrow holdings...</div>
        ) : escrows.length === 0 ? (
          <div className="p-8 text-center text-gray-500">No active escrow holdings.</div>
        ) : (
          <table className="w-full text-left text-sm text-gray-300">
            <thead className="bg-gray-900/60 text-xs uppercase text-gray-400 border-b border-gray-800">
              <tr>
                <th className="px-5 py-3">Booking ID</th>
                <th className="px-5 py-3">Hotel</th>
                <th className="px-5 py-3">Host</th>
                <th className="px-5 py-3">Net Payable</th>
                <th className="px-5 py-3">Holding Matures</th>
                <th className="px-5 py-3">Maturity Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800/60">
              {escrows.map((e) => (
                <tr key={e.id} className="hover:bg-gray-900/40">
                  <td className="px-5 py-3 font-mono text-xs text-blue-400">{e.booking_id}</td>
                  <td className="px-5 py-3 text-xs text-gray-300">{e.hotel_name || 'N/A'}</td>
                  <td className="px-5 py-3 font-semibold text-white">{e.host_name}</td>
                  <td className="px-5 py-3 font-bold text-emerald-400">₹{e.net_amount}</td>
                  <td className="px-5 py-3 text-xs text-gray-400">{e.hold_until ? new Date(e.hold_until).toLocaleDateString() : 'N/A'}</td>
                  <td className="px-5 py-3">
                    {e.is_hold_matured ? (
                      <span className="px-2 py-0.5 text-xs rounded-full bg-emerald-950 text-emerald-300 border border-emerald-800 font-bold">
                        Mature (Payable)
                      </span>
                    ) : (
                      <span className="px-2 py-0.5 text-xs rounded-full bg-amber-950 text-amber-300 border border-amber-800">
                        Holding Active
                      </span>
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

// 3. Payout Detail Page
export const PayoutDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const [payout, setPayout] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [statusMsg, setStatusMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  const loadData = () => {
    if (id) {
      setLoading(true);
      setError(null);
      fetchStaffPayoutDetail(id, getToken())
        .then((res) => {
          setPayout(res.payout || res.data || res);
          setLoading(false);
        })
        .catch((err: any) => {
          setError(err.message || 'Failed to load payout details');
          setLoading(false);
        });
    }
  };

  useEffect(() => {
    loadData();
  }, [id]);

  const handleDisburse = async () => {
    if (!id || isProcessing) return;
    if (!window.confirm('Execute bank payout transfer?')) return;
    setIsProcessing(true);
    setStatusMsg(null);
    try {
      await processStaffPayout(id, {}, getToken());
      setStatusMsg({ type: 'success', text: 'Payout disbursed successfully!' });
      loadData();
    } catch (e: any) {
      setStatusMsg({ type: 'error', text: e.message || 'Payout failed' });
    } finally {
      setIsProcessing(false);
    }
  };

  if (loading) return <div className="p-8 text-gray-400">Loading payout details...</div>;
  if (error || !payout) return <div className="p-8 text-rose-400">{error || 'Payout not found.'}</div>;

  return (
    <div className="space-y-6 max-w-4xl">
      <div>
        <h1 className="text-2xl font-black text-white">Payout #{payout.payout_id || payout.id}</h1>
        <p className="text-sm text-gray-400">Host: {payout.host_name}</p>
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
          <p className="text-xs text-gray-400">Disbursement Amount</p>
          <p className="text-2xl font-bold text-emerald-400">₹{payout.amount}</p>
        </div>
        <div>
          <p className="text-xs text-gray-400">Status</p>
          <span className="inline-block mt-1 px-3 py-1 text-xs rounded-full bg-amber-950 text-amber-300 border border-amber-800">
            {payout.status}
          </span>
        </div>
      </div>

      {payout.status !== 'COMPLETED' && (
        <button
          onClick={handleDisburse}
          disabled={isProcessing}
          className="px-6 py-2.5 bg-amber-600 hover:bg-amber-700 disabled:opacity-50 text-white rounded-lg font-bold text-sm transition"
        >
          {isProcessing ? 'Disbursing Payout Now...' : 'Disburse Payout Now'}
        </button>
      )}
    </div>
  );
};

// 4. Settlement Statements Page
export const PayoutSettlementsPage: React.FC = () => {
  const [settlements, setSettlements] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    fetchStaffSettlements({}, getToken())
      .then((res) => {
        const list = Array.isArray(res?.settlements)
          ? res.settlements
          : Array.isArray(res)
            ? res
            : [];
        setSettlements(list);
        setLoading(false);
      })
      .catch((err: any) => {
        setError(err.message || 'Failed to load settlements');
        setLoading(false);
      });
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-black text-white">Settlement Statements</h1>
        <p className="text-sm text-gray-400">Host revenue breakdowns and platform commission deductions.</p>
      </div>

      {error && (
        <div className="p-4 bg-rose-950/40 border border-rose-800 rounded-xl text-rose-300 text-sm">
          {error}
        </div>
      )}

      <div className="bg-gray-950 rounded-xl border border-gray-800 overflow-hidden">
        {loading ? (
          <div className="p-8 text-center text-gray-500">Loading settlements...</div>
        ) : settlements.length === 0 ? (
          <div className="p-8 text-center text-gray-500">No settlement records found.</div>
        ) : (
          <table className="w-full text-left text-sm text-gray-300">
            <thead className="bg-gray-900/60 text-xs uppercase text-gray-400 border-b border-gray-800">
              <tr>
                <th className="px-5 py-3">Booking</th>
                <th className="px-5 py-3">Host</th>
                <th className="px-5 py-3">Gross</th>
                <th className="px-5 py-3">Platform Fee</th>
                <th className="px-5 py-3 font-bold">Net Payable</th>
                <th className="px-5 py-3">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800/60">
              {settlements.map((s) => (
                <tr key={s.id} className="hover:bg-gray-900/40">
                  <td className="px-5 py-3 font-mono text-xs text-blue-400">{s.booking_id}</td>
                  <td className="px-5 py-3 font-semibold text-white">{s.host_name}</td>
                  <td className="px-5 py-3 text-gray-300">₹{s.gross_amount}</td>
                  <td className="px-5 py-3 text-rose-400">-₹{s.platform_fee}</td>
                  <td className="px-5 py-3 font-bold text-emerald-400">₹{s.net_amount}</td>
                  <td className="px-5 py-3">
                    <span className="px-2 py-0.5 text-xs rounded-full bg-gray-800 text-gray-300">
                      {s.status}
                    </span>
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

// 5. Authorized Payout Processing Page
export const PayoutProcessPage: React.FC = () => {
  const [payoutId, setPayoutId] = useState('');
  const [msg, setMsg] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async () => {
    if (!payoutId.trim()) {
      setMsg('❌ Please enter a Payout ID.');
      return;
    }
    setMsg(null);
    setIsSubmitting(true);
    try {
      const res = await processStaffPayout(payoutId.trim(), {}, getToken());
      setMsg(`✅ ${res.message || 'Payout disbursed successfully.'}`);
    } catch (e: any) {
      setMsg(`❌ ${e.message}`);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="space-y-6 max-w-xl">
      <div>
        <h1 className="text-2xl font-black text-white">Authorized Payout Processing</h1>
        <p className="text-sm text-gray-400">Direct disbursement terminal for matured host payouts.</p>
      </div>

      <div className="bg-gray-950 p-6 rounded-xl border border-gray-800 space-y-4">
        <div>
          <label className="text-xs font-semibold text-gray-300 uppercase">Payout ID or Record ID</label>
          <input
            type="number"
            className="w-full mt-1 bg-gray-900 border border-gray-800 rounded-lg px-4 py-2 text-white text-sm"
            placeholder="e.g. 1"
            value={payoutId}
            onChange={(e) => setPayoutId(e.target.value)}
          />
        </div>
        <button
          onClick={handleSubmit}
          disabled={isSubmitting || !payoutId.trim()}
          className="w-full py-2.5 bg-amber-600 hover:bg-amber-700 disabled:opacity-50 text-white rounded-lg text-sm font-bold transition"
        >
          {isSubmitting ? 'Executing Payout Transfer...' : 'Execute Payout Transfer'}
        </button>
        {msg && <div className="p-3 bg-gray-900 border border-gray-800 rounded text-sm text-gray-200">{msg}</div>}
      </div>
    </div>
  );
};

// 6. Payout History Page
export const PayoutHistoryPage: React.FC = () => {
  const [history, setHistory] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    fetchStaffPayoutHistory(getToken())
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
        setError(err.message || 'Failed to load payout history');
        setLoading(false);
      });
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-black text-white">Payout History</h1>
        <p className="text-sm text-gray-400">Completed bank payouts and settlement references.</p>
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
          <div className="p-8 text-center text-gray-500">No completed payout records.</div>
        ) : (
          <table className="w-full text-left text-sm text-gray-300">
            <thead className="bg-gray-900/60 text-xs uppercase text-gray-400 border-b border-gray-800">
              <tr>
                <th className="px-5 py-3">Payout ID</th>
                <th className="px-5 py-3">Host</th>
                <th className="px-5 py-3">Amount</th>
                <th className="px-5 py-3">Transaction Reference</th>
                <th className="px-5 py-3">Date</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800/60">
              {history.map((h) => (
                <tr key={h.id} className="hover:bg-gray-900/40">
                  <td className="px-5 py-3 font-mono text-xs text-amber-400">{h.payout_id || `#${h.id}`}</td>
                  <td className="px-5 py-3 font-semibold text-white">{h.host_name}</td>
                  <td className="px-5 py-3 font-bold text-emerald-400">₹{h.amount}</td>
                  <td className="px-5 py-3 font-mono text-xs text-gray-400">{h.transaction_reference || 'N/A'}</td>
                  <td className="px-5 py-3 text-xs text-gray-400">{h.processed_at ? new Date(h.processed_at).toLocaleDateString() : 'N/A'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
};
