import { Network, Route, Globe, Shield, Link2, Workflow, ExternalLink, Copy, Check, Search, ChevronDown, ChevronRight, RefreshCw, Server, Database, Box, Cloud, Wifi } from 'lucide-react'
import { useState, useEffect, useCallback } from 'react'
import { fetchWithRetry } from '../../utils'

// Copy to clipboard helper
function CopyButton({ text }) {
  const [copied, setCopied] = useState(false)
  const handleCopy = async () => {
    await navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }
  return (
    <button onClick={handleCopy} className="ml-2 text-gray-500 hover:text-gray-300 transition-colors">
      {copied ? <Check className="w-3 h-3 text-green-400" /> : <Copy className="w-3 h-3" />}
    </button>
  )
}

// Info row helper
function InfoRow({ label, value, mono = false, copy = false, color }) {
  if (!value && value !== 0) return null
  return (
    <div className="flex justify-between items-center">
      <span className="text-gray-500">{label}</span>
      <span className={`${mono ? 'font-mono text-xs' : ''} ${color || 'text-gray-300'} flex items-center`}>
        {value}
        {copy && <CopyButton text={value} />}
      </span>
    </div>
  )
}

/**
 * Route Table Details - shows routes and associations
 */
export function RouteTableDetails({ routeTable, env }) {
  if (!routeTable) {
    return <p className="text-red-400">Route table data not available</p>
  }

  // Build console URL
  const region = 'eu-west-3'
  const consoleUrl = routeTable.consoleUrl ||
    `https://${region}.console.aws.amazon.com/vpcconsole/home?region=${region}#RouteTables:routeTableId=${routeTable.id}`

  return (
    <div className="space-y-4">
      {/* General Info */}
      <div className="bg-gray-900 rounded-lg p-4">
        <h3 className="text-sm font-medium text-gray-300 mb-3 flex items-center gap-2">
          <Route className="w-4 h-4 text-cyan-400" />
          Route Table Info
        </h3>
        <div className="space-y-2 text-sm">
          <InfoRow label="ID" value={routeTable.id} mono copy />
          <InfoRow label="Name" value={routeTable.name} />
          <InfoRow label="VPC ID" value={routeTable.vpcId} mono copy />
          <InfoRow
            label="Main"
            value={routeTable.isMain ? 'Yes' : 'No'}
            color={routeTable.isMain ? 'text-green-400' : 'text-gray-400'}
          />
          <InfoRow
            label="Associations"
            value={`${routeTable.subnetAssociations?.length || routeTable.associations?.length || 0} subnets`}
          />
        </div>
      </div>

      {/* Routes */}
      <div className="bg-gray-900 rounded-lg p-4">
        <h3 className="text-sm font-medium text-gray-300 mb-3 flex items-center gap-2">
          <Network className="w-4 h-4" />
          Routes ({routeTable.routes?.length || 0})
        </h3>
        <div className="space-y-2 max-h-64 overflow-y-auto">
          {routeTable.routes?.map((route, idx) => {
            // Get target info - handle both old and new field formats
            const targetType = route.targetType || (route.gatewayId?.startsWith('igw-') ? 'internet-gateway' : route.gatewayId === 'local' ? 'local' : route.natGatewayId ? 'nat-gateway' : route.transitGatewayId ? 'transit-gateway' : route.vpcPeeringConnectionId ? 'vpc-peering' : route.networkInterfaceId ? 'network-interface' : route.instanceId ? 'instance' : null)
            const targetId = route.targetId || route.gatewayId || route.natGatewayId || route.transitGatewayId || route.vpcPeeringConnectionId || route.networkInterfaceId || route.instanceId || route.target
            const destination = route.destination || route.destinationCidrBlock
            const isDefaultRoute = destination === '0.0.0.0/0'

            // Target type labels and colors
            const targetConfig = {
              'internet-gateway': { label: 'Internet Gateway', color: 'text-green-400', bg: 'bg-green-500/20' },
              'nat-gateway': { label: 'NAT Gateway', color: 'text-yellow-400', bg: 'bg-yellow-500/20' },
              'transit-gateway': { label: 'Transit Gateway', color: 'text-purple-400', bg: 'bg-purple-500/20' },
              'vpc-peering': { label: 'VPC Peering', color: 'text-pink-400', bg: 'bg-pink-500/20' },
              'network-interface': { label: 'ENI', color: 'text-blue-400', bg: 'bg-blue-500/20' },
              'instance': { label: 'NAT Instance', color: 'text-orange-400', bg: 'bg-orange-500/20' },
              'local': { label: 'Local', color: 'text-cyan-400', bg: 'bg-cyan-500/20' },
              'gateway': { label: 'Gateway', color: 'text-gray-400', bg: 'bg-gray-500/20' },
            }
            const config = targetConfig[targetType] || { label: targetType || 'Unknown', color: 'text-gray-400', bg: 'bg-gray-500/20' }

            return (
              <div key={idx} className={`rounded p-2 text-xs ${isDefaultRoute ? 'bg-gray-700 border border-gray-600' : 'bg-gray-800'}`}>
                <div className="flex justify-between items-center mb-1.5">
                  <span className={`font-mono ${isDefaultRoute ? 'text-white font-bold' : 'text-cyan-400'}`}>
                    {destination}
                    {isDefaultRoute && <span className="ml-2 text-gray-400 font-normal">(default)</span>}
                  </span>
                  <span className={`px-1.5 py-0.5 rounded ${
                    route.state === 'active' ? 'bg-green-500/20 text-green-400' : 'bg-yellow-500/20 text-yellow-400'
                  }`}>
                    {route.state}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <span className={`px-2 py-0.5 rounded ${config.bg} ${config.color}`}>
                    {config.label}
                  </span>
                  {targetId && targetId !== 'local' && (
                    <span className="text-gray-400 font-mono truncate flex-1" title={targetId}>
                      {targetId}
                    </span>
                  )}
                </div>
              </div>
            )
          })}
          {(!routeTable.routes || routeTable.routes.length === 0) && (
            <div className="text-gray-500 italic text-xs">No routes</div>
          )}
        </div>
      </div>

      {/* Associations */}
      {(() => {
        // Handle both formats: subnetAssociations (array of IDs) or associations (array of objects)
        const associations = routeTable.subnetAssociations || routeTable.associations || []
        const assocCount = associations.length

        return (
          <div className="bg-gray-900 rounded-lg p-4">
            <h3 className="text-sm font-medium text-gray-300 mb-3 flex items-center gap-2">
              <Link2 className="w-4 h-4" />
              Subnet Associations ({assocCount})
            </h3>
            <div className="space-y-1">
              {associations.map((assoc, idx) => {
                // Handle both string IDs and object format
                const subnetId = typeof assoc === 'string' ? assoc : (assoc.subnetId || assoc.id)
                const isMain = typeof assoc === 'object' && assoc.main

                return (
                  <div key={idx} className="flex justify-between text-xs bg-gray-800 rounded px-2 py-1.5">
                    <span className="font-mono text-gray-300">{subnetId}</span>
                    <CopyButton text={subnetId} />
                  </div>
                )
              })}
              {assocCount === 0 && (
                <div className="text-gray-500 italic text-xs">No explicit associations (uses main RT)</div>
              )}
            </div>
          </div>
        )
      })()}

      {/* Console Link */}
      <a href={consoleUrl} target="_blank" rel="noopener noreferrer"
         className="block w-full bg-cyan-500/20 hover:bg-cyan-500/30 text-cyan-400 text-center py-2 rounded-lg text-sm font-medium transition-colors">
        <ExternalLink className="w-4 h-4 inline mr-2" />
        Open in AWS Console
      </a>
    </div>
  )
}

