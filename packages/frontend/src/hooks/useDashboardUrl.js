import { useCallback, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'

/**
 * Hook to sync dashboard state with URL search params
 * Enables deep-linking for views, services, resources, logs, events
 */
export function useDashboardUrl() {
  const [searchParams, setSearchParams] = useSearchParams()

  // Read current values from URL
  const urlState = useMemo(() => ({
    // View - for future use (simple, network, routing)
    view: searchParams.get('view') || 'simple',

    // Selected service (ECS)
    service: searchParams.get('service') || null,

    // Selected infrastructure resource
    resource: searchParams.get('resource') || null,
    resourceId: searchParams.get('id') || null,

    // Logs panel tabs (comma-separated service names)
    logs: searchParams.get('logs')?.split(',').filter(Boolean) || [],

    // Events panel state
    events: searchParams.get('events') === 'true',
    hours: parseInt(searchParams.get('hours'), 10) || 24,
    types: searchParams.get('types')?.split(',').filter(Boolean) || null,

    // Pipeline details (service name)
    pipeline: searchParams.get('pipeline') || null,

    // Task details
    task: searchParams.get('task') || null,
  }), [searchParams])

  // Update URL params helper - merges with existing and removes null/undefined
  const updateParams = useCallback((updates, options = {}) => {
    setSearchParams(prev => {
      const newParams = new URLSearchParams(prev)

      Object.entries(updates).forEach(([key, value]) => {
        if (value === null || value === undefined || value === '' || value === false) {
          newParams.delete(key)
        } else if (Array.isArray(value)) {
          if (value.length > 0) {
            newParams.set(key, value.join(','))
          } else {
            newParams.delete(key)
          }
        } else if (value === true) {
          newParams.set(key, 'true')
        } else {
          newParams.set(key, String(value))
        }
      })

      return newParams
    }, { replace: options.replace !== false }) // Default to replace to avoid history pollution
  }, [setSearchParams])

  // Clear all params related to selection
  const clearSelection = useCallback(() => {
    updateParams({
      service: null,
      resource: null,
      id: null,
      pipeline: null,
      task: null,
    })
  }, [updateParams])

  // Set view (simple, network, routing) - clears selection
  const setView = useCallback((view) => {
    updateParams({
      view: view === 'simple' ? null : view, // 'simple' is default, no need to show in URL
      service: null,
      resource: null,
      id: null,
      pipeline: null,
      task: null,
    })
  }, [updateParams])

  // Select a service (ECS) - clears resource/pipeline selection
  const selectService = useCallback((serviceName, taskId = null) => {
    updateParams({
      service: serviceName,
      task: taskId,
      resource: null,
      id: null,
      pipeline: null,
    })
  }, [updateParams])

  // Select an infrastructure resource - clears service/pipeline selection
  const selectResource = useCallback((resourceType, resourceId) => {
    updateParams({
      resource: resourceType,
      id: resourceId,
      service: null,
      pipeline: null,
      task: null,
    })
  }, [updateParams])

  // Select a pipeline - clears service/resource selection
  const selectPipeline = useCallback((serviceName) => {
    updateParams({
      pipeline: serviceName,
      service: null,
      resource: null,
      id: null,
      task: null,
    })
  }, [updateParams])

  // Open logs for services (adds to existing)
  const openLogs = useCallback((services) => {
    const current = urlState.logs
    const merged = [...new Set([...current, ...services])]
    updateParams({ logs: merged })
  }, [updateParams, urlState.logs])

  // Close logs for a service
  const closeLogs = useCallback((service) => {
    const filtered = urlState.logs.filter(s => s !== service)
    updateParams({ logs: filtered })
  }, [updateParams, urlState.logs])

  // Close all logs
  const closeAllLogs = useCallback(() => {
    updateParams({ logs: null })
  }, [updateParams])

  // Toggle events panel
  const setEventsVisible = useCallback((visible) => {
    updateParams({ events: visible || null })
  }, [updateParams])

  // Set events hours filter
  const setEventsHours = useCallback((hours) => {
    updateParams({ hours: hours === 24 ? null : hours }) // 24 is default
  }, [updateParams])

  // Set events type filter
  const setEventsTypes = useCallback((types) => {
    updateParams({ types: types })
  }, [updateParams])

  return {
    // Current state from URL
    ...urlState,

    // Setters
    setView,
    selectService,
    selectResource,
    selectPipeline,
    clearSelection,
    openLogs,
    closeLogs,
    closeAllLogs,
    setEventsVisible,
    setEventsHours,
    setEventsTypes,

    // Raw update for custom cases
    updateParams,
  }
}

export default useDashboardUrl
