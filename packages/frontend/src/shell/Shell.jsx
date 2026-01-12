/**
 * Dashborion Shell
 *
 * Main application shell with header, sidebar navigation, content area, and footer.
 * Provides the layout structure for the dashboard.
 */

import { useState, useEffect } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import {
  RefreshCw,
  Menu,
  X,
  ChevronDown,
  LogOut,
  User,
  Settings,
  Home,
  Clock,
  Server,
  ArrowLeftRight,
  RotateCcw,
  LayoutDashboard,
} from 'lucide-react';
import { useConfig } from '../ConfigContext';
import { useAuth } from '../hooks/useAuth';
import { ProjectSelector } from '../components/common';

/**
 * View Navigation - Links to different views based on features
 */
function ViewNavigation() {
  const config = useConfig();
  const location = useLocation();

  // Get current project from URL
  const pathParts = location.pathname.split('/').filter(Boolean);
  const currentProject = pathParts[0];

  if (!currentProject || currentProject === 'login' || currentProject === 'auth') {
    return null;
  }

  // Check which features are enabled
  const features = config.features || {};
  const projectFeatures = config.projects?.[currentProject]?.features || {};

  // Features are opt-in: only show if explicitly enabled at global or project level
  // Project-level setting overrides global setting
  const showComparison = projectFeatures.comparison ?? features.comparison ?? false;
  const showRefresh = projectFeatures.refresh ?? features.refresh ?? false;

  // Determine current view
  const isComparison = location.pathname.includes('/comparison');
  const isRefresh = location.pathname.includes('/refresh');
  const isDashboard = !isComparison && !isRefresh;

  // Get first env for dashboard link
  const projectConfig = config.projects?.[currentProject];
  const firstEnv = (() => {
    const envs = projectConfig?.environments;
    if (!envs) return null;
    if (Array.isArray(envs)) {
      const first = envs[0];
      return typeof first === 'string' ? first : first?.id || first?.name;
    }
    return Object.keys(envs)[0];
  })();

  const navItems = [
    {
      id: 'dashboard',
      label: 'Dashboard',
      icon: LayoutDashboard,
      href: firstEnv ? `/${currentProject}/${firstEnv}` : `/${currentProject}`,
      active: isDashboard,
      show: true,
    },
    {
      id: 'comparison',
      label: 'Comparison',
      icon: ArrowLeftRight,
      href: `/${currentProject}/comparison`,
      active: isComparison,
      show: showComparison,
    },
    {
      id: 'refresh',
      label: 'Refresh',
      icon: RotateCcw,
      href: `/${currentProject}/refresh`,
      active: isRefresh,
      show: showRefresh,
    },
  ];

  const visibleItems = navItems.filter(item => item.show);

  // Don't show navigation if only dashboard is available
  if (visibleItems.length <= 1) {
    return null;
  }

  return (
    <nav className="flex items-center gap-1">
      {visibleItems.map((item) => {
        const Icon = item.icon;
        return (
          <Link
            key={item.id}
            to={item.href}
            className={`
              flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm font-medium
              transition-colors
              ${item.active
                ? 'bg-blue-600/20 text-blue-400 border border-blue-500/30'
                : 'text-gray-400 hover:text-gray-200 hover:bg-gray-700/50'}
            `}
          >
            <Icon className="w-4 h-4" />
            <span className="hidden lg:inline">{item.label}</span>
          </Link>
        );
      })}
    </nav>
  );
}

/**
 * Role badge colors
 */
const ROLE_COLORS = {
  admin: 'bg-red-500/20 text-red-400 border-red-500/30',
  operator: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
  viewer: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
};

/**
 * Header component
 */
