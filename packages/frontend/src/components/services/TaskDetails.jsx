import { useState, useEffect, useCallback, useRef } from 'react'
import {
  RefreshCw, Server, Clock, ExternalLink, Package,
  Activity, XCircle, AlertCircle, FileText, Terminal, MapPin,
  Layers, Maximize2
} from 'lucide-react'
import SecurityGroupsPanel from '../infrastructure/SecurityGroupsPanel'
import EnvVarsSecretsPanel from '../common/EnvVarsSecretsPanel'
import CollapsibleSection from '../common/CollapsibleSection'
import { useConfig } from '../../ConfigContext'
import { fetchWithRetry } from '../../utils'

export default function TaskDetails({ task, env, onOpenLogsPanel }) {
  const appConfig = useConfig()
  const currentProjectId = appConfig.currentProjectId
  const [details, setDetails] = useState(null)
  const [loading, setLoading] = useState(true)
  const [isTailing, setIsTailing] = useState(false)
  const [securityGroups, setSecurityGroups] = useState([])
  const logsContainerRef = useRef(null)

  const fetchTaskDetails = useCallback(() => {
    const taskId = task?.fullId || task?.taskId
    if (taskId && task?.service && currentProjectId) {
      return fetchWithRetry(`/api/${currentProjectId}/tasks/${env}/${task.service}/${taskId}`)
        .then(res => res.json())
        .then(data => {
          setDetails(data)
          return data
        })
        .catch(err => {
          console.error('Failed to fetch task details:', err)
        })
    }
  }, [task?.fullId, task?.taskId, task?.service, env, currentProjectId])

  useEffect(() => {
    setLoading(true)
    fetchTaskDetails().finally(() => setLoading(false))
  }, [fetchTaskDetails])

  // Tailing effect
  useEffect(() => {
    let interval
    if (isTailing) {
      interval = setInterval(fetchTaskDetails, 3000)
    }
    return () => { if (interval) clearInterval(interval) }
  }, [isTailing, fetchTaskDetails])

  // Auto-scroll to bottom when logs change (always, not just when tailing)
  useEffect(() => {
    if (logsContainerRef.current) {
      const container = logsContainerRef.current
      container.scrollTop = container.scrollHeight
    }
  }, [details?.logs])

  // Fetch security groups from ENI when available
  useEffect(() => {
    const privateIp = details?.placement?.privateIp
    if (privateIp && env && currentProjectId) {
      fetchWithRetry(`/api/${currentProjectId}/infrastructure/${env}/enis?searchIp=${encodeURIComponent(privateIp)}`)
        .then(res => res.json())
        .then(data => {
          // Find the ENI that matches this task's private IP
          const matchingEni = data?.enis?.find(eni => eni.privateIp === privateIp)
          if (matchingEni?.securityGroups) {
            setSecurityGroups(matchingEni.securityGroups)
          }
        })
        .catch(err => console.error('Failed to fetch ENI security groups:', err))
    }
  }, [details?.placement?.privateIp, env, currentProjectId])

  if (!task) {
    return <p className="text-red-400">Task data not available</p>
  }

  const formatDate = (dateStr) => {
    if (!dateStr) return '-'
    const date = new Date(dateStr)
    return date.toLocaleString('fr-FR', { dateStyle: 'short', timeStyle: 'medium' })
  }

  const getStatusColor = (status) => {
    switch (status) {
      case 'RUNNING': return 'text-green-400'
      case 'PENDING': return 'text-yellow-400'
      case 'STOPPED': return 'text-red-400'
      default: return 'text-gray-400'
    }
  }

  const getHealthColor = (health) => {
    switch (health) {
      case 'HEALTHY': return 'text-green-400'
      case 'UNHEALTHY': return 'text-red-400'
      default: return 'text-gray-400'
    }
  }

  const d = details || task

  return (
    <div className="space-y-4">
      {/* Loading indicator */}
      {loading && (
        <div className="flex items-center justify-center py-2">
          <RefreshCw className="w-4 h-4 text-brand-500 animate-spin mr-2" />
          <span className="text-sm text-gray-400">Loading details...</span>
        </div>
      )}

      {/* Status Banner */}
      <div className={`rounded-lg p-4 ${task.isLatest ? 'bg-green-500/20 border border-green-500/50' : 'bg-orange-500/20 border border-orange-500/50'}`}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className={`w-3 h-3 rounded-full ${d.status === 'RUNNING' ? 'bg-green-500' : d.status === 'PENDING' ? 'bg-yellow-500 animate-pulse' : 'bg-red-500'}`} />
            <span className={`font-medium ${task.isLatest ? 'text-green-400' : 'text-orange-400'}`}>
              {task.isLatest ? 'Latest Revision' : 'Old Revision (Draining)'}
            </span>
          </div>
          <span className={`text-sm font-medium ${getStatusColor(d.status)}`}>{d.status}</span>
        </div>
      </div>

      {/* Quick Actions */}
      {details?.consoleUrls && (
        <div className="grid grid-cols-2 gap-2">
          <a href={details.consoleUrls.task} target="_blank" rel="noopener noreferrer"
             className="flex items-center justify-center gap-2 bg-blue-500/20 hover:bg-blue-500/30 text-blue-400 py-2 px-3 rounded-lg text-sm transition-colors">
            <Server className="w-4 h-4" />
            Task Console
          </a>
          <a href={details.consoleUrls.ecsExec} target="_blank" rel="noopener noreferrer"
             className="flex items-center justify-center gap-2 bg-green-500/20 hover:bg-green-500/30 text-green-400 py-2 px-3 rounded-lg text-sm transition-colors">
            <Terminal className="w-4 h-4" />
            ECS Exec
          </a>
          <a href={details.consoleUrls.logs} target="_blank" rel="noopener noreferrer"
             className="flex items-center justify-center gap-2 bg-purple-500/20 hover:bg-purple-500/30 text-purple-400 py-2 px-3 rounded-lg text-sm transition-colors">
            <FileText className="w-4 h-4" />
            CloudWatch Logs
          </a>
          <a href={details.consoleUrls.service} target="_blank" rel="noopener noreferrer"
             className="flex items-center justify-center gap-2 bg-gray-500/20 hover:bg-gray-500/30 text-gray-400 py-2 px-3 rounded-lg text-sm transition-colors">
            <Layers className="w-4 h-4" />
            Service
          </a>
        </div>
      )}

      {/* ECS Exec Status */}
      {details && (
        <div className={`rounded-lg p-3 ${details.enableExecuteCommand ? 'bg-green-500/10 border border-green-500/30' : 'bg-yellow-500/10 border border-yellow-500/30'}`}>
          <div className="flex items-center gap-2">
            <Terminal className={`w-4 h-4 ${details.enableExecuteCommand ? 'text-green-400' : 'text-yellow-400'}`} />
            <span className={`text-sm ${details.enableExecuteCommand ? 'text-green-400' : 'text-yellow-400'}`}>
              ECS Exec: {details.enableExecuteCommand ? 'Active' : 'Desactive'}
            </span>
          </div>
        </div>
      )}

      {/* Task Info */}
      <CollapsibleSection title="Task Info" icon={Server} iconColor="text-blue-400" defaultOpen={false}>
        <div className="space-y-2 text-sm">
          <div className="flex justify-between">
            <span className="text-gray-500">Task ID</span>
            <span className="text-gray-300 font-mono text-xs">{d.taskId || task.fullId}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-500">Service</span>
            <span className="text-gray-300 capitalize">{d.service || task.service}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-500">Status</span>
            <span className={getStatusColor(d.status)}>{d.status}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-500">Health</span>
            <span className={getHealthColor(d.health)}>{d.health}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-500">Revision</span>
            <span className={`font-mono ${task.isLatest ? 'text-green-400' : 'text-orange-400'}`}>{d.revision || task.revision}</span>
          </div>
          {details?.launchType && (
            <div className="flex justify-between">
              <span className="text-gray-500">Launch Type</span>
              <span className="text-gray-300">{details.launchType}</span>
            </div>
          )}
          {details?.platformVersion && (
            <div className="flex justify-between">
              <span className="text-gray-500">Platform</span>
              <span className="text-gray-300">{details.platformVersion}</span>
            </div>
          )}
        </div>
      </CollapsibleSection>

      {/* Placement Info */}
      <CollapsibleSection title="Placement" icon={MapPin} iconColor="text-purple-400" defaultOpen={false}>
        <div className="space-y-2 text-sm">
          <div className="flex justify-between">
            <span className="text-gray-500">Availability Zone</span>
            <span className="text-gray-300 font-mono">{details?.placement?.az || task.az || '-'}</span>
          </div>
          {(details?.placement?.privateIp) && (
            <div className="flex justify-between">
              <span className="text-gray-500">Private IP</span>
              <span className="text-gray-300 font-mono">{details.placement.privateIp}</span>
            </div>
          )}
          {(details?.placement?.subnetId || task.subnetId) && (
            <div className="flex justify-between">
              <span className="text-gray-500">Subnet ID</span>
              <span className="text-gray-300 font-mono text-xs">{details?.placement?.subnetId || task.subnetId}</span>
            </div>
          )}
          {details?.placement?.eniId && (
            <div className="flex justify-between">
              <span className="text-gray-500">ENI ID</span>
              <span className="text-gray-300 font-mono text-xs">{details.placement.eniId}</span>
            </div>
          )}
        </div>
      </CollapsibleSection>

      {/* Container Info */}
      {details?.container && (
        <CollapsibleSection title="Container" icon={Package} iconColor="text-cyan-400" defaultOpen={false}>
          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-gray-500">Name</span>
              <span className="text-gray-300">{details.container.name}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Image</span>
              <span className="text-gray-300 font-mono text-xs truncate max-w-[200px]" title={details.container.image}>
                {details.container.image?.split('/').pop()?.split(':')[0]}
              </span>
            </div>
            {details.container.imageDigest && (
              <div className="flex justify-between">
                <span className="text-gray-500">Digest</span>
                <span className="text-gray-300 font-mono text-xs">{details.container.imageDigest?.substring(7, 19)}...</span>
              </div>
            )}
            <div className="flex justify-between">
              <span className="text-gray-500">Container Status</span>
              <span className={getStatusColor(details.container.lastStatus)}>{details.container.lastStatus}</span>
            </div>
          </div>
        </CollapsibleSection>
      )}

      {/* Resources */}
      {details?.resources && (
        <CollapsibleSection title="Resources" icon={Activity} iconColor="text-yellow-400">
          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-gray-500">CPU</span>
              <span className="text-gray-300">{details.resources.cpu} units ({(parseInt(details.resources.cpu) / 1024).toFixed(2)} vCPU)</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Memory</span>
              <span className="text-gray-300">{details.resources.memory} MB</span>
            </div>
            {details.resources.ephemeralStorage && (
              <div className="flex justify-between">
                <span className="text-gray-500">Ephemeral Storage</span>
                <span className="text-gray-300">{details.resources.ephemeralStorage} GB</span>
              </div>
            )}
          </div>
        </CollapsibleSection>
      )}

      {/* Timing Info */}
      <CollapsibleSection title="Timing" icon={Clock} iconColor="text-cyan-400">
        <div className="space-y-2 text-sm">
          <div className="flex justify-between">
            <span className="text-gray-500">Started At</span>
            <span className="text-gray-300">{formatDate(d.startedAt || task.startedAt)}</span>
          </div>
          {(d.startedAt || task.startedAt) && (
            <div className="flex justify-between">
              <span className="text-gray-500">Uptime</span>
              <span className="text-gray-300">
                {(() => {
                  const start = new Date(d.startedAt || task.startedAt)
                  const now = d.stoppedAt ? new Date(d.stoppedAt) : new Date()
                  const diff = Math.floor((now - start) / 1000)
                  const hours = Math.floor(diff / 3600)
                  const minutes = Math.floor((diff % 3600) / 60)
                  if (hours > 24) {
                    const days = Math.floor(hours / 24)
                    return `${days}j ${hours % 24}h ${minutes}m`
                  }
                  return `${hours}h ${minutes}m`
                })()}
              </span>
            </div>
          )}
          {details?.pullStartedAt && (
            <div className="flex justify-between">
              <span className="text-gray-500">Image Pull Started</span>
              <span className="text-gray-300">{formatDate(details.pullStartedAt)}</span>
            </div>
          )}
          {d.stoppedAt && (
            <div className="flex justify-between">
              <span className="text-gray-500">Stopped At</span>
              <span className="text-gray-300">{formatDate(d.stoppedAt)}</span>
            </div>
          )}
        </div>
      </CollapsibleSection>

      {/* Environment Variables & Secrets */}
      <EnvVarsSecretsPanel
        environmentVariables={details?.environmentVariables}
        secrets={details?.secrets}
        consoleUrls={details?.consoleUrls}
        collapsible
        defaultOpen={false}
      />

      {/* Security Groups */}
      {securityGroups.length > 0 && (
        <SecurityGroupsPanel securityGroups={securityGroups} env={env} title="Security Groups" />
      )}

      {/* Task Logs */}
      <div className="bg-gray-900 rounded-lg p-4">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-medium text-gray-300 flex items-center gap-2">
            <FileText className="w-4 h-4 text-purple-400" />
            Recent Logs
          </h3>
          <div className="flex items-center gap-2">
            <button
              onClick={fetchTaskDetails}
              className="text-xs px-2 py-1 bg-gray-700 hover:bg-gray-600 rounded text-gray-300"
              title="Refresh logs"
            >
              <RefreshCw className={`w-3 h-3 ${isTailing ? 'animate-spin' : ''}`} />
            </button>
            <button
              onClick={() => setIsTailing(!isTailing)}
              className={`text-xs px-3 py-1 rounded flex items-center gap-1 ${
                isTailing ? 'bg-green-500/20 text-green-400 border border-green-500/50' : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
              }`}
            >
              <Activity className={`w-3 h-3 ${isTailing ? 'animate-pulse' : ''}`} />
              {isTailing ? 'Tailing...' : 'Tail'}
            </button>
            <button
              onClick={() => onOpenLogsPanel?.({
                env,
                service: task.service,
                taskId: task?.fullId || task?.taskId,
                type: 'task',
                autoTail: true
              })}
              className="text-xs px-2 py-1 bg-gray-700 hover:bg-gray-600 rounded text-gray-300 flex items-center gap-1"
              title="Open in bottom panel"
            >
              <Maximize2 className="w-3 h-3" />
              Expand
            </button>
            {details?.consoleUrls?.logs && (
              <a href={details.consoleUrls.logs} target="_blank" rel="noopener noreferrer"
                 className="text-xs text-purple-400 hover:text-purple-300 flex items-center gap-1">
                <ExternalLink className="w-3 h-3" /> Full
              </a>
            )}
          </div>
        </div>
        <div ref={logsContainerRef} className="bg-black rounded p-2 max-h-[250px] overflow-y-auto scrollbar-brand font-mono text-xs">
          {!details?.logs || details.logs.length === 0 ? (
            <p className="text-gray-500 italic">No logs available. Click "Tail" to start streaming.</p>
          ) : details.logs[0]?.error ? (
            <p className="text-yellow-400">{details.logs[0].error}</p>
          ) : (
            details.logs.map((log, i) => (
              <div key={i} className="py-0.5 border-b border-gray-900 last:border-0 hover:bg-gray-800/50">
                <span className="text-gray-500">{new Date(log.timestamp).toLocaleTimeString('fr-FR')}</span>
                <span className={`ml-2 whitespace-pre-wrap break-all ${log.message?.toLowerCase().includes('error') ? 'text-red-400' : 'text-gray-300'}`}>{log.message}</span>
              </div>
            ))
          )}
        </div>
        {isTailing && (
          <div className="mt-2 flex items-center gap-2 text-xs text-green-400">
            <div className="w-2 h-2 bg-green-400 rounded-full animate-pulse" />
            Live - Refreshing every 3s
          </div>
        )}
      </div>

      {/* Rolling Update Notice */}
      {!task.isLatest && d.status === 'RUNNING' && (
        <div className="bg-orange-500/10 border border-orange-500/30 rounded-lg p-4">
          <div className="flex items-start gap-3">
            <AlertCircle className="w-5 h-5 text-orange-400 flex-shrink-0 mt-0.5" />
            <div>
              <p className="text-orange-400 font-medium text-sm">Rolling Update in Progress</p>
              <p className="text-orange-300/80 text-xs mt-1">
                Cette task utilise une ancienne revision et sera remplacee par une nouvelle task avec la derniere revision.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Stopped Reason */}
      {details?.stoppedReason && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-4">
          <div className="flex items-start gap-3">
            <XCircle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
            <div>
              <p className="text-red-400 font-medium text-sm">Task Stopped</p>
              <p className="text-red-300/80 text-xs mt-1">{details.stoppedReason}</p>
              {details.stopCode && (
                <p className="text-red-300/60 text-xs mt-1">Code: {details.stopCode}</p>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
