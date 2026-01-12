import { createContext, useContext, useState, useEffect, useCallback } from 'react'
import { RefreshCw, XCircle } from 'lucide-react'

const ConfigContext = createContext(null)

// LocalStorage keys
const STORAGE_KEYS = {
  currentProject: 'dashboard_currentProject',
  favoriteProjects: 'dashboard_favoriteProjects'
}

/**
 * Configuration Provider
 * Loads runtime configuration from /config.json and manages project selection
 */
export function ConfigProvider({ children }) {
  const [rawConfig, setRawConfig] = useState(null)
  const [currentProjectId, setCurrentProjectId] = useState(null)
  const [favoriteProjects, setFavoriteProjects] = useState([])
  const [error, setError] = useState(null)

  // Load config and restore project selection from localStorage
  useEffect(() => {
    fetch('/config.json')
      .then(res => {
        if (!res.ok) throw new Error(`Failed to load config: ${res.status}`)
        return res.json()
      })
      .then(data => {
        setRawConfig(data)

        // Restore current project from localStorage or use default
        const savedProject = localStorage.getItem(STORAGE_KEYS.currentProject)
        const projectIds = Object.keys(data.projects || {})

        if (savedProject && projectIds.includes(savedProject)) {
          setCurrentProjectId(savedProject)
        } else {
          setCurrentProjectId(data.defaultProject || projectIds[0] || null)
        }

        // Restore favorites from localStorage
        try {
          const savedFavorites = JSON.parse(localStorage.getItem(STORAGE_KEYS.favoriteProjects) || '[]')
          // Filter to only valid project IDs
          const validFavorites = savedFavorites.filter(id => projectIds.includes(id))
          setFavoriteProjects(validFavorites)
        } catch {
          setFavoriteProjects([])
        }
      })
      .catch(err => {
        console.error('Failed to load app configuration:', err)
        setError(err.message)
      })
  }, [])

  // Persist current project to localStorage
  const selectProject = useCallback((projectId) => {
    if (rawConfig?.projects?.[projectId]) {
      setCurrentProjectId(projectId)
      localStorage.setItem(STORAGE_KEYS.currentProject, projectId)
    }
  }, [rawConfig])

  // Toggle favorite status
  const toggleFavorite = useCallback((projectId) => {
    setFavoriteProjects(prev => {
      const newFavorites = prev.includes(projectId)
        ? prev.filter(id => id !== projectId)
        : [...prev, projectId]
      localStorage.setItem(STORAGE_KEYS.favoriteProjects, JSON.stringify(newFavorites))
      return newFavorites
    })
  }, [])

  // Loading screen while config is loading or project not found
  const currentProject = rawConfig?.projects?.[currentProjectId]
  if (!rawConfig || !currentProjectId || !currentProject) {
    return (
      <div className="min-h-screen bg-gray-900 text-gray-100 flex items-center justify-center">
        <div className="text-center">
          {error ? (
            <>
              <XCircle className="w-16 h-16 text-red-400 mx-auto mb-4" />
              <h1 className="text-xl font-bold mb-2">Configuration Error</h1>
              <p className="text-gray-400">{error}</p>
              <button
                onClick={() => window.location.reload()}
                className="mt-4 px-4 py-2 bg-sky-600 hover:bg-sky-500 rounded-lg transition-colors"
              >
                Retry
              </button>
            </>
          ) : (
            <>
              <RefreshCw className="w-16 h-16 text-sky-500 mx-auto mb-4 animate-spin" />
              <h1 className="text-xl font-bold">Loading Dashboard...</h1>
            </>
          )}
        </div>
      </div>
    )
  }

  // Build the context value - merge global config with current project
  // This maintains backward compatibility with existing useConfig() usage
  const contextValue = {
    // Global config
    global: rawConfig.global,
    api: rawConfig.api,
    auth: rawConfig.auth,
    features: rawConfig.features || {},

    // Project-specific config (exposed at root level for backward compatibility)
    branding: {
      name: currentProject.name,
      title: `${currentProject.name} Operations`,
      logo: rawConfig.global.logo,
      logoAlt: rawConfig.global.logoAlt
    },
    aws: {
      ssoPortalUrl: rawConfig.global.ssoPortalUrl,
      defaultRegion: rawConfig.global.defaultRegion,
      accounts: currentProject.aws?.accounts || {}
    },
    // Services: use explicit list, or extract from topology components for EKS projects
    services: currentProject.services || (() => {
      // For EKS projects with topology, extract k8s-deployment/statefulset components as services
      if (currentProject.topology?.components) {
        return Object.entries(currentProject.topology.components)
          .filter(([_, comp]) => comp.type === 'k8s-deployment' || comp.type === 'k8s-statefulset')
          .map(([name, _]) => name)
      }
      return []
    })(),
    environments: currentProject.environments || [],
    serviceNaming: currentProject.serviceNaming || { prefix: currentProjectId },
    envColors: currentProject.envColors || {},
    infrastructure: currentProject.infrastructure || {},
    topology: currentProject.topology || null,

    // Per-project pipelines configuration
    pipelines: currentProject.pipelines || { enabled: false },

    // Project management
    currentProjectId,
    currentProject,
    projects: rawConfig.projects,
    projectList: Object.entries(rawConfig.projects).map(([id, project]) => ({
      id,
      ...project,
      isFavorite: favoriteProjects.includes(id)
    })),
    favoriteProjects,
    selectProject,
    toggleFavorite
  }

  return (
    <ConfigContext.Provider value={contextValue}>
      {children}
    </ConfigContext.Provider>
  )
}

/**
 * Hook to access the configuration
 * Returns the merged config (global + current project)
 * @returns {Object} The configuration object
 */
export function useConfig() {
  const config = useContext(ConfigContext)
  if (!config) {
    throw new Error('useConfig must be used within a ConfigProvider')
  }
  return config
}

/**
 * Hook to access project management functions
 */
export function useProjectManager() {
  const config = useConfig()
  return {
    currentProjectId: config.currentProjectId,
    currentProject: config.currentProject,
    projects: config.projects,
    projectList: config.projectList,
    favoriteProjects: config.favoriteProjects,
    selectProject: config.selectProject,
    toggleFavorite: config.toggleFavorite
  }
}

/**
 * Helper functions that work with config
 */
export function useConfigHelpers() {
  const config = useConfig()

  const getAwsConsoleUrl = (accountId, region = config.aws?.defaultRegion || 'eu-west-3') => {
    const destination = `https://${region}.console.aws.amazon.com/console/home?region=${region}`
    return `${config.global?.ssoPortalUrl || config.aws?.ssoPortalUrl}/#/console?account_id=${accountId}&destination=${encodeURIComponent(destination)}`
  }

  const getCodePipelineConsoleUrl = (accountId, region = config.aws?.defaultRegion || 'eu-west-3') => {
    const destination = `https://${region}.console.aws.amazon.com/codesuite/codepipeline/pipelines?region=${region}`
    return `${config.global?.ssoPortalUrl || config.aws?.ssoPortalUrl}/#/console?account_id=${accountId}&destination=${encodeURIComponent(destination)}`
  }

  const getServiceName = (env, service) => {
    const prefix = config.serviceNaming?.prefix || 'app'
    return `${prefix}-${env}-${service}`
  }

  const getDefaultAzs = (region = config.aws?.defaultRegion || 'eu-west-3') => {
    return [`${region}a`, `${region}b`]
  }

  return {
    getAwsConsoleUrl,
    getCodePipelineConsoleUrl,
    getServiceName,
    getDefaultAzs
  }
}

export default ConfigContext
