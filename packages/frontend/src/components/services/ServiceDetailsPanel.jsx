import { useState, useEffect, useCallback, useRef } from 'react'
import {
  RefreshCw, Clock, ExternalLink, Activity, AlertTriangle, FileText, Terminal,
  X, Rocket, Play, Square, Maximize2, Key, Lock
} from 'lucide-react'
import { useConfig } from '../../ConfigContext'
import { useAuth } from '../../hooks/useAuth'
import { fetchWithRetry, formatRelativeTime, PIPELINE_STATUS_COLORS } from '../../utils'
import EnvVarsSecretsPanel from '../common/EnvVarsSecretsPanel'

export default function ServiceDetailsPanel({ details, loading, onClose, metrics, onForceReload, onDeployLatest, onScaleService, actionLoading, onOpenLogsPanel }) {
  const { canDeploy, canScale } = useAuth()
  const [activeTab, setActiveTab] = useState('taskdef')
  const [logs, setLogs] = useState(details?.recentLogs || [])
  const [isTailing, setIsTailing] = useState(false)
  const logsContainerRef = useRef(null)

  // Get config from context
  const appConfig = useConfig()
  const currentProjectId = appConfig.currentProjectId
  const ENV_COLORS = appConfig.envColors || {}

  // Pipeline tailing state
  const [isPipelineTailing, setIsPipelineTailing] = useState(false)
  const [pipelineLogs, setPipelineLogs] = useState(details?.deployPipeline?.buildLogs || [])
  const pipelineLogsContainerRef = useRef(null)

  // Update logs when details change
  useEffect(() => {
    if (details?.recentLogs) {
      setLogs(details.recentLogs)
    }
  }, [details?.recentLogs])

  // Update pipeline logs when details change
  useEffect(() => {
    if (details?.deployPipeline?.buildLogs) {
      setPipelineLogs(details.deployPipeline.buildLogs)
    }
  }, [details?.deployPipeline?.buildLogs])

  // Fetch logs function for tailing (ECS logs)
  const fetchLogs = useCallback(async () => {
    if (!details?.environment || !details?.service || !currentProjectId) return
    try {
      const res = await fetchWithRetry(`/api/${currentProjectId}/logs/${details.environment}/${details.service}`)
      const data = await res.json()
      if (data.logs) {
        setLogs(data.logs)
      }
    } catch (error) {
      console.error('Error fetching logs:', error)
    }
  }, [details?.environment, details?.service, currentProjectId])

  // Fetch pipeline logs for tailing
  const fetchPipelineLogs = useCallback(async () => {
    if (!details?.environment || !details?.service || !currentProjectId) return
    try {
      const res = await fetchWithRetry(`/api/${currentProjectId}/details/${details.environment}/${details.service}`)
      const data = await res.json()
      if (data?.deployPipeline?.buildLogs) {
        setPipelineLogs(data.deployPipeline.buildLogs)
      }
    } catch (error) {
      console.error('Error fetching pipeline logs:', error)
    }
  }, [details?.environment, details?.service, currentProjectId])

  // Tailing effect for ECS logs
  useEffect(() => {
    let interval
    if (isTailing && activeTab === 'logs') {
      interval = setInterval(fetchLogs, 3000)
    }
    return () => { if (interval) clearInterval(interval) }
  }, [isTailing, activeTab, fetchLogs])

  // Tailing effect for pipeline logs
  useEffect(() => {
    let interval
    if (isPipelineTailing && activeTab === 'pipeline') {
      fetchPipelineLogs() // Initial fetch
      interval = setInterval(fetchPipelineLogs, 3000)
    }
    return () => { if (interval) clearInterval(interval) }
  }, [isPipelineTailing, activeTab, fetchPipelineLogs])

  // Auto-scroll to bottom when logs change (always, not just when tailing)
  useEffect(() => {
    if (logsContainerRef.current) {
      const container = logsContainerRef.current
      container.scrollTop = container.scrollHeight
    }
  }, [logs])

  // Auto-scroll to bottom when pipeline logs change (always, not just when tailing)
  useEffect(() => {
    if (pipelineLogsContainerRef.current) {
      const container = pipelineLogsContainerRef.current
      container.scrollTop = container.scrollHeight
    }
  }, [pipelineLogs])

  if (loading) {
    return (
      <div className="fixed right-0 top-[73px] h-[calc(100vh-73px)] w-[500px] bg-gray-800 border-l border-gray-700 shadow-xl z-40 overflow-y-auto">
        <div className="flex items-center justify-center h-full">
          <RefreshCw className="w-8 h-8 text-brand-500 animate-spin" />
        </div>
      </div>
    )
  }

  if (!details || details.error) {
    return (
      <div className="fixed right-0 top-[73px] h-[calc(100vh-73px)] w-[500px] bg-gray-800 border-l border-gray-700 shadow-xl z-40 overflow-y-auto">
        <div className="p-4">
          <button onClick={onClose} className="absolute top-4 right-4 text-gray-400 hover:text-white">
            <X className="w-5 h-5" />
          </button>
          <p className="text-red-400">{details?.error || 'Failed to load details'}</p>
        </div>
      </div>
    )
  }

  const currentTd = details.currentTaskDefinition
  const latestTd = details.latestTaskDefinition
  const colors = ENV_COLORS[details.environment] || { bg: 'bg-gray-500', text: 'text-gray-400', border: 'border-gray-500' }

  // Combine environment variables and secrets for display, sorted alphabetically
  const allEnvVars = [
    ...(details.environmentVariables || []),
    ...(details.secrets || [])
  ].sort((a, b) => a.name.localeCompare(b.name))

  return (
    <div className="fixed right-0 top-[73px] h-[calc(100vh-73px)] w-[500px] bg-gray-800 border-l border-gray-700 shadow-xl z-40 overflow-y-auto">
      {/* Header */}
      <div className="sticky top-0 bg-gray-800 border-b border-gray-700 p-4 z-10">
        <div className="flex items-center justify-between">
          <div>
            <div className="flex items-center gap-2">
              <span className={`w-2 h-2 rounded-full ${colors.bg}`}></span>
              <h2 className="text-lg font-semibold capitalize">{details.service}</h2>
              <span className={`text-sm ${colors.text}`}>({details.environment})</span>
            </div>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-white">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Last Deploy Info */}
        <div className="mt-3 flex items-center gap-4 text-sm">
          <div className="flex items-center gap-1 text-gray-400">
            <Clock className="w-4 h-4" />
            <span>Last deploy: {formatRelativeTime(details.lastDeployment)}</span>
          </div>
          {!details.isLatest && (
            <span className="px-2 py-0.5 bg-yellow-500/20 text-yellow-400 text-xs rounded">
              Not latest
            </span>
          )}
          {details.deploymentState === 'rolling_back' && (
            <span className="px-2 py-0.5 bg-red-500/20 text-red-400 text-xs rounded animate-pulse">
              Rollback
            </span>
          )}
          {details.deploymentState === 'in_progress' && (
            <span className="px-2 py-0.5 bg-blue-500/20 text-blue-400 text-xs rounded animate-pulse">
              Deploying
            </span>
          )}
          {details.deploymentState === 'failed' && (
            <span className="px-2 py-0.5 bg-red-500/20 text-red-400 text-xs rounded">
              Failed
            </span>
          )}
        </div>

        {/* Rollback Warning Banner */}
        {details.isRollingBack && details.lastRollbackEvent && (
          <div className="mt-3 p-3 bg-red-900/30 border border-red-700 rounded-lg">
            <div className="flex items-start gap-2">
              <AlertTriangle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
              <div>
                <h4 className="text-red-400 font-medium text-sm">Deployment Rollback Detected</h4>
                <p className="text-gray-300 text-xs mt-1">{details.lastRollbackEvent.message}</p>
                <p className="text-gray-500 text-xs mt-1">{formatRelativeTime(details.lastRollbackEvent.createdAt)}</p>
              </div>
            </div>
          </div>
        )}

        {/* Console Links */}
        <div className="mt-3 flex flex-wrap gap-2">
          <a
            href={details.consoleUrls?.service}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1 px-2 py-1 bg-gray-700 hover:bg-gray-600 rounded text-xs"
          >
            <ExternalLink className="w-3 h-3" />
            Service
          </a>
          <a
            href={details.consoleUrls?.secret}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1 px-2 py-1 bg-gray-700 hover:bg-gray-600 rounded text-xs"
          >
            <Key className="w-3 h-3" />
            Secret
          </a>
          <a
            href={details.consoleUrls?.logs}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1 px-2 py-1 bg-gray-700 hover:bg-gray-600 rounded text-xs"
          >
            <Terminal className="w-3 h-3" />
            Logs
          </a>
          <a
            href={details.consoleUrls?.taskDefinitions}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1 px-2 py-1 bg-gray-700 hover:bg-gray-600 rounded text-xs"
          >
            <FileText className="w-3 h-3" />
            Task Defs
          </a>
        </div>

        {/* Actions - requires operator or admin permissions */}
        {(() => {
          const hasScalePermission = canScale(currentProjectId, details.environment, details.service)
          const hasDeployPermission = canDeploy(currentProjectId, details.environment, details.service)
          const hasAnyPermission = hasScalePermission || hasDeployPermission

          if (!hasAnyPermission) {
            return (
              <div className="mt-3 pt-3 border-t border-gray-700">
                <div className="flex items-center justify-center gap-2 py-2 text-gray-500 text-sm">
                  <Lock className="w-4 h-4" />
                  <span>Viewer access - actions require operator or admin role</span>
                </div>
              </div>
            )
          }

          return (
            <div className="mt-3 pt-3 border-t border-gray-700">
              <div className="flex gap-2">
                <div className="flex-1">
                  {details.desiredCount === 0 ? (
                    <>
                      <button
                        onClick={() => onScaleService?.(details.environment, details.service, 'start')}
                        disabled={!hasScalePermission || actionLoading?.[`scale-${details.environment}-${details.service}`]}
                        title={!hasScalePermission ? 'Scale permission required' : undefined}
                        className="w-full flex items-center justify-center gap-2 px-3 py-1.5 bg-green-600 hover:bg-green-500 disabled:bg-gray-600 disabled:opacity-50 rounded text-sm font-medium transition-colors"
                      >
                        {actionLoading?.[`scale-${details.environment}-${details.service}`] ? (
                          <RefreshCw className="w-4 h-4 animate-spin" />
                        ) : !hasScalePermission ? (
                          <Lock className="w-4 h-4" />
                        ) : (
                          <Play className="w-4 h-4" />
                        )}
                        Start
                      </button>
                      <p className="text-xs text-gray-500 mt-1 text-center">Scale to N replicas</p>
                    </>
                  ) : (
                    <>
                      <button
                        onClick={() => onScaleService?.(details.environment, details.service, 'stop')}
                        disabled={!hasScalePermission || actionLoading?.[`scale-${details.environment}-${details.service}`]}
                        title={!hasScalePermission ? 'Scale permission required' : undefined}
                        className="w-full flex items-center justify-center gap-2 px-3 py-1.5 bg-red-600 hover:bg-red-500 disabled:bg-gray-600 disabled:opacity-50 rounded text-sm font-medium transition-colors"
                      >
                        {actionLoading?.[`scale-${details.environment}-${details.service}`] ? (
                          <RefreshCw className="w-4 h-4 animate-spin" />
                        ) : !hasScalePermission ? (
                          <Lock className="w-4 h-4" />
                        ) : (
                          <Square className="w-4 h-4" />
                        )}
                        Stop
                      </button>
                      <p className="text-xs text-gray-500 mt-1 text-center">Scale to 0 replicas</p>
                    </>
                  )}
                </div>
                <div className="flex-1">
                  <button
                    onClick={() => onForceReload?.(details.environment, details.service)}
                    disabled={!hasDeployPermission || actionLoading?.[`reload-${details.environment}-${details.service}`]}
                    title={!hasDeployPermission ? 'Deploy permission required' : undefined}
                    className="w-full flex items-center justify-center gap-2 px-3 py-1.5 bg-orange-600 hover:bg-orange-500 disabled:bg-gray-600 disabled:opacity-50 rounded text-sm font-medium transition-colors"
                  >
                    {actionLoading?.[`reload-${details.environment}-${details.service}`] ? (
                      <RefreshCw className="w-4 h-4 animate-spin" />
                    ) : !hasDeployPermission ? (
                      <Lock className="w-4 h-4" />
                    ) : (
                      <RefreshCw className="w-4 h-4" />
                    )}
                    Reload
                  </button>
                  <p className="text-xs text-gray-500 mt-1 text-center">Restart tasks (reload secrets)</p>
                </div>
                <div className="flex-1">
                  <button
                    onClick={() => onDeployLatest?.(details.environment, details.service)}
                    disabled={!hasDeployPermission || actionLoading?.[`deploy-${details.environment}-${details.service}`] || details.deployPipeline?.lastExecution?.status === 'InProgress'}
                    title={!hasDeployPermission ? 'Deploy permission required' : undefined}
                    className="w-full flex items-center justify-center gap-2 px-3 py-1.5 bg-blue-600 hover:bg-blue-500 disabled:bg-gray-600 disabled:opacity-50 rounded text-sm font-medium transition-colors"
                  >
                    {actionLoading?.[`deploy-${details.environment}-${details.service}`] ? (
                      <RefreshCw className="w-4 h-4 animate-spin" />
                    ) : !hasDeployPermission ? (
                      <Lock className="w-4 h-4" />
                    ) : (
                      <Rocket className="w-4 h-4" />
                    )}
                    Deploy Latest
                  </button>
                  <p className="text-xs text-gray-500 mt-1 text-center">Update image & task def</p>
                </div>
              </div>
            </div>
          )
        })()}
      </div>

      {/* Tabs */}
      <div className="border-b border-gray-700 flex overflow-x-auto">
        <button
          onClick={() => setActiveTab('taskdef')}
          className={`px-3 py-2 text-sm font-medium whitespace-nowrap ${activeTab === 'taskdef' ? 'text-brand-400 border-b-2 border-brand-400' : 'text-gray-400'}`}
        >
          Task Defs
        </button>
        <button
          onClick={() => setActiveTab('pipeline')}
          className={`px-3 py-2 text-sm font-medium whitespace-nowrap ${activeTab === 'pipeline' ? 'text-brand-400 border-b-2 border-brand-400' : 'text-gray-400'}`}
        >
          Pipeline
          {details.deployPipeline?.lastExecution?.status === 'InProgress' && (
            <span className="ml-1 w-2 h-2 bg-yellow-500 rounded-full inline-block animate-pulse"></span>
          )}
        </button>
        <button
          onClick={() => setActiveTab('envvars')}
          className={`px-3 py-2 text-sm font-medium whitespace-nowrap ${activeTab === 'envvars' ? 'text-brand-400 border-b-2 border-brand-400' : 'text-gray-400'}`}
        >
          Env Vars
        </button>
        <button
          onClick={() => setActiveTab('logs')}
          className={`px-3 py-2 text-sm font-medium whitespace-nowrap ${activeTab === 'logs' ? 'text-brand-400 border-b-2 border-brand-400' : 'text-gray-400'}`}
        >
          Logs
        </button>
        <button
          onClick={() => setActiveTab('events')}
          className={`px-3 py-2 text-sm font-medium whitespace-nowrap ${activeTab === 'events' ? 'text-brand-400 border-b-2 border-brand-400' : 'text-gray-400'}`}
        >
          Events
          {details.isRollingBack && (
            <span className="ml-1 w-2 h-2 bg-red-500 rounded-full inline-block animate-pulse"></span>
          )}
        </button>
      </div>

      {/* Tab Content */}
      <div className="p-4">
        {activeTab === 'taskdef' && (
          <div className="space-y-4">
            {/* Current Task Definition */}
            <div className="bg-gray-900 rounded-lg p-3">
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-green-400">Current (Active)</span>
                  <span className="text-xs text-gray-500">Rev {currentTd.revision}</span>
                </div>
                <a
                  href={currentTd.consoleUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-gray-400 hover:text-brand-400"
                >
                  <ExternalLink className="w-4 h-4" />
                </a>
              </div>
              <div className="text-xs text-gray-400 space-y-1">
                <p><span className="text-gray-500">Image:</span> {currentTd.imageTag}</p>
                <p><span className="text-gray-500">CPU:</span> {currentTd.cpu} | <span className="text-gray-500">Memory:</span> {currentTd.memory}MB</p>
                <p><span className="text-gray-500">Env vars:</span> {allEnvVars.length}</p>
              </div>
            </div>

            {/* Latest Task Definition with Diff */}
            {(latestTd.revision !== currentTd.revision || currentTd.latestDiff) && (
              <div className="bg-gray-900 rounded-lg p-3 border border-yellow-500/30">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-yellow-400">Latest (Not deployed)</span>
                    <span className="text-xs text-gray-500">Rev {currentTd.latestDiff?.latestRevision || latestTd.revision}</span>
                  </div>
                  <a
                    href={latestTd.consoleUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-gray-400 hover:text-brand-400"
                  >
                    <ExternalLink className="w-4 h-4" />
                  </a>
                </div>

                {/* Diff display */}
                {currentTd.latestDiff?.changes?.length > 0 ? (
                  <div className="mt-2 border-t border-gray-700 pt-2">
                    <p className="text-xs font-medium text-yellow-400 mb-2">Changes from Rev {currentTd.latestDiff.currentRevision} to Rev {currentTd.latestDiff.latestRevision}:</p>
                    <div className="space-y-1">
                      {currentTd.latestDiff.changes.map((change, i) => (
                        <div key={i} className="text-xs grid grid-cols-3 gap-2 py-1 border-b border-gray-800 last:border-0">
                          <span className="text-gray-400 font-medium">{change.label}</span>
                          <span className="text-red-400 truncate" title={change.current}>{change.current}</span>
                          <span className="text-green-400 truncate" title={change.latest}>{change.latest}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                ) : (
                  <div className="text-xs text-gray-400 space-y-1">
                    <p><span className="text-gray-500">Image:</span> {latestTd.imageTag}</p>
                    <p><span className="text-gray-500">CPU:</span> {latestTd.cpu} | <span className="text-gray-500">Memory:</span> {latestTd.memory}MB</p>
                  </div>
                )}
              </div>
            )}

            {/* ECS Deployments */}
            <div>
              <h4 className="text-sm font-medium mb-2">ECS Deployments</h4>
              <p className="text-xs text-gray-500 mb-2">Task definition rollouts managed by ECS</p>
              <div className="space-y-2">
                {details.ecsDeployments?.map((d, i) => (
                  <div key={i} className="bg-gray-900 rounded p-2 text-xs">
                    <div className="flex items-center justify-between">
                      <span className={`font-medium ${d.status === 'PRIMARY' ? 'text-green-400' : 'text-gray-400'}`}>
                        {d.status}
                      </span>
                      <span className="text-gray-500">{d.taskDefinition}</span>
                    </div>
                    <div className="text-gray-500 mt-1">
                      {d.runningCount}/{d.desiredCount} tasks | {formatRelativeTime(d.updatedAt)}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {activeTab === 'pipeline' && (
          <div className="space-y-4">
            {details.deployPipeline ? (
              <>
                {/* Pipeline Header */}
                <div className="flex items-center justify-between">
                  <div>
                    <h4 className="text-sm font-medium">{details.deployPipeline.pipelineName}</h4>
                    <p className="text-xs text-gray-500">CodePipeline deployments</p>
                  </div>
                  <a
                    href={details.deployPipeline.consoleUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-1 px-2 py-1 bg-gray-700 hover:bg-gray-600 rounded text-xs"
                  >
                    <ExternalLink className="w-3 h-3" />
                    View Pipeline
                  </a>
                </div>

                {/* Current Pipeline Status */}
                {details.deployPipeline.stages && (
                  <div className="bg-gray-900 rounded-lg p-3">
                    <div className="text-xs text-gray-400 mb-2">Current Status</div>
                    <div className="flex gap-1 mb-2">
                      {details.deployPipeline.stages.map((stage, i) => (
                        <div
                          key={i}
                          className={`flex-1 h-2 rounded-full ${PIPELINE_STATUS_COLORS[stage.status] || 'bg-gray-600'}`}
                          title={`${stage.name}: ${stage.status}`}
                        />
                      ))}
                    </div>
                    <div className="flex justify-between text-xs text-gray-500">
                      {details.deployPipeline.stages.map((stage, i) => (
                        <span key={i} className="truncate">{stage.name}</span>
                      ))}
                    </div>
                  </div>
                )}

                {/* Build Logs if In Progress - with Tailing */}
                {details.deployPipeline.lastExecution?.status === 'InProgress' && (
                  <div className="bg-gray-900 rounded-lg p-3">
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <span className="w-2 h-2 bg-yellow-500 rounded-full animate-pulse"></span>
                        <span className="text-xs text-yellow-400">Deployment in progress</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => onOpenLogsPanel?.({
                            env: details.environment,
                            service: details.service,
                            type: 'deploy',
                            autoTail: true
                          })}
                          className="text-xs px-2 py-1 bg-gray-700 hover:bg-gray-600 rounded text-gray-300 flex items-center gap-1"
                          title="Open in bottom panel"
                        >
                          <Maximize2 className="w-3 h-3" />
                          Expand
                        </button>
                        <button
                          onClick={fetchPipelineLogs}
                          className="text-xs px-2 py-1 bg-gray-700 hover:bg-gray-600 rounded text-gray-300"
                          title="Refresh logs"
                        >
                          <RefreshCw className={`w-3 h-3 ${isPipelineTailing ? 'animate-spin' : ''}`} />
                        </button>
                        <button
                          onClick={() => setIsPipelineTailing(!isPipelineTailing)}
                          className={`text-xs px-3 py-1 rounded flex items-center gap-1 ${
                            isPipelineTailing ? 'bg-green-500/20 text-green-400 border border-green-500/50' : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                          }`}
                        >
                          <Activity className={`w-3 h-3 ${isPipelineTailing ? 'animate-pulse' : ''}`} />
                          {isPipelineTailing ? 'Tailing...' : 'Tail'}
                        </button>
                      </div>
                    </div>
                    <div ref={pipelineLogsContainerRef} className="bg-gray-950 rounded p-2 max-h-[250px] overflow-y-auto scrollbar-brand font-mono text-xs">
                      {pipelineLogs && pipelineLogs.length > 0 ? (
                        <>
                          {pipelineLogs.map((log, i) => (
                            <div key={i} className="py-0.5 text-gray-400 hover:bg-gray-800/50">
                              <span className="text-gray-600">{new Date(log.timestamp).toLocaleTimeString()}</span>
                              <span className={`ml-2 ${log.message?.includes('Error') || log.message?.includes('error') ? 'text-red-400' : 'text-gray-300'}`}>{log.message}</span>
                            </div>
                          ))}
                        </>
                      ) : (
                        <p className="text-gray-500 italic">No logs available. Click "Tail" to start streaming.</p>
                      )}
                    </div>
                    {isPipelineTailing && (
                      <div className="mt-2 flex items-center gap-2 text-xs text-green-400">
                        <div className="w-2 h-2 bg-green-400 rounded-full animate-pulse" />
                        Live - Refreshing every 3s
                      </div>
                    )}
                  </div>
                )}

                {/* Last 5 Executions */}
                <div>
                  <h4 className="text-sm font-medium mb-2">Recent Pipeline Executions</h4>
                  <div className="space-y-2">
                    {details.deployPipeline.executions?.map((exec, i) => (
                      <div key={i} className="bg-gray-900 rounded p-2 text-xs">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            <span className={`font-medium ${
                              exec.status === 'Succeeded' ? 'text-green-400' :
                              exec.status === 'Failed' ? 'text-red-400' :
                              exec.status === 'InProgress' ? 'text-yellow-400' :
                              'text-gray-400'
                            }`}>
                              {exec.status}
                              {exec.status === 'InProgress' && (
                                <span className="ml-1 w-1.5 h-1.5 bg-yellow-500 rounded-full inline-block animate-pulse"></span>
                              )}
                            </span>
                            {exec.consoleUrl && (
                              <a
                                href={exec.consoleUrl}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-gray-500 hover:text-brand-400"
                                title="View execution"
                              >
                                <ExternalLink className="w-3 h-3" />
                              </a>
                            )}
                          </div>
                          <span className="text-gray-500 font-mono">{exec.id.substring(0, 8)}</span>
                        </div>
                        <div className="text-gray-500 mt-1">
                          Started: {formatRelativeTime(exec.startTime)}
                          {exec.lastUpdateTime && exec.lastUpdateTime !== exec.startTime && (
                            <span> | Updated: {formatRelativeTime(exec.lastUpdateTime)}</span>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </>
            ) : (
              <p className="text-gray-500 text-sm">No pipeline information available</p>
            )}
          </div>
        )}

        {activeTab === 'envvars' && (
          <div className="space-y-4">
            <div className="flex items-center justify-between mb-2">
              <div className="text-xs text-gray-400">
                Showing variables from current task definition (Rev {currentTd.revision})
              </div>
              <span className="text-xs text-gray-500">
                {allEnvVars.length} vars
              </span>
            </div>

            <EnvVarsSecretsPanel
              environmentVariables={details.environmentVariables}
              secrets={details.secrets}
              consoleUrls={details.consoleUrls}
              variant="inline"
              showTitle={false}
              emptyMessage="No environment variables configured"
            />
          </div>
        )}

        {activeTab === 'logs' && (
          <div className="space-y-2">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs text-gray-400">
                Recent logs ({logs.length} entries)
                {isTailing && <span className="ml-2 text-green-400 animate-pulse">Tailing...</span>}
              </span>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => onOpenLogsPanel?.({
                    env: details.environment,
                    service: details.service,
                    logs: logs,
                    consoleUrl: details.consoleUrls?.logs
                  })}
                  className="text-xs text-gray-400 hover:text-white flex items-center gap-1 px-2 py-1 bg-gray-700 rounded"
                  title="Open in bottom panel"
                >
                  <Maximize2 className="w-3 h-3" />
                  Expand
                </button>
                <button
                  onClick={fetchLogs}
                  className="text-xs text-gray-400 hover:text-white flex items-center gap-1 px-2 py-1 bg-gray-700 rounded"
                >
                  <RefreshCw className="w-3 h-3" />
                  Refresh
                </button>
                <button
                  onClick={() => setIsTailing(!isTailing)}
                  className={`text-xs flex items-center gap-1 px-2 py-1 rounded ${
                    isTailing ? 'bg-green-600 text-white' : 'bg-gray-700 text-gray-400 hover:text-white'
                  }`}
                >
                  <Play className="w-3 h-3" />
                  {isTailing ? 'Stop' : 'Tail'}
                </button>
                <a
                  href={details.consoleUrls?.logs}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs text-brand-400 hover:text-brand-300 flex items-center gap-1"
                >
                  <ExternalLink className="w-3 h-3" />
                  Full logs
                </a>
              </div>
            </div>

            <div ref={logsContainerRef} className="bg-gray-900 rounded-lg p-2 max-h-[500px] overflow-y-auto scrollbar-brand font-mono text-xs">
              {logs.length > 0 ? (
                logs.map((log, i) => (
                  <div key={i} className="py-1 border-b border-gray-800 last:border-0">
                    <span className="text-gray-500">{new Date(log.timestamp).toLocaleTimeString()}</span>
                    <span className="text-gray-600 mx-2">[{log.stream}]</span>
                    <span className="text-gray-300 break-all">{log.message}</span>
                  </div>
                ))
              ) : (
                <p className="text-gray-500 text-center py-4">No recent logs available</p>
              )}
            </div>
          </div>
        )}

        {activeTab === 'events' && (
          <div className="space-y-3">
            <div className="text-xs text-gray-400 mb-2">
              Recent ECS service events (last 10)
            </div>

            {/* ECS Deployments Summary */}
            {details.ecsDeployments?.length > 0 && (
              <div className="bg-gray-900 rounded-lg p-3 mb-4">
                <h4 className="text-sm font-medium mb-2 text-gray-300">Active Deployments</h4>
                <div className="space-y-2">
                  {details.ecsDeployments.map((dep, i) => (
                    <div key={i} className={`text-xs p-2 rounded ${
                      dep.rolloutState === 'FAILED' ? 'bg-red-900/20 border border-red-800' :
                      dep.rolloutState === 'IN_PROGRESS' ? 'bg-yellow-900/20 border border-yellow-800' :
                      'bg-gray-800'
                    }`}>
                      <div className="flex items-center justify-between">
                        <span className="font-medium text-gray-300">
                          {dep.status}
                          {dep.status === 'PRIMARY' && <span className="ml-1 text-green-400">(active)</span>}
                        </span>
                        <span className={`px-1.5 py-0.5 rounded text-xs ${
                          dep.rolloutState === 'COMPLETED' ? 'bg-green-500/20 text-green-400' :
                          dep.rolloutState === 'IN_PROGRESS' ? 'bg-yellow-500/20 text-yellow-400' :
                          dep.rolloutState === 'FAILED' ? 'bg-red-500/20 text-red-400' :
                          'bg-gray-600 text-gray-300'
                        }`}>
                          {dep.rolloutState || 'UNKNOWN'}
                        </span>
                      </div>
                      <div className="mt-1 text-gray-500">
                        <span>Rev: {dep.taskDefinition.split(':').pop()}</span>
                        <span className="mx-2">|</span>
                        <span>Running: {dep.runningCount}/{dep.desiredCount}</span>
                        {dep.pendingCount > 0 && <span className="ml-2 text-yellow-400">(+{dep.pendingCount} pending)</span>}
                      </div>
                      {dep.rolloutStateReason && (
                        <div className="mt-1 text-red-400 text-xs italic">{dep.rolloutStateReason}</div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* ECS Events List */}
            <div className="bg-gray-900 rounded-lg overflow-hidden">
              {details.ecsEvents?.length > 0 ? (
                details.ecsEvents.map((event, i) => {
                  const isRollback = event.message?.toLowerCase().includes('rolling back')
                  const isFailed = event.message?.toLowerCase().includes('failed')
                  const isStopped = event.message?.toLowerCase().includes('stopped')
                  const isStarted = event.message?.toLowerCase().includes('started')
                  const isSteady = event.message?.toLowerCase().includes('steady state')

                  return (
                    <div key={event.id || i} className={`p-3 border-b border-gray-800 last:border-0 ${
                      isRollback || isFailed ? 'bg-red-900/10' :
                      isSteady ? 'bg-green-900/10' :
                      ''
                    }`}>
                      <div className="flex items-start gap-2">
                        <div className={`w-2 h-2 rounded-full mt-1.5 flex-shrink-0 ${
                          isRollback || isFailed ? 'bg-red-500' :
                          isStopped ? 'bg-yellow-500' :
                          isStarted ? 'bg-blue-500' :
                          isSteady ? 'bg-green-500' :
                          'bg-gray-500'
                        }`} />
                        <div className="flex-1 min-w-0">
                          <p className={`text-xs break-words ${
                            isRollback || isFailed ? 'text-red-300' :
                            isSteady ? 'text-green-300' :
                            'text-gray-300'
                          }`}>
                            {event.message}
                          </p>
                          <p className="text-xs text-gray-500 mt-1">
                            {formatRelativeTime(event.createdAt)}
                          </p>
                        </div>
                      </div>
                    </div>
                  )
                })
              ) : (
                <p className="text-gray-500 text-sm p-4 text-center">No recent events</p>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
