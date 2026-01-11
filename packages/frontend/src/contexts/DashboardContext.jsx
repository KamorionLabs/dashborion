/**
 * Dashboard Context
 *
 * Provides shared state between Shell (header) and dashboard content.
 * Manages refresh state, auto-refresh toggle, and last updated timestamp.
 */

import { createContext, useContext, useState, useCallback, useRef, useEffect } from 'react';

const DashboardContext = createContext(null);

export function DashboardProvider({ children }) {
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [lastUpdated, setLastUpdated] = useState(null);

  // Ref to store the refresh callback from the dashboard component
  const refreshCallbackRef = useRef(null);

  // Register refresh callback from dashboard component
  const registerRefreshCallback = useCallback((callback) => {
    refreshCallbackRef.current = callback;
  }, []);

  // Trigger refresh - called from Shell header
  const triggerRefresh = useCallback(async () => {
    if (refreshCallbackRef.current) {
      setRefreshing(true);
      try {
        await refreshCallbackRef.current();
      } finally {
        setRefreshing(false);
        setLastUpdated(new Date());
      }
    }
  }, []);

  // Update last updated timestamp
  const updateLastUpdated = useCallback(() => {
    setLastUpdated(new Date());
  }, []);

  // Set refreshing state
  const setRefreshingState = useCallback((state) => {
    setRefreshing(state);
  }, []);

  const value = {
    autoRefresh,
    setAutoRefresh,
    refreshing,
    setRefreshing: setRefreshingState,
    lastUpdated,
    setLastUpdated: updateLastUpdated,
    triggerRefresh,
    registerRefreshCallback,
  };

  return (
    <DashboardContext.Provider value={value}>
      {children}
    </DashboardContext.Provider>
  );
}

export function useDashboard() {
  const context = useContext(DashboardContext);
  if (!context) {
    throw new Error('useDashboard must be used within a DashboardProvider');
  }
  return context;
}

export default DashboardContext;