function Header({
  onToggleSidebar,
  sidebarOpen,
  onRefresh,
  refreshing,
  lastUpdated,
  autoRefresh,
  onAutoRefreshChange,
  showSidebarToggle = false,
}) {
  const auth = useAuth();
  const config = useConfig();
  const [userMenuOpen, setUserMenuOpen] = useState(false);

  return (
    <header className="bg-gray-800 border-b border-gray-700 px-4 py-3 flex items-center justify-between sticky top-0 z-50">
      {/* Left: Menu toggle + Logo + Project */}
      <div className="flex items-center gap-4">
        {showSidebarToggle && (
          <button
            onClick={onToggleSidebar}
            className="p-2 hover:bg-gray-700 rounded-lg lg:hidden"
            aria-label="Toggle sidebar"
          >
            {sidebarOpen ? <X size={20} /> : <Menu size={20} />}
          </button>
        )}

        <img src={config.branding?.logo} alt={config.branding?.logoAlt} className="h-10" />
        <div className="h-6 w-px bg-gray-600"></div>
        <div className="flex items-center gap-2">
          <Server className="w-6 h-6 text-blue-500" />
          <h1 className="text-lg font-bold">{config.global?.title || 'Operations Dashboard'}</h1>
        </div>
        <div className="h-6 w-px bg-gray-600"></div>
        <ProjectSelector />
        <div className="h-6 w-px bg-gray-600"></div>
        <ViewNavigation />
      </div>

      {/* Right: Auto-refresh + Refresh + User */}
      <div className="flex items-center gap-4">
        {/* Auto-refresh toggle */}
        {onAutoRefreshChange && (
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => onAutoRefreshChange(e.target.checked)}
              className="w-4 h-4 rounded bg-gray-700 border-gray-600 text-blue-500 focus:ring-blue-500"
            />
            <span className="text-sm text-gray-400">Auto-refresh</span>
          </label>
        )}

        {/* Refresh button */}
        {onRefresh && (
          <button
            onClick={onRefresh}
            disabled={refreshing}
            className="flex items-center gap-2 px-3 py-1.5 bg-gray-700 hover:bg-gray-600 rounded-md transition-colors disabled:opacity-50"
            aria-label="Refresh"
          >
            <RefreshCw
              size={16}
              className={refreshing ? 'animate-spin' : ''}
            />
            <span className="text-sm">{refreshing ? 'Refreshing...' : 'Refresh'}</span>
          </button>
        )}

        {/* Last updated */}
        {lastUpdated && (
          <div className="flex items-center gap-1 text-sm text-gray-500">
            <Clock className="w-4 h-4" />
            <span>{lastUpdated.toLocaleTimeString()}</span>
          </div>
        )}

        {/* User menu */}
        {auth?.user && (
          <div className="relative flex items-center gap-3 ml-4 pl-4 border-l border-gray-600">
            <button
              onClick={() => setUserMenuOpen(!userMenuOpen)}
              className="flex items-center gap-2 p-2 hover:bg-gray-700 rounded-lg"
            >
              <div className="w-8 h-8 bg-gray-700 rounded-full flex items-center justify-center">
                <User size={16} className="text-gray-400" />
              </div>
              <span className="text-sm text-gray-300 hidden md:inline">
                {auth.user.name || auth.user.email}
              </span>
              <ChevronDown size={14} className="text-gray-500" />
            </button>

            {userMenuOpen && (
              <>
                <div
                  className="fixed inset-0 z-40"
                  onClick={() => setUserMenuOpen(false)}
                />
                <div className="absolute right-0 top-full mt-2 w-64 bg-gray-800 border border-gray-700 rounded-lg shadow-lg z-50">
                  <div className="px-4 py-3 border-b border-gray-700">
                    <p className="text-sm text-gray-300">{auth.user.email}</p>
                    {auth.user.groups?.length > 0 && (
                      <p className="text-xs text-gray-500 mt-1">
                        {auth.user.groups.join(', ')}
                      </p>
                    )}
                  </div>

                  {/* Permissions section */}
                  {auth.permissions?.length > 0 && (
                    <div className="px-4 py-2 border-b border-gray-700">
                      <p className="text-xs text-gray-500 mb-2">Permissions</p>
                      <div className="space-y-1 max-h-32 overflow-y-auto">
                        {auth.permissions.map((perm, idx) => (
                          <div
                            key={idx}
                            className="flex items-center justify-between text-xs"
                          >
                            <span className="text-gray-400">
                              {perm.project === '*' ? 'All projects' : perm.project}
                              {perm.environment !== '*' && `/${perm.environment}`}
                            </span>
                            <span
                              className={`px-1.5 py-0.5 rounded text-xs ${
                                ROLE_COLORS[perm.role] || ROLE_COLORS.viewer
                              }`}
                            >
                              {perm.role}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  <div className="py-1">
                    <Link
                      to="/settings"
                      className="flex items-center gap-2 px-4 py-2 text-sm text-gray-300 hover:bg-gray-700"
                      onClick={() => setUserMenuOpen(false)}
                    >
                      <Settings size={16} />
                      Settings
                    </Link>
                    <button
                      onClick={() => auth.logout?.()}
                      className="flex items-center gap-2 px-4 py-2 text-sm text-red-400 hover:bg-gray-700 w-full text-left"
                    >
                      <LogOut size={16} />
                      Logout
                    </button>
                  </div>
                </div>
              </>
            )}
          </div>
        )}
      </div>
    </header>
  );
}

/**
 * Main Shell component
 */
export function Shell({
  children,
  onRefresh,
  refreshing = false,
  lastUpdated,
  autoRefresh,
  onAutoRefreshChange,
}) {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const location = useLocation();

  // Close sidebar on route change (mobile)
  useEffect(() => {
    setSidebarOpen(false);
  }, [location.pathname]);

  return (
    <div className="min-h-screen bg-gray-900 text-gray-100 flex flex-col">
      <Header
        onToggleSidebar={() => setSidebarOpen(!sidebarOpen)}
        sidebarOpen={sidebarOpen}
        onRefresh={onRefresh}
        refreshing={refreshing}
        lastUpdated={lastUpdated}
        autoRefresh={autoRefresh}
        onAutoRefreshChange={onAutoRefreshChange}
        showSidebarToggle={false}
      />

      <div className="flex flex-1">
        <main className="flex-1 overflow-x-hidden">
          {children}
        </main>
      </div>

      <footer className="py-4 text-center text-sm text-gray-400">
        <a
          href="https://github.com/kamorionlabs/dashborion"
          target="_blank"
          rel="noopener noreferrer"
          className="hover:text-white transition-colors"
        >
          Made with ❤️ by Kamorion
        </a>
      </footer>
    </div>
  );
}

export default Shell;
