import { useState, useEffect, useCallback, useRef } from 'react'
import {
  RefreshCw, Server, Clock, ExternalLink, Package,
  CheckCircle, XCircle, Network, X, LogOut, User, Shield
} from 'lucide-react'
// Configuration context
import { useConfig, useConfigHelpers } from './ConfigContext'
// Auth context
import { useAuth, PermissionGuard, AdminGuard } from './hooks/useAuth'
// Utilities
import { fetchWithRetry, sessionExpiredEvent } from './utils'
// Components
import { SessionExpiredModal, MetricsChart, ProjectSelector } from './components/common'
import { TabbedLogsPanel, LogsBottomPanel } from './components/logs'
import { EventsTimelinePanel } from './components/events'
import { BuildPipelineCard, PipelineDetails } from './components/pipelines'
import { InfrastructureDiagram, InfrastructureDetailsPanel } from './components/infrastructure'
import { ServiceDetailsPanel, TaskDetails } from './components/services'

export default function App() {
  // Get configuration from context (loaded by ConfigProvider)
  const appConfig = useConfig()
  const { getAwsConsoleUrl, getCodePipelineConsoleUrl, getServiceName, getDefaultAzs } = useConfigHelpers()

  // Get auth context
  const auth = useAuth()
  const currentProjectId = appConfig.currentProjectId || 'unknown'

  // Derive constants from config
  const ENVIRONMENTS = appConfig.environments || []
  const SERVICES = appConfig.services || []
  const AWS_ACCOUNTS = appConfig.aws?.accounts || {}
  const ENV_COLORS = appConfig.envColors || {}

  // Session expiration state
  const [sessionExpired, setSessionExpired] = useState(false)

  // Listen for session expiration events
  useEffect(() => {
    const handleSessionExpired = () => setSessionExpired(true)
    sessionExpiredEvent.addEventListener('sessionExpired', handleSessionExpired)
    return () => sessionExpiredEvent.removeEventListener('sessionExpired', handleSessionExpired)
  }, [])

  // Handle reconnect - force full page reload to trigger SSO flow
  const handleReconnect = useCallback(() => {
    window.location.reload()
  }, [])

  // Data states - per section
  const [services, setServices] = useState({})
  const [pipelines, setPipelines] = useState({})
  const [images, setImages] = useState({})
  const [metrics, setMetrics] = useState({})
  const [serviceConfig, setServiceConfig] = useState({})
  const [infrastructure, setInfrastructure] = useState({})

  // Loading states - per section
  const [loadingStates, setLoadingStates] = useState({
    services: false,
    pipelines: false,
    images: false,
    infrastructure: false
  })

  // UI states
  const [autoRefresh, setAutoRefresh] = useState(true)
  const [lastUpdated, setLastUpdated] = useState(null)
  const [selectedService, setSelectedService] = useState(null)
  const [serviceDetails, setServiceDetails] = useState(null)
  const [detailsLoading, setDetailsLoading] = useState(false)
  const [selectedInfraEnv, setSelectedInfraEnv] = useState(ENVIRONMENTS[0] || 'staging')
  const [selectedInfraComponent, setSelectedInfraComponent] = useState(null)

  // Bottom logs panel state - supports multiple tabs
  const [bottomLogsTabs, setBottomLogsTabs] = useState([]) // [{ id, env, service, autoTail, type }, ...]
  const [activeBottomTab, setActiveBottomTab] = useState(null) // id of active tab

  // Events timeline panel state
  const [events, setEvents] = useState([])
  const [eventsLoading, setEventsLoading] = useState(false)
  const [eventsPanelVisible, setEventsPanelVisible] = useState(true)
  const [eventsPanelWidth, setEventsPanelWidth] = useState(320)
  const [eventsHours, setEventsHours] = useState(24)
  const [eventsTypeFilter, setEventsTypeFilter] = useState(['build', 'deploy', 'rollback', 'cache_invalidation', 'rds_stop', 'rds_start']) // exclude 'scale' by default
  const [eventsServiceFilter, setEventsServiceFilter] = useState([]) // empty = all services

  // Refs for stable callback access (avoids stale closures)
  const eventsHoursRef = useRef(eventsHours)
  const eventsTypeFilterRef = useRef(eventsTypeFilter)
  const eventsPanelVisibleRef = useRef(eventsPanelVisible)
  const servicesRef = useRef(SERVICES)
  const currentProjectRef = useRef(currentProjectId)
  eventsHoursRef.current = eventsHours
  eventsTypeFilterRef.current = eventsTypeFilter
  eventsPanelVisibleRef.current = eventsPanelVisible
  servicesRef.current = SERVICES
  currentProjectRef.current = currentProjectId

  // Track project changes to reset data
  const prevProjectRef = useRef(appConfig.currentProjectId)

  // Reset data when project changes
  useEffect(() => {
    if (prevProjectRef.current !== appConfig.currentProjectId) {
      // Project changed - reset all data
      setServices({})
      setPipelines({})
      setImages({})
      setMetrics({})
      setServiceConfig({})
      setInfrastructure({})
      setEvents([])
      setSelectedService(null)
      setSelectedInfraComponent(null)
      setBottomLogsTabs([])
      setActiveBottomTab(null)
      setLastUpdated(null)
      // Reset selected env to first env of new project
      if (ENVIRONMENTS.length > 0) {
        setSelectedInfraEnv(ENVIRONMENTS[0])
      }
      prevProjectRef.current = appConfig.currentProjectId
      // Fetch pipelines and images for new project will be triggered by the refs update
      // Set a flag to trigger fetch after render
      setLastUpdated(null)  // This will trigger a visual update
    }
  }, [appConfig.currentProjectId, ENVIRONMENTS])

  // Helper to check if anything is loading
  const loading = Object.values(loadingStates).some(v => v)
  const refreshing = loading

  // Helper to get environment button classes from ENV_COLORS
  const getEnvButtonClasses = (env) => {
    const colors = ENV_COLORS[env] || {}
    // Extract base color from bg class (e.g., "bg-yellow-500" -> "yellow-500")
    const bgColor = colors.bg?.replace('bg-', '') || 'gray-500'
    const textClass = colors.text || 'text-gray-400'
    return `bg-${bgColor}/20 hover:bg-${bgColor}/30 ${textClass}`
  }


  // Fetch services for selected env only
  const fetchServices = useCallback(async (env) => {
    const project = currentProjectRef.current
    setLoadingStates(prev => ({ ...prev, services: true }))
    try {
      const res = await fetchWithRetry(`/api/${project}/services/${env}`)
      const data = await res.json()
      setServices(prev => ({ ...prev, [env]: data }))
      setServiceConfig(data.config || {})
    } catch (error) {
      console.error('Error fetching services:', error)
    } finally {
      setLoadingStates(prev => ({ ...prev, services: false }))
    }
  }, [])

  // Fetch build pipelines (shared across envs)
  const fetchPipelines = useCallback(async () => {
    const project = currentProjectRef.current
    const projectServices = servicesRef.current
    if (!projectServices || projectServices.length === 0) return
    setLoadingStates(prev => ({ ...prev, pipelines: true }))
    try {
      const pipelinePromises = projectServices.map(async (service) => {
        const res = await fetchWithRetry(`/api/${project}/pipelines/build/${service}`)
        return { service, data: await res.json() }
      })
      const pipelinesData = await Promise.all(pipelinePromises)
      const pipelinesMap = {}
      pipelinesData.forEach(({ service, data }) => {
        pipelinesMap[service] = data
      })
      setPipelines(pipelinesMap)
    } catch (error) {
      console.error('Error fetching pipelines:', error)
    } finally {
      setLoadingStates(prev => ({ ...prev, pipelines: false }))
    }
  }, [])

  // Fetch ECR images (shared across envs)
  const fetchImages = useCallback(async () => {
    const project = currentProjectRef.current
    const projectServices = servicesRef.current
    if (!projectServices || projectServices.length === 0) return
    setLoadingStates(prev => ({ ...prev, images: true }))
    try {
      const imagePromises = projectServices.map(async (service) => {
        try {
          const res = await fetchWithRetry(`/api/${project}/images/${service}`)
          if (!res.ok) {
            console.error(`Failed to fetch images for ${service}: ${res.status}`)
            return { service, data: { error: `HTTP ${res.status}`, images: [] } }
          }
          return { service, data: await res.json() }
        } catch (err) {
          console.error(`Error fetching images for ${service}:`, err)
          return { service, data: { error: err.message, images: [] } }
        }
      })
      const imagesData = await Promise.all(imagePromises)
      const imagesMap = {}
      imagesData.forEach(({ service, data }) => {
        imagesMap[service] = data
      })
      setImages(imagesMap)
    } catch (error) {
      console.error('Error fetching images:', error)
    } finally {
      setLoadingStates(prev => ({ ...prev, images: false }))
    }
  }, [])

  // Refetch pipelines and images when project changes
  const prevProjectForPipelinesRef = useRef(appConfig.currentProjectId)
  useEffect(() => {
    // Skip initial mount (handled by the mount useEffect)
    if (prevProjectForPipelinesRef.current === appConfig.currentProjectId) return
    prevProjectForPipelinesRef.current = appConfig.currentProjectId
    // Fetch with small delay to ensure servicesRef is updated
    const timer = setTimeout(() => {
      fetchPipelines()
      fetchImages()
    }, 50)
    return () => clearTimeout(timer)
  }, [appConfig.currentProjectId, fetchPipelines, fetchImages])

  // Fetch infrastructure for selected env only
  // Uses discovery tags and other config from appConfig.infrastructure
  const fetchInfrastructure = useCallback(async (env, infraConfig) => {
    const project = currentProjectRef.current
    setLoadingStates(prev => ({ ...prev, infrastructure: true }))
    try {
      // Build query params from infrastructure config
      const params = new URLSearchParams()
      if (infraConfig?.discoveryTags) {
        params.set('discoveryTags', JSON.stringify(infraConfig.discoveryTags))
      }
      if (infraConfig?.domains) {
        params.set('domainConfig', JSON.stringify({ domains: infraConfig.domains, pattern: infraConfig.domainPattern }))
      }
      if (infraConfig?.databases?.length) {
        params.set('databases', infraConfig.databases.join(','))
      }
      if (infraConfig?.caches?.length) {
        params.set('caches', infraConfig.caches.join(','))
      }
      // Services are also passed for filtering
      const services = appConfig.services || []
      if (services.length) {
        params.set('services', services.join(','))
      }
      const queryString = params.toString()
      const url = `/api/${project}/infrastructure/${env}${queryString ? `?${queryString}` : ''}`
      const res = await fetchWithRetry(url)
      const data = await res.json()
      setInfrastructure(prev => ({ ...prev, [env]: data }))
    } catch (error) {
      console.error('Error fetching infrastructure:', error)
    } finally {
      setLoadingStates(prev => ({ ...prev, infrastructure: false }))
    }
  }, [appConfig.services])  // Depend on services for filtering

  // Force refresh infrastructure (bypass cache)
  const refreshInfrastructure = useCallback(async (env, infraConfig) => {
    const project = currentProjectRef.current
    setLoadingStates(prev => ({ ...prev, infrastructure: true }))
    try {
      // Build query params from infrastructure config
      const params = new URLSearchParams()
      if (infraConfig?.discoveryTags) {
        params.set('discoveryTags', JSON.stringify(infraConfig.discoveryTags))
      }
      if (infraConfig?.domains) {
        params.set('domainConfig', JSON.stringify({ domains: infraConfig.domains, pattern: infraConfig.domainPattern }))
      }
      if (infraConfig?.databases?.length) {
        params.set('databases', infraConfig.databases.join(','))
      }
      if (infraConfig?.caches?.length) {
        params.set('caches', infraConfig.caches.join(','))
      }
      const services = appConfig.services || []
      if (services.length) {
        params.set('services', services.join(','))
      }
      const queryString = params.toString()
      const url = `/api/${project}/infrastructure/${env}${queryString ? `?${queryString}` : ''}`
      const res = await fetchWithRetry(url)
      const data = await res.json()
      setInfrastructure(prev => ({ ...prev, [env]: data }))
    } catch (error) {
      console.error('Error fetching infrastructure:', error)
    } finally {
      setLoadingStates(prev => ({ ...prev, infrastructure: false }))
    }
  }, [appConfig.services])

  // Fetch events timeline (fast) then enrich with CloudTrail (async)
  const fetchEvents = useCallback(async (env, hours) => {
    if (!eventsPanelVisibleRef.current) return
    const project = currentProjectRef.current
    const actualHours = hours ?? eventsHoursRef.current
    const typeFilter = eventsTypeFilterRef.current
    const projectServices = servicesRef.current
    setEventsLoading(true)
    try {
      const typesParam = typeFilter.length > 0 ? `&types=${typeFilter.join(',')}` : ''
      const servicesParam = projectServices.length > 0 ? `&services=${projectServices.join(',')}` : ''
      const res = await fetchWithRetry(`/api/${project}/events/${env}?hours=${actualHours}${typesParam}${servicesParam}`)
      const data = await res.json()
      const eventsData = data.events || []

      // Only update events if they actually changed (avoid flicker)
      // IMPORTANT: Preserve user/actorType from previous enrichment to avoid flicker
      setEvents(prev => {
        // Build a map of existing users by event ID
        const existingUsers = {}
        prev.forEach(e => {
          if (e.user) existingUsers[e.id] = { user: e.user, actorType: e.actorType }
        })

        // Merge new data with existing user info
        const merged = eventsData.map(e => {
          if (!e.user && existingUsers[e.id]) {
            return { ...e, user: existingUsers[e.id].user, actorType: existingUsers[e.id].actorType }
          }
          return e
        })

        // Compare only non-enriched fields to detect real changes
        const prevKey = prev.map(e => `${e.id}|${e.status}|${e.timestamp}`).join(',')
        const newKey = merged.map(e => `${e.id}|${e.status}|${e.timestamp}`).join(',')
        if (prevKey === newKey && prev.length === merged.length) {
          // No structural change - keep previous state to avoid flicker
          return prev
        }
        return merged
      })

      // Async: enrich events with CloudTrail user info (non-blocking)
      // Only enrich events that don't already have user info
      const eventsToEnrich = eventsData.filter(e => !e.user)
      if (eventsToEnrich.length > 0) {
        fetchWithRetry(`/api/${project}/events/${env}/enrich`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ events: eventsData })
        })
          .then(res => res.json())
          .then(enrichedData => {
            if (enrichedData.events && enrichedData.enrichedCount > 0) {
              // Build actor info map (user + actorType)
              const actorMap = {}
              enrichedData.events.forEach(e => {
                if (e.user) actorMap[e.id] = { user: e.user, actorType: e.actorType }
              })
              // Only update state if we have new info - single atomic update
              setEvents(prev => {
                const updated = prev.map(evt => {
                  const actor = actorMap[evt.id]
                  if (actor && !evt.user) {
                    return { ...evt, user: actor.user, actorType: actor.actorType }
                  }
                  return evt
                })
                // Check if anything actually changed
                const hasChanges = updated.some((u, i) => u !== prev[i])
                return hasChanges ? updated : prev
              })
            }
          })
          .catch(err => console.log('CloudTrail enrichment skipped:', err.message))
      }

      // Async: fetch task definition diffs for deploy events with previous task def info
      const deployEventsWithPrev = eventsData.filter(e =>
        (e.type === 'deploy' || e.type === 'rollback') &&
        e.details?.taskDefinition &&
        e.details?.previousTaskDefinition
      )
      if (deployEventsWithPrev.length > 0) {
        // Build items for diff API call
        const diffItems = deployEventsWithPrev.map(e => {
          const taskDef = e.details.taskDefinition
          const prevTaskDef = e.details.previousTaskDefinition
          // Parse family:revision format
          const [family, toRev] = taskDef.includes(':') ? [taskDef.split(':')[0], taskDef.split(':')[1]] : [taskDef, null]
          const fromRev = prevTaskDef.includes(':') ? prevTaskDef.split(':')[1] : null
          return { family, fromRevision: fromRev, toRevision: toRev, eventId: e.id }
        }).filter(item => item.fromRevision && item.toRevision)

        if (diffItems.length > 0) {
          fetchWithRetry(`/api/${project}/events/${env}/task-diff`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ items: diffItems.map(({ family, fromRevision, toRevision }) => ({ family, fromRevision, toRevision })) })
          })
            .then(res => res.json())
            .then(diffData => {
              if (diffData.diffs) {
                // Build lookup by eventId using diffItems
                const diffByEventId = {}
                diffItems.forEach(item => {
                  const key = `${item.family}:${item.fromRevision}-${item.toRevision}`
                  if (diffData.diffs[key]) {
                    diffByEventId[item.eventId] = diffData.diffs[key]
                  } else {
                    // Mark as loaded but no changes
                    diffByEventId[item.eventId] = { changes: [] }
                  }
                })
                // Update events with diff info
                setEvents(prev => {
                  const updated = prev.map(evt => {
                    if (diffByEventId[evt.id]) {
                      return { ...evt, diff: diffByEventId[evt.id] }
                    }
                    return evt
                  })
                  return updated
                })
              }
            })
            .catch(err => console.log('Task def diff enrichment skipped:', err.message))
        }
      }
    } catch (error) {
      console.error('Error fetching events:', error)
      setEvents([])
    } finally {
      setEventsLoading(false)
    }
  }, [])  // Stable callback - env/hours/types passed as params

  // Initial load - fetch in parallel but only for selected env
  const fetchData = useCallback(async () => {
    setLastUpdated(new Date())
    // Load all sections in parallel
    await Promise.all([
      fetchServices(selectedInfraEnv),
      fetchPipelines(),
      fetchImages(),
      refreshInfrastructure(selectedInfraEnv, appConfig.infrastructure)
    ])
  }, [selectedInfraEnv, fetchServices, fetchPipelines, fetchImages, refreshInfrastructure, appConfig.infrastructure])

  const fetchMetrics = useCallback(async (env, service) => {
    const project = currentProjectRef.current
    try {
      const res = await fetchWithRetry(`/api/${project}/metrics/${env}/${service}`)
      const data = await res.json()
      setMetrics(prev => ({
        ...prev,
        [`${env}-${service}`]: data.metrics
      }))
    } catch (error) {
      console.error('Error fetching metrics:', error)
    }
  }, [])

  const fetchDetails = useCallback(async (env, service) => {
    const project = currentProjectRef.current
    setDetailsLoading(true)
    try {
      const res = await fetchWithRetry(`/api/${project}/details/${env}/${service}`)
      const data = await res.json()
      setServiceDetails(data)
    } catch (error) {
      console.error('Error fetching details:', error)
      setServiceDetails({ error: error.message })
    }
    setDetailsLoading(false)
  }, [])

  // Action handlers
  const [actionLoading, setActionLoading] = useState({})
  const [actionResult, setActionResult] = useState(null)

  const handleTriggerBuild = useCallback(async (service) => {
    const project = currentProjectRef.current
    if (!window.confirm(`Trigger build for ${service}?`)) return
    setActionLoading(prev => ({ ...prev, [`build-${service}`]: true }))
    try {
      const res = await fetchWithRetry(`/api/${project}/actions/build/${service}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({})
      })
      const data = await res.json()
      if (data.error) {
        setActionResult({ type: 'error', message: data.error })
      } else {
        setActionResult({ type: 'success', message: `Build triggered for ${service}` })
        // Refresh pipelines after a short delay
        setTimeout(() => fetchPipelines(), 2000)
      }
    } catch (error) {
      setActionResult({ type: 'error', message: error.message })
    }
    setActionLoading(prev => ({ ...prev, [`build-${service}`]: false }))
    // Clear result after 5s
    setTimeout(() => setActionResult(null), 5000)
  }, [fetchPipelines])

  const handleForceReload = useCallback(async (env, service) => {
    const project = currentProjectRef.current
    if (!window.confirm(`Reload ${service} on ${env}?\nThis will restart ECS tasks to pick up new secret values.`)) return
    setActionLoading(prev => ({ ...prev, [`reload-${env}-${service}`]: true }))
    try {
      const res = await fetchWithRetry(`/api/${project}/actions/deploy/${env}/${service}/reload`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({})
      })
      const data = await res.json()
      if (data.error) {
        setActionResult({ type: 'error', message: data.error })
      } else {
        setActionResult({ type: 'success', message: `Reload triggered for ${service} (${env})` })
        // Refresh services after a short delay
        setTimeout(() => fetchServices(env), 5000)
      }
    } catch (error) {
      setActionResult({ type: 'error', message: error.message })
    }
    setActionLoading(prev => ({ ...prev, [`reload-${env}-${service}`]: false }))
    setTimeout(() => setActionResult(null), 5000)
  }, [fetchServices])

  const handleDeployLatest = useCallback(async (env, service) => {
    const project = currentProjectRef.current
    if (!window.confirm(`Deploy latest for ${service} on ${env}?\nThis will trigger the deploy pipeline to update to the latest image and task definition.`)) return
    setActionLoading(prev => ({ ...prev, [`deploy-${env}-${service}`]: true }))
    try {
      const res = await fetchWithRetry(`/api/${project}/actions/deploy/${env}/${service}/latest`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({})
      })
      const data = await res.json()
      if (data.error) {
        setActionResult({ type: 'error', message: data.error })
      } else {
        setActionResult({ type: 'success', message: `Deploy pipeline triggered for ${service} (${env})` })
        // Refresh services after a short delay
        setTimeout(() => fetchServices(env), 5000)
      }
    } catch (error) {
      setActionResult({ type: 'error', message: error.message })
    }
    setActionLoading(prev => ({ ...prev, [`deploy-${env}-${service}`]: false }))
    setTimeout(() => setActionResult(null), 5000)
  }, [fetchServices])

  const handleScaleService = useCallback(async (env, service, action) => {
    const project = currentProjectRef.current
    let desiredCount = 1
    if (action === 'stop') {
      if (!window.confirm(`Stop ${service} on ${env}?\nThis will set replicas to 0.`)) return
    } else {
      const input = window.prompt(`Start ${service} on ${env}\nEnter number of replicas (1-10):`, '1')
      if (input === null) return
      desiredCount = parseInt(input, 10)
      if (isNaN(desiredCount) || desiredCount < 1 || desiredCount > 10) {
        setActionResult({ type: 'error', message: 'Invalid replica count. Must be between 1 and 10.' })
        setTimeout(() => setActionResult(null), 5000)
        return
      }
    }
    const actionLabel = action === 'stop' ? 'Stop' : 'Start'
    setActionLoading(prev => ({ ...prev, [`scale-${env}-${service}`]: true }))
    try {
      const res = await fetchWithRetry(`/api/${project}/actions/deploy/${env}/${service}/${action}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ desiredCount })
      })
      const data = await res.json()
      if (data.error) {
        setActionResult({ type: 'error', message: data.error })
      } else {
        const msg = action === 'stop'
          ? `Stop triggered for ${service} (${env})`
          : `Start triggered for ${service} (${env}) with ${desiredCount} replica(s)`
        setActionResult({ type: 'success', message: msg })
        setTimeout(() => fetchServices(env), 5000)
      }
    } catch (error) {
      setActionResult({ type: 'error', message: error.message })
    }
    setActionLoading(prev => ({ ...prev, [`scale-${env}-${service}`]: false }))
    setTimeout(() => setActionResult(null), 5000)
  }, [fetchServices])

  const handleControlRds = useCallback(async (env, action) => {
    const project = currentProjectRef.current
    const actionLabel = action === 'stop' ? 'Stop' : 'Start'
    if (!window.confirm(`${actionLabel} RDS database on ${env}?`)) return
    setActionLoading(prev => ({ ...prev, [`rds-${env}`]: true }))
    try {
      const res = await fetchWithRetry(`/api/${project}/actions/rds/${env}/${action}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      })
      const data = await res.json()
      if (data.error) {
        setActionResult({ type: 'error', message: data.error })
      } else {
        setActionResult({ type: 'success', message: `RDS ${actionLabel} triggered (${env})` })
        setTimeout(() => fetchInfrastructure(env, appConfig.infrastructure), 10000)
      }
    } catch (error) {
      setActionResult({ type: 'error', message: error.message })
    }
    setActionLoading(prev => ({ ...prev, [`rds-${env}`]: false }))
    setTimeout(() => setActionResult(null), 5000)
  }, [fetchInfrastructure, appConfig.infrastructure])

  const handleInvalidateCloudfront = useCallback(async (env, distributionId) => {
    const project = currentProjectRef.current
    const input = window.prompt(`Invalidate CloudFront cache on ${env}\nEnter paths (comma-separated, e.g. /*):`, '/*')
    if (input === null) return
    const paths = input.split(',').map(p => p.trim()).filter(p => p)
    if (paths.length === 0) {
      setActionResult({ type: 'error', message: 'No paths specified' })
      return
    }
    setActionLoading(prev => ({ ...prev, [`cf-${env}`]: true }))
    try {
      const res = await fetchWithRetry(`/api/${project}/actions/cloudfront/${env}/invalidate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ distributionId, paths })
      })
      const data = await res.json()
      if (data.error) {
        setActionResult({ type: 'error', message: data.error })
      } else {
        setActionResult({ type: 'success', message: `CloudFront invalidation created: ${data.invalidationId}` })
      }
    } catch (error) {
      setActionResult({ type: 'error', message: error.message })
    }
    setActionLoading(prev => ({ ...prev, [`cf-${env}`]: false }))
    setTimeout(() => setActionResult(null), 5000)
  }, [])

  // Bottom logs panel tab management
  const openLogsTab = useCallback((logsData) => {
    const tabId = `${logsData.env}-${logsData.service}`
    setBottomLogsTabs(prev => {
      // Check if tab already exists
      const existingTab = prev.find(t => t.id === tabId)
      if (existingTab) {
        // Tab exists - just activate it
        setActiveBottomTab(tabId)
        return prev
      }
      // Add new tab (max 5 tabs)
      const newTab = { id: tabId, ...logsData }
      const newTabs = [...prev, newTab].slice(-5) // Keep last 5 tabs
      setActiveBottomTab(tabId)
      return newTabs
    })
  }, [])

  const closeLogsTab = useCallback((tabId) => {
    setBottomLogsTabs(prev => {
      const newTabs = prev.filter(t => t.id !== tabId)
      // If we closed the active tab, activate another one
      if (activeBottomTab === tabId && newTabs.length > 0) {
        setActiveBottomTab(newTabs[newTabs.length - 1].id)
      } else if (newTabs.length === 0) {
        setActiveBottomTab(null)
      }
      return newTabs
    })
  }, [activeBottomTab])

  const closeAllLogsTabs = useCallback(() => {
    setBottomLogsTabs([])
    setActiveBottomTab(null)
  }, [])

  // Open build logs in bottom panel
  const handleOpenBuildLogs = useCallback((service) => {
    openLogsTab({
      env: 'build',  // Special marker for build logs
      service,
      type: 'build',
      autoTail: true
    })
  }, [openLogsTab])

  // Open deploy pipeline logs in bottom panel
  const handleOpenDeployLogs = useCallback((env, service) => {
    openLogsTab({
      env,
      service,
      type: 'deploy',
      autoTail: true
    })
  }, [openLogsTab])

  // Initial load - pipelines, images (once on mount)
  // Note: User info is now loaded by AuthProvider
  useEffect(() => {
    fetchPipelines()
    fetchImages()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])  // Run once on mount - callbacks are stable

  // Load data when selected env changes
  useEffect(() => {
    // Reset events immediately when env changes to avoid showing stale data
    setEvents([])
    fetchServices(selectedInfraEnv)
    fetchInfrastructure(selectedInfraEnv, appConfig.infrastructure)
    fetchEvents(selectedInfraEnv)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedInfraEnv, appConfig.infrastructure])  // Re-run when env or project changes

  // Refetch events when filter or hours change (not on env change - handled above)
  const prevEnvRef = useRef(selectedInfraEnv)
  useEffect(() => {
    // Skip if this is an env change (already handled by the effect above)
    if (prevEnvRef.current !== selectedInfraEnv) {
      prevEnvRef.current = selectedInfraEnv
      return
    }
    fetchEvents(selectedInfraEnv)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [eventsHours, eventsTypeFilter, eventsPanelVisible])  // Only re-run when filters change

  // Auto refresh - 30 second interval
  useEffect(() => {
    if (!autoRefresh) return
    const interval = setInterval(() => {
      fetchServices(selectedInfraEnv)
      refreshInfrastructure(selectedInfraEnv, appConfig.infrastructure)
      fetchPipelines()
      fetchEvents(selectedInfraEnv)
    }, 30000)
    return () => clearInterval(interval)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoRefresh, selectedInfraEnv, appConfig.infrastructure])  // Re-run when autoRefresh, env, or project changes

  // Fetch details when service selection changes
  useEffect(() => {
    if (selectedService) {
      const [env, service] = selectedService.split('-')
      fetchMetrics(env, service)
      fetchDetails(env, service)
    } else {
      setServiceDetails(null)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedService])  // Callbacks are stable

  // Handle infra component selection - for services, load the service details
  const handleInfraComponentSelect = useCallback((type, env, data) => {
    if (type === 'service' && data?.name) {
      // Extract service name from full name (prefix-env-service -> service)
      const serviceName = data.name.split('-').pop()
      setSelectedService(`${env}-${serviceName}`)
      setSelectedInfraComponent(null)
    } else {
      setSelectedInfraComponent({ type, env, data })
      setSelectedService(null)
    }
  }, [])

  // Handle click on timeline event - open relevant panel
  const handleEventClick = useCallback((event) => {
    const eventType = event.type || ''
    const eventService = event.service || ''
    const eventEnv = event.environment || selectedInfraEnv

    // Map event type to the appropriate panel
    if (eventType === 'build') {
      // Open pipeline panel for build events
      if (pipelines[eventService]) {
        setSelectedInfraComponent({ type: 'pipeline', env: 'shared', data: { service: eventService, pipeline: pipelines[eventService], images: images[eventService] }})
        setSelectedService(null)
      }
    } else if (['deploy', 'rollback', 'scale', 'ecs_event'].includes(eventType)) {
      // Open service detail panel for deploy/scale events
      if (eventService) {
        setSelectedService(`${eventEnv}-${eventService}`)
        setSelectedInfraComponent(null)
      }
    } else if (['rds_stop', 'rds_start'].includes(eventType)) {
      // Open RDS infra component
      if (infrastructure[eventEnv]?.rds) {
        setSelectedInfraComponent({ type: 'rds', env: eventEnv, data: infrastructure[eventEnv].rds })
        setSelectedService(null)
      }
    } else if (eventType === 'cache_invalidation') {
      // Open CloudFront infra component
      if (infrastructure[eventEnv]?.cloudfront) {
        setSelectedInfraComponent({ type: 'cloudfront', env: eventEnv, data: infrastructure[eventEnv].cloudfront })
        setSelectedService(null)
      }
    }
  }, [selectedInfraEnv, pipelines, images, infrastructure])

  // Loading skeleton component
  const LoadingSkeleton = ({ className = '' }) => (
    <div className={`animate-pulse bg-gray-700 rounded ${className}`}></div>
  )

  return (
    <div className="min-h-screen bg-gray-900 text-gray-100">
      {/* Session Expired Modal */}
      {sessionExpired && <SessionExpiredModal onReconnect={handleReconnect} />}

      {/* Action Result Toast */}
      {actionResult && (
        <div className={`fixed top-4 right-4 z-[100] px-4 py-3 rounded-lg shadow-lg flex items-center gap-2 ${
          actionResult.type === 'success' ? 'bg-green-600' : 'bg-red-600'
        }`}>
          {actionResult.type === 'success' ? (
            <CheckCircle className="w-5 h-5" />
          ) : (
            <XCircle className="w-5 h-5" />
          )}
          <span>{actionResult.message}</span>
          <button onClick={() => setActionResult(null)} className="ml-2 hover:opacity-80">
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Header */}
      <header className="bg-gray-800 border-b border-gray-700 sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 py-4 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <img src={appConfig.branding?.logo} alt={appConfig.branding?.logoAlt} className="h-10" />
            <div className="h-6 w-px bg-gray-600"></div>
            <div className="flex items-center gap-2">
              <Server className="w-6 h-6 text-brand-500" />
              <h1 className="text-lg font-bold">{appConfig.global?.title || 'Operations Dashboard'}</h1>
            </div>
            <div className="h-6 w-px bg-gray-600"></div>
            <ProjectSelector />
          </div>

          <div className="flex items-center gap-4">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={autoRefresh}
                onChange={(e) => setAutoRefresh(e.target.checked)}
                className="w-4 h-4 rounded bg-gray-700 border-gray-600 text-brand-500 focus:ring-brand-500"
              />
              <span className="text-sm text-gray-400">Auto-refresh</span>
            </label>

            <button
              onClick={fetchData}
              disabled={refreshing}
              className="flex items-center gap-2 px-3 py-1.5 bg-gray-700 hover:bg-gray-600 rounded-md transition-colors disabled:opacity-50"
            >
              <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} />
              <span className="text-sm">{refreshing ? 'Refreshing...' : 'Refresh'}</span>
            </button>

            {lastUpdated && (
              <div className="flex items-center gap-1 text-sm text-gray-500">
                <Clock className="w-4 h-4" />
                <span>{lastUpdated.toLocaleTimeString()}</span>
              </div>
            )}

            {/* User info, role badge, and logout */}
            <div className="flex items-center gap-3 ml-4 pl-4 border-l border-gray-600">
              {auth.user && (
                <>
                  <div className="flex items-center gap-2 text-sm text-gray-300">
                    <User className="w-4 h-4 text-gray-400" />
                    <span>{auth.user.email}</span>
                  </div>
                  {/* Role badge */}
                  {auth.getRoleFor(currentProjectId) && (
                    <span className={`px-2 py-0.5 text-xs rounded-full ${
                      auth.getRoleFor(currentProjectId) === 'admin'
                        ? 'bg-purple-500/20 text-purple-400'
                        : auth.getRoleFor(currentProjectId) === 'operator'
                          ? 'bg-blue-500/20 text-blue-400'
                          : 'bg-gray-500/20 text-gray-400'
                    }`}>
                      {auth.getRoleFor(currentProjectId)}
                    </span>
                  )}
                </>
              )}
              <button
                onClick={auth.logout}
                className="flex items-center gap-1 px-2 py-1 text-sm text-gray-400 hover:text-white hover:bg-gray-700 rounded transition-colors"
                title="Logout"
              >
                <LogOut className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>
      </header>

      <div className="flex">
        {/* Events Timeline Panel - Left */}
        <EventsTimelinePanel
          events={events}
          loading={eventsLoading}
          visible={eventsPanelVisible}
          onToggleVisible={() => setEventsPanelVisible(!eventsPanelVisible)}
          width={eventsPanelWidth}
          onWidthChange={setEventsPanelWidth}
          hours={eventsHours}
          onHoursChange={setEventsHours}
          typeFilter={eventsTypeFilter}
          onTypeFilterChange={setEventsTypeFilter}
          serviceFilter={eventsServiceFilter}
          onServiceFilterChange={setEventsServiceFilter}
          env={selectedInfraEnv}
          autoRefresh={autoRefresh}
          onEventClick={handleEventClick}
        />

        {/* Main Content - adjusts for left panel */}
        <main
          className="flex-1 px-4 py-6 space-y-6 transition-all duration-200"
          style={{ marginLeft: eventsPanelVisible ? `${eventsPanelWidth}px` : '32px' }}
        >
          <div className="max-w-7xl mx-auto">
          {/* Build Pipelines - At the top */}
          <section>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold flex items-center gap-2">
                <Package className="w-5 h-5 text-brand-400" />
                Build Pipelines
                {loadingStates.pipelines && (
                  <RefreshCw className="w-4 h-4 text-brand-500 animate-spin" />
                )}
              </h2>
              <a
                href={getCodePipelineConsoleUrl(AWS_ACCOUNTS['shared-services'].id)}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-2 text-xs bg-purple-500/20 hover:bg-purple-500/30 text-purple-400 px-3 py-1.5 rounded-lg transition-colors"
                title="Open AWS Console for shared-services account"
              >
                <span className="font-medium">{AWS_ACCOUNTS['shared-services'].alias}</span>
                <span className="text-purple-400/60 font-mono">{AWS_ACCOUNTS['shared-services'].id}</span>
                <ExternalLink className="w-3 h-3" />
              </a>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {SERVICES.map(service => (
                <BuildPipelineCard
                  key={service}
                  service={service}
                  pipeline={pipelines[service]}
                  images={images[service]}
                  loading={loadingStates.pipelines && !pipelines[service]}
                  onSelect={() => handleInfraComponentSelect('pipeline', 'shared', { service, pipeline: pipelines[service], images: images[service] })}
                  isSelected={selectedInfraComponent?.type === 'pipeline' && selectedInfraComponent?.data?.service === service}
                  onTriggerBuild={() => handleTriggerBuild(service)}
                  actionLoading={actionLoading[`build-${service}`]}
                  onTailBuildLogs={() => handleOpenBuildLogs(service)}
                />
              ))}
            </div>
          </section>

          {/* Infrastructure Diagram */}
          <section className="mt-8">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-4">
                <h2 className="text-lg font-semibold flex items-center gap-2">
                  <Network className="w-5 h-5 text-brand-400" />
                  Infrastructure
                </h2>
                {AWS_ACCOUNTS[selectedInfraEnv] && (
                  <a
                    href={getAwsConsoleUrl(AWS_ACCOUNTS[selectedInfraEnv].id)}
                    target="_blank"
                    rel="noopener noreferrer"
                    className={`flex items-center gap-2 text-xs px-3 py-1.5 rounded-lg transition-colors ${getEnvButtonClasses(selectedInfraEnv)}`}
                    title={`Open AWS Console for ${selectedInfraEnv} account`}
                  >
                    <span className="font-medium">{AWS_ACCOUNTS[selectedInfraEnv].alias}</span>
                    <span className="opacity-60 font-mono">{AWS_ACCOUNTS[selectedInfraEnv].id}</span>
                    <ExternalLink className="w-3 h-3" />
                  </a>
                )}
              </div>
              <div className="flex gap-2">
                {ENVIRONMENTS.map(env => (
                  <button
                    key={env}
                    onClick={() => setSelectedInfraEnv(env)}
                    className={`px-3 py-1 rounded text-sm capitalize transition-colors ${
                      selectedInfraEnv === env
                        ? `${(ENV_COLORS[env] || { bg: 'bg-gray-500' }).bg} text-white`
                        : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                    }`}
                  >
                    {env}
                  </button>
                ))}
              </div>
            </div>

            {/* Loading overlay for infrastructure */}
            {(loadingStates.infrastructure || loadingStates.services) && !infrastructure[selectedInfraEnv] && (
              <div className="bg-gray-800 rounded-lg p-8 flex items-center justify-center">
                <div className="text-center">
                  <RefreshCw className="w-8 h-8 text-brand-500 animate-spin mx-auto mb-2" />
                  <p className="text-gray-400 text-sm">Loading infrastructure...</p>
                </div>
              </div>
            )}

            {/* Show diagram when data is available */}
            {infrastructure[selectedInfraEnv] && (
              <div className="relative">
                {/* Refresh indicator overlay */}
                {(loadingStates.infrastructure || loadingStates.services) && (
                  <div className="absolute top-2 right-2 z-10">
                    <RefreshCw className="w-4 h-4 text-brand-500 animate-spin" />
                  </div>
                )}
                <InfrastructureDiagram
                  data={infrastructure[selectedInfraEnv]}
                  env={selectedInfraEnv}
                  onComponentSelect={handleInfraComponentSelect}
                  selectedComponent={selectedInfraComponent}
                  services={services[selectedInfraEnv]}
                  pipelines={pipelines}
                  onForceReload={handleForceReload}
                  onDeployLatest={handleDeployLatest}
                  onScaleService={handleScaleService}
                  actionLoading={actionLoading}
                  onOpenLogsPanel={openLogsTab}
                  onTailDeployLogs={handleOpenDeployLogs}
                />
              </div>
            )}
          </section>
          </div>
        </main>

        {/* Details Panel - Service */}
        {selectedService && (
          <ServiceDetailsPanel
            details={serviceDetails}
            loading={detailsLoading}
            onClose={() => setSelectedService(null)}
            metrics={metrics[selectedService]}
            onForceReload={handleForceReload}
            onDeployLatest={handleDeployLatest}
            onScaleService={handleScaleService}
            actionLoading={actionLoading}
            onOpenLogsPanel={openLogsTab}
          />
        )}

        {/* Details Panel - Infrastructure Components */}
        {selectedInfraComponent && (
          <InfrastructureDetailsPanel
            component={selectedInfraComponent}
            infrastructure={infrastructure[selectedInfraComponent.env]}
            onClose={() => setSelectedInfraComponent(null)}
            onControlRds={handleControlRds}
            onInvalidateCloudfront={handleInvalidateCloudfront}
            actionLoading={actionLoading}
            onOpenLogsPanel={openLogsTab}
            TaskDetails={TaskDetails}
          />
        )}
      </div>

      {/* Bottom Logs Panel with Tabs */}
      {bottomLogsTabs.length > 0 && (
        <TabbedLogsPanel
          tabs={bottomLogsTabs}
          activeTab={activeBottomTab}
          onTabSelect={setActiveBottomTab}
          onTabClose={closeLogsTab}
          onCloseAll={closeAllLogsTabs}
        />
      )}
    </div>
  )
}
