import { useMemo } from 'react'
import AwsCloudFront from 'aws-react-icons/lib/icons/ArchitectureServiceAmazonCloudFront'
import AwsS3 from 'aws-react-icons/lib/icons/ArchitectureServiceAmazonSimpleStorageService'
import AwsALB from 'aws-react-icons/lib/icons/ArchitectureServiceElasticLoadBalancing'
import AwsRDS from 'aws-react-icons/lib/icons/ArchitectureServiceAmazonRDS'
import AwsElastiCache from 'aws-react-icons/lib/icons/ArchitectureServiceAmazonElastiCache'
import AwsEFS from 'aws-react-icons/lib/icons/ArchitectureServiceAmazonEFS'
import { Server, Database } from 'lucide-react'
import { stripServiceName } from '../../utils/serviceNaming'

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
  const servicesMap = envServices?.services || envServices || {}

  // Get topology from appConfig
  const topology = data?.topology || appConfig?.topology || appConfig?.currentProject?.topology

  const getShortServiceLabel = (value) => {
    return stripServiceName(value, appConfig?.serviceNaming, appConfig?.currentProjectId, env)
  }

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
    const availableServices = Object.keys(servicesMap || {})
    const topologyComponents = topology?.components && typeof topology.components === 'object'
      ? topology.components
      : {}
    const configuredComponentIds = Object.keys(topologyComponents)
    const nodeMap = new Map()
    const conns = []
    const layoutNodes = topology?.layout?.nodes || {}
    const layoutPositions = Object.values(layoutNodes)
    const hasLayout = layoutPositions.length > 0
    const layoutOrigin = hasLayout
      ? {
          minX: Math.min(...layoutPositions.map(pos => pos.x)),
          minY: Math.min(...layoutPositions.map(pos => pos.y))
        }
      : null

    const layerOrder = Array.isArray(topology?.layers) ? [...topology.layers] : []
    const layerServices = {}

    const resolveServiceKey = (componentId) => {
      if (servicesMap?.[componentId]) return componentId
      const shortComponentId = getShortServiceLabel(componentId)
      if (shortComponentId && servicesMap?.[shortComponentId]) return shortComponentId
      return availableServices.find((svc) => {
        const shortSvc = getShortServiceLabel(svc)
        return shortSvc === componentId || shortSvc === shortComponentId
      }) || null
    }

    const resolvedEntries = configuredComponentIds
      .map((componentId) => ({
        componentId,
        serviceKey: resolveServiceKey(componentId),
      }))
      .filter((entry) => entry.serviceKey)

    const fallbackServiceKeys =
      availableServices.length > 0
        ? availableServices
        : SERVICES.length > 0
          ? SERVICES
          : []

    const effectiveEntries = resolvedEntries.length > 0
      ? resolvedEntries
      : fallbackServiceKeys.map((serviceKey) => ({
        componentId: serviceKey,
        serviceKey,
      }))

    // Group services by layer
    effectiveEntries.forEach(({ componentId, serviceKey }) => {
      const svcData = servicesMap?.[serviceKey]
      if (!svcData) return

      const component = topologyComponents[componentId] || {}
      const layer = component.layer || 'application'

      if (!layerServices[layer]) layerServices[layer] = []
      if (!layerOrder.includes(layer)) layerOrder.push(layer)
      layerServices[layer].push({
        id: componentId,
        serviceKey,
        name: component.label || getShortServiceLabel(serviceKey) || componentId,
        layer,
        data: svcData
      })
    })

    // Calculate positions for each service - enlarged for better visibility
    const nodeWidth = 145
    const nodeHeight = 85
    const layerGap = 170
    const nodeGap = 92
    const startX = 15
    const startY = 10

    // Find max services in any layer for height calculation
    const maxServicesInLayer = Math.max(...Object.values(layerServices).map(l => l.length), 1)

    // Position nodes by layer - use compact index (only active layers)
    const columns = {}
    const activeLayers = layerOrder.length > 0
      ? layerOrder.filter(l => (layerServices[l] || []).length > 0)
      : Object.keys(layerServices).filter(l => (layerServices[l] || []).length > 0)

    activeLayers.forEach((layer, compactIdx) => {
      const layerSvcs = layerServices[layer] || []
      columns[layer] = { x: startX + compactIdx * layerGap, services: layerSvcs }

      layerSvcs.forEach((svc, svcIdx) => {
        // No vertical centering - align all services to top
        let x = startX + compactIdx * layerGap
        let y = startY + svcIdx * nodeGap

        if (hasLayout && layoutNodes[svc.id] && layoutOrigin) {
          x = startX + (layoutNodes[svc.id].x - layoutOrigin.minX)
          y = startY + (layoutNodes[svc.id].y - layoutOrigin.minY)
        }

        nodeMap.set(svc.id, {
          ...svc,
          x,
          y,
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
  }, [servicesMap, topology, SERVICES])

  // Calculate SVG dimensions
  const numLayers = Object.values(layerColumns).filter(c => c.services.length > 0).length
  const maxServicesInLayer = Math.max(...Object.values(layerColumns).map(c => c.services.length), 1)

  // Calculate workloads section dimensions - enlarged for better visibility
  // Header: 32px, Labels at y=50 (fontSize 13), Transform: 65px, StartY: 10px, NodeGap: 92px, NodeHeight: 85px
  const workloadsWidth = Math.max(numLayers * 170 + 20, 500)
  const workloadsHeight = Math.max(65 + 10 + (maxServicesInLayer - 1) * 92 + 85 + 40, 360)

  // SVG layout calculations - ensure minimum height based on workloads
  const dataStoresWidth = 190
  const workloadsX = hasCloudFront ? 560 : 340
  const dataStoresX = workloadsX + workloadsWidth + 50
  const svgWidth = Math.max(dataStoresX + dataStoresWidth + 30, 1200)  // Ensure Data Stores fits
  const svgHeight = Math.max(workloadsHeight + 80, 400)
  const workloadsY = 30

  // Helper to render service node - enlarged for better visibility
  const renderServiceNode = (node) => {
    const svcData = node.data
    const isHealthy = svcData?.health === 'healthy' || svcData?.runningCount === svcData?.desiredCount
    const layerColor = LAYER_CONFIG[node.layer]?.color || '#6b7280'
    const serviceWithName = {
      ...svcData,
      name: node.name || svcData?.name || getShortServiceLabel(node.serviceKey || node.id),
    }
    const labelLines = serviceWithName.name
      ? serviceWithName.name
          .split(/[-_ ]+/)
          .map((part) => part.trim())
          .filter(Boolean)
      : ['']
    const displayLines = labelLines.length > 2 ? labelLines.slice(0, 2) : labelLines

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
          rx="8"
          fill="#1f2937"
          stroke={isHealthy ? '#22c55e' : '#fbbf24'}
          strokeWidth="2"
        />
        <rect
          x="0" y="0"
          width={node.width} height="26"
          rx="8"
          fill={layerColor}
          fillOpacity="0.3"
        />
        <circle
          cx="14" cy="13"
          r="6"
          fill={isHealthy ? '#22c55e' : '#fbbf24'}
        />
        <text
          x={node.width / 2} y="18"
          fill="white"
          fontSize="13"
          fontWeight="bold"
          textAnchor="middle"
        >
          <title>{serviceWithName.name}</title>
          {displayLines.map((line, idx) => (
            <tspan
              key={`label-${node.id}-${idx}`}
              x={node.width / 2}
              dy={idx === 0 ? 0 : 14}
            >
              {line}
              {idx === displayLines.length - 1 && labelLines.length > displayLines.length ? '…' : ''}
            </tspan>
          ))}
        </text>
        <text
          x={node.width / 2} y="46"
          fill="#9ca3af"
          fontSize="12"
          textAnchor="middle"
        >
          {svcData?.runningCount ?? '?'}/{svcData?.desiredCount ?? '?'} pods
        </text>
        <text
          x={node.width / 2} y="66"
          fill={svcData?.status === 'ACTIVE' ? '#4ade80' : '#fbbf24'}
          fontSize="12"
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

          {/* Header - enlarged for better visibility */}
          <rect x="0" y="0" width={workloadsWidth} height="32" rx="10" fill="#10b981" />
          <text x={workloadsWidth / 2} y="22" fill="white" fontSize="14" textAnchor="middle" fontWeight="bold">
            {isEKS ? 'EKS Workloads' : 'ECS Services'}
          </text>
          <text x={workloadsWidth - 12} y="22" fill="#d1fae5" fontSize="11" textAnchor="end">
            {nodes.length} services
          </text>

          {/* Layer labels - enlarged for better visibility */}
          {Object.entries(layerColumns).map(([layer, col]) => {
            if (col.services.length === 0) return null
            const layerConf = LAYER_CONFIG[layer] || { color: LAYER_CONFIG.other.color }
            return (
              <g key={layer}>
                <text
                  x={col.x + 72} y="50"
                  fill={layerConf.color}
                  fontSize="13"
                  fontWeight="bold"
                  textAnchor="middle"
                >
                  {layerConf.label || layer.charAt(0).toUpperCase() + layer.slice(1)}
                </text>
              </g>
            )
          })}

          {/* Connections between services */}
          <g transform="translate(0, 65)">
            {connections.map((conn, idx) => renderConnection(conn, idx))}
          </g>

          {/* Service nodes */}
          <g transform="translate(0, 65)">
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

        {/* Data Stores - enlarged for better visibility */}
        <g transform={`translate(${dataStoresX}, ${workloadsY})`}>
          <rect x="0" y="0" width={dataStoresWidth} height={workloadsHeight} rx="10" fill="#1e293b" stroke="#06b6d4" strokeWidth="2" />
          <rect x="0" y="0" width={dataStoresWidth} height="32" rx="10" fill="#06b6d4" />
          <text x={dataStoresWidth / 2} y="22" fill="white" fontSize="14" textAnchor="middle" fontWeight="bold">Data Stores</text>

          {/* RDS - enlarged for better visibility */}
          {hasRds && (
            <g transform="translate(10, 42)" className="cursor-pointer" onClick={() => onComponentSelect?.('rds', env, rds)}>
              <rect x="0" y="0" width={dataStoresWidth - 20} height="80" rx="6" fill="#1f2937" stroke="#22d3ee" strokeWidth="1.5" />
              <foreignObject x="8" y="10" width="34" height="34">
                <AwsRDS style={{ width: 34, height: 34 }} />
              </foreignObject>
              <text x="48" y="24" fill="white" fontSize="11" fontWeight="bold">Aurora</text>
              <text x="48" y="40" fill={rds.status === 'available' ? '#4ade80' : '#fbbf24'} fontSize="10">{rds.status}</text>
              <text x={dataStoresWidth / 2 - 10} y="60" fill="#9ca3af" fontSize="10" textAnchor="middle">{rds.instanceClass}</text>
              <text x={dataStoresWidth / 2 - 10} y="74" fill="#6b7280" fontSize="9" textAnchor="middle">{rds.multiAz ? 'Multi-AZ' : 'Single-AZ'}</text>
            </g>
          )}

          {/* Redis - enlarged for better visibility */}
          {hasRedis && (
            <g transform={`translate(10, ${hasRds ? 130 : 42})`} className="cursor-pointer" onClick={() => onComponentSelect?.('redis', env, redis)}>
              <rect x="0" y="0" width={dataStoresWidth - 20} height="80" rx="6" fill="#1f2937" stroke="#ef4444" strokeWidth="1.5" />
              <foreignObject x="8" y="10" width="34" height="34">
                <AwsElastiCache style={{ width: 34, height: 34 }} />
              </foreignObject>
              <text x="48" y="24" fill="white" fontSize="11" fontWeight="bold">Redis</text>
              <text x="48" y="40" fill={redis.status === 'available' ? '#4ade80' : '#fbbf24'} fontSize="10">{redis.status}</text>
              <text x={dataStoresWidth / 2 - 10} y="60" fill="#9ca3af" fontSize="10" textAnchor="middle">{redis.cacheNodeType}</text>
              <text x={dataStoresWidth / 2 - 10} y="74" fill="#6b7280" fontSize="9" textAnchor="middle">{redis.numCacheNodes} node(s)</text>
            </g>
          )}

          {/* EFS - enlarged for better visibility */}
          {hasEfs && (
            <g transform={`translate(10, ${(hasRds ? 88 : 0) + (hasRedis ? 88 : 0) + 42})`} className="cursor-pointer" onClick={() => onComponentSelect?.('efs', env, efs)}>
              <rect x="0" y="0" width={dataStoresWidth - 20} height="60" rx="6" fill="#1f2937" stroke="#f59e0b" strokeWidth="1.5" />
              <foreignObject x="8" y="8" width="34" height="34">
                <AwsEFS style={{ width: 34, height: 34 }} />
              </foreignObject>
              <text x="48" y="22" fill="white" fontSize="11" fontWeight="bold">EFS</text>
              <text x="48" y="38" fill={efs.lifeCycleState === 'available' ? '#4ade80' : '#fbbf24'} fontSize="10">{efs.lifeCycleState}</text>
            </g>
          )}

          {/* No data stores */}
          {!hasRds && !hasRedis && !hasEfs && (
            <g transform={`translate(${dataStoresWidth / 2}, ${workloadsHeight / 2})`}>
              <Database className="w-8 h-8" style={{ transform: 'translate(-16px, -16px)', color: '#6b7280' }} />
              <text y="24" fill="#6b7280" fontSize="11" textAnchor="middle">No data stores</text>
            </g>
          )}
        </g>
      </svg>
    </div>
  )
}
