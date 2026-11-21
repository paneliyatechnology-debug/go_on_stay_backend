import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  fetchStaffSupportTickets,
  fetchStaffSupportTicketDetail,
  updateStaffSupportTicket,
  addStaffTicketNote,
  sendStaffTicketMessage
} from '../../services/portalApi';

function getToken(): string {
  return localStorage.getItem('access_token') || sessionStorage.getItem('access_token') || '';
}

// 1. Support Tickets Queue Page
export const SupportTicketsPage: React.FC = () => {
  const [tickets, setTickets] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState('');
  const [search, setSearch] = useState('');
  const navigate = useNavigate();

  const loadData = () => {
    setLoading(true);
    setError(null);
    const params: any = {};
    if (statusFilter) params.status = statusFilter;
    if (search) params.search = search;
    fetchStaffSupportTickets(params, getToken())
      .then((res) => {
        const list = Array.isArray(res?.tickets)
          ? res.tickets
          : Array.isArray(res)
            ? res
            : Array.isArray(res?.results)
              ? res.results
              : [];
        setTickets(list);
        setLoading(false);
      })
      .catch((err: any) => {
        setError(err.message || 'Failed to load support tickets');
        setLoading(false);
      });
  };

  useEffect(() => {
    loadData();
  }, [statusFilter]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-black text-white">Customer Support Tickets</h1>
        <p className="text-sm text-gray-400">Incoming inquiries, guest messages, and resolution queues.</p>
      </div>

      <div className="flex gap-3 bg-gray-950 p-4 rounded-xl border border-gray-800">
        <input
          type="text"
          placeholder="Search ticket number, subject, customer..."
          className="flex-1 bg-gray-900 border border-gray-800 rounded-lg px-4 py-2 text-sm text-white placeholder-gray-500 focus:outline-none"
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
          <option value="OPEN">Open</option>
          <option value="IN_PROGRESS">In Progress</option>
          <option value="RESOLVED">Resolved</option>
          <option value="CLOSED">Closed</option>
        </select>
        <button
          onClick={loadData}
          disabled={loading}
          className="px-5 py-2 bg-purple-600 hover:bg-purple-700 disabled:opacity-50 text-white rounded-lg text-sm font-semibold transition"
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
          <div className="p-8 text-center text-gray-500">Loading tickets...</div>
        ) : tickets.length === 0 ? (
          <div className="p-8 text-center text-gray-500">No support tickets found.</div>
        ) : (
          <table className="w-full text-left text-sm text-gray-300">
            <thead className="bg-gray-900/60 text-xs uppercase text-gray-400 border-b border-gray-800">
              <tr>
                <th className="px-5 py-3">Ticket #</th>
                <th className="px-5 py-3">Subject</th>
                <th className="px-5 py-3">Customer</th>
                <th className="px-5 py-3">Priority</th>
                <th className="px-5 py-3">Status</th>
                <th className="px-5 py-3 text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800/60">
              {tickets.map((t) => (
                <tr key={t.id} className="hover:bg-gray-900/40">
                  <td className="px-5 py-3 font-mono text-xs text-purple-400">{t.ticket_number}</td>
                  <td className="px-5 py-3 font-semibold text-white">{t.subject}</td>
                  <td className="px-5 py-3 text-gray-300 text-xs">{t.customer_name}</td>
                  <td className="px-5 py-3">
                    <span className="px-2 py-0.5 text-xs rounded-full bg-gray-800 text-gray-300">
                      {t.priority}
                    </span>
                  </td>
                  <td className="px-5 py-3">
                    <span className="px-2 py-0.5 text-xs rounded-full bg-purple-950 text-purple-300 border border-purple-800">
                      {t.status}
                    </span>
                  </td>
                  <td className="px-5 py-3 text-right">
                    <button
                      onClick={() => navigate(`/staff/support/tickets/${t.id}`)}
                      className="px-3 py-1 text-xs bg-purple-600 hover:bg-purple-700 text-white rounded font-medium"
                    >
                      Open
                    </button>
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

// 2. Customer Complaints Page
export const SupportComplaintsPage: React.FC = () => {
  const [complaints, setComplaints] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    setLoading(true);
    setError(null);
    fetchStaffSupportTickets({ priority: 'URGENT' }, getToken())
      .then((res) => {
        const list = Array.isArray(res?.tickets)
          ? res.tickets
          : Array.isArray(res)
            ? res
            : Array.isArray(res?.results)
              ? res.results
              : [];
        setComplaints(list);
        setLoading(false);
      })
      .catch((err: any) => {
        setError(err.message || 'Failed to load complaints');
        setLoading(false);
      });
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-black text-white">Customer Complaints</h1>
        <p className="text-sm text-gray-400">High-priority and escalated guest complaints requiring urgent intervention.</p>
      </div>

      {error && (
        <div className="p-4 bg-rose-950/40 border border-rose-800 rounded-xl text-rose-300 text-sm">
          {error}
        </div>
      )}

      <div className="bg-gray-950 rounded-xl border border-gray-800 overflow-hidden">
        {loading ? (
          <div className="p-8 text-center text-gray-500">Loading complaints...</div>
        ) : complaints.length === 0 ? (
          <div className="p-8 text-center text-gray-500">No active complaints found.</div>
        ) : (
          <table className="w-full text-left text-sm text-gray-300">
            <thead className="bg-gray-900/60 text-xs uppercase text-gray-400 border-b border-gray-800">
              <tr>
                <th className="px-5 py-3">Ticket #</th>
                <th className="px-5 py-3">Subject</th>
                <th className="px-5 py-3">Customer</th>
                <th className="px-5 py-3">Priority</th>
                <th className="px-5 py-3 text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800/60">
              {complaints.map((c) => (
                <tr key={c.id} className="hover:bg-gray-900/40">
                  <td className="px-5 py-3 font-mono text-xs text-rose-400">{c.ticket_number}</td>
                  <td className="px-5 py-3 font-semibold text-white">{c.subject}</td>
                  <td className="px-5 py-3 text-gray-300">{c.customer_name}</td>
                  <td className="px-5 py-3 text-xs text-rose-400 font-bold">{c.priority}</td>
                  <td className="px-5 py-3 text-right">
                    <button
                      onClick={() => navigate(`/staff/support/tickets/${c.id}`)}
                      className="px-3 py-1 text-xs bg-rose-600 hover:bg-rose-700 text-white rounded font-medium"
                    >
                      Resolve
                    </button>
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

// 3. Ticket Detail & Messaging Page
export const SupportTicketDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const [ticket, setTicket] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [replyMessage, setReplyMessage] = useState('');
  const [internalNote, setInternalNote] = useState('');
  const [statusVal, setStatusVal] = useState('');
  const [isSendingMessage, setIsSendingMessage] = useState(false);
  const [isAddingNote, setIsAddingNote] = useState(false);
  const [isUpdatingStatus, setIsUpdatingStatus] = useState(false);
  const [feedbackMsg, setFeedbackMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  const loadTicket = () => {
    if (id) {
      fetchStaffSupportTicketDetail(id, getToken())
        .then((res) => {
          const t = res.ticket || res.data || res;
          setTicket(t);
          setStatusVal(t.status);
          setLoading(false);
        })
        .catch((err: any) => {
          setError(err.message || 'Failed to load ticket');
          setLoading(false);
        });
    }
  };

  useEffect(() => {
    loadTicket();
  }, [id]);

  const handleSendMessage = async () => {
    if (!replyMessage.trim() || !id || isSendingMessage) return;
    setFeedbackMsg(null);
    setIsSendingMessage(true);
    try {
      await sendStaffTicketMessage(id, replyMessage.trim(), getToken());
      setReplyMessage('');
      setFeedbackMsg({ type: 'success', text: 'Reply sent to customer successfully.' });
      loadTicket();
    } catch (e: any) {
      setFeedbackMsg({ type: 'error', text: e.message || 'Failed to send message' });
    } finally {
      setIsSendingMessage(false);
    }
  };

  const handleAddNote = async () => {
    if (!internalNote.trim() || !id || isAddingNote) return;
    setFeedbackMsg(null);
    setIsAddingNote(true);
    try {
      await addStaffTicketNote(id, internalNote.trim(), getToken());
      setInternalNote('');
      setFeedbackMsg({ type: 'success', text: 'Internal note saved.' });
      loadTicket();
    } catch (e: any) {
      setFeedbackMsg({ type: 'error', text: e.message || 'Failed to add internal note' });
    } finally {
      setIsAddingNote(false);
    }
  };

  const handleStatusChange = async (newStatus: string) => {
    if (!id || isUpdatingStatus) return;
    setFeedbackMsg(null);
    setIsUpdatingStatus(true);
    try {
      await updateStaffSupportTicket(id, { status: newStatus }, getToken());
      setStatusVal(newStatus);
      setFeedbackMsg({ type: 'success', text: `Status updated to ${newStatus}` });
      loadTicket();
    } catch (e: any) {
      setFeedbackMsg({ type: 'error', text: e.message || 'Failed to update status' });
    } finally {
      setIsUpdatingStatus(false);
    }
  };

  if (loading) return <div className="p-8 text-gray-400">Loading support conversation...</div>;
  if (error || !ticket) return <div className="p-8 text-rose-400">{error || 'Ticket not found.'}</div>;

  return (
    <div className="space-y-6 max-w-4xl">
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-black text-white">Ticket #{ticket.ticket_number}</h1>
          <p className="text-sm text-gray-400">{ticket.subject}</p>
        </div>
        <div className="flex items-center gap-3">
          <label className="text-xs text-gray-400">Status:</label>
          <select
            value={statusVal}
            disabled={isUpdatingStatus}
            onChange={(e) => handleStatusChange(e.target.value)}
            className="bg-gray-950 border border-gray-800 rounded px-3 py-1.5 text-xs text-white disabled:opacity-50"
          >
            <option value="OPEN">OPEN</option>
            <option value="IN_PROGRESS">IN_PROGRESS</option>
            <option value="RESOLVED">RESOLVED</option>
            <option value="CLOSED">CLOSED</option>
          </select>
        </div>
      </div>

      {feedbackMsg && (
        <div className={`p-3 rounded-lg text-sm border ${
          feedbackMsg.type === 'success' 
            ? 'bg-emerald-950/40 border-emerald-800 text-emerald-300' 
            : 'bg-rose-950/40 border-rose-800 text-rose-300'
        }`}>
          {feedbackMsg.text}
        </div>
      )}

      {/* Messages Thread */}
      <div className="bg-gray-950 p-5 rounded-xl border border-gray-800 space-y-4">
        <h3 className="text-sm font-bold text-gray-300 uppercase">Customer Conversation</h3>
        <div className="space-y-3 max-h-80 overflow-y-auto">
          {(ticket.messages || []).map((m: any) => (
            <div key={m.id} className="p-3 bg-gray-900 rounded-lg text-sm border border-gray-800">
              <div className="flex justify-between text-xs text-gray-400 mb-1">
                <span className="font-bold text-white">{m.sender_username}</span>
                <span>{m.created_at ? new Date(m.created_at).toLocaleTimeString() : ''}</span>
              </div>
              <p className="text-gray-200">{m.message}</p>
            </div>
          ))}
        </div>

        {/* Reply Box */}
        <div className="flex gap-2 pt-2">
          <input
            type="text"
            className="flex-1 bg-gray-900 border border-gray-800 rounded-lg px-4 py-2 text-sm text-white"
            placeholder="Type response to customer..."
            value={replyMessage}
            onChange={(e) => setReplyMessage(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSendMessage()}
          />
          <button
            onClick={handleSendMessage}
            disabled={!replyMessage.trim() || isSendingMessage}
            className="px-4 py-2 bg-purple-600 hover:bg-purple-700 disabled:opacity-50 text-white rounded-lg text-sm font-bold transition"
          >
            {isSendingMessage ? 'Sending...' : 'Send Reply'}
          </button>
        </div>
      </div>

      {/* Internal Notes Panel */}
      <div className="bg-gray-950 p-5 rounded-xl border border-gray-800 space-y-4">
        <h3 className="text-sm font-bold text-amber-400 uppercase">Confidential Internal Notes</h3>
        <div className="space-y-2">
          {(ticket.internal_notes || []).map((n: any) => (
            <div key={n.id} className="p-3 bg-gray-900/60 border border-amber-900/30 rounded text-xs text-amber-200">
              <span className="font-bold text-gray-300">{n.staff_name}: </span>
              {n.note}
            </div>
          ))}
        </div>
        <div className="flex gap-2">
          <input
            type="text"
            className="flex-1 bg-gray-900 border border-gray-800 rounded-lg px-4 py-2 text-sm text-white"
            placeholder="Add internal coordination note..."
            value={internalNote}
            onChange={(e) => setInternalNote(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleAddNote()}
          />
          <button
            onClick={handleAddNote}
            disabled={!internalNote.trim() || isAddingNote}
            className="px-4 py-2 bg-amber-700 hover:bg-amber-600 disabled:opacity-50 text-white rounded-lg text-sm font-bold transition"
          >
            {isAddingNote ? 'Adding...' : 'Add Note'}
          </button>
        </div>
      </div>
    </div>
  );
};

// 4. Support History Page
export const SupportHistoryPage: React.FC = () => {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-black text-white">Customer Support History</h1>
        <p className="text-sm text-gray-400">Archived cases and closed support inquiries.</p>
      </div>
      <div className="bg-gray-950 p-6 rounded-xl border border-gray-800 text-sm text-gray-400">
        Historic customer interaction records and satisfaction logs.
      </div>
    </div>
  );
};

// 5. Internal Notes Page
export const SupportNotesPage: React.FC = () => {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-black text-white">Internal Notes Directory</h1>
        <p className="text-sm text-gray-400">Cross-team coordination notes and customer history remarks.</p>
      </div>
      <div className="bg-gray-950 p-6 rounded-xl border border-gray-800 text-sm text-gray-400">
        All internal notes are strictly encrypted and hidden from customer view.
      </div>
    </div>
  );
};

// 6. Authorized Support Actions Page
export const SupportActionsPage: React.FC = () => {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-black text-white">Authorized Support Actions</h1>
        <p className="text-sm text-gray-400">Emergency escalations, ticket transfers, and customer notifications.</p>
      </div>
      <div className="bg-gray-950 p-6 rounded-xl border border-gray-800 text-sm text-gray-400">
        Support staff members are authorized to triage, respond, and escalate customer complaints according to platform SLA.
      </div>
    </div>
  );
};
