/**
 * Dashborion Shell
 *
 * Main application shell with header, sidebar navigation, and content area.
 * Provides the layout structure for the plugin-based frontend.
 */

import { useState, useEffect, useCallback } from 'react';
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
} from 'lucide-react';
import { usePluginNav, useRouteParams } from '../plugins';
import { useConfig } from '../ConfigContext';
import { useAuth } from '../hooks/useAuth';

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
  currentProject,
  currentEnv,
}) {
  const auth = useAuth();
  const [userMenuOpen, setUserMenuOpen] = useState(false);

  // Get role for current project/env
  const currentRole = auth.getRoleFor?.(currentProject, currentEnv);

  return (
    <header className="bg-gray-900 border-b border-gray-800 px-4 py-3 flex items-center justify-between sticky top-0 z-40">
      {/* Left: Menu toggle + Logo */}
      <div className="flex items-center gap-4">
        <button
          onClick={onToggleSidebar}
          className="p-2 hover:bg-gray-800 rounded-lg lg:hidden"
          aria-label="Toggle sidebar"
        >
          {sidebarOpen ? <X size={20} /> : <Menu size={20} />}
        </button>

        <Link to="/" className="flex items-center gap-2">
          <div className="w-8 h-8 bg-gradient-to-br from-blue-500 to-purple-600 rounded-lg flex items-center justify-center">
            <span className="text-white font-bold text-sm">D</span>
          </div>
          <span className="text-lg font-semibold text-white hidden sm:inline">
            Dashborion
          </span>
        </Link>
      </div>

      {/* Right: Refresh + User */}
      <div className="flex items-center gap-3">
        {/* Last updated */}
        {lastUpdated && (
          <span className="text-xs text-gray-500 hidden md:inline">
            Updated {lastUpdated}
          </span>
        )}

        {/* Refresh button */}
        <button
          onClick={onRefresh}
          disabled={refreshing}
          className="p-2 hover:bg-gray-800 rounded-lg transition-colors disabled:opacity-50"
          aria-label="Refresh"
        >
          <RefreshCw
            size={18}
            className={refreshing ? 'animate-spin text-blue-400' : 'text-gray-400'}
          />
        </button>

        {/* Role badge for current project */}
        {currentRole && currentProject && (
          <span
            className={`hidden md:inline-flex items-center px-2 py-1 text-xs font-medium rounded border ${
              ROLE_COLORS[currentRole] || ROLE_COLORS.viewer
            }`}
            title={`Your role for ${currentProject}/${currentEnv || '*'}`}
          >
            {currentRole}
          </span>
        )}

        {/* User menu */}
        {auth?.user && (
          <div className="relative">
            <button
              onClick={() => setUserMenuOpen(!userMenuOpen)}
              className="flex items-center gap-2 p-2 hover:bg-gray-800 rounded-lg"
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
                <div className="absolute right-0 mt-2 w-64 bg-gray-800 border border-gray-700 rounded-lg shadow-lg z-50">
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
 * Project/Environment selector
 */
function ProjectEnvSelector({ projects, currentProject, currentEnv, onNavigate }) {
  const [projectMenuOpen, setProjectMenuOpen] = useState(false);
  const [envMenuOpen, setEnvMenuOpen] = useState(false);

  const project = projects?.[currentProject];
  const environments = project?.environments ? Object.keys(project.environments) : [];

  return (
    <div className="px-4 py-3 border-b border-gray-800">
      {/* Project selector */}
      <div className="relative mb-2">
        <button
          onClick={() => setProjectMenuOpen(!projectMenuOpen)}
          className="w-full flex items-center justify-between p-2 bg-gray-800 hover:bg-gray-750 rounded-lg text-left"
        >
          <span className="text-sm font-medium text-white">
            {project?.displayName || currentProject || 'Select Project'}
          </span>
          <ChevronDown size={14} className="text-gray-500" />
        </button>

        {projectMenuOpen && projects && (
          <>
            <div className="fixed inset-0 z-40" onClick={() => setProjectMenuOpen(false)} />
            <div className="absolute left-0 right-0 mt-1 bg-gray-800 border border-gray-700 rounded-lg shadow-lg z-50 max-h-64 overflow-auto">
              {Object.entries(projects).map(([id, proj]) => (
                <button
                  key={id}
                  onClick={() => {
                    onNavigate(`/${id}`);
                    setProjectMenuOpen(false);
                  }}
                  className={`w-full px-4 py-2 text-sm text-left hover:bg-gray-700 ${
                    id === currentProject ? 'text-blue-400' : 'text-gray-300'
                  }`}
                >
                  {proj.displayName || id}
                </button>
              ))}
            </div>
          </>
        )}
      </div>

      {/* Environment selector */}
      {currentProject && environments.length > 0 && (
        <div className="relative">
          <button
            onClick={() => setEnvMenuOpen(!envMenuOpen)}
            className="w-full flex items-center justify-between p-2 bg-gray-800 hover:bg-gray-750 rounded-lg text-left"
          >
            <div className="flex items-center gap-2">
              <span
                className={`w-2 h-2 rounded-full ${
                  currentEnv === 'production' ? 'bg-red-500' :
                  currentEnv === 'staging' ? 'bg-yellow-500' :
                  'bg-green-500'
                }`}
              />
              <span className="text-sm text-gray-300">
                {currentEnv || 'Select Environment'}
              </span>
            </div>
            <ChevronDown size={14} className="text-gray-500" />
          </button>

          {envMenuOpen && (
            <>
              <div className="fixed inset-0 z-40" onClick={() => setEnvMenuOpen(false)} />
              <div className="absolute left-0 right-0 mt-1 bg-gray-800 border border-gray-700 rounded-lg shadow-lg z-50">
                {environments.map((env) => (
                  <button
                    key={env}
                    onClick={() => {
                      onNavigate(`/${currentProject}/${env}`);
                      setEnvMenuOpen(false);
                    }}
                    className={`w-full px-4 py-2 text-sm text-left hover:bg-gray-700 flex items-center gap-2 ${
                      env === currentEnv ? 'text-blue-400' : 'text-gray-300'
                    }`}
                  >
                    <span
                      className={`w-2 h-2 rounded-full ${
                        env === 'production' ? 'bg-red-500' :
                        env === 'staging' ? 'bg-yellow-500' :
                        'bg-green-500'
                      }`}
                    />
                    {env}
                  </button>
                ))}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}

/**
 * Sidebar navigation
 */
function Sidebar({ open, onClose, projects }) {
  const location = useLocation();
  const navigate = useNavigate();
  const { project: currentProject, environment: currentEnv } = useRouteParams();
  const pluginNavItems = usePluginNav();

  // Build navigation items from plugins
  const navItems = [
    { id: 'home', label: 'Dashboard', path: '/', icon: Home },
    ...pluginNavItems,
  ];

  // Check if a path is active
  const isActive = (path) => {
    if (path === '/') return location.pathname === '/';
    return location.pathname.startsWith(path);
  };

  // Build full path with current project/env
  const buildPath = (path) => {
    if (path.startsWith('/') && !path.includes(':')) return path;
    if (!currentProject) return '/';
    if (!currentEnv) return `/${currentProject}`;
    return path
      .replace(':project', currentProject)
      .replace(':env', currentEnv);
  };

  return (
    <>
      {/* Backdrop for mobile */}
      {open && (
        <div
          className="fixed inset-0 bg-black/50 z-40 lg:hidden"
          onClick={onClose}
        />
      )}

      {/* Sidebar */}
      <aside
        className={`fixed lg:static inset-y-0 left-0 z-50 w-64 bg-gray-900 border-r border-gray-800 transform transition-transform duration-200 ease-in-out ${
          open ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'
        }`}
      >
        <div className="flex flex-col h-full">
          {/* Project/Env selector */}
          <ProjectEnvSelector
            projects={projects}
            currentProject={currentProject}
            currentEnv={currentEnv}
            onNavigate={(path) => {
              navigate(path);
              onClose();
            }}
          />

          {/* Navigation */}
          <nav className="flex-1 overflow-y-auto py-4">
            <ul className="space-y-1 px-3">
              {navItems.map((item) => {
                const path = buildPath(item.path);
                const Icon = item.icon;
                const active = isActive(path);

                return (
                  <li key={item.id}>
                    <Link
                      to={path}
                      onClick={onClose}
                      className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
                        active
                          ? 'bg-blue-600/20 text-blue-400'
                          : 'text-gray-400 hover:text-white hover:bg-gray-800'
                      }`}
                    >
                      {Icon && <Icon size={18} />}
                      {item.label}
                    </Link>

                    {/* Sub-items */}
                    {item.children && active && (
                      <ul className="ml-6 mt-1 space-y-1">
                        {item.children.map((child) => {
                          const childPath = buildPath(child.path);
                          const ChildIcon = child.icon;
                          return (
                            <li key={child.id}>
                              <Link
                                to={childPath}
                                onClick={onClose}
                                className={`flex items-center gap-2 px-3 py-1.5 rounded text-xs ${
                                  location.pathname === childPath
                                    ? 'text-blue-400'
                                    : 'text-gray-500 hover:text-gray-300'
                                }`}
                              >
                                {ChildIcon && <ChildIcon size={14} />}
                                {child.label}
                              </Link>
                            </li>
                          );
                        })}
                      </ul>
                    )}
                  </li>
                );
              })}
            </ul>
          </nav>
        </div>
      </aside>
    </>
  );
}

/**
 * Main Shell component
 */
export function Shell({ children, onRefresh, refreshing = false, lastUpdated }) {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const config = useConfig();
  const location = useLocation();
  const { project: currentProject, environment: currentEnv } = useRouteParams();

  // Close sidebar on route change (mobile)
  useEffect(() => {
    setSidebarOpen(false);
  }, [location.pathname]);

  const handleRefresh = useCallback(() => {
    onRefresh?.();
  }, [onRefresh]);

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100">
      <Header
        onToggleSidebar={() => setSidebarOpen(!sidebarOpen)}
        sidebarOpen={sidebarOpen}
        onRefresh={handleRefresh}
        refreshing={refreshing}
        lastUpdated={lastUpdated}
        currentProject={currentProject}
        currentEnv={currentEnv}
      />

      <div className="flex">
        <Sidebar
          open={sidebarOpen}
          onClose={() => setSidebarOpen(false)}
          projects={config?.projects}
        />

        <main className="flex-1 min-h-[calc(100vh-57px)] overflow-x-hidden">
          {children}
        </main>
      </div>
    </div>
  );
}

export default Shell;
