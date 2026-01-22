/**
 * useAuth Hook - Authentication and Authorization Context
 *
 * Provides user authentication state and permission checking helpers
 * for conditional UI rendering.
 */

import { useState, useEffect, useCallback, createContext, useContext } from 'react';
import { fetchWithRetry, clearAuthTokens, storeToken, refreshAccessToken } from '../utils/fetch';

// Role hierarchy for permission checks
const ROLE_HIERARCHY = {
  admin: 3,
  operator: 2,
  viewer: 1,
};

// Action to minimum role mapping
const ACTION_ROLES = {
  read: 'viewer',
  deploy: 'operator',
  scale: 'operator',
  restart: 'operator',
  invalidate: 'operator',
  'rds-control': 'admin',
  'manage-permissions': 'admin',
};

/**
 * Check if role level is sufficient for action
 */
function roleCanPerform(userRole, action) {
  const requiredRole = ACTION_ROLES[action] || 'admin';
  const userLevel = ROLE_HIERARCHY[userRole] || 0;
  const requiredLevel = ROLE_HIERARCHY[requiredRole] || 0;
  return userLevel >= requiredLevel;
}

/**
 * Auth Context
 */
const AuthContext = createContext(null);

/**
 * Auth Provider Component
 */
export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [permissions, setPermissions] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);

  // Fetch user info on mount
  useEffect(() => {
    async function fetchUserInfo() {
      try {
        setIsLoading(true);

        // Check if we already have a valid token
        const existingToken = localStorage.getItem('dashborion_token');

        if (existingToken) {
          // We have a token - use direct API
          const response = await fetchWithRetry('/api/auth/me');

          if (response.ok) {
            const data = await response.json();
            setUser(data.user);
            setPermissions(data.permissions || []);
          } else if (response.status === 401 || response.status === 403) {
            // Token expired/invalid or unauthorized - clear and retry with cookie
            clearAuthTokens();
            await tryAuthViaCookie();
          } else {
            throw new Error(`Failed to fetch user info: ${response.status}`);
          }
        } else {
          // No token - try SSO cookie auth
          await tryAuthViaCookie();
        }
      } catch (err) {
        console.error('Auth error:', err);
        setError(err.message);
        setUser(null);
        setPermissions([]);
      } finally {
        setIsLoading(false);
      }
    }

    /**
     * Try authentication via SSO cookie (cross-origin with credentials)
     */
    async function tryAuthViaCookie() {
      // Use credentials to send SSO cookie to API
      const response = await fetchWithRetry('/api/auth/me', {}, 3, true);

      if (response.ok) {
        const data = await response.json();
        setUser(data.user);
        setPermissions(data.permissions || []);

        // SSO authenticated - exchange for Bearer token
        await exchangeSsoForToken();
      } else if (response.status === 401 || response.status === 403) {
        // Not authenticated (401) or unauthorized (403 from Lambda Authorizer)
        setUser(null);
        setPermissions([]);
      } else {
        throw new Error(`Failed to fetch user info: ${response.status}`);
      }
    }

    /**
     * Exchange SSO session (cookie) for Bearer token
     * This allows direct API calls without sending cookies
     */
    async function exchangeSsoForToken() {
      try {
        // Use credentials to send SSO cookie to API
        const response = await fetchWithRetry('/api/auth/token/issue', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
        }, 3, true);

        if (response.ok) {
          const data = await response.json();
          // Store tokens for direct API access (including expiration time)
          storeToken(data.access_token, data.refresh_token, data.expires_in || 3600, data.user);
          localStorage.setItem('dashborion_auth_method', 'saml');
          console.log('SSO session exchanged for Bearer token');
        } else {
          console.warn('Failed to exchange SSO for token:', response.status);
        }
      } catch (err) {
        console.warn('SSO token exchange failed:', err);
        // Non-fatal - can retry with cookie auth later
      }
    }

    fetchUserInfo();
  }, []);

  /**
   * Check if user has permission for an action on a resource
   */
  const hasPermission = useCallback((action, project, environment = '*', resource = '*') => {
    if (!user) return false;

    for (const perm of permissions) {
      // Check project match
      if (perm.project !== '*' && perm.project !== project) continue;

      // Check environment match
      if (perm.environment !== '*' && perm.environment !== environment) continue;

      // Check resource match
      if (resource !== '*' && !perm.resources.includes('*') && !perm.resources.includes(resource)) continue;

      // Check if role can perform action
      if (roleCanPerform(perm.role, action)) {
        return true;
      }
    }

    return false;
  }, [user, permissions]);

  /**
   * Check if user can view a project/environment
   */
  const canView = useCallback((project, environment = '*', resource = '*') => {
    return hasPermission('read', project, environment, resource);
  }, [hasPermission]);

  /**
   * Check if user can deploy to a project/environment
   */
  const canDeploy = useCallback((project, environment, resource = '*') => {
    return hasPermission('deploy', project, environment, resource);
  }, [hasPermission]);

  /**
   * Check if user can scale services
   */
  const canScale = useCallback((project, environment, resource = '*') => {
    return hasPermission('scale', project, environment, resource);
  }, [hasPermission]);

  /**
   * Check if user has admin access to a project
   */
  const canAdmin = useCallback((project, environment = '*') => {
    if (!user) return false;

    for (const perm of permissions) {
      if (perm.project !== '*' && perm.project !== project) continue;
      if (perm.environment !== '*' && perm.environment !== environment) continue;
      if (perm.role === 'admin') return true;
    }

    return false;
  }, [user, permissions]);

  /**
   * Check if user is a global admin
   */
  const isGlobalAdmin = useCallback(() => {
    if (!user) return false;
    return permissions.some(p => p.project === '*' && p.role === 'admin');
  }, [user, permissions]);

  /**
   * Get user's role for a specific project/environment
   */
  const getRoleFor = useCallback((project, environment = '*') => {
    if (!user) return null;

    let highestRole = null;
    let highestLevel = 0;

    for (const perm of permissions) {
      if (perm.project !== '*' && perm.project !== project) continue;
      if (perm.environment !== '*' && perm.environment !== environment) continue;

      const level = ROLE_HIERARCHY[perm.role] || 0;
      if (level > highestLevel) {
        highestLevel = level;
        highestRole = perm.role;
      }
    }

    return highestRole;
  }, [user, permissions]);

  /**
   * Get all projects user has access to
   */
  const getAccessibleProjects = useCallback(() => {
    if (!user) return [];

    const projects = new Set();
    for (const perm of permissions) {
      if (perm.project === '*') {
        // Has access to all projects - return special marker
        return ['*'];
      }
      projects.add(perm.project);
    }

    return Array.from(projects);
  }, [user, permissions]);

  /**
   * Logout - adapts to auth method (SAML or simple)
   */
  const logout = useCallback(() => {
    const authMethod = localStorage.getItem('dashborion_auth_method');

    // Always clear local tokens (includes auth_method)
    clearAuthTokens();

    if (authMethod === 'saml') {
      // SAML logout - redirect to IdP logout
      window.location.href = '/saml/logout';
    } else {
      // Simple auth - just go to login page
      window.location.href = '/login';
    }
  }, []);

  /**
   * Refresh auth state
   */
  const refresh = useCallback(async () => {
    setIsLoading(true);
    try {
      const response = await fetchWithRetry('/api/auth/me');
      if (response.ok) {
        const data = await response.json();
        setUser(data.user);
        setPermissions(data.permissions || []);
      }
    } catch (err) {
      console.error('Auth refresh error:', err);
    } finally {
      setIsLoading(false);
    }
  }, []);

  const value = {
    // State
    user,
    permissions,
    isLoading,
    error,
    isAuthenticated: !!user,

    // Permission checks
    hasPermission,
    canView,
    canDeploy,
    canScale,
    canAdmin,
    isGlobalAdmin,
    getRoleFor,
    getAccessibleProjects,

    // Actions
    logout,
    refresh,
  };

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
}

/**
 * useAuth Hook
 */
export function useAuth() {
  const context = useContext(AuthContext);

  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }

  return context;
}

/**
 * PermissionGuard Component
 *
 * Conditionally renders children based on permissions.
 */
export function PermissionGuard({
  action,
  project,
  environment = '*',
  resource = '*',
  fallback = null,
  children,
}) {
  const { hasPermission, isLoading } = useAuth();

  if (isLoading) {
    return null; // Or a loading indicator
  }

  if (!hasPermission(action, project, environment, resource)) {
    return fallback;
  }

  return children;
}

/**
 * AdminGuard Component
 *
 * Only renders children if user is admin for the project.
 */
export function AdminGuard({ project, environment = '*', fallback = null, children }) {
  const { canAdmin, isLoading } = useAuth();

  if (isLoading) {
    return null;
  }

  if (!canAdmin(project, environment)) {
    return fallback;
  }

  return children;
}

export default useAuth;
