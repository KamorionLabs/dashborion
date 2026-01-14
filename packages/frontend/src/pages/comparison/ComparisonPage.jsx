/**
 * ComparisonPage - Environment comparison view
 *
 * Displays side-by-side comparison between source and destination environments.
 * Route: /:project/comparison/:sourceEnv/:destEnv
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { ArrowLeftRight, RefreshCw, ChevronDown, AlertCircle, Loader2, Clock, LayoutGrid, List, GitBranch, Eye, EyeOff } from 'lucide-react';
import { useConfig } from '../../ConfigContext';
import { fetchWithRetry } from '../../utils/fetch';
import HeroSummary from '../../components/comparison/HeroSummary';
import ComparisonCard from '../../components/comparison/ComparisonCard';
import ComparisonDetailPanel from '../../components/comparison/ComparisonDetailPanel';
import SimpleView from '../../components/comparison/SimpleView';
import ReadinessView from '../../components/comparison/ReadinessView';

// View modes
const VIEW_MODES = {
  simple: { id: 'simple', label: 'Simple', icon: LayoutGrid, description: 'Simplified view' },
  technical: { id: 'technical', label: 'Technical', icon: List, description: 'Detailed view' },
  readiness: { id: 'readiness', label: 'Readiness', icon: GitBranch, description: 'Environment status' },
};

/**
 * View Mode Selector
 */
function ViewSelector({ currentView, onChange }) {
  return (
    <div className="flex items-center gap-1 p-1 bg-gray-800 rounded-lg border border-gray-700">
      {Object.values(VIEW_MODES).map((mode) => {
        const Icon = mode.icon;
        const isActive = currentView === mode.id;
        return (
          <button
            key={mode.id}
            onClick={() => onChange(mode.id)}
            title={mode.description}
            className={`
              flex items-center gap-2 px-3 py-1.5 rounded-md text-sm transition-all
              ${isActive
                ? 'bg-blue-600 text-white'
                : 'text-gray-400 hover:text-gray-200 hover:bg-gray-700'}
            `}
          >
            <Icon className="w-4 h-4" />
            <span className="hidden sm:inline">{mode.label}</span>
          </button>
        );
      })}
    </div>
  );
}

/**
 * Execution Status Banner
 * Shows when comparison is running or has recently completed
 */
function ExecutionStatusBanner({ status, startedAt, onRefreshData }) {
  if (!status || status === 'idle') return null;

  const isRunning = status === 'running';
  const elapsedTime = startedAt ? Math.round((Date.now() - new Date(startedAt).getTime()) / 1000) : 0;

  return (
    <div className={`
      flex items-center gap-3 px-4 py-3 rounded-lg mb-4
      ${isRunning ? 'bg-blue-900/30 border border-blue-700' : 'bg-green-900/30 border border-green-700'}
    `}>
      {isRunning ? (
        <>
          <Loader2 className="w-5 h-5 text-blue-400 animate-spin" />
          <span className="text-blue-300">
            Comparison in progress... {elapsedTime > 0 && `(${elapsedTime}s)`}
          </span>
        </>
      ) : (
        <>
          <Clock className="w-5 h-5 text-green-400" />
          <span className="text-green-300">Comparison completed</span>
          <button
            onClick={onRefreshData}
            className="ml-auto text-sm text-green-400 hover:text-green-300 underline"
          >
            Refresh data
          </button>
        </>
      )}
    </div>
  );
}

/**
 * Environment Selector Dropdown
 */
