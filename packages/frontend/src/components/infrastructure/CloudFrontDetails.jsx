import { useState } from 'react'
import { Cloud, Globe, Layers, Shield, RefreshCw, Trash2, ExternalLink, Settings, Lock, ChevronDown } from 'lucide-react'
import CollapsibleSection from '../common/CollapsibleSection'
import { useAuth } from '../../hooks/useAuth'
import { useConfig } from '../../ConfigContext'

export default function CloudFrontDetails({ cloudfront, infrastructure, env, onInvalidate, actionLoading }) {
  const { hasPermission } = useAuth()
  const appConfig = useConfig()
  const currentProjectId = appConfig.currentProjectId
  const [selectedDistIdx, setSelectedDistIdx] = useState(0)

  if (!cloudfront || cloudfront.error) {
    return <p className="text-red-400">{cloudfront?.error || 'CloudFront data not available'}</p>
  }

  // Check if this is a multi-distribution response
  const isMultiDist = cloudfront.distributions && cloudfront.distributions.length > 1
  const distributions = cloudfront.distributions || [cloudfront]
  const selectedDist = distributions[selectedDistIdx] || distributions[0]

  const isLoading = actionLoading?.[`cf-${env}`]
  const canInvalidate = hasPermission('invalidate', currentProjectId, env, 'cloudfront')

  return (
    <div className="space-y-4">
      {/* Distribution Selector (for multi-distribution) */}
      {isMultiDist && (
        <div className="bg-gray-900 rounded-lg p-3 border border-gray-700">
          <label className="block text-xs text-gray-500 mb-2">Select Distribution ({distributions.length} total)</label>
          <div className="relative">
            <select
              value={selectedDistIdx}
              onChange={(e) => setSelectedDistIdx(parseInt(e.target.value))}
              className="w-full bg-gray-800 border border-gray-600 rounded px-3 py-2 text-sm text-gray-200 appearance-none cursor-pointer hover:border-gray-500 focus:border-orange-500 focus:outline-none"
            >
              {distributions.map((dist, idx) => (
                <option key={dist.id} value={idx}>
                  {dist.aliases?.[0] || dist.domainName || dist.id}
                </option>
              ))}
            </select>
            <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" />
          </div>
        </div>
      )}

      {/* General Info */}
      <CollapsibleSection title="Distribution Info" icon={Cloud} iconColor="text-orange-400">
        <div className="space-y-2 text-sm">
          <div className="flex justify-between">
            <span className="text-gray-500">Distribution ID</span>
            <span className="text-gray-300 font-mono">{selectedDist.id}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-500">Status</span>
            <span className={selectedDist.status === 'Deployed' ? 'text-green-400' : 'text-yellow-400'}>{selectedDist.status}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-500">Domain</span>
            <span className="text-gray-300 text-xs font-mono">{selectedDist.domainName}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-500">Enabled</span>
            <span className={selectedDist.enabled ? 'text-green-400' : 'text-red-400'}>{selectedDist.enabled ? 'Yes' : 'No'}</span>
          </div>
        </div>
        <div className="mt-3 flex flex-col gap-2">
          {onInvalidate && (
            <div className="flex gap-2">
              <button
                onClick={() => onInvalidate(env, selectedDist.id)}
                disabled={!canInvalidate || isLoading}
                title={!canInvalidate ? 'Invalidate permission required (operator or admin)' : `Invalidate ${selectedDist.id}`}
                className="flex-1 flex items-center justify-center gap-2 bg-orange-600 hover:bg-orange-500 disabled:bg-gray-600 text-white py-2 px-3 rounded text-sm font-medium transition-colors"
              >
                {isLoading ? <RefreshCw className="w-4 h-4 animate-spin" /> : !canInvalidate ? <Lock className="w-4 h-4" /> : <Trash2 className="w-4 h-4" />}
                Invalidate Cache
              </button>
              {selectedDist.consoleUrl && (
                <a
                  href={selectedDist.consoleUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center justify-center gap-2 px-3 py-2 bg-gray-700 hover:bg-gray-600 rounded text-sm"
                  title="Open in AWS Console"
                >
                  <ExternalLink className="w-4 h-4" />
                </a>
              )}
            </div>
          )}
          {/* Invalidate All button for multi-distribution */}
          {isMultiDist && onInvalidate && (
            <button
              onClick={() => {
                // Invalidate all distributions sequentially
                distributions.forEach(dist => onInvalidate(env, dist.id))
              }}
              disabled={!canInvalidate || isLoading}
              title={!canInvalidate ? 'Invalidate permission required' : `Invalidate all ${distributions.length} distributions`}
              className="flex items-center justify-center gap-2 bg-red-600 hover:bg-red-500 disabled:bg-gray-600 text-white py-2 px-3 rounded text-sm font-medium transition-colors"
            >
              {isLoading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Trash2 className="w-4 h-4" />}
              Invalidate All ({distributions.length})
            </button>
          )}
        </div>
      </CollapsibleSection>

      {/* Aliases */}
      {selectedDist.aliases?.length > 0 && (
        <CollapsibleSection title={`Alternate Domain Names (${selectedDist.aliases.length})`} icon={Globe} iconColor="text-blue-400" defaultOpen={false}>
          <div className="space-y-1">
            {selectedDist.aliases.map((alias, i) => (
              <div key={i} className="text-sm font-mono text-brand-400">
                {alias}
              </div>
            ))}
          </div>
        </CollapsibleSection>
      )}

      {/* Origins */}
      {selectedDist.origins?.length > 0 && (
        <CollapsibleSection title={`Origins (${selectedDist.origins.length})`} icon={Layers} iconColor="text-purple-400">
          <div className="space-y-2">
            {selectedDist.origins.map((origin, i) => (
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
      {selectedDist.webAclId && (
        <CollapsibleSection title="WAF Web ACL" icon={Shield} iconColor="text-green-400" defaultOpen={false}>
          <div className="text-sm text-gray-400 font-mono break-all">
            {selectedDist.webAclId}
          </div>
        </CollapsibleSection>
      )}

      {/* Cache Behaviors (if available) */}
      {selectedDist.cacheBehaviors?.length > 0 && (
        <CollapsibleSection title={`Cache Behaviors (${selectedDist.cacheBehaviors.length})`} icon={Settings} iconColor="text-gray-400" defaultOpen={false}>
          <div className="space-y-2">
            {selectedDist.cacheBehaviors.map((behavior, i) => (
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
