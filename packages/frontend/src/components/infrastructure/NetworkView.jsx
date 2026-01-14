import { useState } from 'react'
import { Server, Cpu, HardDrive } from 'lucide-react'
import AwsCloudFront from 'aws-react-icons/lib/icons/ArchitectureServiceAmazonCloudFront'
import AwsS3 from 'aws-react-icons/lib/icons/ArchitectureServiceAmazonSimpleStorageService'
import AwsALB from 'aws-react-icons/lib/icons/ArchitectureServiceElasticLoadBalancing'
import AwsRDS from 'aws-react-icons/lib/icons/ArchitectureServiceAmazonRDS'
import AwsElastiCache from 'aws-react-icons/lib/icons/ArchitectureServiceAmazonElastiCache'
import { formatServicePrefix } from '../../utils/serviceNaming'

/**
 * Detailed network architecture diagram with VPC, subnets, AZs
 * Supports both ECS (tasks) and EKS (nodes/pods) orchestrators
 */
export default function NetworkView({
  env,
  data,
  services: envServices,
  nodes,
  onComponentSelect,
  selectedComponent,
  serviceColors,
  SERVICES,
  getServiceName,
  getDefaultAzs,
  appConfig
}) {
  const [showAlbFlows, setShowAlbFlows] = useState(false)

  const { cloudfront, alb, s3Buckets, services, rds, redis, network } = data

  // Detect orchestrator type
  const isEKS = data.orchestrator === 'eks'

  // For EKS: use services from backend data if SERVICES config is empty
  const effectiveServices = SERVICES.length > 0 ? SERVICES : Object.keys(services || {})

  // Determine which infrastructure components exist
  const hasCloudFront = cloudfront !== null && cloudfront !== undefined
  const hasS3 = s3Buckets && s3Buckets.length > 0

  // Get S3 buckets by type
  const frontendBucket = s3Buckets?.find(b => b.type === 'frontend')
  const assetsBucket = s3Buckets?.find(b => b.type === 'cms-public' || b.type === 'assets')

  // Helper to check if component is selected
  const isSelected = (type) => selectedComponent?.type === type && selectedComponent?.env === env

  // Group nodes by AZ for EKS view
  const nodesByAz = {}
  if (isEKS && nodes) {
    nodes.forEach(node => {
      const az = node.az || 'unknown'
      if (!nodesByAz[az]) nodesByAz[az] = []
      nodesByAz[az].push(node)
    })
  }

  // Get utilization color based on percentage
  const getUtilizationColor = (percent) => {
    if (percent >= 90) return '#ef4444' // red
    if (percent >= 75) return '#eab308' // yellow
    return '#22c55e' // green
  }

  return (
    <div className="p-4 relative overflow-x-auto">
      <svg viewBox="0 0 1400 800" className="w-full h-auto min-w-[1200px]" style={{ minHeight: '750px' }}>
        {/* Defs */}
        <defs>
          <linearGradient id={`flow-${env}`} x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#f97316" stopOpacity="0" />
            <stop offset="50%" stopColor="#f97316" stopOpacity="1" />
            <stop offset="100%" stopColor="#f97316" stopOpacity="0" />
            <animate attributeName="x1" from="-100%" to="100%" dur="2s" repeatCount="indefinite" />
            <animate attributeName="x2" from="0%" to="200%" dur="2s" repeatCount="indefinite" />
          </linearGradient>
          <marker id="arrowhead" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
            <polygon points="0 0, 10 3.5, 0 7" fill="#6b7280" />
          </marker>
          {/* Task/Pod status gradients */}
          <linearGradient id="task-new" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#22c55e" />
            <stop offset="100%" stopColor="#16a34a" />
          </linearGradient>
          <linearGradient id="task-old" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#f97316" />
            <stop offset="100%" stopColor="#ea580c" />
          </linearGradient>
          <linearGradient id="task-pending" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#eab308" />
            <stop offset="100%" stopColor="#ca8a04" />
            <animate attributeName="x1" values="0%;100%;0%" dur="1.5s" repeatCount="indefinite" />
          </linearGradient>
          {/* Node gradient */}
          <linearGradient id="node-gradient" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#1e293b" />
            <stop offset="100%" stopColor="#0f172a" />
          </linearGradient>
        </defs>

        {/* Internet Zone (outside VPC) - enlarged for better visibility */}
        <g transform="translate(10, 10)">
          <rect x="0" y="0" width="230" height={hasCloudFront || hasS3 ? 460 : 160} rx="8" fill="#1e293b" stroke="#475569" strokeWidth="1" strokeDasharray="4" />
          <text x="115" y="30" fill="#94a3b8" fontSize="16" textAnchor="middle" fontWeight="bold">Internet</text>

          {/* Users */}
          <g transform="translate(52, 60)">
            <circle cx="32" cy="32" r="32" fill="#334155" stroke="#64748b" strokeWidth="2" />
            <circle cx="32" cy="20" r="10" fill="#94a3b8" />
            <path d="M 32 34 L 32 52 M 18 42 L 46 42 M 32 52 L 20 68 M 32 52 L 44 68" stroke="#94a3b8" strokeWidth="2.5" fill="none" />
            <text x="32" y="90" fill="#94a3b8" fontSize="13" textAnchor="middle">Users</text>
          </g>

          {/* CloudFront - only if exists */}
          {hasCloudFront && (
            <g transform="translate(25, 170)" className="cursor-pointer" onClick={() => onComponentSelect?.('cloudfront', env, cloudfront)}>
              <rect x="0" y="0" width="180" height="120" rx="8" fill={isSelected('cloudfront') ? '#334155' : '#1f2937'} stroke={isSelected('cloudfront') ? '#f97316' : '#f97316'} strokeWidth={isSelected('cloudfront') ? 3 : 2} />
              <rect x="0" y="0" width="180" height="32" rx="8" fill="#f97316" />
              <text x="90" y="22" fill="white" fontSize="15" textAnchor="middle" fontWeight="bold">CloudFront</text>
              <foreignObject x="70" y="38" width="44" height="44">
                <AwsCloudFront style={{ width: 44, height: 44 }} />
              </foreignObject>
              <text x="90" y="96" fill="#9ca3af" fontSize="12" textAnchor="middle">{cloudfront?.id}</text>
              <text x="90" y="112" fill={cloudfront?.status === 'Deployed' ? '#4ade80' : '#fbbf24'} fontSize="13" textAnchor="middle" fontWeight="500">{cloudfront?.status || 'Loading...'}</text>
            </g>
          )}

          {/* S3 - only if exists */}
          {hasS3 && (
            <g transform="translate(25, 310)" className="cursor-pointer" onClick={() => onComponentSelect?.('s3', env, s3Buckets)}>
              <rect x="0" y="0" width="180" height="125" rx="8" fill={isSelected('s3') ? '#334155' : '#1f2937'} stroke="#a855f7" strokeWidth={isSelected('s3') ? 3 : 2} />
              <rect x="0" y="0" width="180" height="32" rx="8" fill="#a855f7" />
              <text x="90" y="22" fill="white" fontSize="15" textAnchor="middle" fontWeight="bold">S3 Buckets</text>
              <foreignObject x="70" y="38" width="44" height="44">
                <AwsS3 style={{ width: 44, height: 44 }} />
              </foreignObject>
              <text x="90" y="98" fill="#9ca3af" fontSize="12" textAnchor="middle">{frontendBucket?.name?.split('-').slice(-3).join('-') || 'frontend'}</text>
              <text x="90" y="116" fill="#9ca3af" fontSize="12" textAnchor="middle">{assetsBucket?.name?.split('-').slice(-3).join('-') || 'assets'}</text>
            </g>
          )}
        </g>

        {/* VPC Container - enlarged for better visibility */}
        <g transform="translate(250, 10)">
          <rect x="0" y="0" width="1130" height="780" rx="10" fill="none" stroke="#3b82f6" strokeWidth="2" />
          <rect x="0" y="0" width="1130" height="36" rx="10" fill="#1e3a5f" />
          <text x="20" y="25" fill="#60a5fa" fontSize="16" fontWeight="bold">VPC: {network?.vpcName || (formatServicePrefix(appConfig?.serviceNaming, appConfig?.currentProjectId, env).replace(/-$/, '') || env || '')}</text>
          <text x="1115" y="25" fill="#93c5fd" fontSize="14" textAnchor="end">{network?.cidr || '10.x.0.0/16'}</text>

          {/* AZ Columns - enlarged for better visibility */}
          {(() => {
            const azs = network?.availabilityZones || getDefaultAzs()
            const azWidth = 550
            const azGap = 22

            return azs.map((az, azIndex) => {
              const azX = 10 + azIndex * (azWidth + azGap)
              const nodesInAz = nodesByAz[az] || []

              return (
                <g key={az} transform={`translate(${azX}, 46)`}>
                  {/* AZ Container */}
                  <rect x="0" y="0" width={azWidth} height="725" rx="8" fill="#0f172a" stroke="#334155" strokeWidth="1" />
                  <rect x="0" y="0" width={azWidth} height="32" rx="8" fill="#1e293b" />
                  <text x={azWidth/2} y="22" fill="#94a3b8" fontSize="14" textAnchor="middle" fontWeight="bold">{az}</text>

                  {/* Public Subnet Layer - for ALB/Ingress */}
                  <g transform="translate(5, 40)">
                    <rect x="0" y="0" width={azWidth - 10} height="90" rx="6" fill="#052e16" stroke="#22c55e" strokeWidth="1" strokeOpacity="0.5" />
                    <text x="10" y="20" fill="#4ade80" fontSize="13" fontWeight="bold">Public Subnet</text>
                    <text x={azWidth - 20} y="20" fill="#4ade80" fontSize="12" textAnchor="end">{network?.subnetsByAz?.[az]?.find(s => s.type === 'public')?.cidr || ''}</text>
                  </g>

                  {/* Private Subnet Layer - ECS Tasks or EKS Nodes */}
                  <g transform="translate(5, 140)">
                    <rect x="0" y="0" width={azWidth - 10} height="350" rx="6" fill="#172554" stroke="#3b82f6" strokeWidth="1" strokeOpacity="0.5" />
                    <text x="10" y="20" fill="#60a5fa" fontSize="13" fontWeight="bold">Private Subnet ({isEKS ? 'EKS' : 'ECS'})</text>
                    <text x={azWidth - 20} y="20" fill="#60a5fa" fontSize="12" textAnchor="end">{network?.subnetsByAz?.[az]?.find(s => s.type === 'private')?.cidr || ''}</text>

                    {/* EKS: Nodes with Pods */}
                    {isEKS && (
                      <>
                        {nodesInAz.length === 0 ? (
                          <text x={(azWidth - 10) / 2} y="170" fill="#475569" fontSize="12" textAnchor="middle" fontStyle="italic">No nodes in this AZ</text>
                        ) : (
                          nodesInAz.map((node, nodeIndex) => {
                            const nodeY = 28 + nodeIndex * 145
                            const cpuPercent = node.utilizationPercent?.cpu || 0
                            const memPercent = node.utilizationPercent?.memory || 0
                            const cpuColor = getUtilizationColor(cpuPercent)
                            const memColor = getUtilizationColor(memPercent)
                            const isNodeSelected = selectedComponent?.type === 'node' && selectedComponent?.data?.name === node.name
                            const isReady = node.status === 'Ready'

                            return (
                              <g key={node.name} transform={`translate(8, ${nodeY})`}>
                                {/* Node Container */}
                                <rect
                                  x="0" y="0" width={azWidth - 26} height="138" rx="6"
                                  fill="url(#node-gradient)"
                                  stroke={isNodeSelected ? '#fff' : isReady ? '#475569' : '#eab308'}
                                  strokeWidth={isNodeSelected ? 2 : 1}
                                  className="cursor-pointer"
                                  onClick={() => onComponentSelect?.('node', env, node)}
                                />
                                {/* Node Header */}
                                <rect x="0" y="0" width={azWidth - 26} height="24" rx="6" fill={isReady ? '#334155' : '#854d0e'} />
                                <foreignObject x="6" y="4" width="16" height="16">
                                  <Server style={{ width: 16, height: 16, color: isReady ? '#22c55e' : '#eab308' }} />
                                </foreignObject>
                                <text x="28" y="16" fill="#e2e8f0" fontSize="11" fontWeight="bold" className="cursor-pointer" onClick={() => onComponentSelect?.('node', env, node)}>
                                  {node.name?.length > 25 ? node.name.substring(0, 25) + '...' : node.name}
                                </text>
                                <text x={azWidth - 36} y="16" fill="#6b7280" fontSize="10" textAnchor="end">{node.instanceType}</text>

                                {/* Resource Bars */}
                                <g transform="translate(8, 30)">
                                  {/* CPU Bar */}
                                  <g>
                                    <foreignObject x="0" y="0" width="12" height="12">
                                      <Cpu style={{ width: 12, height: 12, color: '#9ca3af' }} />
                                    </foreignObject>
                                    <text x="16" y="10" fill="#9ca3af" fontSize="9">CPU</text>
                                    <rect x="45" y="2" width="120" height="8" rx="2" fill="#1e293b" />
                                    <rect x="45" y="2" width={Math.min(cpuPercent, 100) * 1.2} height="8" rx="2" fill={cpuColor} />
                                    <text x="170" y="10" fill={cpuColor} fontSize="9" fontWeight="bold">{cpuPercent.toFixed(0)}%</text>
                                  </g>
                                  {/* Memory Bar */}
                                  <g transform="translate(0, 14)">
                                    <foreignObject x="0" y="0" width="12" height="12">
                                      <HardDrive style={{ width: 12, height: 12, color: '#9ca3af' }} />
                                    </foreignObject>
                                    <text x="16" y="10" fill="#9ca3af" fontSize="9">Mem</text>
                                    <rect x="45" y="2" width="120" height="8" rx="2" fill="#1e293b" />
                                    <rect x="45" y="2" width={Math.min(memPercent, 100) * 1.2} height="8" rx="2" fill={memColor} />
                                    <text x="170" y="10" fill={memColor} fontSize="9" fontWeight="bold">{memPercent.toFixed(0)}%</text>
                                  </g>
                                  {/* Pods count */}
                                  <text x="220" y="10" fill="#6b7280" fontSize="9">{node.podCount || 0}/{node.allocatablePods || '?'} pods</text>
                                </g>

                                {/* Pods in this node */}
                                <g transform="translate(8, 62)">
                                  {(!node.pods || node.pods.length === 0) ? (
                                    <text x="100" y="35" fill="#475569" fontSize="10" textAnchor="middle" fontStyle="italic">No pods data</text>
                                  ) : (
                                    node.pods.slice(0, 8).map((pod, podIndex) => {
                                      const podX = (podIndex % 4) * 118
                                      const podY = Math.floor(podIndex / 4) * 36
                                      const podColor = pod.status === 'Running' && pod.ready ? 'url(#task-new)' :
                                                       pod.status === 'Running' ? 'url(#task-old)' :
                                                       pod.status === 'Pending' ? 'url(#task-pending)' : '#ef4444'
                                      const borderColor = pod.status === 'Running' && pod.ready ? '#22c55e' :
                                                          pod.status === 'Running' ? '#f97316' :
                                                          pod.status === 'Pending' ? '#eab308' : '#ef4444'
                                      const isPodSelected = selectedComponent?.type === 'pod' && selectedComponent?.data?.name === pod.name

                                      return (
                                        <g key={pod.name || podIndex} transform={`translate(${podX}, ${podY})`} className="cursor-pointer" onClick={(e) => { e.stopPropagation(); onComponentSelect?.('pod', env, { ...pod, node: node.name }) }}>
                                          <rect
                                            x="0" y="0" width="114" height="32" rx="4"
                                            fill={podColor}
                                            stroke={isPodSelected ? '#fff' : borderColor}
                                            strokeWidth={isPodSelected ? 2 : 1}
                                          >
                                            {pod.status === 'Pending' && (
                                              <animate attributeName="opacity" values="0.6;1;0.6" dur="1s" repeatCount="indefinite" />
                                            )}
                                          </rect>
                                          <text x="57" y="13" fill="white" fontSize="9" textAnchor="middle" fontWeight="bold" style={{ textShadow: '0 1px 2px rgba(0,0,0,0.5)' }}>
                                            {pod.name?.length > 16 ? pod.name.substring(0, 16) + '...' : pod.name}
                                          </text>
                                          <text x="57" y="25" fill="rgba(255,255,255,0.8)" fontSize="8" textAnchor="middle">
                                            {pod.component || pod.namespace}
                                            {pod.restarts > 0 && <tspan fill="#fbbf24"> ({pod.restarts}r)</tspan>}
                                          </text>
                                        </g>
                                      )
                                    })
                                  )}
                                  {node.pods && node.pods.length > 8 && (
                                    <text x="230" y="60" fill="#6b7280" fontSize="9">+{node.pods.length - 8} more</text>
                                  )}
                                </g>
                              </g>
                            )
                          })
                        )}
                      </>
                    )}

                    {/* ECS: Services and Tasks */}
                    {!isEKS && (
                      <>
                        {effectiveServices.map((svc, svcIndex) => {
                          const service = services?.[svc]
                          const infraService = data?.services?.[svc]
                          const svcData = infraService || service
                          const tasksInAz = svcData?.tasksByAz?.[az] || []
                          const isRolling = svcData?.isRollingUpdate
                          const yPos = 25 + svcIndex * 90

                          return (
                            <g key={svc} transform={`translate(8, ${yPos})`}>
                              {/* Service Label */}
                              <rect x="0" y="0" width="95" height="80" rx="5" fill="#1e293b" stroke="#475569" strokeWidth="1" className="cursor-pointer" onClick={() => onComponentSelect?.('service', env, svcData)} />
                              <text x="48" y="20" fill="#e2e8f0" fontSize="13" textAnchor="middle" fontWeight="bold" className="capitalize">{svc}</text>
                              {isRolling && (
                                <text x="48" y="36" fill="#fbbf24" fontSize="10" textAnchor="middle">
                                  <tspan>Rolling Update</tspan>
                                  <animate attributeName="opacity" values="1;0.5;1" dur="1s" repeatCount="indefinite" />
                                </text>
                              )}
                              <text x="48" y={isRolling ? 52 : 40} fill="#9ca3af" fontSize="12" textAnchor="middle">
                                {svcData?.runningCount || 0}/{svcData?.desiredCount || 0} tasks
                              </text>
                              <text x="48" y={isRolling ? 68 : 58} fill="#6b7280" fontSize="11" textAnchor="middle">
                                rev {svcData?.currentRevision || '?'}
                              </text>

                              {/* Tasks in this AZ */}
                              <g transform="translate(105, 0)">
                                {tasksInAz.length === 0 ? (
                                  <text x="120" y="42" fill="#475569" fontSize="12" textAnchor="middle" fontStyle="italic">No task in this AZ</text>
                                ) : (
                                  tasksInAz.map((task, taskIndex) => {
                                    const taskX = (taskIndex % 5) * 78
                                    const taskY = Math.floor(taskIndex / 5) * 45
                                    const taskColor = task.status === 'PENDING' ? 'url(#task-pending)' :
                                                      task.isLatest ? 'url(#task-new)' : 'url(#task-old)'
                                    const borderColor = task.status === 'PENDING' ? '#eab308' :
                                                        task.isLatest ? '#22c55e' : '#f97316'
                                    const isTaskSelected = selectedComponent?.type === 'task' && selectedComponent?.data?.taskId === task.taskId

                                    return (
                                      <g key={task.taskId} transform={`translate(${taskX}, ${taskY})`} className="cursor-pointer" onClick={(e) => { e.stopPropagation(); onComponentSelect?.('task', env, { ...task, service: svc, serviceName: svcData?.name }) }}>
                                        <rect
                                          x="0" y="0" width="74" height="42" rx="5"
                                          fill={taskColor}
                                          stroke={isTaskSelected ? '#fff' : borderColor}
                                          strokeWidth={isTaskSelected ? 2 : 1}
                                          opacity={task.status === 'PENDING' ? 0.8 : 1}
                                        >
                                          {task.status === 'PENDING' && (
                                            <animate attributeName="opacity" values="0.6;1;0.6" dur="1s" repeatCount="indefinite" />
                                          )}
                                          {!task.isLatest && task.status === 'RUNNING' && (
                                            <animate attributeName="opacity" values="1;0.5;1" dur="2s" repeatCount="indefinite" />
                                          )}
                                        </rect>
                                        <text x="37" y="18" fill="white" fontSize="11" textAnchor="middle" fontWeight="bold" style={{ textShadow: '0 1px 2px rgba(0,0,0,0.5)' }}>
                                          {task.taskId}
                                        </text>
                                        <text x="37" y="34" fill="rgba(255,255,255,0.9)" fontSize="10" textAnchor="middle">
                                          {task.status === 'PENDING' ? 'STARTING...' : task.health === 'HEALTHY' ? 'HEALTHY' : task.isLatest ? 'NEW' : 'DRAINING'}
                                        </text>
                                      </g>
                                    )
                                  })
                                )}
                              </g>
                            </g>
                          )
                        })}
                      </>
                    )}
                  </g>

                  {/* Database Subnet Layer */}
                  <g transform="translate(5, 500)">
                    <rect x="0" y="0" width={azWidth - 10} height="140" rx="6" fill="#3b0764" stroke="#a855f7" strokeWidth="1" strokeOpacity="0.5" />
                    <text x="10" y="20" fill="#c084fc" fontSize="13" fontWeight="bold">Database Subnet</text>
                    <text x={azWidth - 20} y="20" fill="#c084fc" fontSize="12" textAnchor="end">{network?.subnetsByAz?.[az]?.find(s => s.type === 'database')?.cidr || ''}</text>

                    {/* RDS - show only in its actual AZ, or both if Multi-AZ */}
                    {rds && !rds.error && (rds.multiAz || rds.availabilityZone === az) && (
                      <g transform="translate(10, 28)" className="cursor-pointer" onClick={() => onComponentSelect?.('rds', env, rds)}>
                        <rect x="0" y="0" width="170" height="95" rx="6" fill={isSelected('rds') ? '#1e3a5f' : '#1e293b'} stroke="#06b6d4" strokeWidth={isSelected('rds') ? 3 : 2} />
                        <rect x="0" y="0" width="170" height="22" rx="6" fill="#06b6d4" />
                        <text x="85" y="16" fill="white" fontSize="11" textAnchor="middle" fontWeight="bold">{rds.engine?.includes('aurora') ? 'Aurora' : 'RDS'} {rds.engine?.includes('postgres') ? 'PostgreSQL' : rds.engine?.includes('mysql') ? 'MySQL' : ''}</text>
                        <foreignObject x="65" y="26" width="40" height="40">
                          <AwsRDS style={{ width: 40, height: 40 }} />
                        </foreignObject>
                        <text x="50" y="82" fill="#67e8f9" fontSize="10" textAnchor="middle">{rds.multiAz ? 'Multi-AZ' : 'Single-AZ'}</text>
                        <text x="125" y="82" fill={rds.status === 'available' ? '#4ade80' : '#fbbf24'} fontSize="10" textAnchor="middle" fontWeight="500">{rds.status}</text>
                      </g>
                    )}

                    {/* Redis - show only in its actual AZ */}
                    {redis && !redis.error && redis.preferredAvailabilityZone === az && (
                      <g transform={`translate(${(rds && (rds.multiAz || rds.availabilityZone === az)) ? 190 : 10}, 28)`} className="cursor-pointer" onClick={() => onComponentSelect?.('redis', env, redis)}>
                        <rect x="0" y="0" width="170" height="95" rx="6" fill={isSelected('redis') ? '#1e3a5f' : '#1e293b'} stroke="#ef4444" strokeWidth={isSelected('redis') ? 3 : 2} />
                        <rect x="0" y="0" width="170" height="22" rx="6" fill="#ef4444" />
                        <text x="85" y="16" fill="white" fontSize="11" textAnchor="middle" fontWeight="bold">Redis Cache</text>
                        <foreignObject x="65" y="26" width="40" height="40">
                          <AwsElastiCache style={{ width: 40, height: 40 }} />
                        </foreignObject>
                        <text x="50" y="82" fill="#fca5a5" fontSize="10" textAnchor="middle">{redis.numCacheNodes} node(s)</text>
                        <text x="125" y="82" fill={redis.status === 'available' ? '#4ade80' : '#fbbf24'} fontSize="10" textAnchor="middle" fontWeight="500">{redis.status}</text>
                      </g>
                    )}
                  </g>
                </g>
              )
            })
          })()}

          {/* ALB - Spanning both Public Subnets - enlarged for better visibility */}
          {alb && (
            <g transform="translate(20, 108)">
              <rect x="0" y="0" width="1090" height="48" rx="6" fill={isSelected('alb') ? '#1e3a5f' : '#1e293b'} stroke={alb.state === 'active' ? '#3b82f6' : '#fbbf24'} strokeWidth={isSelected('alb') ? 3 : 2} className="cursor-pointer" onClick={() => onComponentSelect?.('alb', env, alb)} />
              <foreignObject x="10" y="8" width="32" height="32" className="cursor-pointer" onClick={() => onComponentSelect?.('alb', env, alb)}>
                <AwsALB style={{ width: 32, height: 32 }} />
              </foreignObject>
              <text x="545" y="22" fill="white" fontSize="14" textAnchor="middle" fontWeight="bold" className="cursor-pointer" onClick={() => onComponentSelect?.('alb', env, alb)}>Application Load Balancer (Multi-AZ)</text>
              <text x="545" y="40" fill={alb.state === 'active' ? '#4ade80' : '#fbbf24'} fontSize="12" textAnchor="middle" className="cursor-pointer" onClick={() => onComponentSelect?.('alb', env, alb)}>{alb.name} • {alb.state}</text>

              {/* Target Group Badges */}
              {alb.targetGroups?.map((tg, idx) => {
                const health = tg?.health?.status
                const healthColor = health === 'healthy' ? '#22c55e' : health === 'unhealthy' ? '#ef4444' : '#fbbf24'
                const svcColor = serviceColors[tg.service] || '#6b7280'
                const xPos = 800 + idx * 95

                return (
                  <g key={idx} transform={`translate(${xPos}, 10)`}>
                    <rect x="0" y="0" width="90" height="28" rx="4" fill="#0f172a" stroke={svcColor} strokeWidth="1.5" />
                    <circle cx="16" cy="14" r="6" fill={healthColor}>
                      {health !== 'healthy' && (
                        <animate attributeName="opacity" values="1;0.5;1" dur="1s" repeatCount="indefinite" />
                      )}
                    </circle>
                    <text x="54" y="18" fill={svcColor} fontSize="11" textAnchor="middle" fontWeight="bold">{tg.service}</text>
                  </g>
                )
              })}
            </g>
          )}

          {/* ALB to Task flow lines (ECS only) */}
          {!isEKS && alb && showAlbFlows && (() => {
            const azs = network?.availabilityZones || getDefaultAzs()
            const azWidth = 515
            const azGap = 20
            const flows = []

            alb.targetGroups?.forEach((tg, tgIndex) => {
              const svc = tg.service
              const svcIndex = effectiveServices.indexOf(svc)
              if (svcIndex === -1) return

              const health = tg?.health?.status
              const healthColor = health === 'healthy' ? '#22c55e' : health === 'unhealthy' ? '#ef4444' : '#fbbf24'
              const svcColor = serviceColors[svc]
              const yPos = 25 + svcIndex * 90

              const badgeX = 20 + 750 + tgIndex * 90 + 42
              const badgeY = 100 + 8 + 24

              azs.forEach((az, azIndex) => {
                const svcData = services?.[svc]
                const tasksInAz = svcData?.tasksByAz?.[az] || []
                if (tasksInAz.length === 0) return

                const azX = 10 + azIndex * (azWidth + azGap)

                tasksInAz.forEach((task, taskIndex) => {
                  const taskX = (taskIndex % 5) * 78
                  const taskCenterX = azX + 5 + 8 + 105 + taskX + 37
                  const taskCenterY = 42 + 125 + yPos + 21

                  flows.push(
                    <g key={`${svc}-${az}-${taskIndex}`}>
                      <path
                        d={`M ${badgeX} ${badgeY} C ${badgeX} ${badgeY + 30}, ${taskCenterX} ${taskCenterY - 30}, ${taskCenterX} ${taskCenterY}`}
                        fill="none"
                        stroke={svcColor}
                        strokeWidth="2"
                        strokeOpacity="0.6"
                        strokeDasharray="4 2"
                      />
                      <circle cx={taskCenterX} cy={taskCenterY} r="4" fill={healthColor} />
                    </g>
                  )
                })
              })
            })

            return <g>{flows}</g>
          })()}
        </g>

        {/* Traffic Flow Arrows */}
        {hasCloudFront ? (
          <>
            <path d="M 90 115 L 115 195" fill="none" stroke="#6b7280" strokeWidth="1.5" strokeDasharray="4" markerEnd="url(#arrowhead)" />
            <path d="M 190 200 L 240 200 L 265 145" fill="none" stroke={`url(#flow-${env})`} strokeWidth="2" />
            <path d="M 190 200 L 240 200 L 265 145" fill="none" stroke="#6b7280" strokeWidth="1.5" strokeDasharray="4" markerEnd="url(#arrowhead)" />
            {hasS3 && <path d="M 115 260 L 115 310" fill="none" stroke="#a855f7" strokeWidth="1.5" strokeDasharray="4" markerEnd="url(#arrowhead)" />}
          </>
        ) : (
          <path d="M 90 115 L 265 145" fill="none" stroke="#6b7280" strokeWidth="1.5" strokeDasharray="4" markerEnd="url(#arrowhead)" />
        )}

      </svg>

      {/* Legend and Controls - enlarged for better visibility */}
      <div className="flex items-start gap-5 mt-4 px-3">
        {/* Legend */}
        <div className="bg-gray-800 rounded-lg border border-gray-700 p-4">
          <div className="text-gray-400 text-sm font-bold mb-3 text-center">{isEKS ? 'Pod' : 'Task'} Legend</div>
          <div className="flex flex-col gap-2">
            <div className="flex items-center gap-3">
              <div className="w-10 h-5 rounded bg-gradient-to-br from-green-500 to-green-600"></div>
              <span className="text-gray-400 text-sm">{isEKS ? 'Running & Ready' : 'New (latest revision)'}</span>
            </div>
            <div className="flex items-center gap-3">
              <div className="w-10 h-5 rounded bg-gradient-to-br from-orange-500 to-orange-600"></div>
              <span className="text-gray-400 text-sm">{isEKS ? 'Running (not ready)' : 'Old (draining)'}</span>
            </div>
            <div className="flex items-center gap-3">
              <div className="w-10 h-5 rounded bg-gradient-to-br from-yellow-500 to-yellow-600 animate-pulse"></div>
              <span className="text-gray-400 text-sm">{isEKS ? 'Pending' : 'Starting'}</span>
            </div>
          </div>
        </div>

        {/* EKS: Node utilization legend */}
        {isEKS && (
          <div className="bg-gray-800 rounded-lg border border-gray-700 p-4">
            <div className="text-gray-400 text-sm font-bold mb-3 text-center">Utilization</div>
            <div className="flex flex-col gap-2">
              <div className="flex items-center gap-3">
                <div className="w-10 h-4 rounded bg-green-500"></div>
                <span className="text-gray-400 text-sm">&lt; 75%</span>
              </div>
              <div className="flex items-center gap-3">
                <div className="w-10 h-4 rounded bg-yellow-500"></div>
                <span className="text-gray-400 text-sm">75-90%</span>
              </div>
              <div className="flex items-center gap-3">
                <div className="w-10 h-4 rounded bg-red-500"></div>
                <span className="text-gray-400 text-sm">&gt; 90%</span>
              </div>
            </div>
          </div>
        )}

        {/* ALB Flows Toggle (ECS only) */}
        {!isEKS && (
          <button
            onClick={() => setShowAlbFlows(!showAlbFlows)}
            className={`bg-gray-800 rounded-lg border px-4 py-2.5 flex items-center gap-3 transition-colors ${showAlbFlows ? 'border-blue-500' : 'border-gray-700'}`}
          >
            <div className={`w-10 h-5 rounded-full relative ${showAlbFlows ? 'bg-blue-500' : 'bg-gray-600'}`}>
              <div className={`absolute w-4 h-4 rounded-full bg-white top-0.5 transition-all ${showAlbFlows ? 'left-5' : 'left-0.5'}`}></div>
            </div>
            <span className={`text-sm ${showAlbFlows ? 'text-blue-400' : 'text-gray-400'}`}>Show ALB traffic flows</span>
          </button>
        )}
      </div>
    </div>
  )
}
