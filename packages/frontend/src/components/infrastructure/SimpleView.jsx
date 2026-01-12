import { useMemo } from 'react'
import AwsCloudFront from 'aws-react-icons/lib/icons/ArchitectureServiceAmazonCloudFront'
import AwsS3 from 'aws-react-icons/lib/icons/ArchitectureServiceAmazonSimpleStorageService'
import AwsALB from 'aws-react-icons/lib/icons/ArchitectureServiceElasticLoadBalancing'
import AwsRDS from 'aws-react-icons/lib/icons/ArchitectureServiceAmazonRDS'
import AwsElastiCache from 'aws-react-icons/lib/icons/ArchitectureServiceAmazonElastiCache'
import AwsEFS from 'aws-react-icons/lib/icons/ArchitectureServiceAmazonEFS'
import { Server, Database } from 'lucide-react'

// Layer configuration with colors
const LAYER_CONFIG = {
  edge: { color: '#f97316', label: 'Edge' },
  ingress: { color: '#3b82f6', label: 'Ingress' },
  frontend: { color: '#8b5cf6', label: 'Frontend' },
  proxy: { color: '#06b6d4', label: 'Proxy' },
  application: { color: '#10b981', label: 'Application' },
  search: { color: '#f59e0b', label: 'Search' },
  data: { color: '#06b6d4', label: 'Data' },
  other: { color: '#6b7280', label: 'Other' }
}

/**
 * Topology-based infrastructure flow diagram
 * Shows services organized by layers with connections between them
 */
