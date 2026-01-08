import { GitBranch, ExternalLink, RefreshCw, Play, Clock, Terminal, Calendar } from 'lucide-react'
import { calculateDuration, formatDuration, formatRelativeTime, PIPELINE_STATUS_COLORS } from '../../utils'

export default function BuildPipelineCard({ service, pipeline, images, loading, onSelect, isSelected, onTriggerBuild, actionLoading, onTailBuildLogs }) {
  const latestImage = images?.images?.[0]
  const execution = pipeline?.lastExecution

  // Calculate pipeline duration (status is lowercase from API)
  const pipelineDuration = execution?.status !== 'inprogress'
    ? calculateDuration(execution?.startTime, execution?.lastUpdateTime)
    : null

  const statusColors = {
    // Lowercase keys to match API response
    succeeded: 'text-green-400',
    failed: 'text-red-400',
    inprogress: 'text-yellow-400',
    stopped: 'text-gray-400',
    // Capitalized for backward compatibility
    Succeeded: 'text-green-400',
    Failed: 'text-red-400',
    InProgress: 'text-yellow-400',
    Stopped: 'text-gray-400'
  }

  if (loading) {
    return (
      <div className="bg-gray-800 rounded-lg border border-gray-700 overflow-hidden animate-pulse">
        <div className="px-4 py-3 border-b border-gray-700">
          <div className="flex items-center gap-2">
            <div className="w-4 h-4 bg-gray-700 rounded" />
            <div className="h-5 w-24 bg-gray-700 rounded" />
          </div>
        </div>
        <div className="px-4 py-3 space-y-3">
          <div className="h-4 w-full bg-gray-700 rounded" />
          <div className="flex gap-1">
            {[1,2,3,4].map(i => <div key={i} className="flex-1 h-1.5 bg-gray-700 rounded-full" />)}
          </div>
          <div className="h-4 w-3/4 bg-gray-700 rounded" />
        </div>
      </div>
    )
  }

  const isInProgress = execution?.status === 'inprogress'

  return (
    <div
      className={`bg-gray-800 rounded-lg border overflow-hidden cursor-pointer transition-all hover:border-gray-500 ${
        isSelected ? 'border-brand-500 ring-2 ring-brand-500/30' :
        isInProgress ? 'border-yellow-500/50 animate-pulse' : 'border-gray-700'
      }`}
      onClick={onSelect}
    >
      <div className={`px-4 py-3 border-b ${isInProgress ? 'border-yellow-500/30 bg-yellow-500/10' : 'border-gray-700'}`}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <GitBranch className={`w-4 h-4 ${isInProgress ? 'text-yellow-400' : 'text-gray-400'}`} />
            <h3 className="font-semibold capitalize">{service}</h3>
            {isInProgress && (
              <span className="text-xs text-yellow-400 animate-pulse">Building...</span>
            )}
          </div>
          <div className="flex items-center gap-2">
            {isInProgress && (
              <button
                onClick={(e) => { e.stopPropagation(); onTailBuildLogs?.(); }}
                className="flex items-center gap-1 px-2 py-1 bg-yellow-600 hover:bg-yellow-500 rounded text-xs transition-colors"
                title="Follow build logs"
              >
                <Terminal className="w-3 h-3" />
                Tail Logs
              </button>
            )}
            <button
              onClick={(e) => { e.stopPropagation(); onTriggerBuild?.(); }}
              disabled={actionLoading || isInProgress}
              className="flex items-center gap-1 px-2 py-1 bg-brand-600 hover:bg-brand-500 disabled:bg-gray-600 disabled:opacity-50 rounded text-xs transition-colors"
              title="Trigger a build"
            >
              {actionLoading ? (
                <RefreshCw className="w-3 h-3 animate-spin" />
              ) : (
                <Play className="w-3 h-3" />
              )}
              Build
            </button>
            {pipeline?.consoleUrl && (
              <a
                href={pipeline.consoleUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="text-gray-400 hover:text-brand-400"
                onClick={(e) => e.stopPropagation()}
              >
                <ExternalLink className="w-4 h-4" />
              </a>
            )}
          </div>
        </div>
      </div>

      <div className="px-4 py-3 space-y-3">
        {/* Pipeline Status */}
        {execution && (
          <div>
            <div className="flex items-center justify-between text-sm mb-1">
              <div className="flex items-center gap-2">
                <span className="text-gray-400">Last Build</span>
                {execution.consoleUrl && (
                  <a
                    href={execution.consoleUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-gray-500 hover:text-brand-400"
                    title="View execution"
                  >
                    <ExternalLink className="w-3 h-3" />
                  </a>
                )}
              </div>
              <div className="flex items-center gap-2">
                {execution.startTime && (
                  <span className="text-gray-500 flex items-center gap-1" title={new Date(execution.startTime).toLocaleString()}>
                    <Calendar className="w-3 h-3" />
                    {formatRelativeTime(execution.startTime)}
                  </span>
                )}
                {pipelineDuration && (
                  <span className="text-gray-500 flex items-center gap-1">
                    <Clock className="w-3 h-3" />
                    {formatDuration(pipelineDuration)}
                  </span>
                )}
                <span className={statusColors[execution.status] || 'text-gray-400'}>
                  {execution.status}
                </span>
              </div>
            </div>
            {execution.commit && (
              <div className="flex items-center gap-2 text-xs">
                {execution.commitUrl ? (
                  <a
                    href={execution.commitUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-brand-400 hover:text-brand-300 font-mono"
                  >
                    {execution.commit}
                  </a>
                ) : (
                  <span className="text-gray-500 font-mono">{execution.commit}</span>
                )}
                <span className="text-gray-500 truncate">{execution.commitMessage}</span>
              </div>
            )}
          </div>
        )}

        {/* Stages */}
        {pipeline?.stages && (
          <div className="space-y-1">
            <div className="flex gap-1">
              {pipeline.stages.map((stage, i) => (
                <div
                  key={i}
                  className={`flex-1 h-1.5 rounded-full ${PIPELINE_STATUS_COLORS[stage.status] || 'bg-gray-600'}`}
                  title={`${stage.name}: ${stage.status}`}
                />
              ))}
            </div>
            <div className="flex gap-1 text-[9px] text-gray-500">
              {pipeline.stages.map((stage, i) => (
                <div key={i} className="flex-1 text-center truncate" title={`${stage.name}: ${stage.status}`}>
                  <span className={stage.status === 'succeeded' ? 'text-green-400' : stage.status === 'failed' ? 'text-red-400' : stage.status === 'inprogress' ? 'text-yellow-400' : 'text-gray-500'}>
                    {stage.name}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Latest Image */}
        <div className="pt-2 border-t border-gray-700">
          <div className="text-xs text-gray-400 mb-1">Latest Image</div>
          {latestImage ? (
            <>
              <div className="flex items-center justify-between text-sm">
                <span className="text-gray-300 truncate max-w-[150px]" title={latestImage.tags?.join(', ')}>
                  {latestImage.tags?.find(t => t !== 'latest') || latestImage.tags?.[0] || 'untagged'}
                </span>
                <span className="text-gray-500 text-xs">{latestImage.sizeMB} MB</span>
              </div>
              {latestImage.pushedAt && (
                <p className="text-xs text-gray-500">
                  {new Date(latestImage.pushedAt).toLocaleString()}
                </p>
              )}
            </>
          ) : loading ? (
            <p className="text-xs text-gray-500 animate-pulse">Loading...</p>
          ) : (
            <p className="text-xs text-gray-500">No image data</p>
          )}
        </div>

        {pipeline?.error && (
          <p className="text-xs text-red-400">{pipeline.error}</p>
        )}
      </div>
    </div>
  )
}
