/**
 * Plugin Context for Dashborion Frontend
 *
 * Provides plugin access throughout the React component tree.
 */

import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { PluginRegistry } from './PluginRegistry';

const PluginContext = createContext(null);

/**
 * Plugin Provider component
 * Wraps the app and provides plugin access to all children
 */
export function PluginProvider({ children, config = {} }) {
  const [initialized, setInitialized] = useState(false);
  const [error, setError] = useState(null);

  // Initialize plugins on mount
  useEffect(() => {
    let mounted = true;

    const init = async () => {
      try {
        await PluginRegistry.initialize(config);
        if (mounted) {
          setInitialized(true);
        }
      } catch (err) {
        console.error('[PluginProvider] Initialization error:', err);
        if (mounted) {
          setError(err);
        }
      }
    };

    init();

    return () => {
      mounted = false;
      PluginRegistry.cleanup();
    };
  }, [config]);

  // Get widgets for a position
  const getWidgets = useCallback((position) => {
    return PluginRegistry.getWidgetsForPosition(position);
  }, []);

  // Get all pages
  const getPages = useCallback(() => {
    return PluginRegistry.getAllPages();
  }, []);

  // Get all nav items
  const getNavItems = useCallback(() => {
    return PluginRegistry.getAllNavItems();
  }, []);

  // Get a specific plugin
  const getPlugin = useCallback((id) => {
    return PluginRegistry.getPlugin(id);
  }, []);

  // Get all plugins
  const getPlugins = useCallback(() => {
    return PluginRegistry.getPlugins();
  }, []);

  // Get detail panel
  const getDetailPanel = useCallback((id) => {
    return PluginRegistry.getDetailPanel(id);
  }, []);

  const value = {
    initialized,
    error,
    getWidgets,
    getPages,
    getNavItems,
    getPlugin,
    getPlugins,
    getDetailPanel,
    registry: PluginRegistry,
  };

  return (
    <PluginContext.Provider value={value}>
      {children}
    </PluginContext.Provider>
  );
}

/**
 * Hook to access plugins
 * @returns {ReturnType<typeof usePluginsInternal>}
 */
export function usePlugins() {
  const context = useContext(PluginContext);

  if (!context) {
    throw new Error('usePlugins must be used within a PluginProvider');
  }

  return context;
}

/**
 * Hook to get widgets for a specific position
 * @param {import('@dashborion/core').WidgetPosition} position
 */
export function useWidgets(position) {
  const { getWidgets, initialized } = usePlugins();
  const [widgets, setWidgets] = useState([]);

  useEffect(() => {
    if (initialized) {
      setWidgets(getWidgets(position));
    }
  }, [initialized, position, getWidgets]);

  return widgets;
}

/**
 * Hook to get all pages from plugins
 */
export function usePluginPages() {
  const { getPages, initialized } = usePlugins();
  const [pages, setPages] = useState([]);

  useEffect(() => {
    if (initialized) {
      setPages(getPages());
    }
  }, [initialized, getPages]);

  return pages;
}

/**
 * Hook to get navigation items from plugins
 */
export function usePluginNav() {
  const { getNavItems, initialized } = usePlugins();
  const [navItems, setNavItems] = useState([]);

  useEffect(() => {
    if (initialized) {
      setNavItems(getNavItems());
    }
  }, [initialized, getNavItems]);

  return navItems;
}

export default PluginContext;
