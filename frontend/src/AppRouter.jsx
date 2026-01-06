/**
 * App Router
 *
 * Handles routing for the Dashborion dashboard.
 */

import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './hooks/useAuth';
import { ConfigProvider } from './ConfigContext';
import App from './App';
import DeviceAuth from './pages/DeviceAuth';
import PermissionDenied from './pages/PermissionDenied';

/**
 * Protected Route wrapper - requires authentication
 */
function ProtectedRoute({ children }) {
  const { isAuthenticated, isLoading } = useAuth();

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-900">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  if (!isAuthenticated) {
    // Redirect to SAML login with return URL
    const returnUrl = window.location.pathname + window.location.search;
    window.location.href = '/saml/login?returnUrl=' + encodeURIComponent(returnUrl);
    return null;
  }

  return children;
}

/**
 * Main App Router
 */
export default function AppRouter() {
  return (
    <BrowserRouter>
      <ConfigProvider>
        <AuthProvider>
          <Routes>
            {/* Public routes */}
            <Route path="/auth/device" element={<DeviceAuth />} />
            <Route path="/403" element={<PermissionDenied />} />
            <Route path="/permission-denied" element={<PermissionDenied />} />

            {/* Protected routes */}
            <Route
              path="/"
              element={
                <ProtectedRoute>
                  <App />
                </ProtectedRoute>
              }
            />

            {/* Catch-all redirect to home */}
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </AuthProvider>
      </ConfigProvider>
    </BrowserRouter>
  );
}
