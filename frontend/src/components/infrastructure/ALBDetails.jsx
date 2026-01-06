import { Box, Link2, ExternalLink, Radio, Target } from 'lucide-react'
import SecurityGroupsPanel from './SecurityGroupsPanel'
import CollapsibleSection from '../common/CollapsibleSection'

export default function ALBDetails({ alb, infrastructure, env }) {
  if (!alb || alb.error) {
    return <p className="text-red-400">{alb?.error || 'ALB data not available'}</p>
  }

  return (
    <div className="space-y-4">
      {/* General Info */}
      <CollapsibleSection title="Load Balancer Info" icon={Box} iconColor="text-gray-400">
        <div className="space-y-2 text-sm">
          <div className="flex justify-between">
            <span className="text-gray-500">Name</span>
            <span className="text-gray-300">{alb.name}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-500">State</span>
            <span className={alb.state === 'active' ? 'text-green-400' : 'text-yellow-400'}>{alb.state}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-500">Type</span>
            <span className="text-gray-300">{alb.type}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-500">Scheme</span>
            <span className="text-gray-300">{alb.scheme}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-500">DNS Name</span>
            <span className="text-gray-300 text-xs font-mono truncate max-w-[200px]" title={alb.dnsName}>{alb.dnsName}</span>
          </div>
        </div>
        {alb.consoleUrl && (
          <a
            href={alb.consoleUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="mt-3 flex items-center justify-center gap-2 px-3 py-2 bg-gray-700 hover:bg-gray-600 rounded text-sm"
          >
            <ExternalLink className="w-4 h-4" />
            Open in Console
          </a>
        )}
      </CollapsibleSection>

      {/* Security Groups */}
      {alb.securityGroups?.length > 0 && (
        <SecurityGroupsPanel securityGroups={alb.securityGroups} env={env} title="Security Groups" />
      )}

      {/* Listeners */}
      {alb.listeners?.length > 0 && (
        <CollapsibleSection title={`Listeners (${alb.listeners.length})`} icon={Radio} iconColor="text-blue-400" defaultOpen={false}>
          <div className="space-y-2">
            {alb.listeners.map((listener, i) => (
              <div key={i} className="flex items-center justify-between bg-gray-800 rounded p-2 text-sm">
                <span className="text-gray-300">{listener.protocol}:{listener.port}</span>
                <span className="text-xs text-gray-500 font-mono">{listener.arn?.split('/').pop()}</span>
              </div>
            ))}
          </div>
        </CollapsibleSection>
      )}

      {/* Target Groups */}
      {alb.targetGroups?.length > 0 && (
        <CollapsibleSection title={`Target Groups (${alb.targetGroups.length})`} icon={Target} iconColor="text-green-400">
          <div className="space-y-2">
            {alb.targetGroups.map((tg, i) => (
              <div key={i} className="bg-gray-800 rounded p-3">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm font-medium text-gray-300">{tg.name}</span>
                  <span className={`text-xs px-2 py-0.5 rounded ${
                    tg.health?.status === 'healthy' ? 'bg-green-500/20 text-green-400' :
                    tg.health?.status === 'unhealthy' ? 'bg-red-500/20 text-red-400' :
                    'bg-gray-500/20 text-gray-400'
                  }`}>
                    {tg.health?.healthy || 0}/{tg.health?.total || 0} healthy
                  </span>
                </div>
                <div className="text-xs space-y-1">
                  <div className="flex justify-between text-gray-500">
                    <span>Service</span>
                    <span className="text-gray-400">{tg.service || 'N/A'}</span>
                  </div>
                  <div className="flex justify-between text-gray-500">
                    <span>Port</span>
                    <span className="text-gray-400">{tg.protocol}:{tg.port}</span>
                  </div>
                  <div className="flex justify-between text-gray-500">
                    <span>Health Check</span>
                    <span className="text-gray-400 font-mono">{tg.healthCheckPath}</span>
                  </div>
                </div>
                {tg.consoleUrl && (
                  <a
                    href={tg.consoleUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="mt-2 flex items-center justify-center gap-1 px-2 py-1 bg-gray-700 hover:bg-gray-600 rounded text-xs"
                  >
                    <ExternalLink className="w-3 h-3" />
                    View Target Group
                  </a>
                )}
              </div>
            ))}
          </div>
        </CollapsibleSection>
      )}

      {/* Routing Rules */}
      {alb.rules?.length > 0 && (
        <CollapsibleSection title={`Routing Rules (${alb.rules.length})`} icon={Link2} iconColor="text-purple-400" defaultOpen={false}>
          <div className="space-y-2">
            {alb.rules.sort((a, b) => parseInt(a.priority) - parseInt(b.priority)).map((rule, i) => {
              const tg = alb.targetGroups?.find(t => t.arn === rule.targetGroupArn)
              return (
                <div key={i} className="bg-gray-800 rounded p-2 text-xs">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-gray-500">Priority {rule.priority}</span>
                    {tg && (
                      <span className={`px-1.5 py-0.5 rounded ${
                        tg.health?.status === 'healthy' ? 'bg-green-500/20 text-green-400' :
                        tg.health?.status === 'unhealthy' ? 'bg-red-500/20 text-red-400' :
                        'bg-gray-500/20 text-gray-400'
                      }`}>
                        {tg.service}
                      </span>
                    )}
                  </div>
                  <div className="text-gray-400 font-mono text-xs">
                    {rule.conditions.join(' ')}
                  </div>
                </div>
              )
            })}
          </div>
        </CollapsibleSection>
      )}
    </div>
  )
}
