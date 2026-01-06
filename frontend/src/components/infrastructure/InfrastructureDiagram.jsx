import { useState } from 'react'
import {
  RefreshCw, Globe, Server, Database, Clock, Rocket, Play, Square, Terminal
} from 'lucide-react'
import { useConfig, useConfigHelpers } from '../../ConfigContext'
import { formatDuration, calculateDuration } from '../../utils'
import SimpleView from './SimpleView'
import NetworkView from './NetworkView'
import RoutingView from './RoutingView'

export default function InfrastructureDiagram({ data, env, onComponentSelect, selectedComponent, services: envServices, pipelines, onForceReload, onDeployLatest, onScaleService, actionLoading, onOpenLogsPanel, onTailDeployLogs }) {
  const [viewMode, setViewMode] = useState('simple') // 'simple', 'network', or 'routing'

  // Get config from context
  const appConfig = useConfig()
  const { getServiceName, getDefaultAzs } = useConfigHelpers()
  const ENV_COLORS = appConfig.envColors || {}
  const SERVICES = appConfig.services || []
  const INFRA_CONFIG = appConfig.infrastructure || {}

  // Use serviceColors from infrastructure config, with defaults for backward compatibility
  const defaultServiceColors = { backend: '#3b82f6', frontend: '#8b5cf6', cms: '#06b6d4', teleoperateur: '#f59e0b' }
  const serviceColors = { ...defaultServiceColors, ...(INFRA_CONFIG.serviceColors || {}) }

  if (!data) {
    return (
      <div className="bg-gray-800 rounded-lg border border-gray-700 p-8 flex items-center justify-center">
        <RefreshCw className="w-8 h-8 text-brand-500 animate-spin" />
      </div>
    )
  }

  if (data.error) {
    return (
      <div className="bg-gray-800 rounded-lg border border-gray-700 p-8">
        <p className="text-red-400 text-center">{data.error}</p>
      </div>
    )
  }

  const colors = ENV_COLORS[env] || { bg: 'bg-gray-500', text: 'text-gray-400', border: 'border-gray-500' }
  const { alb, domains } = data

  return (
    <div className={`bg-gray-800 rounded-lg border ${colors.border} overflow-hidden`}>
      {/* Header with domains */}
      <div className="px-4 py-3 border-b border-gray-700">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className={`w-3 h-3 rounded-full ${colors.bg}`}></span>
            <span className={`font-semibold capitalize ${colors.text}`}>{env}</span>
            {/* View Mode Toggle */}
            <div className="flex items-center bg-gray-700 rounded-lg p-0.5 ml-2">
              <button
                onClick={() => setViewMode('simple')}
                className={`px-2 py-1 text-xs rounded-md transition-colors ${viewMode === 'simple' ? 'bg-brand-500 text-white' : 'text-gray-400 hover:text-white'}`}
              >
                Simple
              </button>
              <button
                onClick={() => setViewMode('network')}
                className={`px-2 py-1 text-xs rounded-md transition-colors ${viewMode === 'network' ? 'bg-brand-500 text-white' : 'text-gray-400 hover:text-white'}`}
              >
                Network
              </button>
              <button
                onClick={() => setViewMode('routing')}
                className={`px-2 py-1 text-xs rounded-md transition-colors ${viewMode === 'routing' ? 'bg-cyan-500 text-white' : 'text-gray-400 hover:text-white'}`}
              >
                Routing
              </button>
            </div>
          </div>
          <div className="flex gap-4 text-xs">
            {domains?.frontend && (
              <a href={domains.frontend} target="_blank" rel="noopener noreferrer"
                 className="text-brand-400 hover:text-brand-300 flex items-center gap-1">
                <Globe className="w-3 h-3" /> Frontend
              </a>
            )}
            {domains?.backend && (
              <a href={domains.backend} target="_blank" rel="noopener noreferrer"
                 className="text-brand-400 hover:text-brand-300 flex items-center gap-1">
                <Server className="w-3 h-3" /> Backend
              </a>
            )}
            {domains?.cms && (
              <a href={domains.cms} target="_blank" rel="noopener noreferrer"
                 className="text-brand-400 hover:text-brand-300 flex items-center gap-1">
                <Database className="w-3 h-3" /> CMS
              </a>
            )}
          </div>
        </div>
      </div>

      {/* Service Cards - Above diagram */}
      {envServices?.services && (
        <ServiceCards
          env={env}
          envServices={envServices}
          alb={alb}
          pipelines={pipelines}
          SERVICES={SERVICES}
          getServiceName={getServiceName}
          onComponentSelect={onComponentSelect}
          onForceReload={onForceReload}
          onDeployLatest={onDeployLatest}
          onScaleService={onScaleService}
          actionLoading={actionLoading}
          onOpenLogsPanel={onOpenLogsPanel}
          onTailDeployLogs={onTailDeployLogs}
        />
      )}

      {/* View Content */}
      {viewMode === 'simple' && (
        <SimpleView
          env={env}
          data={data}
          services={envServices}
          onComponentSelect={onComponentSelect}
          selectedComponent={selectedComponent}
          serviceColors={serviceColors}
          SERVICES={SERVICES}
          getServiceName={getServiceName}
          domains={domains}
        />
      )}

      {viewMode === 'network' && (
        <NetworkView
          env={env}
          data={data}
          services={envServices}
          onComponentSelect={onComponentSelect}
          selectedComponent={selectedComponent}
          serviceColors={serviceColors}
          SERVICES={SERVICES}
          getServiceName={getServiceName}
          getDefaultAzs={getDefaultAzs}
          appConfig={appConfig}
        />
      )}

      {viewMode === 'routing' && (
        <RoutingView
          env={env}
          data={data}
          onComponentSelect={onComponentSelect}
          selectedComponent={selectedComponent}
          getDefaultAzs={getDefaultAzs}
          appConfig={appConfig}
        />
      )}

    </div>
  )
}

