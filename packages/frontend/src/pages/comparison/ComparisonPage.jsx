/**
 * ComparisonPage - Environment comparison view
 *
 * Displays side-by-side comparison between source and destination environments.
 * Route: /:project/comparison/:sourceEnv/:destEnv
 */

import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeftRight, RefreshCw, ChevronDown, AlertCircle } from 'lucide-react';
import { useConfig } from '../../ConfigContext';
import { fetchWithRetry } from '../../utils/fetch';
import HeroSummary from '../../components/comparison/HeroSummary';
import ComparisonCard from '../../components/comparison/ComparisonCard';
import ComparisonDetailPanel from '../../components/comparison/ComparisonDetailPanel';

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
  const config = useConfig();

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [comparisonData, setComparisonData] = useState(null);
  const [comparisonConfig, setComparisonConfig] = useState(null);
  const [selectedCheckType, setSelectedCheckType] = useState(null);

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

  // Fetch comparison data
  const fetchData = useCallback(async () => {
    if (!sourceEnv || !destEnv) return;

    setLoading(true);
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
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [project, sourceEnv, destEnv]);

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

  // Group items by category
  const groupedItems = comparisonData?.items?.reduce((acc, item) => {
    const cat = item.category || 'other';
    if (!acc[cat]) acc[cat] = [];
    acc[cat].push(item);
    return acc;
  }, {}) || {};

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <div className="p-3 bg-blue-600/20 rounded-xl">
            <ArrowLeftRight className="w-6 h-6 text-blue-400" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-gray-100">Environment Comparison</h1>
            <p className="text-gray-500 text-sm">Compare configurations between environments</p>
          </div>
        </div>

        <button
          onClick={fetchData}
          disabled={loading || !sourceEnv || !destEnv}
          className="flex items-center gap-2 px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg text-sm disabled:opacity-50"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
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
            onClick={fetchData}
            className="mt-4 px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg text-sm"
          >
            Retry
          </button>
        </div>
      ) : comparisonData ? (
        <>
          {/* Hero Summary */}
          <HeroSummary
            sourceLabel={comparisonData.sourceLabel}
            destinationLabel={comparisonData.destinationLabel}
            overallStatus={comparisonData.overallStatus}
            overallSyncPercentage={comparisonData.overallSyncPercentage}
            categories={comparisonData.categories}
            lastUpdated={comparisonData.lastUpdated}
          />

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