export default function SimpleView({
  env,
  data,
  services: envServices,
  onComponentSelect,
  selectedComponent,
  serviceColors,
  SERVICES,
  getServiceName,
  domains,
  appConfig
}) {
  const { cloudfront, alb, s3Buckets, services, rds, redis, efs, orchestrator } = data
  const isEKS = orchestrator === 'eks'

  // Get topology from appConfig
  const topology = appConfig?.topology || appConfig?.currentProject?.topology

  // Determine which infrastructure components exist
  const hasCloudFront = cloudfront !== null && cloudfront !== undefined
  const hasS3 = s3Buckets && s3Buckets.length > 0
  const hasRds = rds && !rds.error
  const hasRedis = redis && !redis.error
  const hasEfs = efs && !efs.error

  // Helper to check if component is selected
  const isSelected = (type) => selectedComponent?.type === type && selectedComponent?.env === env

  // Build service nodes from topology or fallback to services data
  const { nodes, connections, layerColumns } = useMemo(() => {
    const effectiveServices = SERVICES.length > 0 ? SERVICES : Object.keys(services || {})
    const nodeMap = new Map()
    const conns = []

    // Define layer order for positioning
    const layerOrder = ['frontend', 'proxy', 'application', 'search']
    const layerServices = {}
    layerOrder.forEach(l => layerServices[l] = [])

    // Group services by layer
    effectiveServices.forEach(svcName => {
      const svcData = services?.[svcName]
      if (!svcData) return

      let layer = 'other'
      if (topology?.components?.[svcName]?.layer) {
        layer = topology.components[svcName].layer
      } else {
        // Fallback layer detection
        const svcLower = svcName.toLowerCase()
        if (svcLower.includes('nextjs') || svcLower.includes('frontend')) layer = 'frontend'
        else if (svcLower.includes('apache') || svcLower.includes('haproxy') || svcLower.includes('nginx')) layer = 'proxy'
        else if (svcLower.includes('hybris') || svcLower.includes('backend')) layer = 'application'
        else if (svcLower.includes('solr') || svcLower.includes('elastic')) layer = 'search'
      }

      // Skip edge/ingress/data layers (handled separately)
      if (['edge', 'ingress', 'data'].includes(layer)) return

      if (!layerServices[layer]) layerServices[layer] = []
      layerServices[layer].push({
        id: svcName,
        name: topology?.components?.[svcName]?.label || svcName,
        layer,
        data: svcData
      })
    })

    // Calculate positions for each service
    const nodeWidth = 100
    const nodeHeight = 60
    const layerGap = 130
    const nodeGap = 70
    const startX = 20
    const startY = 30

    // Find max services in any layer for height calculation
    const maxServicesInLayer = Math.max(...Object.values(layerServices).map(l => l.length), 1)

    // Position nodes by layer
    const columns = {}
    layerOrder.forEach((layer, layerIdx) => {
      const layerSvcs = layerServices[layer] || []
      columns[layer] = { x: startX + layerIdx * layerGap, services: layerSvcs }

      layerSvcs.forEach((svc, svcIdx) => {
        const totalInLayer = layerSvcs.length
        const yOffset = (maxServicesInLayer - totalInLayer) * nodeGap / 2
        nodeMap.set(svc.id, {
          ...svc,
          x: startX + layerIdx * layerGap,
          y: startY + svcIdx * nodeGap + yOffset,
          width: nodeWidth,
          height: nodeHeight
        })
      })
    })

    // Build connections from topology
    if (topology?.connections) {
      topology.connections.forEach(conn => {
        const fromNode = nodeMap.get(conn.from)
        const toNode = nodeMap.get(conn.to)
        // Only add connections between service nodes (not infra like aurora, efs)
        if (fromNode && toNode) {
          conns.push({
            from: conn.from,
            to: conn.to,
            protocol: conn.protocol,
            fromNode,
            toNode
          })
        }
      })
    } else {
      // Fallback: create connections between adjacent layers
      const orderedLayers = layerOrder.filter(l => layerServices[l]?.length > 0)
      for (let i = 0; i < orderedLayers.length - 1; i++) {
        const fromLayer = orderedLayers[i]
        const toLayer = orderedLayers[i + 1]
        layerServices[fromLayer]?.forEach(fromSvc => {
          layerServices[toLayer]?.forEach(toSvc => {
            const fromNode = nodeMap.get(fromSvc.id)
            const toNode = nodeMap.get(toSvc.id)
            if (fromNode && toNode) {
              conns.push({ from: fromSvc.id, to: toSvc.id, fromNode, toNode })
            }
          })
        })
      }
    }

    return {
      nodes: Array.from(nodeMap.values()),
      connections: conns,
      layerColumns: columns
    }
  }, [services, topology, SERVICES])

  // Calculate SVG dimensions
  const numLayers = Object.values(layerColumns).filter(c => c.services.length > 0).length
  const maxServicesInLayer = Math.max(...Object.values(layerColumns).map(c => c.services.length), 1)

  // Calculate workloads section dimensions - more generous sizing
  const workloadsWidth = Math.max(numLayers * 130, 400)
  const workloadsHeight = Math.max(maxServicesInLayer * 75 + 80, 300)

  // SVG layout calculations - ensure minimum height of 400px
  const svgWidth = 1200
  const svgHeight = Math.max(workloadsHeight + 60, 400)

  // Position elements with enough space for visible arrows (at least 40px between components)
  const workloadsX = hasCloudFront ? 540 : 320
  const workloadsY = 30
  const dataStoresX = workloadsX + workloadsWidth + 60
  const dataStoresWidth = 170

  // Helper to render service node
  const renderServiceNode = (node) => {
    const svcData = node.data
    const isHealthy = svcData?.health === 'healthy' || svcData?.runningCount === svcData?.desiredCount
    const layerColor = LAYER_CONFIG[node.layer]?.color || '#6b7280'
    const serviceWithName = { ...svcData, name: svcData?.name || getServiceName(env, node.id) }

    return (
      <g
        key={node.id}
        transform={`translate(${node.x}, ${node.y})`}
        className="cursor-pointer"
        onClick={() => onComponentSelect?.('service', env, serviceWithName)}
      >
        <rect
          x="0" y="0"
          width={node.width} height={node.height}
          rx="6"
          fill="#1f2937"
          stroke={isHealthy ? '#22c55e' : '#fbbf24'}
          strokeWidth="1.5"
        />
        <rect
          x="0" y="0"
          width={node.width} height="18"
          rx="6"
          fill={layerColor}
          fillOpacity="0.3"
        />
        <circle
          cx="10" cy="9"
          r="4"
          fill={isHealthy ? '#22c55e' : '#fbbf24'}
        />
        <text
          x={node.width / 2} y="12"
          fill="white"
          fontSize="9"
          fontWeight="bold"
          textAnchor="middle"
        >
          {node.name.length > 12 ? node.name.substring(0, 11) + '…' : node.name}
        </text>
        <text
          x={node.width / 2} y="32"
          fill="#9ca3af"
          fontSize="8"
          textAnchor="middle"
        >
          {svcData?.runningCount ?? '?'}/{svcData?.desiredCount ?? '?'} pods
        </text>
        <text
          x={node.width / 2} y="45"
          fill={svcData?.status === 'ACTIVE' ? '#4ade80' : '#fbbf24'}
          fontSize="8"
          textAnchor="middle"
        >
          {svcData?.status || 'UNKNOWN'}
        </text>
      </g>
    )
  }

  // Helper to render connection arrow
  const renderConnection = (conn, idx) => {
    const from = conn.fromNode
    const to = conn.toNode

    // Calculate connection points
    const fromX = from.x + from.width
    const fromY = from.y + from.height / 2
    const toX = to.x
    const toY = to.y + to.height / 2

    // Create a curved path
    const midX = (fromX + toX) / 2
    const path = `M ${fromX} ${fromY} C ${midX} ${fromY}, ${midX} ${toY}, ${toX} ${toY}`

    return (
      <path
        key={`conn-${idx}`}
        d={path}
        stroke="#4b5563"
        strokeWidth="1.5"
        fill="none"
        markerEnd={`url(#arrow-small-${env})`}
        opacity="0.6"
      />
    )
  }

  return (
    <div className="p-4">
      <svg viewBox={`0 0 ${svgWidth} ${svgHeight}`} className="w-full h-auto" style={{ minHeight: `${svgHeight}px` }}>
        <defs>
          <marker id={`arrow-${env}`} markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
            <polygon points="0 0, 10 3.5, 0 7" fill="#6b7280" />
          </marker>
          <marker id={`arrow-small-${env}`} markerWidth="6" markerHeight="5" refX="5" refY="2.5" orient="auto">
            <polygon points="0 0, 6 2.5, 0 5" fill="#4b5563" />
          </marker>
        </defs>

        {/* Users */}
        <g transform={`translate(20, ${svgHeight / 2 - 50})`}>
          <circle cx="35" cy="35" r="32" fill="#334155" stroke="#64748b" strokeWidth="2" />
          <circle cx="35" cy="26" r="10" fill="#94a3b8" />
          <path d="M 35 38 L 35 55 M 23 46 L 47 46 M 35 55 L 25 70 M 35 55 L 45 70" stroke="#94a3b8" strokeWidth="2.5" fill="none" />
          <text x="35" y="85" fill="#94a3b8" fontSize="11" textAnchor="middle">Users</text>
        </g>

        {/* Arrow Users -> CloudFront/ALB */}
        <line
          x1="95" y1={svgHeight / 2 - 15}
          x2="135" y2={svgHeight / 2 - 15}
          stroke="#94a3b8" strokeWidth="2.5"
          markerEnd={`url(#arrow-${env})`}
        />

        {hasCloudFront ? (
          <>
            {/* CloudFront */}
            <g transform={`translate(140, ${svgHeight / 2 - 65})`} className="cursor-pointer" onClick={() => onComponentSelect?.('cloudfront', env, cloudfront)}>
              <rect x="0" y="0" width="140" height="100" rx="8" fill={isSelected('cloudfront') ? '#334155' : '#1f2937'} stroke="#f97316" strokeWidth={isSelected('cloudfront') ? 3 : 2} />
              <rect x="0" y="0" width="140" height="24" rx="8" fill="#f97316" />
              <text x="70" y="17" fill="white" fontSize="11" textAnchor="middle" fontWeight="bold">CloudFront</text>
              <foreignObject x="50" y="28" width="40" height="40">
                <AwsCloudFront style={{ width: 40, height: 40 }} />
              </foreignObject>
              <text x="70" y="78" fill={cloudfront?.status === 'Deployed' ? '#4ade80' : '#fbbf24'} fontSize="10" textAnchor="middle">{cloudfront?.status || '...'}</text>
              <text x="70" y="92" fill="#6b7280" fontSize="8" textAnchor="middle">{cloudfront?.id?.substring(0, 13)}</text>
            </g>

            {/* Arrows CloudFront -> S3/ALB */}
            {hasS3 && (
              <>
                <path d={`M 280 ${svgHeight / 2 - 40} Q 315 ${svgHeight / 2 - 80}, 355 ${svgHeight / 2 - 100}`} stroke="#94a3b8" strokeWidth="2.5" fill="none" markerEnd={`url(#arrow-${env})`} />
                {/* S3 */}
                <g transform={`translate(360, ${svgHeight / 2 - 140})`} className="cursor-pointer" onClick={() => onComponentSelect?.('s3', env, s3Buckets)}>
                  <rect x="0" y="0" width="120" height="80" rx="8" fill={isSelected('s3') ? '#334155' : '#1f2937'} stroke="#a855f7" strokeWidth={isSelected('s3') ? 3 : 2} />
                  <rect x="0" y="0" width="120" height="20" rx="8" fill="#a855f7" />
                  <text x="60" y="14" fill="white" fontSize="10" textAnchor="middle" fontWeight="bold">S3 Buckets</text>
                  <foreignObject x="40" y="24" width="40" height="40">
                    <AwsS3 style={{ width: 40, height: 40 }} />
                  </foreignObject>
                  <text x="60" y="72" fill="#9ca3af" fontSize="9" textAnchor="middle">{s3Buckets.length} bucket(s)</text>
                </g>
              </>
            )}

            <path d={`M 280 ${svgHeight / 2 - 15} Q 315 ${svgHeight / 2 + 20}, 355 ${svgHeight / 2 + 20}`} stroke="#94a3b8" strokeWidth="2.5" fill="none" markerEnd={`url(#arrow-${env})`} />

            {/* ALB */}
            <g transform={`translate(360, ${svgHeight / 2 - 20})`} className="cursor-pointer" onClick={() => onComponentSelect?.('alb', env, alb)}>
              <rect x="0" y="0" width="120" height="80" rx="8" fill={isSelected('alb') ? '#334155' : '#1f2937'} stroke="#3b82f6" strokeWidth={isSelected('alb') ? 3 : 2} />
              <rect x="0" y="0" width="120" height="20" rx="8" fill="#3b82f6" />
              <text x="60" y="14" fill="white" fontSize="10" textAnchor="middle" fontWeight="bold">Load Balancer</text>
              <foreignObject x="40" y="24" width="40" height="40">
                <AwsALB style={{ width: 40, height: 40 }} />
              </foreignObject>
              <text x="60" y="72" fill={alb?.status === 'active' ? '#4ade80' : '#9ca3af'} fontSize="9" textAnchor="middle">{alb?.targetGroups?.length || 0} targets</text>
            </g>

            {/* Arrow ALB -> Workloads */}
            <line x1="485" y1={svgHeight / 2 + 15} x2={workloadsX - 15} y2={svgHeight / 2 + 15} stroke="#94a3b8" strokeWidth="2.5" markerEnd={`url(#arrow-${env})`} />
          </>
        ) : (
          <>
            {/* ALB directly */}
            <g transform={`translate(140, ${svgHeight / 2 - 50})`} className="cursor-pointer" onClick={() => onComponentSelect?.('alb', env, alb)}>
              <rect x="0" y="0" width="120" height="80" rx="8" fill={isSelected('alb') ? '#334155' : '#1f2937'} stroke="#3b82f6" strokeWidth={isSelected('alb') ? 3 : 2} />
              <rect x="0" y="0" width="120" height="20" rx="8" fill="#3b82f6" />
              <text x="60" y="14" fill="white" fontSize="10" textAnchor="middle" fontWeight="bold">Load Balancer</text>
              <foreignObject x="40" y="24" width="40" height="40">
                <AwsALB style={{ width: 40, height: 40 }} />
              </foreignObject>
              <text x="60" y="72" fill={alb?.status === 'active' ? '#4ade80' : '#9ca3af'} fontSize="9" textAnchor="middle">{alb?.targetGroups?.length || 0} targets</text>
            </g>

            {/* Arrow ALB -> Workloads */}
            <line x1="265" y1={svgHeight / 2 - 10} x2={workloadsX - 15} y2={svgHeight / 2 - 10} stroke="#94a3b8" strokeWidth="2.5" markerEnd={`url(#arrow-${env})`} />
          </>
        )}

        {/* Workloads Container */}
        <g transform={`translate(${workloadsX}, ${workloadsY})`}>
          {/* Background */}
          <rect
            x="0" y="0"
            width={workloadsWidth} height={workloadsHeight}
            rx="10"
            fill="#1e293b"
            stroke="#10b981"
            strokeWidth="2"
          />

          {/* Header */}
          <rect x="0" y="0" width={workloadsWidth} height="28" rx="10" fill="#10b981" />
          <text x={workloadsWidth / 2} y="19" fill="white" fontSize="12" textAnchor="middle" fontWeight="bold">
            {isEKS ? 'EKS Workloads' : 'ECS Services'}
          </text>
          <text x={workloadsWidth - 10} y="19" fill="#d1fae5" fontSize="9" textAnchor="end">
            {nodes.length} services
          </text>

          {/* Layer labels */}
          {Object.entries(layerColumns).map(([layer, col]) => {
            if (col.services.length === 0) return null
            const layerConf = LAYER_CONFIG[layer] || LAYER_CONFIG.other
            return (
              <g key={layer}>
                <text
                  x={col.x + 50} y="45"
                  fill={layerConf.color}
                  fontSize="9"
                  fontWeight="bold"
                  textAnchor="middle"
                >
                  {layerConf.label}
                </text>
              </g>
            )
          })}

          {/* Connections between services */}
          <g transform="translate(0, 25)">
            {connections.map((conn, idx) => renderConnection(conn, idx))}
          </g>

          {/* Service nodes */}
          <g transform="translate(0, 25)">
            {nodes.map(node => renderServiceNode(node))}
          </g>

          {/* No services message */}
          {nodes.length === 0 && (
            <g transform={`translate(${workloadsWidth / 2}, ${workloadsHeight / 2})`}>
              <Server className="w-6 h-6" style={{ transform: 'translate(-12px, -12px)' }} />
              <text y="20" fill="#6b7280" fontSize="10" textAnchor="middle">No services</text>
            </g>
          )}
        </g>

        {/* Arrow Workloads -> Data */}
        <line
          x1={workloadsX + workloadsWidth + 5} y1={svgHeight / 2}
          x2={dataStoresX - 15} y2={svgHeight / 2}
          stroke="#94a3b8" strokeWidth="2.5"
          markerEnd={`url(#arrow-${env})`}
        />

        {/* Data Stores */}
        <g transform={`translate(${dataStoresX}, ${workloadsY})`}>
          <rect x="0" y="0" width={dataStoresWidth} height={workloadsHeight} rx="10" fill="#1e293b" stroke="#06b6d4" strokeWidth="2" />
          <rect x="0" y="0" width={dataStoresWidth} height="28" rx="10" fill="#06b6d4" />
          <text x={dataStoresWidth / 2} y="19" fill="white" fontSize="12" textAnchor="middle" fontWeight="bold">Data Stores</text>

          {/* RDS */}
          {hasRds && (
            <g transform="translate(10, 38)" className="cursor-pointer" onClick={() => onComponentSelect?.('rds', env, rds)}>
              <rect x="0" y="0" width={dataStoresWidth - 20} height="70" rx="6" fill="#1f2937" stroke="#22d3ee" strokeWidth="1.5" />
              <foreignObject x="5" y="8" width="30" height="30">
                <AwsRDS style={{ width: 30, height: 30 }} />
              </foreignObject>
              <text x="40" y="20" fill="white" fontSize="9" fontWeight="bold">Aurora</text>
              <text x="40" y="32" fill={rds.status === 'available' ? '#4ade80' : '#fbbf24'} fontSize="8">{rds.status}</text>
              <text x={dataStoresWidth / 2 - 10} y="55" fill="#9ca3af" fontSize="8" textAnchor="middle">{rds.instanceClass}</text>
              <text x={dataStoresWidth / 2 - 10} y="65" fill="#6b7280" fontSize="7" textAnchor="middle">{rds.multiAz ? 'Multi-AZ' : 'Single-AZ'}</text>
            </g>
          )}

          {/* Redis */}
          {hasRedis && (
            <g transform={`translate(10, ${hasRds ? 118 : 38})`} className="cursor-pointer" onClick={() => onComponentSelect?.('redis', env, redis)}>
              <rect x="0" y="0" width={dataStoresWidth - 20} height="70" rx="6" fill="#1f2937" stroke="#ef4444" strokeWidth="1.5" />
              <foreignObject x="5" y="8" width="30" height="30">
                <AwsElastiCache style={{ width: 30, height: 30 }} />
              </foreignObject>
              <text x="40" y="20" fill="white" fontSize="9" fontWeight="bold">Redis</text>
              <text x="40" y="32" fill={redis.status === 'available' ? '#4ade80' : '#fbbf24'} fontSize="8">{redis.status}</text>
              <text x={dataStoresWidth / 2 - 10} y="55" fill="#9ca3af" fontSize="8" textAnchor="middle">{redis.cacheNodeType}</text>
              <text x={dataStoresWidth / 2 - 10} y="65" fill="#6b7280" fontSize="7" textAnchor="middle">{redis.numCacheNodes} node(s)</text>
            </g>
          )}

          {/* EFS */}
          {hasEfs && (
            <g transform={`translate(10, ${(hasRds ? 80 : 0) + (hasRedis ? 80 : 0) + 38})`} className="cursor-pointer" onClick={() => onComponentSelect?.('efs', env, efs)}>
              <rect x="0" y="0" width={dataStoresWidth - 20} height="50" rx="6" fill="#1f2937" stroke="#f59e0b" strokeWidth="1.5" />
              <foreignObject x="5" y="5" width="30" height="30">
                <AwsEFS style={{ width: 30, height: 30 }} />
              </foreignObject>
              <text x="40" y="18" fill="white" fontSize="9" fontWeight="bold">EFS</text>
              <text x="40" y="30" fill={efs.lifeCycleState === 'available' ? '#4ade80' : '#fbbf24'} fontSize="8">{efs.lifeCycleState}</text>
            </g>
          )}

          {/* No data stores */}
          {!hasRds && !hasRedis && !hasEfs && (
            <g transform={`translate(${dataStoresWidth / 2}, ${workloadsHeight / 2})`}>
              <Database className="w-6 h-6" style={{ transform: 'translate(-12px, -12px)', color: '#6b7280' }} />
              <text y="20" fill="#6b7280" fontSize="9" textAnchor="middle">No data stores</text>
            </g>
          )}
        </g>
      </svg>
    </div>
  )
}
