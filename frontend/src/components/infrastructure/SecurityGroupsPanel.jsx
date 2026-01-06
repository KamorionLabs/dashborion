import { Shield, ArrowDownToLine, ArrowUpFromLine, ChevronDown, ChevronRight, RefreshCw, ExternalLink } from 'lucide-react'
import { useState } from 'react'
import { fetchWithRetry } from '../../utils'

/**
 * SecurityGroupsPanel - Displays security groups and their rules
 * Can be embedded in RDSDetails, RedisDetails, ALBDetails, etc.
 * Now fetches rules on-demand from the API for detailed view
 */
export default function SecurityGroupsPanel({ securityGroups, env, title = 'Security Groups' }) {
  const [expandedSg, setExpandedSg] = useState(null)

  if (!securityGroups || securityGroups.length === 0) {
    return null
  }

  return (
    <div className="bg-gray-900 rounded-lg p-4">
      <h3 className="text-sm font-medium text-gray-300 mb-3 flex items-center gap-2">
        <Shield className="w-4 h-4 text-orange-400" />
        {title}
      </h3>
      <div className="space-y-2">
        {securityGroups.map((sg, idx) => (
          <SecurityGroupCard
            key={sg.id || sg.groupId || idx}
            sg={sg}
            env={env}
            expanded={expandedSg === (sg.id || sg.groupId || idx)}
            onToggle={() => setExpandedSg(expandedSg === (sg.id || sg.groupId || idx) ? null : (sg.id || sg.groupId || idx))}
          />
        ))}
      </div>
    </div>
  )
}

