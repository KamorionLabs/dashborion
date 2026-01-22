/**
 * Admin Layout
 *
 * Layout for admin pages with sidebar navigation.
 */
import { NavLink, Outlet } from 'react-router-dom';
import {
  Settings,
  FolderKanban,
  Server,
  Cloud,
  GitBranch,
  LayoutDashboard,
  ChevronLeft,
} from 'lucide-react';

const navItems = [
  { path: '/admin/config', label: 'Overview', icon: LayoutDashboard, exact: true },
  { path: '/admin/config/projects', label: 'Projects', icon: FolderKanban },
  { path: '/admin/config/accounts', label: 'AWS Accounts', icon: Cloud },
  { path: '/admin/config/clusters', label: 'Clusters', icon: Server },
  { path: '/admin/config/ci-providers', label: 'CI Providers', icon: GitBranch },
  { path: '/admin/config/settings', label: 'Settings', icon: Settings },
];

export default function AdminLayout() {
  return (
    <div className="flex h-full min-h-screen bg-gray-950">
      {/* Sidebar */}
      <aside className="w-64 bg-gray-900 border-r border-gray-800 flex flex-col">
        {/* Header */}
        <div className="p-4 border-b border-gray-800">
          <NavLink
            to="/"
            className="flex items-center gap-2 text-gray-400 hover:text-white text-sm"
          >
            <ChevronLeft size={16} />
            Back to Dashboard
          </NavLink>
          <h1 className="text-lg font-semibold text-white mt-3">
            Config Registry
          </h1>
          <p className="text-sm text-gray-500">Manage your configuration</p>
        </div>

        {/* Navigation */}
        <nav className="flex-1 p-4 space-y-1">
          {navItems.map(({ path, label, icon: Icon, exact }) => (
            <NavLink
              key={path}
              to={path}
              end={exact}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
                  isActive
                    ? 'bg-blue-600/20 text-blue-400'
                    : 'text-gray-400 hover:text-white hover:bg-gray-800'
                }`
              }
            >
              <Icon size={18} />
              {label}
            </NavLink>
          ))}
        </nav>

        {/* Footer */}
        <div className="p-4 border-t border-gray-800 text-xs text-gray-600">
          Config Registry v2.1
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-auto">
        <Outlet />
      </main>
    </div>
  );
}
