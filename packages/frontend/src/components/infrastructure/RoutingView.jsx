import { useState, useEffect, useCallback, useMemo } from 'react'
import { RefreshCw, AlertCircle } from 'lucide-react'
import { fetchWithRetry } from '../../utils'
import { formatServicePrefix } from '../../utils/serviceNaming'
import AwsNAT from 'aws-react-icons/lib/icons/ResourceAmazonVPCNATGateway'
import AwsIGW from 'aws-react-icons/lib/icons/ResourceAmazonVPCInternetGateway'
import AwsVPN from 'aws-react-icons/lib/icons/ArchitectureServiceAWSSiteToSiteVPN'
import AwsTGW from 'aws-react-icons/lib/icons/ArchitectureServiceAWSTransitGateway'
import AwsVPCPeering from 'aws-react-icons/lib/icons/ResourceAmazonVPCPeeringConnection'
import AwsRouter from 'aws-react-icons/lib/icons/ResourceAmazonVPCRouter'
import AwsEndpoint from 'aws-react-icons/lib/icons/ResourceAmazonVPCEndpoints'

/**
 * Routing-focused network diagram
 * Shows VPC, Subnets, Route Tables, NAT, VPN, TGW, Peering
 * With hover highlighting for subnet-RT relationships
 */
export default function RoutingView({
  env,
  data,
  onComponentSelect,
  selectedComponent,
  getDefaultAzs,
  appConfig
}) {
  const [routingData, setRoutingData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [hoveredSubnet, setHoveredSubnet] = useState(null)
  const [hoveredRouteTable, setHoveredRouteTable] = useState(null)

  // Layout constants (defined early for useMemo hooks) - enlarged for better visibility
  const azWidth = 420
  const azGap = 18
  const leftPanelWidth = 270

  // Fetch routing data
  const currentProjectId = appConfig?.currentProjectId
  const fetchRoutingData = useCallback(async () => {
    if (!env || !currentProjectId) return
    setLoading(true)
    setError(null)
    try {
      const response = await fetchWithRetry(`/api/${currentProjectId}/infrastructure/${env}/routing`)
      if (!response.ok) {
        throw new Error(`Failed to fetch routing data: ${response.status}`)
      }
      const result = await response.json()
      setRoutingData(result)
    } catch (err) {
      console.error('Error fetching routing data:', err)
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [env, currentProjectId])

  // Load routing data on mount
  useEffect(() => {
    fetchRoutingData()
  }, [fetchRoutingData])

  const { network } = data || {}

  // Get route tables and their associations
  const routeTables = useMemo(() => {
    return routingData?.routing?.routeTables || []
  }, [routingData])

  // Build subnet-to-routeTable mapping
  const subnetRouteTableMap = useMemo(() => {
    const map = {}
    routeTables.forEach(rt => {
      (rt.subnetAssociations || []).forEach(subnetId => {
        map[subnetId] = rt.id
      })
    })
    return map
  }, [routeTables])

  // Build routeTable-to-subnets mapping (inverse)
  const routeTableSubnetsMap = useMemo(() => {
    const map = {}
    routeTables.forEach(rt => {
      map[rt.id] = rt.subnetAssociations || []
    })
    return map
  }, [routeTables])

  // Internet Gateway
  const igw = routingData?.routing?.internetGateway

  // NAT Gateways/Instances
  const natGateways = routingData?.routing?.natGateways || []
  const hasNat = natGateways.length > 0 || network?.egressIps?.length > 0

  // VPC Endpoints
  const vpcEndpoints = routingData?.routing?.vpcEndpoints || []

  // VPC Connectivity
  const vpcPeerings = routingData?.connectivity?.vpcPeerings || []
  const vpnConnections = routingData?.connectivity?.vpnConnections || []
  const tgwAttachments = routingData?.connectivity?.transitGatewayAttachments || []

  // Helper to derive descriptive name for route table based on its routes and subnet associations
  const getRouteTableDisplayName = (rt) => {
    // Check default route target to determine type
    const defaultRoute = rt.routes?.find(r => r.destination === '0.0.0.0/0')
    const hasIgwRoute = defaultRoute?.targetType === 'internet-gateway'
    const hasNatRoute = defaultRoute?.targetType === 'nat-gateway' || defaultRoute?.targetType === 'instance'

    // Try to infer from subnet associations using subnetsByAz
    const associatedSubnetTypes = new Set()
    if (network?.subnetsByAz && rt.subnetAssociations?.length > 0) {
      for (const [az, azSubnets] of Object.entries(network.subnetsByAz)) {
        azSubnets?.forEach(s => {
          if (rt.subnetAssociations.includes(s.id)) {
            associatedSubnetTypes.add(s.type)
          }
        })
      }
    }

    // Determine display name based on characteristics
    if (rt.isMain) {
      return 'Main RT (VPC default)'
    }
    if (hasIgwRoute || associatedSubnetTypes.has('public')) {
      return 'Public RT'
    }
    if (hasNatRoute && associatedSubnetTypes.has('private')) {
      return 'Private RT'
    }
    if (associatedSubnetTypes.has('database')) {
      return 'Database RT'
    }
    if (hasNatRoute) {
      return 'Private RT'
    }
    // Fallback: show short ID
    return rt.id.replace('rtb-', '').substring(0, 12)
  }

  // Helper to check if component is selected
  const isSelected = (type, id) => {
    return selectedComponent?.type === type &&
           (selectedComponent?.data?.id === id || selectedComponent?.data?.routeTableId === id)
  }

  // Get the selected route table (if any)
  const selectedRouteTable = selectedComponent?.type === 'routeTable' ? selectedComponent.data : null

  // Build subnet position map for route visualization
  const subnetPositions = useMemo(() => {
    const positions = {}
    const azList = network?.availabilityZones || []

    azList.forEach((az, azIndex) => {
      const azSubnets = network?.subnetsByAz?.[az] || []
      const azX = leftPanelWidth + 30 + 10 + azIndex * (azWidth + azGap)

      // Calculate Y positions based on subnet stacking
      let currentY = 42 + 35 // VPC header + AZ header + first subnet offset
      const hasNatInAz = natGateways.find(nat => nat.az === az) || (azIndex === 0 && network?.egressIps?.[0])

      const publicSubnet = azSubnets.find(s => s.type === 'public')
      const privateSubnet = azSubnets.find(s => s.type === 'private')
      const dbSubnet = azSubnets.find(s => s.type === 'database')

      if (publicSubnet) {
        const height = hasNatInAz ? 150 : 110
        positions[publicSubnet.id] = {
          x: azX + (azWidth - 10) / 2,
          y: 10 + currentY + height / 2,
          type: 'public'
        }
        currentY += height + 10
      }

      if (privateSubnet) {
        positions[privateSubnet.id] = {
          x: azX + (azWidth - 10) / 2,
          y: 10 + currentY + 130 / 2,
          type: 'private'
        }
        currentY += 140
      }

      if (dbSubnet) {
        positions[dbSubnet.id] = {
          x: azX + (azWidth - 10) / 2,
          y: 10 + currentY + 110 / 2,
          type: 'database'
        }
      }
    })
    return positions
  }, [network, natGateways, leftPanelWidth, azWidth, azGap])

  // Target positions for route arrows
  const targetPositions = useMemo(() => {
    return {
      igw: igw ? { x: 10 + leftPanelWidth / 2, y: 10 + 40 + 37, label: 'IGW' } : null,
      nat: natGateways.length > 0 ? (() => {
        // Find first NAT position (in public subnet)
        const firstNat = natGateways[0]
        const azIndex = network?.availabilityZones?.indexOf(firstNat?.az) || 0
        const azX = leftPanelWidth + 30 + 10 + azIndex * (azWidth + azGap)
        return { x: azX + (azWidth - 10) / 2, y: 10 + 42 + 35 + 78 + 30, label: 'NAT' }
      })() : null
    }
  }, [igw, natGateways, network, leftPanelWidth, azWidth, azGap])

  // Check if subnet should be highlighted (hovered or related to hovered RT)
  const isSubnetHighlighted = (subnetId) => {
    if (hoveredSubnet === subnetId) return true
    if (hoveredRouteTable && routeTableSubnetsMap[hoveredRouteTable]?.includes(subnetId)) return true
    return false
  }

  // Check if route table should be highlighted (hovered or related to hovered subnet)
  const isRouteTableHighlighted = (rtId) => {
    if (hoveredRouteTable === rtId) return true
    if (hoveredSubnet && subnetRouteTableMap[hoveredSubnet] === rtId) return true
    return false
  }

  // Loading state
  if (loading && !routingData) {
    return (
      <div className="p-8 flex items-center justify-center">
        <RefreshCw className="w-8 h-8 text-cyan-500 animate-spin" />
        <span className="ml-3 text-gray-400">Loading routing data...</span>
      </div>
    )
  }

  // Error state
  if (error) {
    return (
      <div className="p-8 flex items-center justify-center text-red-400">
        <AlertCircle className="w-6 h-6 mr-2" />
        {error}
        <button onClick={fetchRoutingData} className="ml-4 text-cyan-400 hover:text-cyan-300">
          Retry
        </button>
      </div>
    )
  }

  const azs = network?.availabilityZones || getDefaultAzs()
  const totalWidth = leftPanelWidth + 20 + azs.length * azWidth + (azs.length - 1) * azGap + 35

  return (
    <div className="p-4 relative overflow-x-auto">
      <svg viewBox={`0 0 ${totalWidth} 720`} className="w-full h-auto" style={{ minHeight: '700px', minWidth: `${totalWidth}px` }}>
        {/* Defs */}
        <defs>
          <marker id="arrow-gray" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
            <polygon points="0 0, 10 3.5, 0 7" fill="#6b7280" />
          </marker>
          <marker id="arrow-cyan" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
            <polygon points="0 0, 10 3.5, 0 7" fill="#06b6d4" />
          </marker>
          <marker id="arrow-green" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
            <polygon points="0 0, 10 3.5, 0 7" fill="#22c55e" />
          </marker>
          <marker id="arrow-yellow" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
            <polygon points="0 0, 10 3.5, 0 7" fill="#eab308" />
          </marker>
          <marker id="arrow-purple" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
            <polygon points="0 0, 10 3.5, 0 7" fill="#a855f7" />
          </marker>
          <marker id="arrow-orange" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
            <polygon points="0 0, 10 3.5, 0 7" fill="#f97316" />
          </marker>
          <marker id="arrow-teal" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
            <polygon points="0 0, 10 3.5, 0 7" fill="#14b8a6" />
          </marker>
          {/* Highlight glow filter */}
          <filter id="glow-cyan" x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur stdDeviation="3" result="coloredBlur"/>
            <feMerge>
              <feMergeNode in="coloredBlur"/>
              <feMergeNode in="SourceGraphic"/>
            </feMerge>
          </filter>
        </defs>

        {/* Left Panel: Internet + Route Tables + Network Egress - enlarged for better visibility */}
        <g transform="translate(10, 10)">
          {/* Internet & IGW Section */}
          <rect x="0" y="0" width={leftPanelWidth} height="145" rx="8" fill="#1e293b" stroke="#475569" strokeWidth="1" strokeDasharray="4" />
          <text x={leftPanelWidth/2} y="26" fill="#94a3b8" fontSize="15" textAnchor="middle" fontWeight="bold">Internet</text>

          {/* Internet Gateway */}
          {igw && (
            <g
              transform="translate(25, 44)"
              className="cursor-pointer"
              onClick={() => onComponentSelect?.('igw', env, igw)}
            >
              <rect
                x="0" y="0" width={leftPanelWidth - 50} height="85" rx="6"
                fill={isSelected('igw', igw.id) ? '#1e3a5f' : '#1f2937'}
                stroke="#22c55e"
                strokeWidth={isSelected('igw', igw.id) ? 3 : 2}
              />
              <rect x="0" y="0" width={leftPanelWidth - 50} height="26" rx="6" fill="#22c55e" />
              <text x={(leftPanelWidth - 50)/2} y="18" fill="white" fontSize="13" textAnchor="middle" fontWeight="bold">Internet Gateway</text>
              <foreignObject x={(leftPanelWidth - 50)/2 - 20} y="30" width="40" height="40">
                <AwsIGW style={{ width: 40, height: 40 }} />
              </foreignObject>
              <text x={(leftPanelWidth - 50)/2} y="78" fill="#4ade80" fontSize="11" textAnchor="middle">{igw.state || 'attached'}</text>
            </g>
          )}

          {/* Route Tables Section */}
          <rect x="0" y="160" width={leftPanelWidth} height={Math.max(200, Math.ceil(routeTables.length / 1) * 68 + 45)} rx="8" fill="#0f172a" stroke="#06b6d4" strokeWidth="1" strokeOpacity="0.5" />
          <text x="15" y="185" fill="#06b6d4" fontSize="14" fontWeight="bold">Route Tables ({routeTables.length})</text>

          {/* Route Table Cards */}
          <g transform="translate(10, 198)">
            {routeTables.map((rt, idx) => {
              const rtWidth = leftPanelWidth - 20
              const rtY = idx * 64
              const highlighted = isRouteTableHighlighted(rt.id)

              return (
                <g
                  key={rt.id}
                  transform={`translate(0, ${rtY})`}
                  className="cursor-pointer"
                  onClick={() => onComponentSelect?.('routeTable', env, rt)}
                  onMouseEnter={() => setHoveredRouteTable(rt.id)}
                  onMouseLeave={() => setHoveredRouteTable(null)}
                  filter={highlighted ? 'url(#glow-cyan)' : undefined}
                >
                  <rect
                    x="0" y="0" width={rtWidth} height="58" rx="6"
                    fill={isSelected('routeTable', rt.id) ? '#164e63' : highlighted ? '#0e4d5c' : '#1e293b'}
                    stroke="#06b6d4"
                    strokeWidth={isSelected('routeTable', rt.id) || highlighted ? 3 : 1}
                  />
                  <foreignObject x="8" y="12" width="32" height="32">
                    <AwsRouter style={{ width: 32, height: 32 }} />
                  </foreignObject>
                  <text x="48" y="24" fill="#e2e8f0" fontSize="12" fontWeight="bold">
                    {getRouteTableDisplayName(rt)}
                  </text>
                  <text x="48" y="44" fill="#9ca3af" fontSize="11">
                    {(rt.subnetAssociations?.length || 0)} subnets • {(rt.routes?.length || 0)} routes
                  </text>
                </g>
              )
            })}
          </g>

          {/* VPC Endpoints Section - enlarged for better visibility */}
          {vpcEndpoints.length > 0 && (
            <g transform={`translate(0, ${170 + Math.max(200, Math.ceil(routeTables.length / 1) * 68 + 45) + 18})`}>
              <rect x="0" y="0" width={leftPanelWidth} height={Math.max(110, Math.ceil(vpcEndpoints.length / 1) * 58 + 45)} rx="8" fill="#0f172a" stroke="#14b8a6" strokeWidth="1" strokeOpacity="0.5" />
              <text x="15" y="26" fill="#14b8a6" fontSize="14" fontWeight="bold">VPC Endpoints ({vpcEndpoints.length})</text>

              {/* Endpoint Cards */}
              <g transform="translate(10, 38)">
                {vpcEndpoints.map((ep, idx) => {
                  const epWidth = leftPanelWidth - 20
                  const epY = idx * 54

                  // Color based on type
                  const isGateway = ep.type === 'Gateway'
                  const borderColor = isGateway ? '#f59e0b' : '#14b8a6'
                  const textColor = isGateway ? '#fcd34d' : '#5eead4'
                  const bgColor = isGateway ? 'rgba(245, 158, 11, 0.1)' : 'rgba(20, 184, 166, 0.1)'

                  return (
                    <g
                      key={ep.id}
                      transform={`translate(0, ${epY})`}
                      className="cursor-pointer"
                      onClick={() => onComponentSelect?.('endpoint', env, ep)}
                    >
                      <rect
                        x="0" y="0" width={epWidth} height="50" rx="5"
                        fill={isSelected('endpoint', ep.id) ? (isGateway ? '#422006' : '#134e4a') : '#1e293b'}
                        stroke={borderColor}
                        strokeWidth={isSelected('endpoint', ep.id) ? 2 : 1}
                      />
                      <foreignObject x="8" y="10" width="28" height="28">
                        <AwsEndpoint style={{ width: 28, height: 28 }} />
                      </foreignObject>
                      <text x="42" y="22" fill={textColor} fontSize="12" fontWeight="bold">
                        {ep.friendlyServiceName || ep.serviceName?.split('.').pop() || 'Endpoint'}
                      </text>
                      <rect x={epWidth - 62} y="8" width="54" height="16" rx="3" fill={bgColor} stroke={borderColor} strokeWidth="0.5" />
                      <text x={epWidth - 35} y="20" fill={textColor} fontSize="9" textAnchor="middle">
                        {ep.type || 'Interface'}
                      </text>
                      <text x="42" y="40" fill="#9ca3af" fontSize="10">
                        {ep.state === 'available' ? '● Available' : ep.state || 'pending'}
                      </text>
                    </g>
                  )
                })}
              </g>
            </g>
          )}

          {/* Network Egress Section (VPN, TGW, Peering) - enlarged for better visibility */}
          {(vpnConnections.length > 0 || tgwAttachments.length > 0 || vpcPeerings.length > 0) && (
            <g transform={`translate(0, ${170 + Math.max(200, Math.ceil(routeTables.length / 1) * 68 + 45) + 18 + (vpcEndpoints.length > 0 ? Math.max(110, Math.ceil(vpcEndpoints.length / 1) * 58 + 45) + 18 : 0)})`}>
              <rect x="0" y="0" width={leftPanelWidth} height="200" rx="8" fill="#1e293b" stroke="#475569" strokeWidth="1" strokeDasharray="4" />
              <text x={leftPanelWidth/2} y="26" fill="#94a3b8" fontSize="14" textAnchor="middle" fontWeight="bold">External Connectivity</text>

              {/* VPN Connections */}
              {vpnConnections.length > 0 && (
                <g transform="translate(20, 40)">
                  <rect x="0" y="0" width={leftPanelWidth - 40} height="48" rx="5" fill="#1f2937" stroke="#f97316" strokeWidth="1.5" />
                  <foreignObject x="10" y="10" width="30" height="30">
                    <AwsVPN style={{ width: 30, height: 30 }} />
                  </foreignObject>
                  <text x="48" y="22" fill="#fb923c" fontSize="12" fontWeight="bold">VPN</text>
                  <text x="48" y="38" fill="#9ca3af" fontSize="11">{vpnConnections.length} connection(s)</text>
                </g>
              )}

              {/* Transit Gateway */}
              {tgwAttachments.length > 0 && (
                <g transform={`translate(20, ${vpnConnections.length > 0 ? 96 : 40})`}>
                  <rect x="0" y="0" width={leftPanelWidth - 40} height="48" rx="5" fill="#1f2937" stroke="#8b5cf6" strokeWidth="1.5" />
                  <foreignObject x="10" y="10" width="30" height="30">
                    <AwsTGW style={{ width: 30, height: 30 }} />
                  </foreignObject>
                  <text x="48" y="22" fill="#a78bfa" fontSize="12" fontWeight="bold">Transit Gateway</text>
                  <text x="48" y="38" fill="#9ca3af" fontSize="11">{tgwAttachments.length} attachment(s)</text>
                </g>
              )}

              {/* VPC Peering */}
              {vpcPeerings.length > 0 && (
                <g transform={`translate(20, ${(vpnConnections.length > 0 ? 56 : 0) + (tgwAttachments.length > 0 ? 56 : 0) + 40})`}>
                  <rect x="0" y="0" width={leftPanelWidth - 40} height="48" rx="5" fill="#1f2937" stroke="#ec4899" strokeWidth="1.5" />
                  <foreignObject x="10" y="10" width="30" height="30">
                    <AwsVPCPeering style={{ width: 30, height: 30 }} />
                  </foreignObject>
                  <text x="48" y="22" fill="#f472b6" fontSize="12" fontWeight="bold">VPC Peering</text>
                  <text x="48" y="38" fill="#9ca3af" fontSize="11">{vpcPeerings.length} connection(s)</text>
                </g>
              )}
            </g>
          )}
        </g>

        {/* VPC Container - enlarged for better visibility */}
        <g transform={`translate(${leftPanelWidth + 35}, 10)`}>
          <rect x="0" y="0" width={azs.length * azWidth + (azs.length - 1) * azGap + 24} height="660" rx="10" fill="none" stroke="#3b82f6" strokeWidth="2" />
          {/* VPC Header - Clickable */}
          <g
            className="cursor-pointer"
            onClick={() => onComponentSelect?.('vpc', env, {
              id: network?.vpcId,
              name: network?.vpcName || (formatServicePrefix(appConfig?.serviceNaming, appConfig?.currentProjectId, env).replace(/-$/, '') || env || ''),
              cidr: network?.cidr,
              consoleUrl: network?.consoleUrl
            })}
          >
            <rect
              x="0" y="0"
              width={azs.length * azWidth + (azs.length - 1) * azGap + 24}
              height="36" rx="10"
              fill={isSelected('vpc', network?.vpcId) ? '#1e40af' : '#1e3a5f'}
              className="hover:fill-[#234876] transition-colors"
            />
            <text x="20" y="25" fill="#60a5fa" fontSize="16" fontWeight="bold">
              VPC: {network?.vpcName || (formatServicePrefix(appConfig?.serviceNaming, appConfig?.currentProjectId, env).replace(/-$/, '') || env || '')}
            </text>
            <text x={azs.length * azWidth + (azs.length - 1) * azGap + 4} y="25" fill="#93c5fd" fontSize="14" textAnchor="end">
              {network?.cidr || '10.x.0.0/16'}
            </text>
          </g>

          {/* AZ Columns with Subnets - enlarged for better visibility */}
          {azs.map((az, azIndex) => {
            const azX = 12 + azIndex * (azWidth + azGap)
            const azSubnets = network?.subnetsByAz?.[az] || []

            // Find NAT in this AZ
            const natInAz = natGateways.find(nat => nat.az === az) ||
                           (azIndex === 0 && network?.egressIps?.[0] ? { ip: network.egressIps[0] } : null)

            return (
              <g key={az} transform={`translate(${azX}, 46)`}>
                {/* AZ Container */}
                <rect x="0" y="0" width={azWidth} height="605" rx="8" fill="#0f172a" stroke="#334155" strokeWidth="1" />
                <rect x="0" y="0" width={azWidth} height="32" rx="8" fill="#1e293b" />
                <text x={azWidth/2} y="22" fill="#94a3b8" fontSize="14" textAnchor="middle" fontWeight="bold">{az}</text>

                {/* Public Subnet */}
                {(() => {
                  const subnet = azSubnets.find(s => s.type === 'public')
                  if (!subnet) return null
                  const highlighted = isSubnetHighlighted(subnet.id)
                  const rtId = subnetRouteTableMap[subnet.id]

                  return (
                    <g
                      transform="translate(5, 40)"
                      className="cursor-pointer"
                      onClick={() => onComponentSelect?.('subnet', env, { ...subnet, subnetType: 'public', az, routeTableId: rtId, vpcId: network?.vpcId })}
                      onMouseEnter={() => setHoveredSubnet(subnet.id)}
                      onMouseLeave={() => setHoveredSubnet(null)}
                    >
                      <rect
                        x="0" y="0" width={azWidth - 10} height={natInAz ? 165 : 120} rx="6"
                        fill={isSelected('subnet', subnet.id) ? '#052e16' : highlighted ? '#073d1f' : '#0a2615'}
                        stroke="#22c55e"
                        strokeWidth={isSelected('subnet', subnet.id) || highlighted ? 3 : 1}
                        strokeOpacity="0.8"
                        filter={highlighted ? 'url(#glow-cyan)' : undefined}
                      />
                      <text x="12" y="26" fill="#4ade80" fontSize="14" fontWeight="bold">Public Subnet</text>
                      <text x={azWidth - 22} y="26" fill="#4ade80" fontSize="12" textAnchor="end">{subnet.cidr}</text>
                      <text x="12" y="48" fill="#6b7280" fontSize="11">{subnet.id}</text>

                      {/* NAT Gateway inside Public Subnet */}
                      {natInAz && (
                        <g transform="translate(12, 88)">
                          <rect x="0" y="0" width={azWidth - 34} height="68" rx="5" fill="#1f2937" stroke="#eab308" strokeWidth="1.5" />
                          <foreignObject x="12" y="12" width="40" height="40">
                            <AwsNAT style={{ width: 40, height: 40 }} />
                          </foreignObject>
                          <text x="62" y="26" fill="#fef08a" fontSize="12" fontWeight="bold">NAT Gateway</text>
                          <text x="62" y="46" fill="#fcd34d" fontSize="11">{natInAz.ip || natInAz.publicIp || 'Elastic IP'}</text>
                          {natInAz.state && (
                            <text x={azWidth - 56} y="40" fill={natInAz.state === 'available' ? '#4ade80' : '#fbbf24'} fontSize="11" textAnchor="end">
                              {natInAz.state}
                            </text>
                          )}
                        </g>
                      )}
                    </g>
                  )
                })()}

                {/* Private Subnet */}
                {(() => {
                  const subnet = azSubnets.find(s => s.type === 'private')
                  if (!subnet) return null
                  const highlighted = isSubnetHighlighted(subnet.id)
                  const rtId = subnetRouteTableMap[subnet.id]
                  const publicSubnet = azSubnets.find(s => s.type === 'public')
                  const yOffset = publicSubnet ? (natGateways.find(nat => nat.az === az) || (azIndex === 0 && network?.egressIps?.[0]) ? 215 : 170) : 40

                  return (
                    <g
                      transform={`translate(5, ${yOffset})`}
                      className="cursor-pointer"
                      onClick={() => onComponentSelect?.('subnet', env, { ...subnet, subnetType: 'private', az, routeTableId: rtId, vpcId: network?.vpcId })}
                      onMouseEnter={() => setHoveredSubnet(subnet.id)}
                      onMouseLeave={() => setHoveredSubnet(null)}
                    >
                      <rect
                        x="0" y="0" width={azWidth - 10} height="145" rx="6"
                        fill={isSelected('subnet', subnet.id) ? '#172554' : highlighted ? '#1e3a5f' : '#0c1a3d'}
                        stroke="#3b82f6"
                        strokeWidth={isSelected('subnet', subnet.id) || highlighted ? 3 : 1}
                        strokeOpacity="0.8"
                        filter={highlighted ? 'url(#glow-cyan)' : undefined}
                      />
                      <text x="12" y="26" fill="#60a5fa" fontSize="14" fontWeight="bold">Private Subnet</text>
                      <text x={azWidth - 22} y="26" fill="#60a5fa" fontSize="12" textAnchor="end">{subnet.cidr}</text>
                      <text x="12" y="48" fill="#6b7280" fontSize="11">{subnet.id}</text>
                      <text x="12" y="72" fill="#9ca3af" fontSize="11">ECS Tasks, Lambda, Internal services</text>
                    </g>
                  )
                })()}

                {/* Database Subnet */}
                {(() => {
                  const subnet = azSubnets.find(s => s.type === 'database')
                  if (!subnet) return null
                  const highlighted = isSubnetHighlighted(subnet.id)
                  const rtId = subnetRouteTableMap[subnet.id]
                  const publicSubnet = azSubnets.find(s => s.type === 'public')
                  const privateSubnet = azSubnets.find(s => s.type === 'private')
                  const hasNatInAz = natGateways.find(nat => nat.az === az) || (azIndex === 0 && network?.egressIps?.[0])
                  let yOffset = 40
                  if (publicSubnet) yOffset += hasNatInAz ? 175 : 130
                  if (privateSubnet) yOffset += 155

                  return (
                    <g
                      transform={`translate(5, ${yOffset})`}
                      className="cursor-pointer"
                      onClick={() => onComponentSelect?.('subnet', env, { ...subnet, subnetType: 'database', az, routeTableId: rtId, vpcId: network?.vpcId })}
                      onMouseEnter={() => setHoveredSubnet(subnet.id)}
                      onMouseLeave={() => setHoveredSubnet(null)}
                    >
                      <rect
                        x="0" y="0" width={azWidth - 10} height="125" rx="6"
                        fill={isSelected('subnet', subnet.id) ? '#3b0764' : highlighted ? '#4c0d7a' : '#1a0533'}
                        stroke="#a855f7"
                        strokeWidth={isSelected('subnet', subnet.id) || highlighted ? 3 : 1}
                        strokeOpacity="0.8"
                        filter={highlighted ? 'url(#glow-cyan)' : undefined}
                      />
                      <text x="12" y="26" fill="#c084fc" fontSize="14" fontWeight="bold">Database Subnet</text>
                      <text x={azWidth - 22} y="26" fill="#c084fc" fontSize="12" textAnchor="end">{subnet.cidr}</text>
                      <text x="12" y="48" fill="#6b7280" fontSize="11">{subnet.id}</text>
                      <text x="12" y="72" fill="#9ca3af" fontSize="11">RDS, ElastiCache, isolated resources</text>
                    </g>
                  )
                })()}

                {/* Connection line from IGW to Public Subnet */}
                {azIndex === 0 && igw && (
                  <path
                    d={`M -${azX - 10} 70 L 5 70`}
                    fill="none"
                    stroke="#22c55e"
                    strokeWidth="2"
                    strokeDasharray="6 3"
                    markerEnd="url(#arrow-green)"
                  />
                )}
              </g>
            )
          })}
        </g>

        {/* Route Visualization Arrows - shown when a Route Table is selected */}
        {selectedRouteTable && selectedRouteTable.routes && (
          <g className="route-arrows">
            {selectedRouteTable.routes
              .filter(route => route.targetType !== 'local') // Skip local routes
              .map((route, idx) => {
                const destination = route.destination || route.destinationCidrBlock
                const targetType = route.targetType
                const targetId = route.targetId

                // Determine arrow color based on target type
                const arrowConfig = {
                  'internet-gateway': { color: '#22c55e', marker: 'arrow-green' },
                  'nat-gateway': { color: '#eab308', marker: 'arrow-yellow' },
                  'transit-gateway': { color: '#a855f7', marker: 'arrow-purple' },
                  'vpc-peering': { color: '#ec4899', marker: 'arrow-purple' },
                  'instance': { color: '#f97316', marker: 'arrow-orange' }, // NAT instance
                  'network-interface': { color: '#14b8a6', marker: 'arrow-teal' },
                  'gateway': { color: '#14b8a6', marker: 'arrow-teal' }, // VPC Endpoint Gateway
                }
                const config = arrowConfig[targetType] || { color: '#6b7280', marker: 'arrow-gray' }

                // Determine target position
                let targetPos = null
                if (targetType === 'internet-gateway') {
                  targetPos = targetPositions.igw
                } else if (targetType === 'nat-gateway' || targetType === 'instance') {
                  targetPos = targetPositions.nat
                }

                // If no target position determined, skip
                if (!targetPos) return null

                // Get associated subnets for this route table
                const associatedSubnets = selectedRouteTable.subnetAssociations || []

                return associatedSubnets.map((subnetId, subIdx) => {
                  const subnetPos = subnetPositions[subnetId]
                  if (!subnetPos) return null

                  // Calculate curved path from subnet to target
                  const startX = subnetPos.x
                  const startY = subnetPos.y
                  const endX = targetPos.x
                  const endY = targetPos.y

                  // Create a curved path
                  const midX = (startX + endX) / 2
                  const midY = Math.min(startY, endY) - 40 // Curve upward

                  // Offset for multiple arrows from same subnet
                  const offsetY = idx * 5

                  return (
                    <g key={`${route.destination}-${subnetId}-${subIdx}`}>
                      <path
                        d={`M ${startX} ${startY + offsetY} Q ${midX} ${midY + offsetY} ${endX} ${endY}`}
                        fill="none"
                        stroke={config.color}
                        strokeWidth="2"
                        strokeDasharray="8 4"
                        markerEnd={`url(#${config.marker})`}
                        opacity="0.8"
                      />
                      {/* CIDR label on the path */}
                      <text
                        x={midX}
                        y={midY + offsetY - 8}
                        fill={config.color}
                        fontSize="10"
                        textAnchor="middle"
                        fontWeight="bold"
                        className="pointer-events-none"
                      >
                        {destination}
                      </text>
                    </g>
                  )
                })
              })}
          </g>
        )}
      </svg>

      {/* Legend and Refresh - enlarged for better visibility */}
      <div className="flex items-center justify-between mt-4 px-3">
        <div className="flex items-center gap-5 flex-wrap">
          <div className="flex items-center gap-2">
            <div className="w-5 h-5 rounded border-2 border-green-500 bg-green-900/30"></div>
            <span className="text-gray-400 text-sm">Public Subnet</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-5 h-5 rounded border-2 border-blue-500 bg-blue-900/30"></div>
            <span className="text-gray-400 text-sm">Private Subnet</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-5 h-5 rounded border-2 border-purple-500 bg-purple-900/30"></div>
            <span className="text-gray-400 text-sm">Database Subnet</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-5 h-5 rounded border-2 border-cyan-500 bg-cyan-900/30"></div>
            <span className="text-gray-400 text-sm">Route Table</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-5 h-5 rounded border-2 border-yellow-500 bg-yellow-900/30"></div>
            <span className="text-gray-400 text-sm">NAT Gateway</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-5 h-5 rounded border-2 border-teal-500 bg-teal-900/30"></div>
            <span className="text-gray-400 text-sm">VPC Endpoint</span>
          </div>
          <div className="text-gray-500 text-sm ml-4 border-l border-gray-700 pl-4">
            Hover subnets or route tables to see associations
          </div>
        </div>
        <button
          onClick={fetchRoutingData}
          disabled={loading}
          className="flex items-center gap-2 px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg text-sm text-gray-300 transition-colors"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>
    </div>
  )
}
