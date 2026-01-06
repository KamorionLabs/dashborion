import { useState, useEffect, useCallback, useRef } from 'react'
import {
  GitBranch, ExternalLink, Clock, Activity, Package, FileText,
  RefreshCw, Maximize2, History
} from 'lucide-react'
import { fetchWithRetry } from '../../utils'
import CollapsibleSection from '../common/CollapsibleSection'

export default function PipelineDetails({ data, onOpenLogsPanel }) {
  const { service, pipeline, images } = data
  const [isTailing, setIsTailing] = useState(false)
  const [logs, setLogs] = useState(pipeline?.buildLogs || [])
  const [pipelineData, setPipelineData] = useState(pipeline)
  const logsContainerRef = useRef(null)

  // Fetch fresh pipeline data with logs
  const fetchLogs = useCallback(async () => {
    try {
      const response = await fetchWithRetry(`/api/pipelines/build/${service}`)
      const data = await response.json()
      if (data && !data.error) {
        setPipelineData(data)
        if (data.buildLogs) {
          setLogs(data.buildLogs)
        }
      }
    } catch (err) {
      console.error('Failed to fetch logs:', err)
    }
  }, [service])

  // Auto-scroll to bottom when logs change (always, not just when tailing)
  useEffect(() => {
    if (logsContainerRef.current) {
      const container = logsContainerRef.current
      container.scrollTop = container.scrollHeight
    }
  }, [logs])

  // Polling interval for tailing
  useEffect(() => {
    let interval
    if (isTailing) {
      fetchLogs() // Initial fetch
      interval = setInterval(fetchLogs, 3000) // Refresh every 3 seconds
    }
    return () => {
      if (interval) clearInterval(interval)
    }
  }, [isTailing, fetchLogs])

  const execution = pipelineData?.lastExecution
  const latestImage = images?.images?.[0]

  const statusColors = {
    // Lowercase keys to match API response
    succeeded: 'text-green-400 bg-green-500/20',
    failed: 'text-red-400 bg-red-500/20',
    inprogress: 'text-yellow-400 bg-yellow-500/20',
    stopped: 'text-gray-400 bg-gray-500/20',
    // Capitalized for backward compatibility
    Succeeded: 'text-green-400 bg-green-500/20',
    Failed: 'text-red-400 bg-red-500/20',
    InProgress: 'text-yellow-400 bg-yellow-500/20',
    Stopped: 'text-gray-400 bg-gray-500/20'
  }

  const formatDate = (dateStr) => {
    if (!dateStr) return '-'
    return new Date(dateStr).toLocaleString('fr-FR', {
      day: '2-digit', month: '2-digit', year: 'numeric',
      hour: '2-digit', minute: '2-digit', second: '2-digit'
    })
  }

  return (
    <div className="space-y-4">
      {/* Pipeline Status Banner */}
      <div className={`rounded-lg p-4 ${statusColors[execution?.status] || 'bg-gray-500/20'}`}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <GitBranch className="w-6 h-6" />
            <div>
              <p className="font-semibold capitalize">{service} Build Pipeline</p>
              <p className="text-sm opacity-80">{execution?.status || 'Unknown'}</p>
            </div>
          </div>
          {pipelineData?.consoleUrl && (
            <a
              href={pipelineData.consoleUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1 text-sm hover:underline"
            >
              <ExternalLink className="w-4 h-4" />
              Console
            </a>
          )}
        </div>
      </div>

      {/* Pipeline Stages */}
      {pipelineData?.stages && (
        <CollapsibleSection title="Pipeline Stages" icon={Activity} iconColor="text-blue-400">
          <div className="flex gap-1 mb-2">
            {pipelineData.stages.map((stage, i) => (
              <div
                key={i}
                className={`flex-1 h-2 rounded-full ${
                  stage.status === 'succeeded' ? 'bg-green-500' :
                  stage.status === 'failed' ? 'bg-red-500' :
                  stage.status === 'inprogress' ? 'bg-yellow-500 animate-pulse' :
                  'bg-gray-600'
                }`}
                title={`${stage.name}: ${stage.status}`}
              />
            ))}
          </div>
          <div className="flex justify-between text-xs text-gray-500">
            {pipelineData.stages.map((stage, i) => (
              <span key={i} className="truncate text-center flex-1">{stage.name}</span>
            ))}
          </div>
        </CollapsibleSection>
      )}

      {/* Last Execution Info */}
      {execution && (
        <CollapsibleSection title="Last Execution" icon={Clock} iconColor="text-yellow-400">
          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-gray-500">Execution ID</span>
              <span className="text-gray-300 font-mono text-xs">{execution.executionId?.substring(0, 12)}...</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Started</span>
              <span className="text-gray-300">{formatDate(execution.startTime)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Updated</span>
              <span className="text-gray-300">{formatDate(execution.lastUpdateTime)}</span>
            </div>
            {execution.commit && (
              <div className="flex justify-between">
                <span className="text-gray-500">Commit</span>
                <div className="text-right">
                  {execution.commitUrl ? (
                    <a href={execution.commitUrl} target="_blank" rel="noopener noreferrer" className="text-brand-400 hover:underline font-mono text-xs">
                      {execution.commit}
                    </a>
                  ) : (
                    <span className="text-gray-300 font-mono text-xs">{execution.commit}</span>
                  )}
                </div>
              </div>
            )}
            {execution.commitMessage && (
              <div className="mt-2 text-xs text-gray-400 italic truncate" title={execution.commitMessage}>
                "{execution.commitMessage}"
              </div>
            )}
            {execution.consoleUrl && (
              <a
                href={execution.consoleUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1 text-xs text-brand-400 hover:underline mt-2"
              >
                <ExternalLink className="w-3 h-3" />
                View Execution
              </a>
            )}
          </div>
        </CollapsibleSection>
      )}

      {/* Latest Image */}
      <CollapsibleSection title="Latest Image" icon={Package} iconColor="text-cyan-400">
        {latestImage ? (
          <div className="space-y-2 text-sm">
            <div className="flex justify-between items-start">
              <span className="text-gray-500">Tags</span>
              <div className="flex flex-wrap gap-1 justify-end max-w-[280px]">
                {latestImage.tags?.length > 0 ? (
                  latestImage.tags.map((tag, i) => (
                    <span key={i} className={`px-2 py-0.5 rounded text-xs font-mono ${
                      tag === 'latest' ? 'bg-green-500/20 text-green-400' : 'bg-gray-700 text-cyan-400'
                    }`}>
                      {tag.length > 20 ? tag.substring(0, 8) + '...' : tag}
                    </span>
                  ))
                ) : (
                  <span className="text-gray-500 text-xs">untagged</span>
                )}
              </div>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Digest</span>
              <span className="text-gray-300 font-mono text-xs">{latestImage.digest?.substring(7, 19)}...</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Pushed</span>
              <span className="text-gray-300">{formatDate(latestImage.pushedAt)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Size</span>
              <span className="text-gray-300">{latestImage.sizeMB || (latestImage.size / 1024 / 1024).toFixed(1)} MB</span>
            </div>
          </div>
        ) : (
          <p className="text-sm text-gray-500">No image data available</p>
        )}
      </CollapsibleSection>

      {/* Build Logs with Tail */}
      <div className="bg-gray-900 rounded-lg p-4">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-medium text-gray-300 flex items-center gap-2">
            <FileText className="w-4 h-4 text-purple-400" />
            Build Logs
          </h3>
          <div className="flex items-center gap-2">
            <button
              onClick={() => onOpenLogsPanel?.({
                env: 'build',
                service: service,
                type: 'build',
                autoTail: true
              })}
              className="text-xs px-2 py-1 bg-gray-700 hover:bg-gray-600 rounded text-gray-300 flex items-center gap-1"
              title="Open in bottom panel"
            >
              <Maximize2 className="w-3 h-3" />
              Expand
            </button>
            <button
              onClick={fetchLogs}
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
          </div>
        </div>

        <div ref={logsContainerRef} className="bg-gray-950 rounded p-3 max-h-[300px] overflow-y-auto scrollbar-brand font-mono text-xs">
          {logs && logs.length > 0 ? (
            logs.map((log, i) => (
              <div key={i} className="py-0.5 text-gray-400 hover:bg-gray-800/50">
                <span className="text-gray-600 mr-2">{new Date(log.timestamp).toLocaleTimeString()}</span>
                <span className={log.message?.includes('error') || log.message?.includes('Error') ? 'text-red-400' : ''}>{log.message}</span>
              </div>
            ))
          ) : (
            <p className="text-gray-500 italic">No logs available. Click "Tail" to start streaming.</p>
          )}
        </div>

        {isTailing && (
          <div className="mt-2 flex items-center gap-2 text-xs text-green-400">
            <div className="w-2 h-2 bg-green-400 rounded-full animate-pulse" />
            Live - Refreshing every 3s
          </div>
        )}
      </div>

      {/* Recent Executions */}
      {pipelineData?.executions?.length > 0 && (
        <CollapsibleSection title={`Recent Executions (${Math.min(pipelineData.executions.length, 5)})`} icon={History} iconColor="text-gray-400" defaultOpen={false}>
          <div className="space-y-2">
            {pipelineData.executions.slice(0, 5).map((exec, i) => (
              <div key={i} className="flex items-center justify-between text-xs py-2 border-b border-gray-800 last:border-0">
                <div className="flex items-center gap-2">
                  <div className={`w-2 h-2 rounded-full ${
                    exec.status === 'succeeded' ? 'bg-green-500' :
                    exec.status === 'failed' ? 'bg-red-500' :
                    exec.status === 'inprogress' ? 'bg-yellow-500 animate-pulse' :
                    'bg-gray-500'
                  }`} />
                  <span className="text-gray-400 font-mono">{exec.executionId?.substring(0, 8)}</span>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-gray-500">{formatDate(exec.startTime)}</span>
                  {exec.consoleUrl && (
                    <a href={exec.consoleUrl} target="_blank" rel="noopener noreferrer" className="text-brand-400 hover:underline">
                      <ExternalLink className="w-3 h-3" />
                    </a>
                  )}
                </div>
              </div>
            ))}
          </div>
        </CollapsibleSection>
      )}
    </div>
  )
}
