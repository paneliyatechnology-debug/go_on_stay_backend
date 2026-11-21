import React from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { PORTAL_HOTEL_OWNER } from '../config/portals';
import { NotificationDropdown } from '../components/NotificationDropdown';

export const HotelOwnerLayout: React.FC = () => {
  const navigate = useNavigate();

  const handleLogout = () => {
    localStorage.removeItem('access_token');
    sessionStorage.removeItem('access_token');
    navigate('/login');
  };

  return (
    <div className="flex h-screen bg-neutral-900 text-neutral-100 font-sans">
      {/* Hotel Owner Dedicated Sidebar */}
      <aside className="w-64 bg-neutral-950 border-r border-neutral-800 flex flex-col">
        <div className="p-5 border-b border-neutral-800 flex items-center justify-between">
          <div>
            <h1 className="text-xl font-black text-amber-500 tracking-wider">GOONSTAY</h1>
            <span className="text-xs uppercase font-bold tracking-widest text-neutral-400">Host Portal</span>
          </div>
          <span className="px-2 py-0.5 text-[10px] font-semibold bg-amber-500/10 text-amber-400 rounded-full border border-amber-500/20">
            HOST
          </span>
        </div>

        {/* Dedicated Host Sidebar Links */}
        <nav className="flex-1 overflow-y-auto p-3 space-y-1">
          {PORTAL_HOTEL_OWNER.sidebar.map((item) => (
            <NavLink
              key={item.id}
              to={item.path}
              end={item.path === '/host/dashboard'}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-amber-600 text-white shadow-sm'
                    : 'text-neutral-400 hover:text-neutral-100 hover:bg-neutral-900'
                }`
              }
            >
              <span className="text-base">▪</span>
              <span className="truncate">{item.title}</span>
            </NavLink>
          ))}
        </nav>

        {/* Host Account Footer & Logout */}
        <div className="p-4 border-t border-neutral-800 bg-neutral-950/60 flex items-center justify-between">
          <div className="truncate">
            <p className="text-xs font-semibold text-neutral-200">Hotel Partner</p>
            <p className="text-[11px] text-neutral-500">Property Manager</p>
          </div>
          <button
            onClick={handleLogout}
            className="px-3 py-1 text-xs font-medium text-neutral-300 hover:text-white bg-neutral-800 hover:bg-red-600 rounded transition-colors"
          >
            Logout
          </button>
        </div>
      </aside>

      {/* Main Host Area */}
      <main className="flex-1 flex flex-col overflow-hidden bg-neutral-900">
        <header className="h-14 border-b border-neutral-800 bg-neutral-950/40 px-6 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-neutral-300">Host Center & Property Management</h2>
          <div className="flex items-center gap-3">
            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-neutral-800 text-amber-400 border border-neutral-700">
              Host Verified
            </span>
            <NotificationDropdown
              user={{
                id: 0,
                email: 'host@goonstay.com',
                fullName: 'Hotel Host',
                role: 'HOTEL_OWNER',
                isStaff: false
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
