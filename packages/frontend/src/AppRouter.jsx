/**
 * App Router
 *
 * Main router for Dashborion dashboard.
 * Uses the original single-page dashboard layout with URL-based state.
 */

import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './hooks/useAuth';
import { ConfigProvider, useConfig } from './ConfigContext';

// Pages
import DeviceAuth from './pages/DeviceAuth';
import PermissionDenied from './pages/PermissionDenied';
import Login from './pages/Login';
import HomeDashboard from './pages/HomeDashboard';

/**
 * Loading screen
 */
function LoadingScreen() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-950">
      <div className="text-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto"></div>
        <p className="mt-4 text-gray-400">Loading Dashborion...</p>
      </div>
    </div>
  );
}

/**
 * Protected Route wrapper - requires authentication
 */
function ProtectedRoute({ children }) {
  const { isAuthenticated, isLoading } = useAuth();

  if (isLoading) {
    return <LoadingScreen />;
  }

  if (!isAuthenticated) {
    // Redirect to login page with return URL (preserves current path)
    const returnUrl = window.location.pathname + window.location.search;
    window.location.href = '/login?returnUrl=' + encodeURIComponent(returnUrl);
    return null;
  }

  return children;
}

/**
 * Default route - redirects to first project/env
 */
function DefaultRedirect() {
  const config = useConfig();

  // Get first project and its first environment
  const projectId = config.currentProjectId || Object.keys(config.projects || {})[0] || 'homebox';
  const project = config.projects?.[projectId];
  const firstEnv = project?.environments?.[0] || 'staging';

  return <Navigate to={`/${projectId}/${firstEnv}`} replace />;
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
            {/* Public routes - no auth required */}
            <Route path="/login" element={<Login />} />
            <Route path="/auth/device" element={<DeviceAuth />} />
            <Route path="/403" element={<PermissionDenied />} />
            <Route path="/permission-denied" element={<PermissionDenied />} />

            {/* Protected routes */}
            {/* Dashboard with project and env in URL */}
            <Route
              path="/:project/:env"
              element={
                <ProtectedRoute>
                  <HomeDashboard />
                </ProtectedRoute>
              }
            />

            {/* Project only - redirect to first env */}
            <Route
              path="/:project"
              element={
                <ProtectedRoute>
                  <ProjectRedirect />
                </ProtectedRoute>
              }
            />

            {/* Root - redirect to default project/env */}
            <Route
              path="/"
              element={
                <ProtectedRoute>
                  <DefaultRedirect />
                </ProtectedRoute>
              }
            />

            {/* Catch all - redirect to home */}
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </AuthProvider>
      </ConfigProvider>
    </BrowserRouter>
  );
}

/**
 * Project redirect - redirects to first environment of the project
 */
function ProjectRedirect() {
  const config = useConfig();
  const projectId = window.location.pathname.split('/')[1];

  const project = config.projects?.[projectId];
  if (!project) {
    // Invalid project, go to default
    return <DefaultRedirect />;
  }

  const firstEnv = project.environments?.[0] || 'staging';
  return <Navigate to={`/${projectId}/${firstEnv}`} replace />;
}
