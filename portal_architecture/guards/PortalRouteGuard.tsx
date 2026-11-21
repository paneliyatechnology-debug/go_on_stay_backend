import React, { useEffect, useState } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { NavigationResponse, fetchPortalNavigation } from '../services/portalApi';

interface PortalRouteGuardProps {
  requiredPortalId?: string;
  requiredRole?: string;
  requiredDepartment?: string;
  children: React.ReactNode;
}

export const PortalRouteGuard: React.FC<PortalRouteGuardProps> = ({
  requiredPortalId,
  requiredRole,
  requiredDepartment,
  children
}) => {
  const location = useLocation();
  const [loading, setLoading] = useState<boolean>(true);
  const [navData, setNavData] = useState<NavigationResponse | null>(null);
  const [errorStatus, setErrorStatus] = useState<string | null>(null);

  useEffect(() => {
    const token = localStorage.getItem('access_token') || sessionStorage.getItem('access_token');
    if (!token) {
      setLoading(false);
      setErrorStatus('NO_TOKEN');
      return;
    }

    fetchPortalNavigation(token)
      .then((data) => {
        setNavData(data);
        setLoading(false);
      })
      .catch((err) => {
        console.error('Portal authorization failed:', err);
        setErrorStatus(err.code || 'UNAUTHORIZED');
        setLoading(false);
      });
  }, [location.pathname]);

  // 1. Loading Skeleton State
  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-gray-50">
        <div className="text-center p-8 bg-white shadow-md rounded-xl max-w-md w-full">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600 mx-auto mb-4"></div>
          <h2 className="text-lg font-semibold text-gray-700">Verifying Role Portal Access...</h2>
          <p className="text-sm text-gray-500 mt-1">Connecting to GoOnStay Enterprise Security Guard</p>
        </div>
      </div>
    );
  }

  // 2. Unauthenticated / Token Missing -> Redirect to Login
  if (errorStatus === 'NO_TOKEN' || !navData) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  // 3. Inactive Account or Password Change Required
  if (errorStatus === 'ACCOUNT_INACTIVE') {
    return (
      <div className="min-h-screen flex items-center justify-center bg-red-50 p-6">
        <div className="max-w-md w-full bg-white p-8 rounded-xl shadow-lg border border-red-200 text-center">
          <h2 className="text-xl font-bold text-red-600">Account Inactive</h2>
          <p className="text-sm text-gray-600 mt-2">
            Your GoOnStay staff account has been deactivated or suspended. Please contact the Platform Administrator.
          </p>
        </div>
      </div>
    );
  }

  if (errorStatus === 'PASSWORD_CHANGE_REQUIRED') {
    return <Navigate to="/staff/change-password" replace />;
  }

  const { portal, user } = navData;
  const portalId = (portal as any)?.portalId || (portal as any)?.portal_id;
  const dashboardUrl = (portal as any)?.dashboardUrl || (portal as any)?.dashboard_url || '/';
  const userRole = user?.role;
  const userDept = (portal as any)?.department || user?.department;

  // 4. Portal-level Enforcement
  if (requiredPortalId && portalId !== requiredPortalId) {
    console.warn(`[PortalGuard] Access denied. Expected portal ${requiredPortalId}, but user belongs to ${portalId}.`);
    return <Navigate to={dashboardUrl} replace />;
  }

  // 5. Role-level Enforcement
  if (requiredRole && userRole !== requiredRole) {
    console.warn(`[PortalGuard] Role mismatch. Expected ${requiredRole}, got ${userRole}.`);
    return <Navigate to={dashboardUrl} replace />;
  }

  // 6. Department-level Enforcement for Staff
  if (requiredDepartment && userDept !== requiredDepartment) {
    console.warn(`[PortalGuard] Cross-department attempt blocked. User is in ${userDept}, attempted ${requiredDepartment}.`);
    return <Navigate to={dashboardUrl} replace />;
  }

  // Authorized
  return <>{children}</>;
};
