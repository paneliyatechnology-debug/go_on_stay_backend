import React from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { 
  PORTAL_RESERVATION, 
  PORTAL_CUSTOMER_SUPPORT, 
  PORTAL_REFUNDS_AND_CLAIMS, 
  PORTAL_PAYOUT_AND_ESCROW, 
  PORTAL_HOTEL_VERIFICATION,
  PortalDefinition,
  StaffDepartmentCode 
} from '../config/portals';
import { NotificationDropdown } from '../components/NotificationDropdown';
import { UserSession } from '../services/portalApi';

interface StaffPortalLayoutProps {
  department: StaffDepartmentCode;
}

const DEPT_CONFIGS: Record<StaffDepartmentCode, { portal: PortalDefinition; badgeColor: string; accentColor: string }> = {
  RESERVATION: {
    portal: PORTAL_RESERVATION,
    badgeColor: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
    accentColor: 'bg-blue-600'
  },
  CUSTOMER_SUPPORT: {
    portal: PORTAL_CUSTOMER_SUPPORT,
    badgeColor: 'bg-purple-500/10 text-purple-400 border-purple-500/20',
    accentColor: 'bg-purple-600'
  },
  REFUNDS_AND_CLAIMS: {
    portal: PORTAL_REFUNDS_AND_CLAIMS,
    badgeColor: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
    accentColor: 'bg-emerald-600'
  },
  PAYOUT_AND_ESCROW: {
    portal: PORTAL_PAYOUT_AND_ESCROW,
    badgeColor: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
    accentColor: 'bg-amber-600'
  },
  HOTEL_VERIFICATION: {
    portal: PORTAL_HOTEL_VERIFICATION,
    badgeColor: 'bg-cyan-500/10 text-cyan-400 border-cyan-500/20',
    accentColor: 'bg-cyan-600'
  }
};

export const StaffPortalLayout: React.FC<StaffPortalLayoutProps> = ({ department }) => {
  const navigate = useNavigate();
  const config = DEPT_CONFIGS[department] || DEPT_CONFIGS.RESERVATION;
  const { portal, badgeColor, accentColor } = config;

  const handleLogout = () => {
    localStorage.removeItem('access_token');
    sessionStorage.removeItem('access_token');
    navigate('/staff/login');
  };

  return (
    <div className="flex h-screen bg-gray-900 text-gray-100 font-sans">
      {/* Strictly Isolated Department Sidebar */}
      <aside className="w-64 bg-gray-950 border-r border-gray-800 flex flex-col">
        <div className="p-5 border-b border-gray-800 flex items-center justify-between">
          <div>
            <h1 className="text-xl font-black text-white tracking-wider">GOONSTAY</h1>
            <span className="text-xs uppercase font-bold tracking-widest text-gray-400">{portal.portalName}</span>
          </div>
          <span className={`px-2 py-0.5 text-[10px] font-semibold rounded-full border ${badgeColor}`}>
            {department}
          </span>
        </div>

        {/* Only This Department's Permitted Sidebar Links */}
        <nav className="flex-1 overflow-y-auto p-3 space-y-1">
          {portal.sidebar
            .filter((item) => !item.hiddenFromMenu)
            .map((item) => (
              <NavLink
                key={item.id}
                to={item.path}
                end={item.path === portal.dashboardUrl}
                className={({ isActive }) =>
                  `flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                    isActive
                      ? `${accentColor} text-white shadow-sm`
                      : 'text-gray-400 hover:text-gray-100 hover:bg-gray-800/60'
                  }`
                }
              >
                <span className="text-base">▪</span>
                <span className="truncate">{item.title}</span>
              </NavLink>
            ))}
        </nav>

        {/* Staff Member Footer & Logout */}
        <div className="p-4 border-t border-gray-800 bg-gray-950/60 flex items-center justify-between">
          <div className="truncate">
            <p className="text-xs font-semibold text-gray-200">Staff Account</p>
            <p className="text-[11px] text-gray-500">{department}</p>
          </div>
          <button
            onClick={handleLogout}
            className="px-3 py-1 text-xs font-medium text-gray-300 hover:text-white bg-gray-800 hover:bg-red-600 rounded transition-colors"
          >
            Logout
          </button>
        </div>
      </aside>

      {/* Main Content Area */}
      <main className="flex-1 flex flex-col overflow-hidden bg-gray-900">
        <header className="h-14 border-b border-gray-800 bg-gray-950/40 px-6 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-gray-300">{portal.portalName} Workspace</h2>
          <div className="flex items-center gap-3">
            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-800 text-gray-300 border border-gray-700">
              Department Secured
            </span>
            <NotificationDropdown
              user={{
                id: 0,
                email: '',
                fullName: `${department} Staff`,
                role: 'STAFF',
                isStaff: true,
                department: department
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
