import React from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { PORTAL_CUSTOMER } from '../config/portals';
import { NotificationDropdown } from '../components/NotificationDropdown';

export const CustomerLayout: React.FC = () => {
  const navigate = useNavigate();

  const handleLogout = () => {
    localStorage.removeItem('access_token');
    sessionStorage.removeItem('access_token');
    navigate('/login');
  };

  return (
    <div className="flex flex-col min-h-screen bg-slate-50 text-slate-900 font-sans">
      {/* Customer Top Navigation Bar */}
      <header className="h-16 bg-white border-b border-slate-200 px-8 flex items-center justify-between sticky top-0 z-30">
        <div className="flex items-center gap-8">
          <div className="flex items-center gap-2 cursor-pointer" onClick={() => navigate('/hotels')}>
            <span className="text-2xl font-black text-indigo-600 tracking-tight">GoOnStay</span>
          </div>

          <nav className="hidden md:flex items-center gap-1">
            {PORTAL_CUSTOMER.sidebar.map((item) => (
              <NavLink
                key={item.id}
                to={item.path}
                className={({ isActive }) =>
                  `px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                    isActive
                      ? 'bg-indigo-50 text-indigo-700'
                      : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
                  }`
                }
              >
                {item.title}
              </NavLink>
            ))}
          </nav>
        </div>

        <div className="flex items-center gap-4">
          <NotificationDropdown
            user={{
              id: 0,
              email: 'guest@goonstay.com',
              fullName: 'Customer Account',
              role: 'CUSTOMER',
              isStaff: false
            }}
            theme="light"
          />
          <button
            onClick={handleLogout}
            className="px-4 py-2 text-sm font-semibold text-slate-700 hover:text-rose-600 transition-colors"
          >
            Sign Out
          </button>
        </div>
      </header>

      {/* Main Customer View */}
      <main className="flex-1 max-w-7xl w-full mx-auto p-6 md:p-8">
        <Outlet />
      </main>
    </div>
  );
};
