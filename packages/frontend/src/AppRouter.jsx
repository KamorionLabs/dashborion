/**
 * App Router
 *
 * Main router for Dashborion dashboard.
 * Integrates plugin system, shell layout, and URL-based routing.
 */

import { useState, useCallback, useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './hooks/useAuth';
import { ConfigProvider, useConfig } from './ConfigContext';
import { PluginProvider, PluginRouter } from './plugins';
import { Shell } from './shell';

// Pages
import DeviceAuth from './pages/DeviceAuth';
import PermissionDenied from './pages/PermissionDenied';
import Dashboard from './pages/Dashboard';

// Register plugins (will be dynamic later)
import { registerPlugins } from './plugins/registerPlugins';

// Register all plugins on startup
registerPlugins();

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
    // Redirect to SAML login with return URL (preserves current path)
    const returnUrl = window.location.pathname + window.location.search;
    window.location.href = '/saml/login?returnUrl=' + encodeURIComponent(returnUrl);
    return null;
  }

  return children;
}

/**
 * Main App with Shell and Plugin Router
 */
function MainApp() {
  const config = useConfig();
  const [refreshKey, setRefreshKey] = useState(0);
  const [refreshing, setRefreshing] = useState(false);
  const [lastUpdated, setLastUpdated] = useState(null);

  // Handle refresh
  const handleRefresh = useCallback(async () => {
    setRefreshing(true);
    setRefreshKey((k) => k + 1);

    // Simulate refresh delay (actual data fetching is in components)
    setTimeout(() => {
      setRefreshing(false);
      setLastUpdated(new Date().toLocaleTimeString());
    }, 500);
  }, []);

  // Initial timestamp
  useEffect(() => {
    setLastUpdated(new Date().toLocaleTimeString());
  }, []);

  // Build plugin config from app config
  const pluginConfig = {
    'aws-ecs': {
      projects: config?.projects || {},
      crossAccountRoles: config?.crossAccountRoles || {},
    },
    'aws-cicd': {
      // Pipeline config
    },
    'aws-infra': {
      // Infrastructure config
    },
  };

  return (
    <PluginProvider config={pluginConfig}>
      <Shell
        onRefresh={handleRefresh}
        refreshing={refreshing}
        lastUpdated={lastUpdated}
      >
        <PluginRouter
          config={pluginConfig}
          defaultElement={<Dashboard refreshKey={refreshKey} />}
        />
      </Shell>
    </PluginProvider>
  );
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
            <Route path="/auth/device" element={<DeviceAuth />} />
            <Route path="/403" element={<PermissionDenied />} />
            <Route path="/permission-denied" element={<PermissionDenied />} />

            {/* All other routes - protected and handled by PluginRouter */}
            <Route
              path="/*"
              element={
                <ProtectedRoute>
                  <MainApp />
                </ProtectedRoute>
              }
            />
          </Routes>
        </AuthProvider>
      </ConfigProvider>
    </BrowserRouter>
  );
}