// ENI type icons and colors
const eniTypeConfig = {
  'ecs-task': { icon: Server, color: 'text-green-400', bg: 'bg-green-500/20', label: 'ECS Task' },
  'lambda': { icon: Cloud, color: 'text-yellow-400', bg: 'bg-yellow-500/20', label: 'Lambda' },
  'rds': { icon: Database, color: 'text-cyan-400', bg: 'bg-cyan-500/20', label: 'RDS' },
  'elasticache': { icon: Database, color: 'text-red-400', bg: 'bg-red-500/20', label: 'ElastiCache' },
  'nat-gateway': { icon: Wifi, color: 'text-yellow-400', bg: 'bg-yellow-500/20', label: 'NAT Gateway' },
  'vpc-endpoint': { icon: Shield, color: 'text-purple-400', bg: 'bg-purple-500/20', label: 'VPC Endpoint' },
  'load-balancer': { icon: Box, color: 'text-blue-400', bg: 'bg-blue-500/20', label: 'Load Balancer' },
  'ec2-instance': { icon: Server, color: 'text-orange-400', bg: 'bg-orange-500/20', label: 'EC2 Instance' },
  'cloudfront': { icon: Cloud, color: 'text-orange-400', bg: 'bg-orange-500/20', label: 'CloudFront' },
  'unknown': { icon: Wifi, color: 'text-gray-400', bg: 'bg-gray-500/20', label: 'Unknown' }
}