function SecurityGroupCard({ sg, env, expanded, onToggle }) {
  const [rules, setRules] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  // Handle both string IDs and object formats
  const isStringId = typeof sg === 'string'
  const sgId = isStringId ? sg : (sg.id || sg.groupId)
  const sgName = isStringId ? sg : (sg.name || sg.groupName || sgId)

  // Fetch rules when expanded
  const fetchRules = async () => {
    if (rules || !sgId || !env) return
    setLoading(true)
    setError(null)
    try {
      const response = await fetchWithRetry(`/api/infrastructure/${env}/security-group/${sgId}`)
      if (response.ok) {
        const data = await response.json()
        setRules(data)
      } else {
        setError('Failed to load rules')
      }
    } catch (err) {
      setError('Failed to load rules')
      console.error('Error fetching SG rules:', err)
    } finally {
      setLoading(false)
    }
  }

  const handleToggle = () => {
    if (!expanded) {
      fetchRules()
    }
    onToggle()
  }

  // Use fetched rules or fallback to inline rules (only for object format)
  const inboundRules = rules?.inboundRules || (!isStringId && (sg.ingressRules || sg.ipPermissions)) || []
  const outboundRules = rules?.outboundRules || (!isStringId && (sg.egressRules || sg.ipPermissionsEgress)) || []

  // Use fetched name if available (for string IDs that got expanded)
  const displayName = rules?.name || sgName

  return (
    <div className="bg-gray-800 rounded-lg overflow-hidden">
      {/* Header - clickable */}
      <button
        onClick={handleToggle}
        className="w-full flex items-center justify-between px-3 py-2 hover:bg-gray-700/50 transition-colors"
      >
        <div className="flex items-center gap-2 min-w-0">
          {expanded ? (
            <ChevronDown className="w-4 h-4 text-gray-500 flex-shrink-0" />
          ) : (
            <ChevronRight className="w-4 h-4 text-gray-500 flex-shrink-0" />
          )}
          <span className="text-xs text-gray-300 truncate" title={displayName}>{displayName}</span>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <span className="text-[10px] text-gray-500 font-mono">{sgId}</span>
        </div>
      </button>

      {/* Expanded Content */}
      {expanded && (
        <div className="px-3 pb-3 border-t border-gray-700">
          {loading ? (
            <div className="flex items-center justify-center py-4 text-gray-400 text-xs">
              <RefreshCw className="w-4 h-4 animate-spin mr-2" />
              Loading rules...
            </div>
          ) : error ? (
            <div className="text-red-400 text-xs py-2">{error}</div>
          ) : (
            <div className="space-y-3 mt-3">
              {/* Description */}
              {(rules?.description || sg.description) && (
                <div className="text-xs text-gray-500">{rules?.description || sg.description}</div>
              )}

              {/* Inbound Rules */}
              <div>
                <div className="text-xs font-medium text-green-400 mb-1.5 flex items-center gap-1">
                  <ArrowDownToLine className="w-3 h-3" />
                  Inbound Rules ({inboundRules.length})
                </div>
                <RulesTable rules={inboundRules} type="ingress" />
              </div>

              {/* Outbound Rules */}
              <div>
                <div className="text-xs font-medium text-blue-400 mb-1.5 flex items-center gap-1">
                  <ArrowUpFromLine className="w-3 h-3" />
                  Outbound Rules ({outboundRules.length})
                </div>
                <RulesTable rules={outboundRules} type="egress" />
              </div>

              {/* Console Link */}
              {rules?.consoleUrl && (
                <a
                  href={rules.consoleUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs text-blue-400 hover:text-blue-300 flex items-center gap-1"
                >
                  <ExternalLink className="w-3 h-3" />
                  Open in AWS Console
                </a>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function RulesTable({ rules, type }) {
  if (!rules || rules.length === 0) {
    return <div className="text-[10px] text-gray-600 italic">No {type} rules</div>
  }

  return (
    <div className="space-y-1">
      {rules.map((rule, idx) => (
        <RuleRow key={idx} rule={rule} />
      ))}
    </div>
  )
}

function RuleRow({ rule }) {
  // Handle new API format (from get_security_group endpoint)
  if (rule.protocol && rule.portRange) {
    // New format from API
    const isSecurityGroup = rule.sourceType === 'security-group'
    const displaySource = isSecurityGroup ? (rule.sourceSgName || rule.source) : rule.source

    return (
      <div className="flex items-start gap-2 text-[10px] bg-gray-900/50 rounded px-2 py-1.5">
        <span className="text-cyan-400 font-mono flex-shrink-0 w-12">{rule.protocol}</span>
        <span className="text-gray-400 font-mono flex-shrink-0 w-14">{rule.portRange}</span>
        <div className="flex-1 min-w-0">
          {isSecurityGroup && rule.sourceSgConsoleUrl ? (
            <a
              href={rule.sourceSgConsoleUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="text-orange-400 hover:text-orange-300 hover:underline flex items-center gap-1"
              title={`Open ${displaySource} in Console`}
            >
              <Shield className="w-3 h-3" />
              <span className="truncate">{displaySource}</span>
            </a>
          ) : isSecurityGroup ? (
            <span className="text-orange-400 flex items-center gap-1">
              <Shield className="w-3 h-3" />
              <span className="truncate">{displaySource}</span>
            </span>
          ) : (
            <span className="text-gray-300 font-mono truncate" title={rule.source}>
              {rule.source}
            </span>
          )}
          {rule.description && (
            <div className="text-gray-500 italic mt-0.5 truncate" title={rule.description}>
              {rule.description}
            </div>
          )}
        </div>
      </div>
    )
  }

  // Legacy format - handle different rule formats (from describe-security-groups vs simplified)
  const protocol = rule.protocol || rule.ipProtocol || '-1'
  const fromPort = rule.fromPort ?? rule.port ?? '-'
  const toPort = rule.toPort ?? rule.port ?? '-'
  const description = rule.description || ''

  // Get sources/destinations
  const sources = []
  if (rule.source) sources.push(rule.source)
  if (rule.destination) sources.push(rule.destination)
  if (rule.cidrBlocks) sources.push(...rule.cidrBlocks)
  if (rule.ipRanges) rule.ipRanges.forEach(r => sources.push(r.cidrIp || r))
  if (rule.ipv6Ranges) rule.ipv6Ranges.forEach(r => sources.push(r.cidrIpv6 || r))
  if (rule.securityGroups) sources.push(...rule.securityGroups)
  if (rule.userIdGroupPairs) rule.userIdGroupPairs.forEach(p => sources.push(p.groupId || p))
  if (rule.prefixListIds) rule.prefixListIds.forEach(p => sources.push(p.prefixListId || p))

  const portDisplay = protocol === '-1' || protocol === 'all'
    ? 'All traffic'
    : fromPort === toPort
      ? `${protocol.toUpperCase()}/${fromPort}`
      : `${protocol.toUpperCase()}/${fromPort}-${toPort}`

  return (
    <div className="flex items-start gap-2 text-[10px] bg-gray-900/50 rounded px-2 py-1.5">
      <span className="text-cyan-400 font-mono flex-shrink-0 w-24">{portDisplay}</span>
      <div className="flex-1 min-w-0">
        {sources.length > 0 ? (
          <div className="space-y-0.5">
            {sources.map((src, idx) => (
              <div key={idx} className="text-gray-300 font-mono truncate" title={String(src)}>
                {String(src)}
              </div>
            ))}
          </div>
        ) : (
          <span className="text-gray-500">-</span>
        )}
        {description && (
          <div className="text-gray-500 italic mt-0.5 truncate" title={description}>
            {description}
          </div>
        )}
      </div>
    </div>
  )
}
