import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  NotificationItem,
  handleNotificationClick
} from '../services/notificationNavigation';
import {
  fetchNotifications,
  fetchStaffNotifications,
  markAllNotificationsRead,
  UserSession
} from '../services/portalApi';

interface NotificationDropdownProps {
  user: UserSession | null;
  theme?: 'dark' | 'light';
  showToast?: (message: string, type?: 'info' | 'success' | 'warning' | 'error') => void;
}

export const NotificationDropdown: React.FC<NotificationDropdownProps> = ({
  user,
  theme = 'dark',
  showToast
}) => {
  const navigate = useNavigate();
  const [isOpen, setIsOpen] = useState(false);
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [unreadCount, setUnreadCount] = useState(0);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const isStaff = Boolean(user?.isStaff || user?.role === 'STAFF');

  const loadNotifications = async () => {
    try {
      setLoading(true);
      const data = isStaff ? await fetchStaffNotifications() : await fetchNotifications();
      let list: NotificationItem[] = [];
      if (Array.isArray(data)) {
        list = data;
      } else if (data && Array.isArray(data.notifications)) {
        list = data.notifications;
      } else if (data && data.data && Array.isArray(data.data.results)) {
        list = data.data.results;
      } else if (data && Array.isArray(data.results)) {
        list = data.results;
      }

      setNotifications(list);
      const unread = list.filter((n) => !n.is_read).length;
      setUnreadCount(unread);
    } catch (err) {
      console.warn('[NotificationDropdown] Error loading notifications:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadNotifications();
    const interval = setInterval(loadNotifications, 45000);
    return () => clearInterval(interval);
  }, [user]);

  // Handle outside click to close dropdown
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }
    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isOpen]);

  const handleMarkAllRead = async () => {
    try {
      await markAllNotificationsRead(isStaff);
      setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })));
      setUnreadCount(0);
      if (showToast) showToast('All notifications marked as read', 'success');
    } catch (err) {
      console.warn('Failed to mark all notifications as read:', err);
    }
  };

  const onItemClick = (item: NotificationItem) => {
    setIsOpen(false);
    handleNotificationClick({
      notification: item,
      user,
      navigate,
      showToast,
      onMarkReadOptimistic: (id) => {
        setNotifications((prev) =>
          prev.map((n) => (n.id === id ? { ...n, is_read: true } : n))
        );
        setUnreadCount((c) => Math.max(0, c - 1));
      }
    });
  };

  const isDark = theme === 'dark';

  const getTypeIcon = (type: string) => {
    const t = (type || '').toUpperCase();
    if (t.includes('BOOKING') || t.includes('STAY') || t.includes('CHECK')) return '🏨';
    if (t.includes('PAYOUT') || t.includes('ESCROW') || t.includes('SETTLEMENT')) return '💰';
    if (t.includes('REFUND') || t.includes('CLAIM')) return '🔄';
    if (t.includes('SUPPORT') || t.includes('TICKET')) return '🎧';
    if (t.includes('HOTEL') || t.includes('VERIFICATION')) return '🛡️';
    if (t.includes('OFFER') || t.includes('COUPON')) return '🏷️';
    return '🔔';
  };

  const formatTimeAgo = (dateStr: string) => {
    try {
      const diff = Math.floor((new Date().getTime() - new Date(dateStr).getTime()) / 1000);
      if (diff < 60) return 'Just now';
      if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
      if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
      return `${Math.floor(diff / 86400)}d ago`;
    } catch {
      return '';
    }
  };

  return (
    <div className="relative inline-block text-left" ref={dropdownRef}>
      {/* Bell Trigger Button */}
      <button
        type="button"
        onClick={() => {
          setIsOpen(!isOpen);
          if (!isOpen) loadNotifications();
        }}
        aria-label="View notifications"
        className={`relative p-2 rounded-lg transition-colors focus:outline-none ${
          isDark
            ? 'text-gray-300 hover:text-white hover:bg-gray-800'
            : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
        }`}
      >
        {/* Bell SVG */}
        <svg
          className="w-5 h-5"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth="2"
            d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9"
          />
        </svg>

        {/* Unread Badge Counter */}
        {unreadCount > 0 && (
          <span className="absolute top-1 right-1 flex h-4 w-4 items-center justify-center rounded-full bg-rose-500 text-[10px] font-bold text-white shadow-sm ring-2 ring-transparent">
            {unreadCount > 9 ? '9+' : unreadCount}
          </span>
        )}
      </button>

      {/* Dropdown Panel */}
      {isOpen && (
        <div
          className={`absolute right-0 mt-2 w-80 sm:w-96 rounded-xl shadow-2xl z-50 border overflow-hidden transition-all ${
            isDark
              ? 'bg-gray-950 border-gray-800 text-gray-100 shadow-black/80'
              : 'bg-white border-slate-200 text-slate-800 shadow-slate-300/60'
          }`}
        >
          {/* Header */}
          <div
            className={`px-4 py-3 flex items-center justify-between border-b ${
              isDark ? 'border-gray-800 bg-gray-900/60' : 'border-slate-100 bg-slate-50'
            }`}
          >
            <div className="flex items-center gap-2">
              <span className="font-semibold text-sm">Notifications</span>
              {unreadCount > 0 && (
                <span
                  className={`text-[11px] font-medium px-2 py-0.5 rounded-full ${
                    isDark ? 'bg-rose-500/20 text-rose-400' : 'bg-rose-100 text-rose-600'
                  }`}
                >
                  {unreadCount} new
                </span>
              )}
            </div>
            {unreadCount > 0 && (
              <button
                onClick={handleMarkAllRead}
                className="text-xs font-medium text-indigo-400 hover:text-indigo-300 transition-colors"
              >
                Mark all read
              </button>
            )}
          </div>

          {/* List Content */}
          <div className="max-h-96 overflow-y-auto divide-y divide-gray-800/40">
            {loading && notifications.length === 0 ? (
              <div className="p-8 text-center text-xs text-gray-400">Loading notifications...</div>
            ) : notifications.length === 0 ? (
              <div className="p-8 text-center">
                <span className="text-3xl block mb-2">🎉</span>
                <p className="text-xs text-gray-400 font-medium">All caught up! No notifications.</p>
              </div>
            ) : (
              notifications.map((item) => (
                <div
                  key={item.id}
                  onClick={() => onItemClick(item)}
                  className={`p-3.5 flex gap-3 cursor-pointer transition-colors ${
                    !item.is_read
                      ? isDark
                        ? 'bg-gray-900/80 hover:bg-gray-800/90'
                        : 'bg-indigo-50/50 hover:bg-indigo-50'
                      : isDark
                      ? 'hover:bg-gray-900/50'
                      : 'hover:bg-slate-50'
                  }`}
                >
                  {/* Icon */}
                  <span className="text-xl flex-shrink-0 mt-0.5">{getTypeIcon(item.notification_type)}</span>

                  {/* Body */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between gap-1 mb-0.5">
                      <p
                        className={`text-xs font-semibold truncate ${
                          !item.is_read
                            ? isDark
                              ? 'text-white'
                              : 'text-slate-900'
                            : isDark
                            ? 'text-gray-300'
                            : 'text-slate-600'
                        }`}
                      >
                        {item.title}
                      </p>
                      <span className="text-[10px] text-gray-500 flex-shrink-0">
                        {formatTimeAgo(item.created_at)}
                      </span>
                    </div>
                    <p className="text-[11px] text-gray-400 line-clamp-2 leading-relaxed">
                      {item.message}
                    </p>

                    {item.target_entity_id && (
                      <span className="inline-block mt-1 text-[10px] font-mono text-indigo-400">
                        Ref #{item.target_entity_id}
                      </span>
                    )}
                  </div>

                  {/* Unread dot */}
                  {!item.is_read && (
                    <span className="h-2 w-2 rounded-full bg-rose-500 self-center flex-shrink-0" />
                  )}
                </div>
              ))
            )}
          </div>

          {/* Footer */}
          <div
            className={`p-2.5 text-center border-t text-[11px] font-medium ${
              isDark
                ? 'border-gray-800 bg-gray-950/80 text-gray-400'
                : 'border-slate-100 bg-slate-50 text-slate-500'
            }`}
          >
            Clicking any notification opens its exact destination
          </div>
        </div>
      )}
    </div>
  );
};