function EnvSelector({ label, value, options, onChange, disabled }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="relative">
      <label className="block text-xs text-gray-500 mb-1">{label}</label>
      <button
        onClick={() => !disabled && setOpen(!open)}
        disabled={disabled}
        className={`
          flex items-center justify-between gap-2 px-3 py-2 min-w-[180px]
          bg-gray-800 border border-gray-700 rounded-lg
          text-sm text-gray-200
          ${disabled ? 'opacity-50 cursor-not-allowed' : 'hover:border-gray-600 cursor-pointer'}
        `}
      >
        <span>{options.find(o => o.value === value)?.label || value}</span>
        <ChevronDown className={`w-4 h-4 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div className="absolute top-full left-0 mt-1 w-full bg-gray-800 border border-gray-700 rounded-lg shadow-xl z-50 max-h-60 overflow-auto">
            {options.map((option) => (
              <button
                key={option.value}
                onClick={() => {
                  onChange(option.value);
                  setOpen(false);
                }}
                className={`
                  w-full px-3 py-2 text-left text-sm
                  ${option.value === value ? 'bg-blue-600 text-white' : 'text-gray-300 hover:bg-gray-700'}
                `}
              >
                {option.label}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

/**
 * Feature disabled message
 */
function FeatureDisabled() {
  const navigate = useNavigate();
  const { project } = useParams();

  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] text-center">
      <AlertCircle className="w-16 h-16 text-gray-600 mb-4" />
      <h2 className="text-xl font-semibold text-gray-300 mb-2">Comparison Not Available</h2>
      <p className="text-gray-500 mb-6 max-w-md">
        Environment comparison is not enabled for this project.
        Contact your administrator to enable this feature.
      </p>
      <button
        onClick={() => navigate(`/${project}`)}
        className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg text-sm"
      >
        Back to Dashboard
      </button>
    </div>
  );
}

/**
 * Main Comparison Page
 */
export default function ComparisonPage() {
  const { project, sourceEnv, destEnv } = useParams();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const config = useConfig();

  // View mode from URL or default to 'simple'
  const viewMode = searchParams.get('view') || 'simple';
  const setViewMode = (mode) => {
    setSearchParams({ view: mode });
  };

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [comparisonData, setComparisonData] = useState(null);
  const [comparisonConfig, setComparisonConfig] = useState(null);
  const [selectedCheckType, setSelectedCheckType] = useState(null);
  const [executionStatus, setExecutionStatus] = useState(null);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [hidePending, setHidePending] = useState(true); // Hide checks without data by default
  const pollIntervalRef = useRef(null);

  // Check if comparison feature is enabled (opt-in: must be explicitly true)
  const projectConfig = config.projects?.[project];
  const projectFeatures = projectConfig?.features || {};
  const isEnabled = projectFeatures.comparison ?? config.features?.comparison ?? false;

  // Get available environments for this project
  // Handle both array format ["env1", "env2"] and object format {env1: {...}, env2: {...}}
  const environments = (() => {
    const envs = projectConfig?.environments;
    if (!envs) return [];

    if (Array.isArray(envs)) {
      // Array format: ["staging", "production"]
      return envs.map(env => ({
        value: typeof env === 'string' ? env : env.id || env.name,
        label: typeof env === 'string' ? env : env.displayName || env.name || env.id,
      }));
    } else {
      // Object format: { staging: { displayName: "Staging" }, ... }
      return Object.entries(envs).map(([key, env]) => ({
        value: key,
        label: typeof env === 'string' ? env : env.displayName || key,
      }));
    }
  })();

  // Fetch comparison config
  const fetchConfig = useCallback(async () => {
    try {
      const response = await fetchWithRetry(`/api/${project}/comparison/config`);
      if (response.ok) {
        const data = await response.json();
        setComparisonConfig(data);
      }
    } catch (err) {
      console.error('Failed to fetch comparison config:', err);
    }
  }, [project]);

  // Refs for functions to avoid circular dependencies
  const fetchDataRef = useRef(null);
  const startPollingRef = useRef(null);

  const stopPolling = useCallback(() => {
    if (pollIntervalRef.current) {
      clearInterval(pollIntervalRef.current);
      pollIntervalRef.current = null;
    }
  }, []);

  // Fetch comparison data
  const fetchData = useCallback(async (showLoading = true) => {
    if (!sourceEnv || !destEnv) return;

    if (showLoading) setLoading(true);
    setError(null);

    try {
      const response = await fetchWithRetry(
        `/api/${project}/comparison/${sourceEnv}/${destEnv}/summary`
      );

      if (!response.ok) {
        const err = await response.json();
        throw new Error(err.error || 'Failed to fetch comparison data');
      }

      const data = await response.json();
      setComparisonData(data);

      // Update execution status from response
      if (data.executionStatus) {
        setExecutionStatus(data.executionStatus);
      }

      // Start polling if execution is running
      if (data.executionStatus?.status === 'running') {
        startPollingRef.current?.();
      } else {
        stopPolling();
      }

      return data;
    } catch (err) {
      setError(err.message);
      return null;
    } finally {
      setLoading(false);
    }
  }, [project, sourceEnv, destEnv, stopPolling]);

  // Store ref
  fetchDataRef.current = fetchData;

  // Trigger comparison refresh
  const triggerRefresh = useCallback(async (wait = false) => {
    if (!sourceEnv || !destEnv) return;

    setIsRefreshing(true);
    setExecutionStatus({ status: 'running', startedAt: new Date().toISOString() });

    try {
      const response = await fetchWithRetry(
        `/api/${project}/comparison/${sourceEnv}/${destEnv}/trigger${wait ? '?wait=true' : ''}`,
        { method: 'POST' }
      );

      const result = await response.json();

      if (result.status === 'already_running') {
        setExecutionStatus({
          status: 'running',
          startedAt: result.startedAt,
          executionArn: result.executionArn,
        });
        startPollingRef.current?.();
      } else if (result.status === 'started') {
        setExecutionStatus({
          status: 'running',
          startedAt: result.startedAt,
          executionArn: result.executionArn,
        });
        startPollingRef.current?.();
      } else if (result.status === 'succeeded') {
        setExecutionStatus({ status: 'succeeded' });
        fetchDataRef.current?.(false);
      } else if (result.status === 'error' || result.status === 'failed') {
        setExecutionStatus({
          status: 'failed',
          error: result.message || result.error,
        });
        setError(result.message || result.error);
      }
    } catch (err) {
      setError(err.message);
      setExecutionStatus({ status: 'failed', error: err.message });
    } finally {
      setIsRefreshing(false);
    }
  }, [project, sourceEnv, destEnv]);

  // Polling for execution status
  const startPolling = useCallback(() => {
    if (pollIntervalRef.current) return;

    pollIntervalRef.current = setInterval(async () => {
      try {
        const response = await fetchWithRetry(
          `/api/${project}/comparison/${sourceEnv}/${destEnv}/status`
        );
        const status = await response.json();

        setExecutionStatus(status);

        if (status.status !== 'running') {
          stopPolling();
          if (status.status === 'succeeded') {
            fetchDataRef.current?.(false);
          }
        }
      } catch (err) {
        console.error('Failed to poll status:', err);
      }
    }, 3000);
  }, [project, sourceEnv, destEnv, stopPolling]);

  // Store ref
  startPollingRef.current = startPolling;

  // Auto-refresh effect - triggers when data is fetched and shouldAutoRefresh is true
  useEffect(() => {
    if (comparisonData?.shouldAutoRefresh &&
        executionStatus?.status !== 'running' &&
        !isRefreshing) {
      console.log('[ComparisonPage] Data is stale, triggering auto-refresh...');
      triggerRefresh(false);
    }
  }, [comparisonData?.shouldAutoRefresh, executionStatus?.status, isRefreshing, triggerRefresh]);

  // Cleanup polling on unmount
  useEffect(() => {
    return () => stopPolling();
  }, [stopPolling]);

  // Initial load
  useEffect(() => {
    fetchConfig();
  }, [fetchConfig]);

  useEffect(() => {
    if (sourceEnv && destEnv) {
      fetchData();
    } else {
      setLoading(false);
    }
  }, [sourceEnv, destEnv, fetchData]);

  // Find matching destination for a source using configured pairs
  const findMatchingDest = (source) => {
    if (!source || !comparisonConfig?.pairs) return null;
    // Find a pair where this source is the source env
    const pair = comparisonConfig.pairs.find(p => p.source?.env === source);
    return pair?.destination?.env || null;
  };

  // Handle environment change
  const handleSourceChange = (newSource) => {
    const matchingDest = findMatchingDest(newSource) || destEnv || environments[1]?.value || '';
    navigate(`/${project}/comparison/${newSource}/${matchingDest}`);
  };

  const handleDestChange = (newDest) => {
    navigate(`/${project}/comparison/${sourceEnv || environments[0]?.value || ''}/${newDest}`);
  };

  // If feature is disabled
  if (!isEnabled) {
    return <FeatureDisabled />;
  }

  // Filter and group items by category
  const filteredItems = comparisonData?.items?.filter((item) => {
    if (hidePending && item.status === 'pending') return false;
    return true;
  }) || [];

  const groupedItems = filteredItems.reduce((acc, item) => {
    const cat = item.category || 'other';
    if (!acc[cat]) acc[cat] = [];
    acc[cat].push(item);
    return acc;
  }, {});

  // Count pending items for display
  const pendingCount = comparisonData?.items?.filter((i) => i.status === 'pending').length || 0;
  const totalCount = comparisonData?.items?.length || 0;

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div className="flex items-center gap-4">
          <div className="p-3 bg-blue-600/20 rounded-xl">
            <ArrowLeftRight className="w-6 h-6 text-blue-400" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-gray-100">Environment Comparison</h1>
            <p className="text-gray-500 text-sm">Compare configurations between environments</p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <ViewSelector currentView={viewMode} onChange={setViewMode} />
          <button
            onClick={() => triggerRefresh(false)}
            disabled={loading || isRefreshing || executionStatus?.status === 'running' || !sourceEnv || !destEnv}
            className="flex items-center gap-2 px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg text-sm disabled:opacity-50"
          >
            <RefreshCw className={`w-4 h-4 ${loading || isRefreshing || executionStatus?.status === 'running' ? 'animate-spin' : ''}`} />
            {executionStatus?.status === 'running' ? 'Refreshing...' : 'Refresh'}
          </button>
        </div>
      </div>

      {/* Environment Selectors */}
      <div className="flex items-end gap-4 p-4 bg-gray-800/50 rounded-xl border border-gray-700">
        <EnvSelector
          label="Source Environment"
          value={sourceEnv || ''}
          options={environments}
          onChange={handleSourceChange}
        />

        <div className="pb-2">
          <ArrowLeftRight className="w-5 h-5 text-gray-500" />
        </div>

        <EnvSelector
          label="Destination Environment"
          value={destEnv || ''}
          options={environments}
          onChange={handleDestChange}
        />

        {/* Quick pair selectors from config */}
        {comparisonConfig?.pairs?.length > 0 && (
          <div className="ml-auto flex items-center gap-2">
            <span className="text-xs text-gray-500">Quick:</span>
            {comparisonConfig.pairs.map((pair) => (
              <button
                key={pair.id}
                onClick={() => navigate(`/${project}/comparison/${pair.source.env}/${pair.destination.env}`)}
                className={`
                  px-3 py-1.5 text-xs rounded-lg border
                  ${sourceEnv === pair.source.env && destEnv === pair.destination.env
                    ? 'bg-blue-600 border-blue-500 text-white'
                    : 'bg-gray-800 border-gray-700 text-gray-400 hover:border-gray-600'}
                `}
              >
                {pair.label}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Execution Status Banner */}
      <ExecutionStatusBanner
        status={executionStatus?.status}
        startedAt={executionStatus?.startedAt}
        onRefreshData={() => fetchData(false)}
      />

      {/* Content */}
      {!sourceEnv || !destEnv ? (
        <div className="text-center py-12 text-gray-500">
          Select source and destination environments to compare
        </div>
      ) : loading ? (
        <div className="flex items-center justify-center py-12">
          <RefreshCw className="w-8 h-8 text-blue-500 animate-spin" />
        </div>
      ) : error ? (
        <div className="text-center py-12">
          <AlertCircle className="w-12 h-12 text-red-500 mx-auto mb-4" />
          <p className="text-red-400">{error}</p>
          <button
            onClick={() => triggerRefresh(false)}
            className="mt-4 px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg text-sm"
          >
            Retry
          </button>
        </div>
      ) : comparisonData ? (
        <>
          {/* View Content based on mode */}
          {viewMode === 'simple' && (
            <SimpleView
              data={comparisonData}
              onSwitchToTechnical={() => setViewMode('technical')}
            />
          )}

          {viewMode === 'technical' && (
            <>
              {/* Hero Summary */}
              <HeroSummary
                sourceLabel={comparisonData.sourceLabel}
                destinationLabel={comparisonData.destinationLabel}
                overallStatus={comparisonData.overallStatus}
                overallSyncPercentage={comparisonData.overallSyncPercentage}
                categories={comparisonData.categories}
                lastUpdated={comparisonData.lastUpdated}
                totalChecks={comparisonData.totalChecks}
                completedChecks={comparisonData.completedChecks}
                pendingChecks={comparisonData.pendingChecks}
              />

              {/* Filter Bar */}
              {pendingCount > 0 && (
                <div className="flex items-center justify-between p-3 bg-gray-800/50 rounded-lg border border-gray-700">
                  <div className="text-sm text-gray-400">
                    Showing <span className="font-medium text-gray-200">{filteredItems.length}</span> of{' '}
                    <span className="font-medium text-gray-200">{totalCount}</span> checks
                    {hidePending && pendingCount > 0 && (
                      <span className="ml-1 text-gray-500">
                        ({pendingCount} pending hidden)
                      </span>
                    )}
                  </div>
                  <button
                    onClick={() => setHidePending(!hidePending)}
                    className={`
                      flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm transition-all
                      ${hidePending
                        ? 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                        : 'bg-blue-600/20 text-blue-400 border border-blue-500/30 hover:bg-blue-600/30'}
                    `}
                  >
                    {hidePending ? (
                      <>
                        <Eye className="w-4 h-4" />
                        Show pending
                      </>
                    ) : (
                      <>
                        <EyeOff className="w-4 h-4" />
                        Hide pending
                      </>
                    )}
                  </button>
                </div>
              )}

              {/* Comparison Cards by Category */}
              {Object.entries(groupedItems).map(([category, items]) => (
                <div key={category} className="space-y-4">
                  <h3 className="text-lg font-semibold text-gray-300 capitalize flex items-center gap-2">
                    {category}
                    <span className="text-sm font-normal text-gray-500">
                      ({items.filter(i => i.status === 'synced').length}/{items.length} synced)
                    </span>
                  </h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                    {items.map((item) => (
                      <ComparisonCard
                        key={item.checkType}
                        checkType={item.checkType}
                        label={item.label}
                        status={item.status}
                        sourceCount={item.sourceCount}
                        destinationCount={item.destinationCount}
                        syncedCount={item.syncedCount}
                        differsCount={item.differsCount}
                        onlySourceCount={item.onlySourceCount}
                        onlyDestinationCount={item.onlyDestinationCount}
                        syncPercentage={item.syncPercentage}
                        lastUpdated={item.lastUpdated}
                        sourceLabel={comparisonData.sourceLabel}
                        destinationLabel={comparisonData.destinationLabel}
                        onClick={() => setSelectedCheckType(item.checkType)}
                      />
                    ))}
                  </div>
                </div>
              ))}
            </>
          )}

          {viewMode === 'readiness' && (
            <ReadinessView
              project={project}
              sourceEnv={sourceEnv}
              destEnv={destEnv}
              comparisonData={comparisonData}
              config={config.comparison?.readiness || projectConfig?.comparison?.readiness}
            />
          )}
        </>
      ) : null}

      {/* Detail Panel */}
      <ComparisonDetailPanel
        isOpen={!!selectedCheckType}
        onClose={() => setSelectedCheckType(null)}
        project={project}
        sourceEnv={sourceEnv}
        destEnv={destEnv}
        checkType={selectedCheckType}
        sourceLabel={comparisonData?.sourceLabel || 'Source'}
        destinationLabel={comparisonData?.destinationLabel || 'Destination'}
      />
    </div>
  );
}
