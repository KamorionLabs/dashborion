import { useState, useEffect, useRef } from 'react'
import {
  Package, Rocket, RotateCcw, Scale, Pause, Power, Trash, Activity,
  History, RefreshCw, PanelLeft, PanelLeftClose, Filter, Clock,
  User, Layers, Zap, Server, GitBranch, Github, GitCommit
} from 'lucide-react'
import { useConfig } from '../../ConfigContext'
import { formatTimeHHMM, formatRelativeTime, formatDuration } from '../../utils'

// Event type icons and colors
export const EVENT_TYPE_CONFIG = {
  build: { icon: Package, color: 'text-purple-400', bg: 'bg-purple-500/20' },
  deploy: { icon: Rocket, color: 'text-blue-400', bg: 'bg-blue-500/20' },
  rollback: { icon: RotateCcw, color: 'text-red-400', bg: 'bg-red-500/20' },
  scale: { icon: Scale, color: 'text-orange-400', bg: 'bg-orange-500/20' },
  rds_stop: { icon: Pause, color: 'text-yellow-400', bg: 'bg-yellow-500/20' },
  rds_start: { icon: Power, color: 'text-green-400', bg: 'bg-green-500/20' },
  cache_invalidation: { icon: Trash, color: 'text-cyan-400', bg: 'bg-cyan-500/20' },
  ecs_event: { icon: Activity, color: 'text-gray-400', bg: 'bg-gray-500/20' }
}

export const EVENT_STATUS_COLORS = {
  success: 'text-green-400',
  failed: 'text-red-400',
  in_progress: 'text-yellow-400 animate-pulse',
  stopped: 'text-gray-400'
}

