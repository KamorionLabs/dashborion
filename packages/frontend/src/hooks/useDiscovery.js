/**
 * useDiscovery Hook
 *
 * Hook for discovering AWS resources via the Discovery API.
 * Note: Cache will be implemented server-side (DynamoDB) later.
 * See docs/TODO-discovery-cache.md
 */
import { useState, useCallback, useRef, useEffect } from 'react';
import { fetchWithRetry } from '../utils/fetch';

/**
 * Hook for discovering AWS resources
 *
 * @param {string} accountId - AWS account ID
 * @param {string} resourceType - Resource type (vpc, eks, rds, etc.)
 * @param {object} options - Additional options (tags, vpc, region, cluster, namespace, autoDiscover)
 * @returns {object} { resources, loading, error, discover, refresh }
 */
export function useDiscovery(accountId, resourceType, options = {}) {
  const [resources, setResources] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const abortControllerRef = useRef(null);

  const discover = useCallback(async () => {
    if (!accountId || !resourceType) {
      return [];
    }

    // Abort previous request if any
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    abortControllerRef.current = new AbortController();

    setLoading(true);
    setError(null);

    try {
      // Build query params
      const params = new URLSearchParams();
      if (options.region) params.set('region', options.region);
      if (options.vpc) params.set('vpc', options.vpc);
      if (options.tags) params.set('tags', options.tags);
      if (options.cluster) params.set('cluster', options.cluster);
      if (options.namespace) params.set('namespace', options.namespace);

      const queryString = params.toString();
      const url = `/api/config/discovery/${accountId}/${resourceType}${queryString ? `?${queryString}` : ''}`;

      const response = await fetchWithRetry(url, {
        signal: abortControllerRef.current.signal,
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.message || `Discovery failed: ${response.status}`);
      }

      const data = await response.json();
      const result = data.resources || [];

      setResources(result);
      return result;
    } catch (err) {
      if (err.name === 'AbortError') {
        return []; // Request was aborted, ignore
      }
      console.error(`Discovery error for ${resourceType}:`, err);
      setError(err.message);
      return [];
    } finally {
      setLoading(false);
    }
  }, [accountId, resourceType, options.region, options.vpc, options.tags, options.cluster, options.namespace]);

  // Auto-discover on mount if requested
  useEffect(() => {
    if (options.autoDiscover && accountId && resourceType) {
      discover();
    }
  }, [options.autoDiscover, accountId, resourceType, discover]);

  return {
    resources,
    loading,
    error,
    discover,
    refresh: discover,
  };
}

/**
 * Hook for testing connection to an AWS account
 *
 * @param {string} accountId - AWS account ID
 * @returns {object} { result, loading, error, testConnection }
 */
export function useTestConnection(accountId) {
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const testConnection = useCallback(async (region) => {
    if (!accountId) {
      setError('Account ID is required');
      return null;
    }

    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const params = new URLSearchParams();
      if (region) params.set('region', region);

      const queryString = params.toString();
      const url = `/api/config/discovery/${accountId}/test${queryString ? `?${queryString}` : ''}`;

      const response = await fetchWithRetry(url);

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.message || `Test failed: ${response.status}`);
      }

      const data = await response.json();
      setResult(data);
      return data;
    } catch (err) {
      console.error('Test connection error:', err);
      setError(err.message);
      setResult({ success: false, error: err.message });
      return { success: false, error: err.message };
    } finally {
      setLoading(false);
    }
  }, [accountId]);

  return {
    result,
    loading,
    error,
    testConnection,
  };
}

export default useDiscovery;