/**
 * Service Cards component - extracted for cleaner orchestrator
 */
function ServiceCards({
  env,
  envServices,
  alb,
  pipelines,
  SERVICES,
  getServiceName,
  onComponentSelect,
  onForceReload,
  onDeployLatest,
  onScaleService,
  actionLoading,
  onOpenLogsPanel,
  onTailDeployLogs
}) {
  return (
    <div className="px-4 pt-4 pb-2">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        {SERVICES.map(svc => {
          const service = envServices.services[svc]
          if (!service) return null
          const tg = alb?.targetGroups?.find(t => t.service === svc)
          const health = tg?.health?.status || service?.health || 'UNKNOWN'
          const isDeploying = service.deployPipeline?.lastExecution?.status === 'InProgress'
          const isBuilding = pipelines?.[svc]?.lastExecution?.status === 'InProgress'
          const isPipelineActive = isDeploying || isBuilding
          const serviceWithName = { ...service, name: service.name || getServiceName(env, svc) }

          return (
            <div
              key={svc}
              className={`bg-gray-900 rounded-lg border cursor-pointer transition-all hover:border-gray-500 ${
                isDeploying ? 'border-yellow-500/70 animate-pulse' :
                health === 'healthy' || health === 'HEALTHY' ? 'border-green-500/50' :
                health === 'unhealthy' || health === 'UNHEALTHY' ? 'border-red-500/50' : 'border-gray-600'
              }`}
              onClick={() => onComponentSelect?.('service', env, serviceWithName)}
            >
              {/* Header */}
              <div className={`px-3 py-2 rounded-t-lg flex items-center justify-between ${
                isDeploying ? 'bg-yellow-500/20' :
                health === 'healthy' || health === 'HEALTHY' ? 'bg-green-500/20' :
                health === 'unhealthy' || health === 'UNHEALTHY' ? 'bg-red-500/20' : 'bg-gray-700'
              }`}>
                <span className="font-medium capitalize text-sm">{svc}</span>
                <span className={`text-xs px-2 py-0.5 rounded ${
                  service.runningCount === service.desiredCount ? 'bg-green-500/30 text-green-400' : 'bg-yellow-500/30 text-yellow-400'
                }`}>
                  {service.runningCount}/{service.desiredCount} tasks
                </span>
              </div>

              {/* Content */}
              <div className="px-3 py-2 space-y-1.5 text-xs">
                <div className="flex justify-between">
                  <span className="text-gray-500">Status</span>
                  <span className={service.status === 'ACTIVE' ? 'text-green-400' : 'text-yellow-400'}>{service.status}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">Rev</span>
                  <span className="text-gray-300">{service.taskDefinition}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">Image</span>
                  <span className="text-gray-300 font-mono text-[10px]">{service.image?.substring(0, 12)}</span>
                </div>

                {/* Deploy Pipeline */}
                {service.deployPipeline && (
                  <div className="pt-1.5 mt-1.5 border-t border-gray-700">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-gray-500">Deploy</span>
                      <div className="flex items-center gap-1.5">
                        {service.deployPipeline.lastExecution?.status !== 'InProgress' &&
                         service.deployPipeline.lastExecution?.startTime &&
                         service.deployPipeline.lastExecution?.lastUpdateTime && (
                          <span className="text-gray-600 text-[9px] flex items-center gap-0.5">
                            <Clock className="w-2.5 h-2.5" />
                            {formatDuration(calculateDuration(
                              service.deployPipeline.lastExecution.startTime,
                              service.deployPipeline.lastExecution.lastUpdateTime
                            ))}
                          </span>
                        )}
                        <span className={`text-[10px] ${
                          service.deployPipeline.lastExecution?.status === 'Succeeded' ? 'text-green-400' :
                          service.deployPipeline.lastExecution?.status === 'Failed' ? 'text-red-400' :
                          service.deployPipeline.lastExecution?.status === 'InProgress' ? 'text-yellow-400' :
                          'text-gray-400'
                        }`}>
                          {service.deployPipeline.lastExecution?.status || '-'}
                        </span>
                      </div>
                    </div>
                    <div className="flex gap-0.5">
                      {service.deployPipeline.stages?.map((stage, idx) => (
                        <div
                          key={idx}
                          className={`flex-1 h-1.5 rounded-full ${
                            stage.status === 'Succeeded' ? 'bg-green-500' :
                            stage.status === 'Failed' ? 'bg-red-500' :
                            stage.status === 'InProgress' ? 'bg-yellow-500 animate-pulse' :
                            'bg-gray-600'
                          }`}
                          title={`${stage.name}: ${stage.status}`}
                        />
                      ))}
                    </div>
                  </div>
                )}

                {/* Action Buttons */}
                <div className="pt-1.5 mt-1.5 border-t border-gray-700 flex gap-1">
                  {service.desiredCount === 0 ? (
                    <button
                      onClick={(e) => { e.stopPropagation(); onScaleService?.(env, svc, 'start') }}
                      disabled={actionLoading?.[`scale-${env}-${svc}`]}
                      className="flex-1 flex items-center justify-center gap-1 px-2 py-1 bg-green-600/80 hover:bg-green-500 disabled:bg-gray-600 disabled:opacity-50 rounded text-[10px] font-medium transition-colors"
                      title="Scale to N replicas"
                    >
                      {actionLoading?.[`scale-${env}-${svc}`] ? (
                        <RefreshCw className="w-3 h-3 animate-spin" />
                      ) : (
                        <Play className="w-3 h-3" />
                      )}
                      Start
                    </button>
                  ) : (
                    <button
                      onClick={(e) => { e.stopPropagation(); onScaleService?.(env, svc, 'stop') }}
                      disabled={actionLoading?.[`scale-${env}-${svc}`]}
                      className="flex-1 flex items-center justify-center gap-1 px-2 py-1 bg-red-600/80 hover:bg-red-500 disabled:bg-gray-600 disabled:opacity-50 rounded text-[10px] font-medium transition-colors"
                      title="Scale to 0 replicas"
                    >
                      {actionLoading?.[`scale-${env}-${svc}`] ? (
                        <RefreshCw className="w-3 h-3 animate-spin" />
                      ) : (
                        <Square className="w-3 h-3" />
                      )}
                      Stop
                    </button>
                  )}
                  <button
                    onClick={(e) => { e.stopPropagation(); onForceReload?.(env, svc) }}
                    disabled={actionLoading?.[`reload-${env}-${svc}`] || isPipelineActive}
                    className="flex-1 flex items-center justify-center gap-1 px-2 py-1 bg-orange-600/80 hover:bg-orange-500 disabled:bg-gray-600 disabled:opacity-50 rounded text-[10px] font-medium transition-colors"
                    title={isPipelineActive ? "Disabled: pipeline in progress" : "Restart tasks (reload secrets)"}
                  >
                    {actionLoading?.[`reload-${env}-${svc}`] ? (
                      <RefreshCw className="w-3 h-3 animate-spin" />
                    ) : (
                      <RefreshCw className="w-3 h-3" />
                    )}
                    Reload
                  </button>
                  <button
                    onClick={(e) => { e.stopPropagation(); onDeployLatest?.(env, svc) }}
                    disabled={actionLoading?.[`deploy-${env}-${svc}`] || isPipelineActive}
                    className="flex-1 flex items-center justify-center gap-1 px-2 py-1 bg-blue-600/80 hover:bg-blue-500 disabled:bg-gray-600 disabled:opacity-50 rounded text-[10px] font-medium transition-colors"
                    title={isPipelineActive ? "Disabled: pipeline in progress" : "Update image & task def"}
                  >
                    {actionLoading?.[`deploy-${env}-${svc}`] ? (
                      <RefreshCw className="w-3 h-3 animate-spin" />
                    ) : (
                      <Rocket className="w-3 h-3" />
                    )}
                    Deploy
                  </button>
                </div>
                {/* Second row - Tail Logs buttons */}
                <div className="pt-1 flex gap-1">
                  <button
                    onClick={(e) => { e.stopPropagation(); onOpenLogsPanel?.({ env, service: svc, logs: [], autoTail: true }) }}
                    className="flex-1 flex items-center justify-center gap-1 px-2 py-1 bg-purple-600/80 hover:bg-purple-500 rounded text-[10px] font-medium transition-colors"
                    title="Open ECS logs panel with live tail"
                  >
                    <Terminal className="w-3 h-3" />
                    Tail Logs
                  </button>
                  {isDeploying && (
                    <button
                      onClick={(e) => { e.stopPropagation(); onTailDeployLogs?.(env, svc) }}
                      className="flex-1 flex items-center justify-center gap-1 px-2 py-1 bg-yellow-600/80 hover:bg-yellow-500 rounded text-[10px] font-medium transition-colors"
                      title="Follow deploy pipeline logs"
                    >
                      <Terminal className="w-3 h-3" />
                      Tail Deploy
                    </button>
                  )}
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