export default function EventsTimelinePanel({
  events, loading, visible, onToggleVisible, width, onWidthChange,
  hours, onHoursChange, typeFilter, onTypeFilterChange,
  serviceFilter, onServiceFilterChange, env, autoRefresh, onEventClick
}) {
  const [isResizing, setIsResizing] = useState(false)
  const [showFilters, setShowFilters] = useState(false)
  const panelRef = useRef(null)

  // Get config from context
  const appConfig = useConfig()
  const ENV_COLORS = appConfig.envColors || {}

  // Available event types and services
  const allEventTypes = ['build', 'deploy', 'rollback', 'scale', 'rds_stop', 'rds_start', 'cache_invalidation', 'ecs_event']
  const allServices = appConfig.services || ['backend', 'frontend', 'cms']

  // Filter events by service (client-side)
  const filteredEvents = Array.isArray(events) ? events.filter(e => {
    if (serviceFilter.length === 0) return true
    return serviceFilter.includes(e.service) || !e.service
  }) : []

  // Toggle service filter
  const toggleServiceFilter = (service) => {
    if (serviceFilter.includes(service)) {
      onServiceFilterChange(serviceFilter.filter(s => s !== service))
    } else {
      onServiceFilterChange([...serviceFilter, service])
    }
  }

  // Handle resize
  const handleMouseDown = (e) => {
    e.preventDefault()
    setIsResizing(true)
  }

  useEffect(() => {
    const handleMouseMove = (e) => {
      if (!isResizing) return
      const newWidth = e.clientX
      if (newWidth >= 200 && newWidth <= 500) {
        onWidthChange(newWidth)
      }
    }

    const handleMouseUp = () => {
      setIsResizing(false)
    }

    if (isResizing) {
      document.addEventListener('mousemove', handleMouseMove)
      document.addEventListener('mouseup', handleMouseUp)
    }

    return () => {
      document.removeEventListener('mousemove', handleMouseMove)
      document.removeEventListener('mouseup', handleMouseUp)
    }
  }, [isResizing, onWidthChange])

  // Toggle type filter
  const toggleTypeFilter = (type) => {
    if (typeFilter.includes(type)) {
      onTypeFilterChange(typeFilter.filter(t => t !== type))
    } else {
      onTypeFilterChange([...typeFilter, type])
    }
  }

  // Collapsed state
  if (!visible) {
    return (
      <div className="fixed left-0 top-[73px] h-[calc(100vh-73px)] z-40">
        <button
          onClick={onToggleVisible}
          className="h-full w-8 bg-gray-800 border-r border-gray-700 flex items-center justify-center hover:bg-gray-700 transition-colors"
          title="Show Events Timeline"
        >
          <PanelLeft className="w-4 h-4 text-gray-400" />
        </button>
      </div>
    )
  }

  const colors = ENV_COLORS[env] || { bg: 'bg-gray-500', text: 'text-gray-400' }

  return (
    <div
      ref={panelRef}
      className="fixed left-0 top-[73px] h-[calc(100vh-73px)] bg-gray-800 border-r border-gray-700 z-40 flex flex-col"
      style={{ width: `${width}px` }}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-gray-700 bg-gray-850 flex-shrink-0">
        <div className="flex items-center gap-2">
          <History className="w-4 h-4 text-brand-400" />
          <span className="text-sm font-medium">Events</span>
          <span className={`text-xs ${colors.text}`}>({env})</span>
          {loading && <RefreshCw className="w-3 h-3 text-brand-500 animate-spin" />}
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={() => setShowFilters(!showFilters)}
            className={`p-1 rounded hover:bg-gray-700 ${showFilters ? 'bg-gray-700 text-brand-400' : 'text-gray-400'}`}
            title="Filters"
          >
            <Filter className="w-4 h-4" />
          </button>
          <button
            onClick={onToggleVisible}
            className="p-1 text-gray-400 hover:text-white hover:bg-gray-700 rounded"
            title="Hide panel"
          >
            <PanelLeftClose className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Filters */}
      {showFilters && (
        <div className="px-3 py-2 border-b border-gray-700 bg-gray-850/50 flex-shrink-0">
          {/* Time Range */}
          <div className="flex items-center gap-2 mb-2">
            <span className="text-xs text-gray-500">Time:</span>
            <div className="flex gap-1">
              {[24, 48, 72, 168].map(h => (
                <button
                  key={h}
                  onClick={() => onHoursChange(h)}
                  className={`px-2 py-0.5 text-xs rounded ${
                    hours === h ? 'bg-brand-600 text-white' : 'bg-gray-700 text-gray-400 hover:text-white'
                  }`}
                >
                  {h <= 48 ? `${h}h` : `${h / 24}d`}
                </button>
              ))}
            </div>
          </div>

          {/* Service Filters */}
          <div className="flex items-center gap-2 mb-2">
            <span className="text-xs text-gray-500">Service:</span>
            <div className="flex gap-1">
              {allServices.map(svc => (
                <button
                  key={svc}
                  onClick={() => toggleServiceFilter(svc)}
                  className={`px-2 py-0.5 text-xs rounded capitalize ${
                    serviceFilter.length === 0 || serviceFilter.includes(svc)
                      ? 'bg-brand-600 text-white'
                      : 'bg-gray-700 text-gray-500'
                  }`}
                >
                  {svc}
                </button>
              ))}
              {serviceFilter.length > 0 && (
                <button
                  onClick={() => onServiceFilterChange([])}
                  className="text-xs text-gray-500 hover:text-white"
                >
                  All
                </button>
              )}
            </div>
          </div>

          {/* Type Filters */}
          <div className="flex flex-wrap gap-1">
            {allEventTypes.map(type => {
              const config = EVENT_TYPE_CONFIG[type]
              const Icon = config?.icon || Activity
              const isActive = typeFilter.includes(type)
              return (
                <button
                  key={type}
                  onClick={() => toggleTypeFilter(type)}
                  className={`flex items-center gap-1 px-2 py-0.5 text-xs rounded ${
                    isActive ? `${config?.bg || 'bg-gray-700'} ${config?.color || 'text-gray-400'}` : 'bg-gray-800 text-gray-600'
                  }`}
                  title={type.replace('_', ' ')}
                >
                  <Icon className="w-3 h-3" />
                  <span className="capitalize">{type.replace('_', ' ').split(' ')[0]}</span>
                </button>
              )
            })}
          </div>
        </div>
      )}

      {/* Auto-refresh indicator */}
      {autoRefresh && (
        <div className="px-3 py-1 text-xs text-gray-500 border-b border-gray-700/50 flex items-center gap-1 flex-shrink-0">
          <RefreshCw className="w-3 h-3" />
          Auto-refresh: 30s
        </div>
      )}

      {/* Events Timeline */}
      <div className="flex-1 overflow-y-auto scrollbar-brand">
        {filteredEvents.length === 0 && !loading && (
          <div className="flex flex-col items-center justify-center h-32 text-gray-500">
            <History className="w-8 h-8 mb-2" />
            <span className="text-sm">No events found</span>
          </div>
        )}

        {/* Timeline with vertical line */}
        <div className="relative pl-3 pr-2 pt-2">
          {/* Vertical timeline line */}
          <div className="absolute left-[18px] top-2 bottom-0 w-0.5 bg-gradient-to-b from-brand-500/50 via-gray-600 to-gray-700" />

          {filteredEvents.map((event, idx) => {
            if (!event || typeof event !== 'object') return null

            // Parse date and validate
            const parseDate = (ts) => {
              if (!ts) return null
              let fixed = ts.replace(/\+00:00Z$/, 'Z')
              const d = new Date(fixed)
              return isNaN(d.getTime()) ? null : d
            }
            const eventDate = parseDate(event.timestamp)
            const prevEvent = idx > 0 ? filteredEvents[idx - 1] : null
            const prevDate = parseDate(prevEvent?.timestamp)
            const showDaySeparator = eventDate && (
              idx === 0 || (prevDate && eventDate.toDateString() !== prevDate.toDateString())
            )

            const eventType = String(event.type || 'ecs_event')
            const config = EVENT_TYPE_CONFIG[eventType] || EVENT_TYPE_CONFIG.ecs_event
            const Icon = config.icon
            const eventStatus = String(event.status || '')
            const eventService = event.service ? String(event.service) : null
            const eventUser = event.user ? String(event.user) : null
            const actorType = event.actorType || (eventUser?.includes('@') ? 'human' : null)
            const eventTime = formatTimeHHMM(event.timestamp)

            // Format details
            let eventDetails = null
            let eventSummary = null
            let stepCount = 0
            let commitInfo = null
            if (event.details) {
              if (typeof event.details === 'string') {
                eventDetails = event.details
              } else if (typeof event.details === 'object') {
                if (event.details.summary) {
                  eventSummary = event.details.summary
                  stepCount = event.details.stepCount || 0
                }
                if ((event.details.commit || event.details.commitMessage) && !event.details.isEcrDigest) {
                  commitInfo = {
                    sha: event.details.commit,
                    message: event.details.commitMessage,
                    url: event.details.commitUrl,
                    trigger: event.details.trigger,
                    triggerMode: event.details.triggerMode,
                    author: event.details.commitAuthor
                  }
                }
                const parts = []
                if (!commitInfo && event.details.message && !event.details.summary) parts.push(event.details.message)
                if (event.details.paths) parts.push(`${Array.isArray(event.details.paths) ? event.details.paths.join(', ') : event.details.paths}`)
                eventDetails = parts.length > 0 ? parts.join(' · ') : null
              }
            }

            const hasSteps = Array.isArray(event.steps) && event.steps.length > 0

            const dotColor = eventStatus === 'succeeded' || eventStatus === 'completed' ? 'bg-green-500'
              : eventStatus === 'failed' ? 'bg-red-500'
              : eventStatus === 'inprogress' || eventStatus === 'in_progress' ? 'bg-yellow-500 animate-pulse'
              : 'bg-gray-500'

            const borderColor = eventStatus === 'succeeded' || eventStatus === 'completed' ? 'border-green-500/30'
              : eventStatus === 'failed' ? 'border-red-500/30'
              : eventStatus === 'inprogress' || eventStatus === 'in_progress' ? 'border-yellow-500/30'
              : 'border-gray-600'

            const formatDayLabel = (date) => {
              if (!date || isNaN(date.getTime())) return ''
              try {
                const today = new Date()
                const yesterday = new Date(today)
                yesterday.setDate(yesterday.getDate() - 1)
                if (date.toDateString() === today.toDateString()) return "Today"
                if (date.toDateString() === yesterday.toDateString()) return "Yesterday"
                return date.toLocaleDateString('en-US', { weekday: 'long', day: 'numeric', month: 'long' })
              } catch (e) {
                return ''
              }
            }

            return (
              <div key={event.id || idx}>
                {showDaySeparator && (
                  <div className="relative flex items-center gap-3 py-3 mb-2">
                    <div className="flex-1 h-px bg-gradient-to-r from-transparent via-brand-500/50 to-transparent" />
                    <span className="text-xs font-medium text-brand-400 bg-gray-900 px-3 py-1 rounded-full border border-brand-500/30">
                      {formatDayLabel(eventDate)}
                    </span>
                    <div className="flex-1 h-px bg-gradient-to-r from-transparent via-brand-500/50 to-transparent" />
                  </div>
                )}

                <div className="relative flex gap-2 pb-3 group">
                  <div className="relative flex-shrink-0 mt-1.5">
                    <div className={`w-2.5 h-2.5 rounded-full ${dotColor} ring-2 ring-gray-800 z-10 relative`} />
                  </div>

                  <div
                    className={`flex-1 min-w-0 p-2 rounded-lg bg-gray-800/50 border ${borderColor} hover:bg-gray-700/50 transition-colors cursor-pointer`}
                    onClick={() => onEventClick && onEventClick(event)}
                  >
                    <div className="flex items-center gap-1.5 flex-wrap">
                      {eventTime && (
                        <span className="text-[10px] font-mono text-brand-400 bg-brand-500/10 px-1.5 py-0.5 rounded">
                          {eventTime}
                        </span>
                      )}
                      <div className={`p-0.5 rounded ${config.bg}`}>
                        <Icon className={`w-3 h-3 ${config.color}`} />
                      </div>
                      <span className="text-xs font-medium text-gray-200 capitalize">
                        {eventType.replace('_', ' ')}
                      </span>
                      {eventService && (
                        <span className="text-[10px] bg-gray-700 px-1.5 py-0.5 rounded text-gray-300 font-medium">
                          {eventService}
                        </span>
                      )}
                      <span className={`text-[10px] px-1.5 py-0.5 rounded capitalize ${
                        eventStatus === 'succeeded' || eventStatus === 'completed' ? 'bg-green-500/20 text-green-400'
                        : eventStatus === 'failed' ? 'bg-red-500/20 text-red-400'
                        : eventStatus === 'inprogress' || eventStatus === 'in_progress' ? 'bg-yellow-500/20 text-yellow-400'
                        : 'bg-gray-600 text-gray-400'
                      }`}>
                        {eventStatus.replace('_', ' ')}
                      </span>
                    </div>

                    {eventSummary && (
                      <p className="text-[11px] text-gray-300 mt-1 font-medium">
                        {eventSummary}
                        {stepCount > 1 && (
                          <span className="text-gray-500 font-normal ml-1">({stepCount} steps)</span>
                        )}
                      </p>
                    )}

                    {eventDetails && (
                      <p className="text-[11px] text-gray-400 mt-1 line-clamp-2" title={eventDetails}>
                        {eventDetails}
                      </p>
                    )}

                    {commitInfo && (
                      <div className="mt-1.5 flex items-start gap-1.5">
                        <Github className="w-3.5 h-3.5 text-gray-400 flex-shrink-0 mt-0.5" />
                        <div className="flex-1 min-w-0">
                          <p className="text-[11px] text-gray-300 line-clamp-2" title={commitInfo.message}>
                            {commitInfo.message || 'No commit message'}
                          </p>
                          <div className="flex items-center gap-2 mt-0.5 flex-wrap">
                            {commitInfo.url ? (
                              <a
                                href={commitInfo.url}
                                target="_blank"
                                rel="noopener noreferrer"
                                onClick={(e) => e.stopPropagation()}
                                className="text-[10px] font-mono text-brand-400 hover:text-brand-300 hover:underline flex items-center gap-0.5"
                              >
                                <GitCommit className="w-2.5 h-2.5" />
                                {commitInfo.sha}
                              </a>
                            ) : commitInfo.sha && (
                              <span className="text-[10px] font-mono text-gray-500 flex items-center gap-0.5">
                                <GitCommit className="w-2.5 h-2.5" />
                                {commitInfo.sha}
                              </span>
                            )}
                            {commitInfo.author && (
                              <span className="text-[10px] text-gray-400 flex items-center gap-0.5">
                                <User className="w-2.5 h-2.5" />
                                {commitInfo.author}
                              </span>
                            )}
                            {commitInfo.triggerMode && (
                              <span className={`text-[10px] px-1.5 py-0.5 rounded ${
                                commitInfo.triggerMode === 'Auto' ? 'bg-blue-500/20 text-blue-400' : 'bg-purple-500/20 text-purple-400'
                              }`}>
                                {commitInfo.triggerMode}
                              </span>
                            )}
                          </div>
                        </div>
                      </div>
                    )}

                    {eventType === 'build' && event.details?.imageTag && (
                      <div className="mt-1.5 flex items-center gap-2 text-[10px]">
                        <span className="text-gray-500">Image:</span>
                        <code className="font-mono text-blue-400 bg-gray-800 px-1 py-0.5 rounded">
                          {event.details.imageTag}
                        </code>
                        {event.details.imageDigest && (
                          <code className="font-mono text-gray-500 bg-gray-800 px-1 py-0.5 rounded" title={event.details.imageDigest}>
                            {event.details.imageDigest}
                          </code>
                        )}
                      </div>
                    )}

                    {eventType === 'deploy' && event.details?.isEcrDigest && event.details?.imageDigest && (
                      <div className="mt-1.5 flex items-center gap-2 text-[10px]">
                        <span className="text-gray-500">Image:</span>
                        <code className="font-mono text-purple-400 bg-gray-800 px-1 py-0.5 rounded" title={event.details.commitFull}>
                          {event.details.imageDigest}
                        </code>
                        {event.details.triggerMode && (
                          <span className={`px-1.5 py-0.5 rounded ${
                            event.details.triggerMode === 'Auto' ? 'bg-blue-500/20 text-blue-400' : 'bg-purple-500/20 text-purple-400'
                          }`}>
                            {event.details.triggerMode}
                          </span>
                        )}
                      </div>
                    )}

                    {(eventType === 'deploy' || eventType === 'rollback') && event.details?.taskDefinition && (
                      <div className="mt-1.5 space-y-1">
                        <div className="flex items-center gap-2 text-[10px]">
                          <span className="text-gray-500">Task Def:</span>
                          {event.details.previousTaskDefinition ? (
                            <>
                              <code className="font-mono text-gray-400 bg-gray-800 px-1 py-0.5 rounded">
                                {event.details.previousTaskDefinition.split(':').pop()}
                              </code>
                              <span className="text-gray-500">→</span>
                              <code className="font-mono text-green-400 bg-gray-800 px-1 py-0.5 rounded">
                                {event.details.taskDefinition.split(':').pop()}
                              </code>
                            </>
                          ) : (
                            <code className="font-mono text-green-400 bg-gray-800 px-1 py-0.5 rounded">
                              {event.details.taskDefinition.split(':').pop()}
                            </code>
                          )}
                        </div>
                        {event.diff?.changes?.length > 0 && (
                          <div className="pl-2 border-l-2 border-yellow-500/50 space-y-0.5">
                            {event.diff.changes.map((change, i) => (
                              <div key={i} className="flex items-center gap-2 text-[10px]">
                                <span className="text-gray-500 w-16 truncate">{change.label}:</span>
                                <span className="text-red-400 line-through">{change.from}</span>
                                <span className="text-gray-500">→</span>
                                <span className="text-green-400">{change.to}</span>
                              </div>
                            ))}
                          </div>
                        )}
                        {event.diff && !event.diff.changes?.length && (
                          <div className="text-[10px] text-gray-500 italic pl-2">No config changes</div>
                        )}
                      </div>
                    )}

                    {hasSteps && (
                      <div className="mt-1.5 pl-2 border-l border-gray-600 space-y-0.5">
                        {event.steps.map((step, stepIdx) => (
                          <div key={stepIdx} className="flex items-center gap-1.5 text-[10px] text-gray-500">
                            <span className={`w-1.5 h-1.5 rounded-full ${
                              step.step === 'steady_state' ? 'bg-green-500'
                              : step.step === 'rolling_back' || step.step === 'failed' ? 'bg-red-500'
                              : step.step === 'registered_targets' ? 'bg-blue-500'
                              : step.step === 'started_tasks' ? 'bg-yellow-500'
                              : 'bg-gray-500'
                            }`} />
                            <span className="capitalize">{step.step.replace(/_/g, ' ')}</span>
                            <span className="text-gray-600">{formatTimeHHMM(step.timestamp)}</span>
                          </div>
                        ))}
                      </div>
                    )}

                    {!commitInfo && event.details?.triggerMode && (
                      <div className="mt-1.5">
                        <span className={`text-[10px] px-1.5 py-0.5 rounded ${
                          event.details.triggerMode === 'Auto' ? 'bg-blue-500/20 text-blue-400' : 'bg-purple-500/20 text-purple-400'
                        }`}>
                          {event.details.triggerMode}
                        </span>
                      </div>
                    )}

                    <div className="flex items-center gap-2 mt-1.5 text-[10px] text-gray-500">
                      <span>{formatRelativeTime(event.timestamp)}</span>
                      {event.duration && (
                        <span className="flex items-center gap-0.5">
                          <Clock className="w-2.5 h-2.5" />
                          {formatDuration(event.duration)}
                        </span>
                      )}
                      {eventUser && (
                        <span className={`flex items-center gap-0.5 ${
                          actorType === 'human' ? 'text-blue-400' :
                          actorType === 'dashboard' ? 'text-purple-400' :
                          actorType === 'eventbridge' ? 'text-yellow-400' :
                          actorType === 'pipeline' ? 'text-orange-400' :
                          'text-brand-400'
                        }`}>
                          {actorType === 'human' ? <User className="w-2.5 h-2.5" /> :
                           actorType === 'dashboard' ? <Layers className="w-2.5 h-2.5" /> :
                           actorType === 'eventbridge' ? <Zap className="w-2.5 h-2.5" /> :
                           actorType === 'pipeline' ? <GitBranch className="w-2.5 h-2.5" /> :
                           <Server className="w-2.5 h-2.5" />}
                          {eventUser.includes('@') ? eventUser.split('@')[0] : eventUser}
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* Footer stats */}
      <div className="px-3 py-1 border-t border-gray-700 text-xs text-gray-500 flex items-center justify-between flex-shrink-0">
        <span>{Array.isArray(events) ? events.length : 0} events</span>
        <span>Last {hours}h</span>
      </div>

      {/* Resize handle */}
      <div
        className="absolute right-0 top-0 bottom-0 w-1 cursor-ew-resize hover:bg-brand-500/50 transition-colors"
        onMouseDown={handleMouseDown}
        style={{ backgroundColor: isResizing ? 'rgba(14, 165, 233, 0.5)' : 'transparent' }}
      />
    </div>
  )
}
