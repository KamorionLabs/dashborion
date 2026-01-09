import { Cloud, Globe, Layers, Shield, RefreshCw, Trash2, ExternalLink, Settings, Lock } from 'lucide-react'
import CollapsibleSection from '../common/CollapsibleSection'
import { useAuth } from '../../hooks/useAuth'
import { useConfig } from '../../ConfigContext'

export default function CloudFrontDetails({ cloudfront, infrastructure, env, onInvalidate, actionLoading }) {
  const { hasPermission } = useAuth()
  const appConfig = useConfig()
  const currentProjectId = appConfig.currentProjectId

  if (!cloudfront || cloudfront.error) {
    return <p className="text-red-400">{cloudfront?.error || 'CloudFront data not available'}</p>
  }

  const isLoading = actionLoading?.[`cf-${env}`]
  const canInvalidate = hasPermission('invalidate', currentProjectId, env, 'cloudfront')

  return (
    <div className="space-y-4">
      {/* General Info */}
      <CollapsibleSection title="Distribution Info" icon={Cloud} iconColor="text-orange-400">
        <div className="space-y-2 text-sm">
          <div className="flex justify-between">
            <span className="text-gray-500">Distribution ID</span>
            <span className="text-gray-300 font-mono">{cloudfront.id}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-500">Status</span>
            <span className={cloudfront.status === 'Deployed' ? 'text-green-400' : 'text-yellow-400'}>{cloudfront.status}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-500">Domain</span>
            <span className="text-gray-300 text-xs font-mono">{cloudfront.domainName}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-500">Enabled</span>
            <span className={cloudfront.enabled ? 'text-green-400' : 'text-red-400'}>{cloudfront.enabled ? 'Yes' : 'No'}</span>
          </div>
        </div>
        <div className="mt-3 flex gap-2">
          {onInvalidate && (
            <button
              onClick={() => onInvalidate(env, cloudfront.id)}
              disabled={!canInvalidate || isLoading}
              title={!canInvalidate ? 'Invalidate permission required (operator or admin)' : undefined}
              className="flex-1 flex items-center justify-center gap-2 bg-orange-600 hover:bg-orange-500 disabled:bg-gray-600 text-white py-2 px-3 rounded text-sm font-medium transition-colors"
            >
              {isLoading ? <RefreshCw className="w-4 h-4 animate-spin" /> : !canInvalidate ? <Lock className="w-4 h-4" /> : <Trash2 className="w-4 h-4" />}
              Invalidate Cache
            </button>
          )}
          {cloudfront.consoleUrl && (
            <a
              href={cloudfront.consoleUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="flex-1 flex items-center justify-center gap-2 px-3 py-2 bg-gray-700 hover:bg-gray-600 rounded text-sm"
            >
              <ExternalLink className="w-4 h-4" />
              Console
            </a>
          )}
        </div>
      </CollapsibleSection>

      {/* Aliases */}
      {cloudfront.aliases?.length > 0 && (
        <CollapsibleSection title={`Alternate Domain Names (${cloudfront.aliases.length})`} icon={Globe} iconColor="text-blue-400" defaultOpen={false}>
          <div className="space-y-1">
            {cloudfront.aliases.map((alias, i) => (
              <div key={i} className="text-sm font-mono text-brand-400">
                {alias}
              </div>
            ))}
          </div>
        </CollapsibleSection>
      )}

      {/* Origins */}
      {cloudfront.origins?.length > 0 && (
        <CollapsibleSection title={`Origins (${cloudfront.origins.length})`} icon={Layers} iconColor="text-purple-400">
          <div className="space-y-2">
            {cloudfront.origins.map((origin, i) => (
              <div key={i} className="bg-gray-800 rounded p-2">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs font-medium text-gray-300">{origin.id}</span>
                  <span className={`text-xs px-1.5 py-0.5 rounded ${
                    origin.type === 'alb' ? 'bg-blue-500/20 text-blue-400' :
                    origin.type === 's3' ? 'bg-purple-500/20 text-purple-400' :
                    'bg-gray-500/20 text-gray-400'
                  }`}>
                    {origin.type}
                  </span>
                </div>
                <div className="text-xs text-gray-500 font-mono truncate" title={origin.domainName}>
                  {origin.domainName}
                </div>
                {origin.path && (
                  <div className="text-xs text-gray-600 mt-1">Path: {origin.path}</div>
                )}
              </div>
            ))}
          </div>
        </CollapsibleSection>
      )}

      {/* WAF Info (if available) */}
      {cloudfront.webAclId && (
        <CollapsibleSection title="WAF Web ACL" icon={Shield} iconColor="text-green-400" defaultOpen={false}>
          <div className="text-sm text-gray-400 font-mono break-all">
            {cloudfront.webAclId}
          </div>
        </CollapsibleSection>
      )}

      {/* Cache Behaviors (if available) */}
      {cloudfront.cacheBehaviors?.length > 0 && (
        <CollapsibleSection title={`Cache Behaviors (${cloudfront.cacheBehaviors.length})`} icon={Settings} iconColor="text-gray-400" defaultOpen={false}>
          <div className="space-y-2">
            {cloudfront.cacheBehaviors.map((behavior, i) => (
              <div key={i} className="bg-gray-800 rounded p-2 text-xs">
                <div className="flex items-center justify-between">
                  <span className="text-gray-300 font-mono">{behavior.pathPattern || 'Default (*)'}</span>
                  <span className="text-gray-500">{behavior.targetOriginId}</span>
                </div>
                <div className="text-gray-600 mt-1">
                  {behavior.viewerProtocolPolicy} | TTL: {behavior.defaultTTL}s
                </div>
              </div>
            ))}
          </div>
        </CollapsibleSection>
      )}
    </div>
  )
}
