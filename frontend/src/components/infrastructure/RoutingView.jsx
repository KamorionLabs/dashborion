import { useState, useEffect, useCallback, useMemo } from 'react'
import { RefreshCw, AlertCircle } from 'lucide-react'
import { fetchWithRetry } from '../../utils'
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

  // Layout constants (defined early for useMemo hooks)
  const azWidth = 380
  const azGap = 15
  const leftPanelWidth = 240

  // Fetch routing data
  const fetchRoutingData = useCallback(async () => {
    if (!env) return
    setLoading(true)
    setError(null)
    try {
      const response = await fetchWithRetry(`/api/infrastructure/${env}/routing`)
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
  }, [env])

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
  const totalWidth = leftPanelWidth + 20 + azs.length * azWidth + (azs.length - 1) * azGap + 30

  return (
    <div className="p-4 relative overflow-x-auto">
      <svg viewBox={`0 0 ${totalWidth} 680`} className="w-full h-auto" style={{ minHeight: '650px', minWidth: `${totalWidth}px` }}>
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

        {/* Left Panel: Internet + Route Tables + Network Egress */}
        <g transform="translate(10, 10)">
          {/* Internet & IGW Section */}
          <rect x="0" y="0" width={leftPanelWidth} height="130" rx="8" fill="#1e293b" stroke="#475569" strokeWidth="1" strokeDasharray="4" />
          <text x={leftPanelWidth/2} y="24" fill="#94a3b8" fontSize="14" textAnchor="middle" fontWeight="bold">Internet</text>

          {/* Internet Gateway */}
          {igw && (
            <g
              transform="translate(25, 40)"
              className="cursor-pointer"
              onClick={() => onComponentSelect?.('igw', env, igw)}
            >
              <rect
                x="0" y="0" width={leftPanelWidth - 50} height="75" rx="6"
                fill={isSelected('igw', igw.id) ? '#1e3a5f' : '#1f2937'}
                stroke="#22c55e"
                strokeWidth={isSelected('igw', igw.id) ? 3 : 2}
              />
              <rect x="0" y="0" width={leftPanelWidth - 50} height="22" rx="6" fill="#22c55e" />
              <text x={(leftPanelWidth - 50)/2} y="15" fill="white" fontSize="11" textAnchor="middle" fontWeight="bold">Internet Gateway</text>
              <foreignObject x={(leftPanelWidth - 50)/2 - 18} y="26" width="36" height="36">
                <AwsIGW style={{ width: 36, height: 36 }} />
              </foreignObject>
              <text x={(leftPanelWidth - 50)/2} y="68" fill="#4ade80" fontSize="10" textAnchor="middle">{igw.state || 'attached'}</text>
            </g>
          )}

          {/* Route Tables Section */}
          <rect x="0" y="145" width={leftPanelWidth} height={Math.max(180, Math.ceil(routeTables.length / 1) * 62 + 40)} rx="8" fill="#0f172a" stroke="#06b6d4" strokeWidth="1" strokeOpacity="0.5" />
          <text x="15" y="168" fill="#06b6d4" fontSize="13" fontWeight="bold">Route Tables ({routeTables.length})</text>

          {/* Route Table Cards */}
          <g transform="translate(10, 180)">
            {routeTables.map((rt, idx) => {
              const rtWidth = leftPanelWidth - 20
              const rtY = idx * 58
              const isMain = rt.isMain
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
                    x="0" y="0" width={rtWidth} height="52" rx="6"
                    fill={isSelected('routeTable', rt.id) ? '#164e63' : highlighted ? '#0e4d5c' : '#1e293b'}
                    stroke="#06b6d4"
                    strokeWidth={isSelected('routeTable', rt.id) || highlighted ? 3 : 1}
                  />
                  <foreignObject x="6" y="10" width="28" height="28">
                    <AwsRouter style={{ width: 28, height: 28 }} />
                  </foreignObject>
                  <text x="40" y="20" fill="#e2e8f0" fontSize="11" fontWeight="bold">
                    {rt.name?.substring(0, 18) || rt.id.substring(4, 18)}
                  </text>
                  {isMain && (
                    <rect x={rtWidth - 40} y="6" width="35" height="16" rx="3" fill="#06b6d4" />
                  )}
                  {isMain && <text x={rtWidth - 22} y="17" fill="white" fontSize="9" textAnchor="middle">Main</text>}
                  <text x="40" y="38" fill="#9ca3af" fontSize="10">
                    {(rt.subnetAssociations?.length || 0)} subnets • {(rt.routes?.length || 0)} routes
                  </text>
                </g>
              )
            })}
          </g>

          {/* VPC Endpoints Section */}
          {vpcEndpoints.length > 0 && (
            <g transform={`translate(0, ${155 + Math.max(180, Math.ceil(routeTables.length / 1) * 62 + 40) + 15})`}>
              <rect x="0" y="0" width={leftPanelWidth} height={Math.max(100, Math.ceil(vpcEndpoints.length / 1) * 52 + 40)} rx="8" fill="#0f172a" stroke="#14b8a6" strokeWidth="1" strokeOpacity="0.5" />
              <text x="15" y="22" fill="#14b8a6" fontSize="13" fontWeight="bold">VPC Endpoints ({vpcEndpoints.length})</text>

              {/* Endpoint Cards */}
              <g transform="translate(10, 32)">
                {vpcEndpoints.map((ep, idx) => {
                  const epWidth = leftPanelWidth - 20
                  const epY = idx * 48

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
                        x="0" y="0" width={epWidth} height="44" rx="5"
                        fill={isSelected('endpoint', ep.id) ? (isGateway ? '#422006' : '#134e4a') : '#1e293b'}
                        stroke={borderColor}
                        strokeWidth={isSelected('endpoint', ep.id) ? 2 : 1}
                      />
                      <foreignObject x="6" y="8" width="24" height="24">
                        <AwsEndpoint style={{ width: 24, height: 24 }} />
                      </foreignObject>
                      <text x="36" y="18" fill={textColor} fontSize="11" fontWeight="bold">
                        {ep.friendlyServiceName || ep.serviceName?.split('.').pop() || 'Endpoint'}
                      </text>
                      <rect x={epWidth - 58} y="6" width="50" height="14" rx="3" fill={bgColor} stroke={borderColor} strokeWidth="0.5" />
                      <text x={epWidth - 33} y="16" fill={textColor} fontSize="8" textAnchor="middle">
                        {ep.type || 'Interface'}
                      </text>
                      <text x="36" y="34" fill="#9ca3af" fontSize="9">
                        {ep.state === 'available' ? '● Available' : ep.state || 'pending'}
                      </text>
                    </g>
                  )
                })}
              </g>
            </g>
          )}

          {/* Network Egress Section (VPN, TGW, Peering) */}
          {(vpnConnections.length > 0 || tgwAttachments.length > 0 || vpcPeerings.length > 0) && (
            <g transform={`translate(0, ${155 + Math.max(180, Math.ceil(routeTables.length / 1) * 62 + 40) + 15 + (vpcEndpoints.length > 0 ? Math.max(100, Math.ceil(vpcEndpoints.length / 1) * 52 + 40) + 15 : 0)})`}>
              <rect x="0" y="0" width={leftPanelWidth} height="180" rx="8" fill="#1e293b" stroke="#475569" strokeWidth="1" strokeDasharray="4" />
              <text x={leftPanelWidth/2} y="22" fill="#94a3b8" fontSize="13" textAnchor="middle" fontWeight="bold">External Connectivity</text>

              {/* VPN Connections */}
              {vpnConnections.length > 0 && (
                <g transform="translate(20, 35)">
                  <rect x="0" y="0" width={leftPanelWidth - 40} height="42" rx="5" fill="#1f2937" stroke="#f97316" strokeWidth="1.5" />
                  <foreignObject x="8" y="8" width="26" height="26">
                    <AwsVPN style={{ width: 26, height: 26 }} />
                  </foreignObject>
                  <text x="42" y="18" fill="#fb923c" fontSize="11" fontWeight="bold">VPN</text>
                  <text x="42" y="32" fill="#9ca3af" fontSize="10">{vpnConnections.length} connection(s)</text>
                </g>
              )}

              {/* Transit Gateway */}
              {tgwAttachments.length > 0 && (
                <g transform={`translate(20, ${vpnConnections.length > 0 ? 85 : 35})`}>
                  <rect x="0" y="0" width={leftPanelWidth - 40} height="42" rx="5" fill="#1f2937" stroke="#8b5cf6" strokeWidth="1.5" />
                  <foreignObject x="8" y="8" width="26" height="26">
                    <AwsTGW style={{ width: 26, height: 26 }} />
                  </foreignObject>
                  <text x="42" y="18" fill="#a78bfa" fontSize="11" fontWeight="bold">Transit Gateway</text>
                  <text x="42" y="32" fill="#9ca3af" fontSize="10">{tgwAttachments.length} attachment(s)</text>
                </g>
              )}

              {/* VPC Peering */}
              {vpcPeerings.length > 0 && (
                <g transform={`translate(20, ${(vpnConnections.length > 0 ? 50 : 0) + (tgwAttachments.length > 0 ? 50 : 0) + 35})`}>
                  <rect x="0" y="0" width={leftPanelWidth - 40} height="42" rx="5" fill="#1f2937" stroke="#ec4899" strokeWidth="1.5" />
                  <foreignObject x="8" y="8" width="26" height="26">
                    <AwsVPCPeering style={{ width: 26, height: 26 }} />
                  </foreignObject>
                  <text x="42" y="18" fill="#f472b6" fontSize="11" fontWeight="bold">VPC Peering</text>
                  <text x="42" y="32" fill="#9ca3af" fontSize="10">{vpcPeerings.length} connection(s)</text>
                </g>
              )}
            </g>
          )}
        </g>

        {/* VPC Container */}
        <g transform={`translate(${leftPanelWidth + 30}, 10)`}>
          <rect x="0" y="0" width={azs.length * azWidth + (azs.length - 1) * azGap + 20} height="610" rx="10" fill="none" stroke="#3b82f6" strokeWidth="2" />
          {/* VPC Header - Clickable */}
          <g
            className="cursor-pointer"
            onClick={() => onComponentSelect?.('vpc', env, {
              id: network?.vpcId,
              name: network?.vpcName || (appConfig?.serviceNaming?.prefix || 'app') + '-' + env,
              cidr: network?.cidr,
              consoleUrl: network?.consoleUrl
            })}
          >
            <rect
              x="0" y="0"
              width={azs.length * azWidth + (azs.length - 1) * azGap + 20}
              height="32" rx="10"
              fill={isSelected('vpc', network?.vpcId) ? '#1e40af' : '#1e3a5f'}
              className="hover:fill-[#234876] transition-colors"
            />
            <text x="20" y="22" fill="#60a5fa" fontSize="15" fontWeight="bold">
              VPC: {network?.vpcName || (appConfig?.serviceNaming?.prefix || 'app') + '-' + env}
            </text>
            <text x={azs.length * azWidth + (azs.length - 1) * azGap} y="22" fill="#93c5fd" fontSize="13" textAnchor="end">
              {network?.cidr || '10.x.0.0/16'}
            </text>
          </g>

          {/* AZ Columns with Subnets */}
          {azs.map((az, azIndex) => {
            const azX = 10 + azIndex * (azWidth + azGap)
            const azSubnets = network?.subnetsByAz?.[az] || []

            // Find NAT in this AZ
            const natInAz = natGateways.find(nat => nat.az === az) ||
                           (azIndex === 0 && network?.egressIps?.[0] ? { ip: network.egressIps[0] } : null)

            return (
              <g key={az} transform={`translate(${azX}, 42)`}>
                {/* AZ Container */}
                <rect x="0" y="0" width={azWidth} height="560" rx="8" fill="#0f172a" stroke="#334155" strokeWidth="1" />
                <rect x="0" y="0" width={azWidth} height="28" rx="8" fill="#1e293b" />
                <text x={azWidth/2} y="19" fill="#94a3b8" fontSize="13" textAnchor="middle" fontWeight="bold">{az}</text>

                {/* Public Subnet */}
                {(() => {
                  const subnet = azSubnets.find(s => s.type === 'public')
                  if (!subnet) return null
                  const highlighted = isSubnetHighlighted(subnet.id)
                  const rtId = subnetRouteTableMap[subnet.id]

                  return (
                    <g
                      transform="translate(5, 35)"
                      className="cursor-pointer"
                      onClick={() => onComponentSelect?.('subnet', env, { ...subnet, subnetType: 'public', az, routeTableId: rtId, vpcId: network?.vpcId })}
                      onMouseEnter={() => setHoveredSubnet(subnet.id)}
                      onMouseLeave={() => setHoveredSubnet(null)}
                    >
                      <rect
                        x="0" y="0" width={azWidth - 10} height={natInAz ? 150 : 110} rx="6"
                        fill={isSelected('subnet', subnet.id) ? '#052e16' : highlighted ? '#073d1f' : '#0a2615'}
                        stroke="#22c55e"
                        strokeWidth={isSelected('subnet', subnet.id) || highlighted ? 3 : 1}
                        strokeOpacity="0.8"
                        filter={highlighted ? 'url(#glow-cyan)' : undefined}
                      />
                      <text x="10" y="22" fill="#4ade80" fontSize="13" fontWeight="bold">Public Subnet</text>
                      <text x={azWidth - 20} y="22" fill="#4ade80" fontSize="11" textAnchor="end">{subnet.cidr}</text>
                      <text x="10" y="42" fill="#6b7280" fontSize="10">{subnet.id}</text>

                      {/* NAT Gateway inside Public Subnet */}
                      {natInAz && (
                        <g transform="translate(10, 78)">
                          <rect x="0" y="0" width={azWidth - 30} height="60" rx="5" fill="#1f2937" stroke="#eab308" strokeWidth="1.5" />
                          <foreignObject x="10" y="10" width="36" height="36">
                            <AwsNAT style={{ width: 36, height: 36 }} />
                          </foreignObject>
                          <text x="55" y="22" fill="#fef08a" fontSize="11" fontWeight="bold">NAT Gateway</text>
                          <text x="55" y="40" fill="#fcd34d" fontSize="10">{natInAz.ip || natInAz.publicIp || 'Elastic IP'}</text>
                          {natInAz.state && (
                            <text x={azWidth - 50} y="35" fill={natInAz.state === 'available' ? '#4ade80' : '#fbbf24'} fontSize="10" textAnchor="end">
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
                  const yOffset = publicSubnet ? (natGateways.find(nat => nat.az === az) || (azIndex === 0 && network?.egressIps?.[0]) ? 195 : 155) : 35

                  return (
                    <g
                      transform={`translate(5, ${yOffset})`}
                      className="cursor-pointer"
                      onClick={() => onComponentSelect?.('subnet', env, { ...subnet, subnetType: 'private', az, routeTableId: rtId, vpcId: network?.vpcId })}
                      onMouseEnter={() => setHoveredSubnet(subnet.id)}
                      onMouseLeave={() => setHoveredSubnet(null)}
                    >
                      <rect
                        x="0" y="0" width={azWidth - 10} height="130" rx="6"
                        fill={isSelected('subnet', subnet.id) ? '#172554' : highlighted ? '#1e3a5f' : '#0c1a3d'}
                        stroke="#3b82f6"
                        strokeWidth={isSelected('subnet', subnet.id) || highlighted ? 3 : 1}
                        strokeOpacity="0.8"
                        filter={highlighted ? 'url(#glow-cyan)' : undefined}
                      />
                      <text x="10" y="22" fill="#60a5fa" fontSize="13" fontWeight="bold">Private Subnet</text>
                      <text x={azWidth - 20} y="22" fill="#60a5fa" fontSize="11" textAnchor="end">{subnet.cidr}</text>
                      <text x="10" y="42" fill="#6b7280" fontSize="10">{subnet.id}</text>
                      <text x="10" y="62" fill="#9ca3af" fontSize="10">ECS Tasks, Lambda, Internal services</text>
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
                  let yOffset = 35
                  if (publicSubnet) yOffset += hasNatInAz ? 160 : 120
                  if (privateSubnet) yOffset += 140

                  return (
                    <g
                      transform={`translate(5, ${yOffset})`}
                      className="cursor-pointer"
                      onClick={() => onComponentSelect?.('subnet', env, { ...subnet, subnetType: 'database', az, routeTableId: rtId, vpcId: network?.vpcId })}
                      onMouseEnter={() => setHoveredSubnet(subnet.id)}
                      onMouseLeave={() => setHoveredSubnet(null)}
                    >
                      <rect
                        x="0" y="0" width={azWidth - 10} height="110" rx="6"
                        fill={isSelected('subnet', subnet.id) ? '#3b0764' : highlighted ? '#4c0d7a' : '#1a0533'}
                        stroke="#a855f7"
                        strokeWidth={isSelected('subnet', subnet.id) || highlighted ? 3 : 1}
                        strokeOpacity="0.8"
                        filter={highlighted ? 'url(#glow-cyan)' : undefined}
                      />
                      <text x="10" y="22" fill="#c084fc" fontSize="13" fontWeight="bold">Database Subnet</text>
                      <text x={azWidth - 20} y="22" fill="#c084fc" fontSize="11" textAnchor="end">{subnet.cidr}</text>
                      <text x="10" y="42" fill="#6b7280" fontSize="10">{subnet.id}</text>
                      <text x="10" y="62" fill="#9ca3af" fontSize="10">RDS, ElastiCache, isolated resources</text>
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

      {/* Legend and Refresh */}
      <div className="flex items-center justify-between mt-3 px-2">
        <div className="flex items-center gap-4 flex-wrap">
          <div className="flex items-center gap-2">
            <div className="w-4 h-4 rounded border-2 border-green-500 bg-green-900/30"></div>
            <span className="text-gray-400 text-xs">Public Subnet</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-4 h-4 rounded border-2 border-blue-500 bg-blue-900/30"></div>
            <span className="text-gray-400 text-xs">Private Subnet</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-4 h-4 rounded border-2 border-purple-500 bg-purple-900/30"></div>
            <span className="text-gray-400 text-xs">Database Subnet</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-4 h-4 rounded border-2 border-cyan-500 bg-cyan-900/30"></div>
            <span className="text-gray-400 text-xs">Route Table</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-4 h-4 rounded border-2 border-yellow-500 bg-yellow-900/30"></div>
            <span className="text-gray-400 text-xs">NAT Gateway</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-4 h-4 rounded border-2 border-teal-500 bg-teal-900/30"></div>
            <span className="text-gray-400 text-xs">VPC Endpoint</span>
          </div>
          <div className="text-gray-500 text-xs ml-4 border-l border-gray-700 pl-4">
            Hover subnets or route tables to see associations
          </div>
        </div>
        <button
          onClick={fetchRoutingData}
          disabled={loading}
          className="flex items-center gap-2 px-3 py-1.5 bg-gray-700 hover:bg-gray-600 rounded-lg text-xs text-gray-300 transition-colors"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>
    </div>
  )
}
