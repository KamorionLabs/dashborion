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
import ComparisonPage from './pages/comparison/ComparisonPage';

// Admin Pages
import AdminLayout from './pages/admin/AdminLayout';
import ConfigDashboard from './pages/admin/ConfigDashboard';
import SettingsPage from './pages/admin/SettingsPage';
import ProjectsPage from './pages/admin/ProjectsPage';
import ProjectForm from './pages/admin/ProjectForm';
import EnvironmentsPage from './pages/admin/EnvironmentsPage';
import EnvironmentForm from './pages/admin/EnvironmentForm';
import ClustersPage from './pages/admin/ClustersPage';
import ClusterForm from './pages/admin/ClusterForm';
import AccountsPage from './pages/admin/AccountsPage';
import AccountForm from './pages/admin/AccountForm';

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
 * Admin Route wrapper - requires authentication + global admin role
 */
function AdminRoute({ children }) {
  const { isAuthenticated, isLoading, isGlobalAdmin } = useAuth();

  if (isLoading) {
    return <LoadingScreen />;
  }

  if (!isAuthenticated) {
    const returnUrl = window.location.pathname + window.location.search;
    window.location.href = '/login?returnUrl=' + encodeURIComponent(returnUrl);
    return null;
  }

  if (!isGlobalAdmin()) {
    return <Navigate to="/403" replace />;
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

              {/* Admin routes - no Shell, uses AdminLayout, requires global admin */}
              <Route
                path="/admin"
                element={
                  <AdminRoute>
                    <Navigate to="/admin/config" replace />
                  </AdminRoute>
                }
              />
              <Route
                path="/admin/config"
                element={
                  <AdminRoute>
                    <AdminLayout />
                  </AdminRoute>
                }
              >
                <Route index element={<ConfigDashboard />} />
                <Route path="settings" element={<SettingsPage />} />
                <Route path="projects" element={<ProjectsPage />} />
                <Route path="projects/new" element={<ProjectForm />} />
                <Route path="projects/:projectId" element={<ProjectForm />} />
                <Route path="projects/:projectId/environments" element={<EnvironmentsPage />} />
                <Route path="projects/:projectId/environments/new" element={<EnvironmentForm />} />
                <Route path="projects/:projectId/environments/:envId" element={<EnvironmentForm />} />
                <Route path="clusters" element={<ClustersPage />} />
                <Route path="clusters/new" element={<ClusterForm />} />
                <Route path="clusters/:clusterId" element={<ClusterForm />} />
                <Route path="accounts" element={<AccountsPage />} />
                <Route path="accounts/new" element={<AccountForm />} />
                <Route path="accounts/:accountId" element={<AccountForm />} />
              </Route>

              {/* Protected routes with Shell */}
              {/* Comparison view */}
              <Route
                path="/:project/comparison/:sourceEnv/:destEnv"
                element={
                  <ProtectedRoute>
                    <ShellWithContext>
                      <ComparisonPage />
                    </ShellWithContext>
                  </ProtectedRoute>
                }
              />
              <Route
                path="/:project/comparison"
                element={
                  <ProtectedRoute>
                    <ShellWithContext>
                      <ComparisonPage />
                    </ShellWithContext>
                  </ProtectedRoute>
                }
              />

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
