import React from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { PORTAL_ADMIN } from '../config/portals';
import { NotificationDropdown } from '../components/NotificationDropdown';

export const AdminLayout: React.FC = () => {
  const navigate = useNavigate();

  const handleLogout = () => {
    localStorage.removeItem('access_token');
    sessionStorage.removeItem('access_token');
    navigate('/login');
  };

  return (
    <div className="flex h-screen bg-slate-900 text-slate-100 font-sans">
      {/* Dedicated Admin Sidebar */}
      <aside className="w-64 bg-slate-950 border-r border-slate-800 flex flex-col">
        <div className="p-5 border-b border-slate-800 flex items-center justify-between">
          <div>
            <h1 className="text-xl font-black text-rose-500 tracking-wider">GOONSTAY</h1>
            <span className="text-xs uppercase font-bold tracking-widest text-slate-400">Admin Portal</span>
          </div>
          <span className="px-2 py-0.5 text-[10px] font-semibold bg-rose-500/10 text-rose-400 rounded-full border border-rose-500/20">
            SYSTEM
          </span>
        </div>

        {/* 17 Dedicated Admin Oversight Navigation Links */}
        <nav className="flex-1 overflow-y-auto p-3 space-y-1 scrollbar-thin">
          {PORTAL_ADMIN.sidebar.map((item) => (
            <NavLink
              key={item.id}
              to={item.path}
              end={item.path === '/admin/dashboard'}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-rose-600 text-white shadow-sm'
                    : 'text-slate-400 hover:text-slate-100 hover:bg-slate-900'
                }`
              }
            >
              <span className="text-base">▪</span>
              <span className="truncate">{item.title}</span>
            </NavLink>
          ))}
        </nav>

        {/* Admin Footer & Logout */}
        <div className="p-4 border-t border-slate-800 bg-slate-950/60 flex items-center justify-between">
          <div className="truncate">
            <p className="text-xs font-semibold text-slate-200">System Admin</p>
            <p className="text-[11px] text-slate-500">Platform Oversight</p>
          </div>
          <button
            onClick={handleLogout}
            className="px-3 py-1 text-xs font-medium text-slate-300 hover:text-white bg-slate-800 hover:bg-rose-600/80 rounded transition-colors"
          >
            Logout
          </button>
        </div>
      </aside>

      {/* Main Administrative Content Area */}
      <main className="flex-1 flex flex-col overflow-hidden bg-slate-900">
        <header className="h-14 border-b border-slate-800 bg-slate-950/40 px-6 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-300">Administrative Oversight & Platform Governance</h2>
          <div className="flex items-center gap-3">
            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-emerald-950 text-emerald-400 border border-emerald-800">
              Live Production
            </span>
            <NotificationDropdown
              user={{
                id: 0,
                email: 'admin@goonstay.com',
                fullName: 'System Admin',
                role: 'ADMIN',
                isStaff: true
              }}
              theme="dark"
            />
          </div>
        </header>
        <section className="flex-1 overflow-y-auto p-6">
          <Outlet />
        </section>
      </main>
    </div>
  );
};
