/**
 * App Router
 *
 * Main router for Dashborion dashboard.
 * Uses Shell for layout and DashboardContext for shared state.
 */

import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './hooks/useAuth';
import { ConfigProvider, useConfig } from './ConfigContext';
import { DashboardProvider, useDashboard } from './contexts/DashboardContext';
import { Shell } from './shell/Shell';

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
 * Shell wrapper that connects to DashboardContext
 */
function ShellWithContext({ children }) {
  const dashboard = useDashboard();

  return (
    <Shell
      onRefresh={dashboard.triggerRefresh}
      refreshing={dashboard.refreshing}
      lastUpdated={dashboard.lastUpdated}
      autoRefresh={dashboard.autoRefresh}
      onAutoRefreshChange={dashboard.setAutoRefresh}
    >
      {children}
    </Shell>
  );
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

/**
 * Main App Router
 */
export default function AppRouter() {
  return (
    <BrowserRouter>
      <ConfigProvider>
        <AuthProvider>
          <DashboardProvider>
            <Routes>
              {/* Public routes - no auth required, no shell */}
              <Route path="/login" element={<Login />} />
              <Route path="/auth/device" element={<DeviceAuth />} />
              <Route path="/403" element={<PermissionDenied />} />
              <Route path="/permission-denied" element={<PermissionDenied />} />

              {/* Protected routes with Shell */}
              {/* Dashboard with project and env in URL */}
              <Route
                path="/:project/:env"
                element={
                  <ProtectedRoute>
                    <ShellWithContext>
                      <HomeDashboard />
                    </ShellWithContext>
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
          </DashboardProvider>
        </AuthProvider>
      </ConfigProvider>
    </BrowserRouter>
  );
}