// Parse resource info from ENI description/type
function parseResourceInfo(eni) {
  const type = eni.attachment?.type
  const description = eni.description || ''

  switch (type) {
    case 'load-balancer':
      // "ELB app/homebox-staging-alb/1c0822a4227e1e3d" -> ALB name
      const albMatch = description.match(/ELB\s+(app|net)\/([^/]+)\//)
      if (albMatch) {
        return {
          resourceType: albMatch[1] === 'app' ? 'ALB' : 'NLB',
          resourceName: albMatch[2],
          resourceId: description.split('/')[2]
        }
      }
      break
    case 'ecs-task':
      // Parse ECS ARN: arn:aws:ecs:region:account:attachment/uuid
      if (description.includes(':attachment/')) {
        return {
          resourceType: 'ECS Task',
          resourceName: 'Fargate Task',
          resourceId: description.split(':attachment/')[1]?.substring(0, 8)
        }
      }
      break
    case 'rds':
      return {
        resourceType: 'RDS',
        resourceName: 'Database Instance',
        resourceId: null
      }
    case 'elasticache':
      // "ElastiCache homebox-staging-redis-001"
      const cacheMatch = description.match(/ElastiCache\s+(.+)/)
      if (cacheMatch) {
        return {
          resourceType: 'ElastiCache',
          resourceName: cacheMatch[1],
          resourceId: null
        }
      }
      break
    case 'nat-gateway':
      // "Interface for NAT Gateway nat-0f463cac01e841070"
      const natMatch = description.match(/NAT Gateway\s+(nat-\w+)/)
      if (natMatch) {
        return {
          resourceType: 'NAT Gateway',
          resourceName: natMatch[1],
          resourceId: natMatch[1]
        }
      }
      break
    case 'cloudfront':
      return {
        resourceType: 'CloudFront',
        resourceName: 'VPC Origin',
        resourceId: null
      }
    case 'lambda':
      // Try to extract function name
      const lambdaMatch = description.match(/:function:([^:]+)/)
      if (lambdaMatch) {
        return {
          resourceType: 'Lambda',
          resourceName: lambdaMatch[1],
          resourceId: null
        }
      }
      break
  }
  return null
}

// Security Group expandable component with rules
function SecurityGroupBadge({ sg, env }) {
  const [expanded, setExpanded] = useState(false)
  const [rules, setRules] = useState(null)
  const [loading, setLoading] = useState(false)

  const fetchRules = async () => {
    if (rules) return // Already loaded
    setLoading(true)
    try {
      const response = await fetchWithRetry(`/api/infrastructure/${env}/security-group/${sg.id}`)
      if (response.ok) {
        const data = await response.json()
        setRules(data)
      }
    } catch (err) {
      console.error('Error fetching SG rules:', err)
    } finally {
      setLoading(false)
    }
  }

  const handleClick = () => {
    if (!expanded) fetchRules()
    setExpanded(!expanded)
  }

  return (
    <div className="bg-gray-700/50 rounded overflow-hidden">
      <button
        onClick={handleClick}
        className="w-full px-2 py-1.5 flex items-center justify-between hover:bg-gray-600/50 transition-colors text-left"
      >
        <div className="flex items-center gap-2 min-w-0 flex-1">
          <Shield className="w-3 h-3 text-orange-400 flex-shrink-0" />
          <span className="text-xs text-gray-300 truncate" title={sg.name}>
            {sg.name}
          </span>
        </div>
        <div className="flex items-center gap-1 flex-shrink-0 ml-2">
          <span className="text-xs text-gray-500 font-mono">{sg.id}</span>
          {expanded ? (
            <ChevronDown className="w-3 h-3 text-gray-500" />
          ) : (
            <ChevronRight className="w-3 h-3 text-gray-500" />
          )}
        </div>
      </button>

      {expanded && (
        <div className="px-2 pb-2 border-t border-gray-600/50">
          {loading ? (
            <div className="text-xs text-gray-500 py-2 flex items-center gap-1">
              <RefreshCw className="w-3 h-3 animate-spin" />
              Loading rules...
            </div>
          ) : rules ? (
            <div className="mt-2 space-y-2">
              {/* Inbound Rules */}
              {rules.inboundRules?.length > 0 && (
                <div>
                  <div className="text-xs text-green-400 font-medium mb-1">Inbound ({rules.inboundRules.length})</div>
                  <div className="space-y-1">
                    {rules.inboundRules.slice(0, 5).map((rule, idx) => (
                      <div key={idx} className="text-xs bg-gray-800 rounded px-2 py-1 flex items-center gap-2">
                        <span className="text-green-400 font-mono w-12">{rule.protocol}</span>
                        <span className="text-cyan-400 font-mono w-16">{rule.portRange}</span>
                        <span className="text-gray-400 truncate flex-1" title={rule.description || rule.source}>
                          {rule.sourceType === 'security-group' ? (
                            rule.sourceSgConsoleUrl ? (
                              <a
                                href={rule.sourceSgConsoleUrl}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-orange-400 hover:text-orange-300 hover:underline flex items-center gap-1"
                                title={`Open ${rule.sourceSgName || rule.sourceSgId} in Console`}
                              >
                                <Shield className="w-3 h-3" />
                                {rule.sourceSgName || rule.source}
                              </a>
                            ) : (
                              <span className="text-orange-400">{rule.sourceSgName || rule.source}</span>
                            )
                          ) : (
                            rule.source
                          )}
                        </span>
                      </div>
                    ))}
                    {rules.inboundRules.length > 5 && (
                      <div className="text-xs text-gray-500">+{rules.inboundRules.length - 5} more...</div>
                    )}
                  </div>
                </div>
              )}

              {/* Outbound Rules */}
              {rules.outboundRules?.length > 0 && (
                <div>
                  <div className="text-xs text-blue-400 font-medium mb-1">Outbound ({rules.outboundRules.length})</div>
                  <div className="space-y-1">
                    {rules.outboundRules.slice(0, 3).map((rule, idx) => (
                      <div key={idx} className="text-xs bg-gray-800 rounded px-2 py-1 flex items-center gap-2">
                        <span className="text-blue-400 font-mono w-12">{rule.protocol}</span>
                        <span className="text-cyan-400 font-mono w-16">{rule.portRange}</span>
                        <span className="text-gray-400 truncate flex-1" title={rule.description || rule.source}>
                          {rule.sourceType === 'security-group' ? (
                            rule.sourceSgConsoleUrl ? (
                              <a
                                href={rule.sourceSgConsoleUrl}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-orange-400 hover:text-orange-300 hover:underline flex items-center gap-1"
                                title={`Open ${rule.sourceSgName || rule.sourceSgId} in Console`}
                              >
                                <Shield className="w-3 h-3" />
                                {rule.sourceSgName || rule.source}
                              </a>
                            ) : (
                              <span className="text-orange-400">{rule.sourceSgName || rule.source}</span>
                            )
                          ) : (
                            rule.source
                          )}
                        </span>
                      </div>
                    ))}
                    {rules.outboundRules.length > 3 && (
                      <div className="text-xs text-gray-500">+{rules.outboundRules.length - 3} more...</div>
                    )}
                  </div>
                </div>
              )}

              {/* Console link */}
              {rules.consoleUrl && (
                <a
                  href={rules.consoleUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs text-blue-400 hover:text-blue-300 flex items-center gap-1 mt-1"
                >
                  <ExternalLink className="w-3 h-3" />
                  View in Console
                </a>
              )}
            </div>
          ) : (
            <div className="text-xs text-gray-500 py-2">No rules data</div>
          )}
        </div>
      )}
    </div>
  )
}

// Enhanced ENI Card component
function ENICard({ eni, env, showSubnet = false }) {
  const typeInfo = eniTypeConfig[eni.attachment?.type] || eniTypeConfig.unknown
  const TypeIcon = typeInfo.icon
  const resourceInfo = parseResourceInfo(eni)

  return (
    <div className="bg-gray-800 rounded-lg p-3 space-y-2">
      {/* Header Row: Type + AZ + IP */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className={`p-1.5 rounded ${typeInfo.bg}`}>
            <TypeIcon className={`w-4 h-4 ${typeInfo.color}`} />
          </div>
          <div>
            <span className={`text-sm font-medium ${typeInfo.color}`}>
              {typeInfo.label}
            </span>
            {/* AZ Badge */}
            <span className="ml-2 px-1.5 py-0.5 text-xs bg-gray-700 text-gray-400 rounded">
              {eni.az}
            </span>
          </div>
        </div>
        <div className="text-right">
          <span className="font-mono text-sm text-cyan-400 font-medium">
            {eni.privateIp}
          </span>
          {eni.publicIp && (
            <div className="text-xs text-orange-400 font-mono">
              {eni.publicIp}
            </div>
          )}
        </div>
      </div>

      {/* Resource Link */}
      {resourceInfo && (
        <div className="flex items-center gap-2 px-2 py-1.5 bg-gray-700/50 rounded">
          <Link2 className={`w-3 h-3 ${typeInfo.color}`} />
          <span className="text-xs text-gray-400">{resourceInfo.resourceType}:</span>
          <span className="text-xs text-gray-200 font-medium">{resourceInfo.resourceName}</span>
          {resourceInfo.resourceId && (
            <span className="text-xs text-gray-500 font-mono">({resourceInfo.resourceId})</span>
          )}
        </div>
      )}

      {/* ENI ID + Status */}
      <div className="flex items-center justify-between text-xs">
        <div className="flex items-center text-gray-500">
          <span className="font-mono">{eni.id}</span>
          <CopyButton text={eni.id} />
        </div>
        <span className={eni.status === 'in-use' ? 'text-green-400' : 'text-yellow-400'}>
          {eni.status}
        </span>
      </div>

      {/* Subnet (for VPC view) */}
      {showSubnet && (
        <div className="text-xs text-gray-500">
          Subnet: <span className="font-mono text-gray-400">{eni.subnetId}</span>
        </div>
      )}

      {/* Security Groups - Full names, expandable */}
      {eni.securityGroups?.length > 0 && (
        <div className="space-y-1">
          <div className="text-xs text-gray-500 font-medium">Security Groups ({eni.securityGroups.length})</div>
          {eni.securityGroups.map((sg) => (
            <SecurityGroupBadge key={sg.id} sg={sg} env={env} />
          ))}
        </div>
      )}

      {/* Console Link */}
      {eni.consoleUrl && (
        <a
          href={eni.consoleUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="text-xs text-blue-400 hover:text-blue-300 flex items-center gap-1"
        >
          <ExternalLink className="w-3 h-3" />
          Open in Console
        </a>
      )}
    </div>
  )
}

/**
 * Subnet Details - enhanced with all info + ENI listing
 */
export function SubnetDetails({ subnet, env }) {
  const [enis, setEnis] = useState([])
  const [eniLoading, setEniLoading] = useState(false)
  const [eniError, setEniError] = useState(null)
  const [eniExpanded, setEniExpanded] = useState(false)
  const [searchIp, setSearchIp] = useState('')
  const [searchInput, setSearchInput] = useState('')
  const [currentSubnetId, setCurrentSubnetId] = useState(null)

  // Reset ENI state when subnet changes
  useEffect(() => {
    if (subnet?.id !== currentSubnetId) {
      setCurrentSubnetId(subnet?.id)
      setEnis([])
      setEniError(null)
      setSearchIp('')
      setSearchInput('')
      // Keep expanded state but refetch if expanded
      if (eniExpanded && subnet?.id) {
        // Will trigger fetch via the next useEffect
      }
    }
  }, [subnet?.id, currentSubnetId, eniExpanded])

  // Fetch ENIs for this subnet
  const fetchEnis = useCallback(async (ipFilter = '') => {
    if (!env || !subnet?.id) return
    setEniLoading(true)
    setEniError(null)
    try {
      const params = new URLSearchParams()
      params.set('subnetId', subnet.id)
      if (ipFilter) params.set('searchIp', ipFilter)

      const response = await fetchWithRetry(`/api/infrastructure/${env}/enis?${params}`)
      if (!response.ok) throw new Error(`Failed to fetch ENIs: ${response.status}`)
      const data = await response.json()
      setEnis(data.enis || [])
    } catch (err) {
      console.error('Error fetching ENIs:', err)
      setEniError(err.message)
    } finally {
      setEniLoading(false)
    }
  }, [env, subnet?.id])

  // Load ENIs when expanded or when subnet changes while expanded
  useEffect(() => {
    if (eniExpanded && subnet?.id && enis.length === 0 && !eniLoading) {
      fetchEnis(searchIp)
    }
  }, [eniExpanded, subnet?.id, enis.length, eniLoading, fetchEnis, searchIp])

  // Handle search
  const handleSearch = () => {
    setSearchIp(searchInput)
    fetchEnis(searchInput)
  }

  if (!subnet) {
    return <p className="text-red-400">Subnet data not available</p>
  }

  // Handle both field naming conventions
  const cidrBlock = subnet.cidrBlock || subnet.cidr
  const availabilityZone = subnet.availabilityZone || subnet.az
  const subnetType = subnet.subnetType || subnet.type

  const typeColors = {
    public: 'text-green-400',
    private: 'text-blue-400',
    database: 'text-purple-400',
  }

  const typeBgColors = {
    public: 'bg-green-500/20 border-green-500/50',
    private: 'bg-blue-500/20 border-blue-500/50',
    database: 'bg-purple-500/20 border-purple-500/50',
  }

  // Build console URL
  const region = 'eu-west-3'
  const consoleUrl = subnet.consoleUrl ||
    `https://${region}.console.aws.amazon.com/vpcconsole/home?region=${region}#SubnetDetails:subnetId=${subnet.id}`

  return (
    <div className="space-y-4">
      {/* Type Badge */}
      <div className={`rounded-lg p-3 border ${typeBgColors[subnetType] || 'bg-gray-500/20 border-gray-500/50'}`}>
        <div className="flex items-center justify-between">
          <span className={`text-lg font-bold ${typeColors[subnetType] || 'text-gray-300'}`}>
            {subnetType?.charAt(0).toUpperCase() + subnetType?.slice(1) || 'Unknown'} Subnet
          </span>
          <span className="text-gray-400 text-sm">{availabilityZone}</span>
        </div>
      </div>

      {/* General Info */}
      <div className="bg-gray-900 rounded-lg p-4">
        <h3 className="text-sm font-medium text-gray-300 mb-3 flex items-center gap-2">
          <Network className="w-4 h-4 text-blue-400" />
          Subnet Info
        </h3>
        <div className="space-y-2 text-sm">
          <InfoRow label="Subnet ID" value={subnet.id} mono copy />
          <InfoRow label="Name" value={subnet.name} />
          <InfoRow label="CIDR Block" value={cidrBlock} mono />
          <InfoRow label="Availability Zone" value={availabilityZone} />
          <InfoRow label="VPC ID" value={subnet.vpcId} mono copy />
        </div>
      </div>

      {/* IP Configuration */}
      <div className="bg-gray-900 rounded-lg p-4">
        <h3 className="text-sm font-medium text-gray-300 mb-3">IP Configuration</h3>
        <div className="space-y-2 text-sm">
          <InfoRow
            label="Available IPs"
            value={subnet.availableIpAddressCount ?? subnet.availableIps ?? '-'}
            color={subnet.availableIpAddressCount > 100 ? 'text-green-400' : subnet.availableIpAddressCount > 20 ? 'text-yellow-400' : 'text-red-400'}
          />
          {subnet.mapPublicIpOnLaunch !== undefined && (
            <InfoRow
              label="Map Public IP"
              value={subnet.mapPublicIpOnLaunch ? 'Yes' : 'No'}
              color={subnet.mapPublicIpOnLaunch ? 'text-green-400' : 'text-gray-400'}
            />
          )}
          <InfoRow
            label="Auto-assign IPv6"
            value={subnet.assignIpv6AddressOnCreation !== undefined ? (subnet.assignIpv6AddressOnCreation ? 'Yes' : 'No') : '-'}
            color={subnet.assignIpv6AddressOnCreation ? 'text-green-400' : 'text-gray-400'}
          />
        </div>
      </div>

      {/* Route Table Association */}
      {subnet.routeTableId && (
        <div className="bg-gray-900 rounded-lg p-4">
          <h3 className="text-sm font-medium text-gray-300 mb-3 flex items-center gap-2">
            <Route className="w-4 h-4 text-cyan-400" />
            Route Table
          </h3>
          <div className="flex items-center justify-between text-xs bg-gray-800 rounded px-3 py-2">
            <span className="text-gray-300 font-mono">{subnet.routeTableId}</span>
            <CopyButton text={subnet.routeTableId} />
          </div>
        </div>
      )}

      {/* Security Groups */}
      {subnet.securityGroups?.length > 0 && (
        <div className="bg-gray-900 rounded-lg p-4">
          <h3 className="text-sm font-medium text-gray-300 mb-3 flex items-center gap-2">
            <Shield className="w-4 h-4 text-orange-400" />
            Associated Security Groups ({subnet.securityGroups.length})
          </h3>
          <div className="space-y-2 max-h-48 overflow-y-auto">
            {subnet.securityGroups.map((sg, idx) => (
              <div key={idx} className="bg-gray-800 rounded p-2 text-xs">
                <div className="flex justify-between items-center">
                  <span className="text-orange-400 font-medium">{sg.name || sg.groupName || sg.GroupName}</span>
                  <span className="text-gray-500 font-mono">{sg.id || sg.groupId || sg.GroupId}</span>
                </div>
                {sg.description && (
                  <div className="text-gray-500 mt-1 text-xs">{sg.description}</div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Network ACL */}
      {subnet.networkAclId && (
        <div className="bg-gray-900 rounded-lg p-4">
          <h3 className="text-sm font-medium text-gray-300 mb-3 flex items-center gap-2">
            <Shield className="w-4 h-4 text-yellow-400" />
            Network ACL
          </h3>
          <div className="flex items-center justify-between text-xs bg-gray-800 rounded px-3 py-2">
            <span className="text-gray-300 font-mono">{subnet.networkAclId}</span>
            <CopyButton text={subnet.networkAclId} />
          </div>
        </div>
      )}

      {/* ENIs Section - Collapsible */}
      <div className="bg-gray-900 rounded-lg overflow-hidden">
        <button
          onClick={() => setEniExpanded(!eniExpanded)}
          className="w-full p-4 flex items-center justify-between hover:bg-gray-800 transition-colors"
        >
          <h3 className="text-sm font-medium text-gray-300 flex items-center gap-2">
            <Wifi className="w-4 h-4 text-cyan-400" />
            Network Interfaces (ENIs)
            {enis.length > 0 && <span className="text-cyan-400 text-xs">({enis.length})</span>}
          </h3>
          {eniExpanded ? (
            <ChevronDown className="w-4 h-4 text-gray-400" />
          ) : (
            <ChevronRight className="w-4 h-4 text-gray-400" />
          )}
        </button>

        {eniExpanded && (
          <div className="px-4 pb-4 border-t border-gray-800">
            {/* Search Bar */}
            <div className="flex gap-2 mt-3 mb-3">
              <div className="flex-1 relative">
                <Search className="absolute left-2 top-1/2 transform -translate-y-1/2 w-4 h-4 text-gray-500" />
                <input
                  type="text"
                  value={searchInput}
                  onChange={(e) => setSearchInput(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                  placeholder="Search by IP..."
                  className="w-full pl-8 pr-3 py-1.5 bg-gray-800 border border-gray-700 rounded text-xs text-gray-300 placeholder-gray-500 focus:outline-none focus:border-cyan-500"
                />
              </div>
              <button
                onClick={handleSearch}
                className="px-3 py-1.5 bg-cyan-500/20 hover:bg-cyan-500/30 text-cyan-400 rounded text-xs transition-colors"
              >
                Search
              </button>
              <button
                onClick={() => fetchEnis(searchIp)}
                className="p-1.5 text-gray-400 hover:text-cyan-400 transition-colors"
                title="Refresh"
              >
                <RefreshCw className={`w-4 h-4 ${eniLoading ? 'animate-spin' : ''}`} />
              </button>
            </div>

            {/* Loading State */}
            {eniLoading && (
              <div className="flex items-center justify-center py-4 text-gray-400 text-xs">
                <RefreshCw className="w-4 h-4 animate-spin mr-2" />
                Loading ENIs...
              </div>
            )}

            {/* Error State */}
            {eniError && (
              <div className="text-red-400 text-xs py-2">{eniError}</div>
            )}

            {/* ENI List */}
            {!eniLoading && !eniError && (
              <div className="space-y-3 max-h-[500px] overflow-y-auto">
                {enis.length === 0 ? (
                  <div className="text-gray-500 text-xs text-center py-4">
                    {searchIp ? 'No ENIs matching this IP' : 'No ENIs in this subnet'}
                  </div>
                ) : (
                  enis.map((eni) => (
                    <ENICard key={eni.id} eni={eni} env={env} />
                  ))
                )}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Console Link */}
      <a href={consoleUrl} target="_blank" rel="noopener noreferrer"
         className="block w-full bg-blue-500/20 hover:bg-blue-500/30 text-blue-400 text-center py-2 rounded-lg text-sm font-medium transition-colors">
        <ExternalLink className="w-4 h-4 inline mr-2" />
        Open in AWS Console
      </a>
    </div>
  )
}

/**
 * Internet Gateway Details
 */
export function IGWDetails({ igw, env }) {
  if (!igw) {
    return <p className="text-red-400">Internet Gateway data not available</p>
  }

  return (
    <div className="space-y-4">
      <div className="bg-gray-900 rounded-lg p-4">
        <h3 className="text-sm font-medium text-gray-300 mb-3 flex items-center gap-2">
          <Globe className="w-4 h-4 text-green-400" />
          Internet Gateway Info
        </h3>
        <div className="space-y-2 text-sm">
          <div className="flex justify-between">
            <span className="text-gray-500">ID</span>
            <span className="text-gray-300 font-mono text-xs">{igw.id}</span>
          </div>
          {igw.name && (
            <div className="flex justify-between">
              <span className="text-gray-500">Name</span>
              <span className="text-gray-300">{igw.name}</span>
            </div>
          )}
          <div className="flex justify-between">
            <span className="text-gray-500">State</span>
            <span className={igw.state === 'attached' || igw.state === 'available' ? 'text-green-400' : 'text-yellow-400'}>
              {igw.state}
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-500">VPC ID</span>
            <span className="text-gray-300 font-mono text-xs">{igw.vpcId}</span>
          </div>
        </div>
      </div>

      {/* Console Link */}
      {igw.consoleUrl && (
        <a href={igw.consoleUrl} target="_blank" rel="noopener noreferrer"
           className="block w-full bg-green-500/20 hover:bg-green-500/30 text-green-400 text-center py-2 rounded-lg text-sm font-medium transition-colors">
          <ExternalLink className="w-4 h-4 inline mr-2" />
          Open in AWS Console
        </a>
      )}
    </div>
  )
}

/**
 * VPC Details - shows VPC info and all ENIs
 */
export function VPCDetails({ vpc, env }) {
  const [enis, setEnis] = useState([])
  const [eniLoading, setEniLoading] = useState(false)
  const [eniError, setEniError] = useState(null)
  const [eniExpanded, setEniExpanded] = useState(true) // Auto-expand for VPC
  const [searchIp, setSearchIp] = useState('')
  const [searchInput, setSearchInput] = useState('')

  // Fetch ENIs for the entire VPC
  const fetchEnis = useCallback(async (ipFilter = '') => {
    if (!env || !vpc?.id) return
    setEniLoading(true)
    setEniError(null)
    try {
      const params = new URLSearchParams()
      params.set('vpcId', vpc.id)
      if (ipFilter) params.set('searchIp', ipFilter)

      const response = await fetchWithRetry(`/api/infrastructure/${env}/enis?${params}`)
      if (!response.ok) throw new Error(`Failed to fetch ENIs: ${response.status}`)
      const data = await response.json()
      setEnis(data.enis || [])
    } catch (err) {
      console.error('Error fetching ENIs:', err)
      setEniError(err.message)
    } finally {
      setEniLoading(false)
    }
  }, [env, vpc?.id])

  // Load ENIs on mount
  useEffect(() => {
    if (vpc?.id && enis.length === 0 && !eniLoading) {
      fetchEnis()
    }
  }, [vpc?.id, enis.length, eniLoading, fetchEnis])

  // Handle search
  const handleSearch = () => {
    setSearchIp(searchInput)
    fetchEnis(searchInput)
  }

  if (!vpc) {
    return <p className="text-red-400">VPC data not available</p>
  }

  const consoleUrl = vpc.consoleUrl ||
    `https://eu-west-3.console.aws.amazon.com/vpcconsole/home?region=eu-west-3#VpcDetails:VpcId=${vpc.id}`

  return (
    <div className="space-y-4">
      {/* VPC Info */}
      <div className="bg-gray-900 rounded-lg p-4">
        <h3 className="text-sm font-medium text-gray-300 mb-3 flex items-center gap-2">
          <Network className="w-4 h-4 text-blue-400" />
          VPC Info
        </h3>
        <div className="space-y-2 text-sm">
          <InfoRow label="VPC ID" value={vpc.id} mono copy />
          <InfoRow label="Name" value={vpc.name} />
          <InfoRow label="CIDR Block" value={vpc.cidr} mono />
        </div>
      </div>

      {/* ENIs Section */}
      <div className="bg-gray-900 rounded-lg overflow-hidden">
        <button
          onClick={() => setEniExpanded(!eniExpanded)}
          className="w-full p-4 flex items-center justify-between hover:bg-gray-800 transition-colors"
        >
          <h3 className="text-sm font-medium text-gray-300 flex items-center gap-2">
            <Wifi className="w-4 h-4 text-cyan-400" />
            All Network Interfaces (ENIs)
            {enis.length > 0 && <span className="text-cyan-400 text-xs">({enis.length})</span>}
          </h3>
          {eniExpanded ? (
            <ChevronDown className="w-4 h-4 text-gray-400" />
          ) : (
            <ChevronRight className="w-4 h-4 text-gray-400" />
          )}
        </button>

        {eniExpanded && (
          <div className="px-4 pb-4 border-t border-gray-800">
            {/* Search Bar */}
            <div className="flex gap-2 mt-3 mb-3">
              <div className="flex-1 relative">
                <Search className="absolute left-2 top-1/2 transform -translate-y-1/2 w-4 h-4 text-gray-500" />
                <input
                  type="text"
                  value={searchInput}
                  onChange={(e) => setSearchInput(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                  placeholder="Search by IP..."
                  className="w-full pl-8 pr-3 py-1.5 bg-gray-800 border border-gray-700 rounded text-xs text-gray-300 placeholder-gray-500 focus:outline-none focus:border-cyan-500"
                />
              </div>
              <button
                onClick={handleSearch}
                className="px-3 py-1.5 bg-cyan-500/20 hover:bg-cyan-500/30 text-cyan-400 rounded text-xs transition-colors"
              >
                Search
              </button>
              <button
                onClick={() => fetchEnis(searchIp)}
                className="p-1.5 text-gray-400 hover:text-cyan-400 transition-colors"
                title="Refresh"
              >
                <RefreshCw className={`w-4 h-4 ${eniLoading ? 'animate-spin' : ''}`} />
              </button>
            </div>

            {/* Loading State */}
            {eniLoading && (
              <div className="flex items-center justify-center py-4 text-gray-400 text-xs">
                <RefreshCw className="w-4 h-4 animate-spin mr-2" />
                Loading ENIs...
              </div>
            )}

            {/* Error State */}
            {eniError && (
              <div className="text-red-400 text-xs py-2">{eniError}</div>
            )}

            {/* ENI List */}
            {!eniLoading && !eniError && (
              <div className="space-y-3 max-h-[500px] overflow-y-auto">
                {enis.length === 0 ? (
                  <div className="text-gray-500 text-xs text-center py-4">
                    {searchIp ? 'No ENIs matching this IP' : 'No ENIs in this VPC'}
                  </div>
                ) : (
                  enis.map((eni) => (
                    <ENICard key={eni.id} eni={eni} env={env} showSubnet={true} />
                  ))
                )}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Console Link */}
      <a href={consoleUrl} target="_blank" rel="noopener noreferrer"
         className="block w-full bg-blue-500/20 hover:bg-blue-500/30 text-blue-400 text-center py-2 rounded-lg text-sm font-medium transition-colors">
        <ExternalLink className="w-4 h-4 inline mr-2" />
        Open in AWS Console
      </a>
    </div>
  )
}

/**
 * VPC Endpoint Details
 */
export function EndpointDetails({ endpoint, env }) {
  if (!endpoint) {
    return <p className="text-red-400">VPC Endpoint data not available</p>
  }

  const isGateway = endpoint.type === 'Gateway'
  const borderColor = isGateway ? 'border-amber-500/50' : 'border-teal-500/50'
  const bgColor = isGateway ? 'bg-amber-500/20' : 'bg-teal-500/20'
  const textColor = isGateway ? 'text-amber-400' : 'text-teal-400'

  // Build console URL
  const region = 'eu-west-3'
  const consoleUrl = endpoint.consoleUrl ||
    `https://${region}.console.aws.amazon.com/vpcconsole/home?region=${region}#Endpoints:vpcEndpointId=${endpoint.id}`

  return (
    <div className="space-y-4">
      {/* Service Badge */}
      <div className={`rounded-lg p-3 border ${borderColor} ${bgColor}`}>
        <div className="flex items-center justify-between">
          <span className={`text-lg font-bold ${textColor}`}>
            {endpoint.friendlyServiceName || endpoint.serviceName?.split('.').pop() || 'VPC Endpoint'}
          </span>
          <span className={`px-2 py-1 rounded text-xs font-medium ${bgColor} ${textColor}`}>
            {endpoint.type || 'Interface'}
          </span>
        </div>
        <div className="text-gray-400 text-xs mt-1 truncate" title={endpoint.serviceName}>
          {endpoint.serviceName}
        </div>
      </div>

      {/* General Info */}
      <div className="bg-gray-900 rounded-lg p-4">
        <h3 className="text-sm font-medium text-gray-300 mb-3 flex items-center gap-2">
          <Network className="w-4 h-4 text-teal-400" />
          Endpoint Info
        </h3>
        <div className="space-y-2 text-sm">
          <InfoRow label="Endpoint ID" value={endpoint.id} mono copy />
          <InfoRow label="Name" value={endpoint.name} />
          <InfoRow label="VPC ID" value={endpoint.vpcId} mono copy />
          <InfoRow
            label="State"
            value={endpoint.state}
            color={endpoint.state === 'available' ? 'text-green-400' : 'text-yellow-400'}
          />
          {endpoint.privateDnsEnabled !== undefined && (
            <InfoRow
              label="Private DNS"
              value={endpoint.privateDnsEnabled ? 'Enabled' : 'Disabled'}
              color={endpoint.privateDnsEnabled ? 'text-green-400' : 'text-gray-400'}
            />
          )}
        </div>
      </div>

      {/* Subnets (Interface endpoints) */}
      {endpoint.subnetIds?.length > 0 && (
        <div className="bg-gray-900 rounded-lg p-4">
          <h3 className="text-sm font-medium text-gray-300 mb-3 flex items-center gap-2">
            <Network className="w-4 h-4 text-blue-400" />
            Subnets ({endpoint.subnetIds.length})
          </h3>
          <div className="space-y-1">
            {endpoint.subnetIds.map((subnetId, idx) => (
              <div key={idx} className="flex justify-between text-xs bg-gray-800 rounded px-2 py-1.5">
                <span className="text-gray-300 font-mono">{subnetId}</span>
                <CopyButton text={subnetId} />
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Route Tables (Gateway endpoints) */}
      {endpoint.routeTableIds?.length > 0 && (
        <div className="bg-gray-900 rounded-lg p-4">
          <h3 className="text-sm font-medium text-gray-300 mb-3 flex items-center gap-2">
            <Route className="w-4 h-4 text-cyan-400" />
            Route Tables ({endpoint.routeTableIds.length})
          </h3>
          <div className="space-y-1">
            {endpoint.routeTableIds.map((rtId, idx) => (
              <div key={idx} className="flex justify-between text-xs bg-gray-800 rounded px-2 py-1.5">
                <span className="text-gray-300 font-mono">{rtId}</span>
                <CopyButton text={rtId} />
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Security Groups (Interface endpoints) */}
      {endpoint.securityGroupIds?.length > 0 && (
        <div className="bg-gray-900 rounded-lg p-4">
          <h3 className="text-sm font-medium text-gray-300 mb-3 flex items-center gap-2">
            <Shield className="w-4 h-4 text-orange-400" />
            Security Groups ({endpoint.securityGroupIds.length})
          </h3>
          <div className="space-y-1">
            {endpoint.securityGroupIds.map((sgId, idx) => (
              <div key={idx} className="flex justify-between text-xs bg-gray-800 rounded px-2 py-1.5">
                <span className="text-gray-300 font-mono">{sgId}</span>
                <CopyButton text={sgId} />
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Console Link */}
      <a href={consoleUrl} target="_blank" rel="noopener noreferrer"
         className={`block w-full ${isGateway ? 'bg-amber-500/20 hover:bg-amber-500/30 text-amber-400' : 'bg-teal-500/20 hover:bg-teal-500/30 text-teal-400'} text-center py-2 rounded-lg text-sm font-medium transition-colors`}>
        <ExternalLink className="w-4 h-4 inline mr-2" />
        Open in AWS Console
      </a>
    </div>
  )
}

/**
 * VPC Peering Details
 */
export function PeeringDetails({ peering, env }) {
  if (!peering) {
    return <p className="text-red-400">VPC Peering data not available</p>
  }

  return (
    <div className="space-y-4">
      <div className="bg-gray-900 rounded-lg p-4">
        <h3 className="text-sm font-medium text-gray-300 mb-3 flex items-center gap-2">
          <Link2 className="w-4 h-4 text-purple-400" />
          VPC Peering Info
        </h3>
        <div className="space-y-2 text-sm">
          <div className="flex justify-between">
            <span className="text-gray-500">ID</span>
            <span className="text-gray-300 font-mono text-xs">{peering.id}</span>
          </div>
          {peering.name && (
            <div className="flex justify-between">
              <span className="text-gray-500">Name</span>
              <span className="text-gray-300">{peering.name}</span>
            </div>
          )}
          <div className="flex justify-between">
            <span className="text-gray-500">Status</span>
            <span className={peering.status === 'active' ? 'text-green-400' : 'text-yellow-400'}>
              {peering.status}
            </span>
          </div>
        </div>
      </div>

      {/* Requester VPC */}
      {peering.requesterVpc && (
        <div className="bg-gray-900 rounded-lg p-4">
          <h3 className="text-sm font-medium text-gray-300 mb-3">Requester VPC</h3>
          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-gray-500">VPC ID</span>
              <span className="text-gray-300 font-mono text-xs">{peering.requesterVpc.vpcId}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">CIDR</span>
              <span className="text-gray-300 font-mono">{peering.requesterVpc.cidrBlock}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Account</span>
              <span className="text-gray-300">{peering.requesterVpc.ownerId}</span>
            </div>
          </div>
        </div>
      )}

      {/* Accepter VPC */}
      {peering.accepterVpc && (
        <div className="bg-gray-900 rounded-lg p-4">
          <h3 className="text-sm font-medium text-gray-300 mb-3">Accepter VPC</h3>
          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-gray-500">VPC ID</span>
              <span className="text-gray-300 font-mono text-xs">{peering.accepterVpc.vpcId}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">CIDR</span>
              <span className="text-gray-300 font-mono">{peering.accepterVpc.cidrBlock}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Account</span>
              <span className="text-gray-300">{peering.accepterVpc.ownerId}</span>
            </div>
          </div>
        </div>
      )}

      {/* Console Link */}
      {peering.consoleUrl && (
        <a href={peering.consoleUrl} target="_blank" rel="noopener noreferrer"
           className="block w-full bg-purple-500/20 hover:bg-purple-500/30 text-purple-400 text-center py-2 rounded-lg text-sm font-medium transition-colors">
          <ExternalLink className="w-4 h-4 inline mr-2" />
          Open in AWS Console
        </a>
      )}
    </div>
  )
}

/**
 * VPN Connection Details
 */
export function VPNDetails({ vpn, env }) {
  if (!vpn) {
    return <p className="text-red-400">VPN Connection data not available</p>
  }

  return (
    <div className="space-y-4">
      <div className="bg-gray-900 rounded-lg p-4">
        <h3 className="text-sm font-medium text-gray-300 mb-3 flex items-center gap-2">
          <Shield className="w-4 h-4 text-orange-400" />
          VPN Connection Info
        </h3>
        <div className="space-y-2 text-sm">
          <div className="flex justify-between">
            <span className="text-gray-500">ID</span>
            <span className="text-gray-300 font-mono text-xs">{vpn.id}</span>
          </div>
          {vpn.name && (
            <div className="flex justify-between">
              <span className="text-gray-500">Name</span>
              <span className="text-gray-300">{vpn.name}</span>
            </div>
          )}
          <div className="flex justify-between">
            <span className="text-gray-500">State</span>
            <span className={vpn.state === 'available' ? 'text-green-400' : 'text-yellow-400'}>
              {vpn.state}
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-500">Type</span>
            <span className="text-gray-300">{vpn.type}</span>
          </div>
          {vpn.customerGatewayId && (
            <div className="flex justify-between">
              <span className="text-gray-500">Customer Gateway</span>
              <span className="text-gray-300 font-mono text-xs">{vpn.customerGatewayId}</span>
            </div>
          )}
          {vpn.vpnGatewayId && (
            <div className="flex justify-between">
              <span className="text-gray-500">VPN Gateway</span>
              <span className="text-gray-300 font-mono text-xs">{vpn.vpnGatewayId}</span>
            </div>
          )}
          {vpn.transitGatewayId && (
            <div className="flex justify-between">
              <span className="text-gray-500">Transit Gateway</span>
              <span className="text-gray-300 font-mono text-xs">{vpn.transitGatewayId}</span>
            </div>
          )}
        </div>
      </div>

      {/* Console Link */}
      {vpn.consoleUrl && (
        <a href={vpn.consoleUrl} target="_blank" rel="noopener noreferrer"
           className="block w-full bg-orange-500/20 hover:bg-orange-500/30 text-orange-400 text-center py-2 rounded-lg text-sm font-medium transition-colors">
          <ExternalLink className="w-4 h-4 inline mr-2" />
          Open in AWS Console
        </a>
      )}
    </div>
  )
}

/**
 * Transit Gateway Details
 */
export function TGWDetails({ tgw, env }) {
  if (!tgw) {
    return <p className="text-red-400">Transit Gateway data not available</p>
  }

  return (
    <div className="space-y-4">
      <div className="bg-gray-900 rounded-lg p-4">
        <h3 className="text-sm font-medium text-gray-300 mb-3 flex items-center gap-2">
          <Workflow className="w-4 h-4 text-yellow-400" />
          Transit Gateway Info
        </h3>
        <div className="space-y-2 text-sm">
          <div className="flex justify-between">
            <span className="text-gray-500">ID</span>
            <span className="text-gray-300 font-mono text-xs">{tgw.id}</span>
          </div>
          {tgw.name && (
            <div className="flex justify-between">
              <span className="text-gray-500">Name</span>
              <span className="text-gray-300">{tgw.name}</span>
            </div>
          )}
          <div className="flex justify-between">
            <span className="text-gray-500">State</span>
            <span className={tgw.state === 'available' ? 'text-green-400' : 'text-yellow-400'}>
              {tgw.state}
            </span>
          </div>
          {tgw.ownerId && (
            <div className="flex justify-between">
              <span className="text-gray-500">Owner</span>
              <span className="text-gray-300">{tgw.ownerId}</span>
            </div>
          )}
        </div>
      </div>

      {/* Attachments */}
      {tgw.attachments?.length > 0 && (
        <div className="bg-gray-900 rounded-lg p-4">
          <h3 className="text-sm font-medium text-gray-300 mb-3">Attachments</h3>
          <div className="space-y-2">
            {tgw.attachments.map((att, idx) => (
              <div key={idx} className="bg-gray-800 rounded p-2 text-xs">
                <div className="flex justify-between">
                  <span className="text-gray-400">{att.resourceType}</span>
                  <span className={att.state === 'available' ? 'text-green-400' : 'text-yellow-400'}>
                    {att.state}
                  </span>
                </div>
                <div className="text-gray-300 font-mono mt-1">{att.resourceId}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Console Link */}
      {tgw.consoleUrl && (
        <a href={tgw.consoleUrl} target="_blank" rel="noopener noreferrer"
           className="block w-full bg-yellow-500/20 hover:bg-yellow-500/30 text-yellow-400 text-center py-2 rounded-lg text-sm font-medium transition-colors">
          <ExternalLink className="w-4 h-4 inline mr-2" />
          Open in AWS Console
        </a>
      )}
    </div>
  )
}
