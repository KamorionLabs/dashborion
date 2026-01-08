import { useState } from 'react'
import AwsCloudFront from 'aws-react-icons/lib/icons/ArchitectureServiceAmazonCloudFront'
import AwsS3 from 'aws-react-icons/lib/icons/ArchitectureServiceAmazonSimpleStorageService'
import AwsALB from 'aws-react-icons/lib/icons/ArchitectureServiceElasticLoadBalancing'
import AwsRDS from 'aws-react-icons/lib/icons/ArchitectureServiceAmazonRDS'
import AwsElastiCache from 'aws-react-icons/lib/icons/ArchitectureServiceAmazonElastiCache'

/**
 * Detailed network architecture diagram with VPC, subnets, AZs and tasks
 */
export default function NetworkView({
  env,
  data,
  services: envServices,
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

  // Determine which infrastructure components exist
  const hasCloudFront = cloudfront !== null && cloudfront !== undefined
  const hasS3 = s3Buckets && s3Buckets.length > 0

  // Get S3 buckets by type
  const frontendBucket = s3Buckets?.find(b => b.type === 'frontend')
  const assetsBucket = s3Buckets?.find(b => b.type === 'cms-public' || b.type === 'assets')

  // Helper to check if component is selected
  const isSelected = (type) => selectedComponent?.type === type && selectedComponent?.env === env

  return (
    <div className="p-4 relative overflow-x-auto">
      <svg viewBox="0 0 1300 750" className="w-full h-auto min-w-[1100px]" style={{ minHeight: '700px' }}>
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
          {/* Task status gradients */}
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
        </defs>

        {/* Internet Zone (outside VPC) */}
        <g transform="translate(10, 10)">
          <rect x="0" y="0" width="210" height={hasCloudFront || hasS3 ? 420 : 150} rx="8" fill="#1e293b" stroke="#475569" strokeWidth="1" strokeDasharray="4" />
          <text x="105" y="28" fill="#94a3b8" fontSize="15" textAnchor="middle" fontWeight="bold">Internet</text>

          {/* Users */}
          <g transform="translate(42, 55)">
            <circle cx="28" cy="28" r="28" fill="#334155" stroke="#64748b" strokeWidth="2" />
            <circle cx="28" cy="18" r="9" fill="#94a3b8" />
            <path d="M 28 30 L 28 46 M 16 38 L 40 38 M 28 46 L 18 60 M 28 46 L 38 60" stroke="#94a3b8" strokeWidth="2.5" fill="none" />
            <text x="28" y="80" fill="#94a3b8" fontSize="12" textAnchor="middle">Users</text>
          </g>

          {/* CloudFront - only if exists */}
          {hasCloudFront && (
            <g transform="translate(25, 155)" className="cursor-pointer" onClick={() => onComponentSelect?.('cloudfront', env, cloudfront)}>
              <rect x="0" y="0" width="160" height="110" rx="8" fill={isSelected('cloudfront') ? '#334155' : '#1f2937'} stroke={isSelected('cloudfront') ? '#f97316' : '#f97316'} strokeWidth={isSelected('cloudfront') ? 3 : 2} />
              <rect x="0" y="0" width="160" height="28" rx="8" fill="#f97316" />
              <text x="80" y="19" fill="white" fontSize="14" textAnchor="middle" fontWeight="bold">CloudFront</text>
              <foreignObject x="60" y="34" width="40" height="40">
                <AwsCloudFront style={{ width: 40, height: 40 }} />
              </foreignObject>
              <text x="80" y="88" fill="#9ca3af" fontSize="11" textAnchor="middle">{cloudfront?.id}</text>
              <text x="80" y="103" fill={cloudfront?.status === 'Deployed' ? '#4ade80' : '#fbbf24'} fontSize="12" textAnchor="middle" fontWeight="500">{cloudfront?.status || 'Loading...'}</text>
            </g>
          )}

          {/* S3 - only if exists */}
          {hasS3 && (
            <g transform="translate(25, 285)" className="cursor-pointer" onClick={() => onComponentSelect?.('s3', env, s3Buckets)}>
              <rect x="0" y="0" width="160" height="115" rx="8" fill={isSelected('s3') ? '#334155' : '#1f2937'} stroke="#a855f7" strokeWidth={isSelected('s3') ? 3 : 2} />
              <rect x="0" y="0" width="160" height="28" rx="8" fill="#a855f7" />
              <text x="80" y="19" fill="white" fontSize="14" textAnchor="middle" fontWeight="bold">S3 Buckets</text>
              <foreignObject x="60" y="34" width="40" height="40">
                <AwsS3 style={{ width: 40, height: 40 }} />
              </foreignObject>
              <text x="80" y="90" fill="#9ca3af" fontSize="11" textAnchor="middle">{frontendBucket?.name?.split('-').slice(-3).join('-') || 'frontend'}</text>
              <text x="80" y="106" fill="#9ca3af" fontSize="11" textAnchor="middle">{assetsBucket?.name?.split('-').slice(-3).join('-') || 'assets'}</text>
            </g>
          )}
        </g>

        {/* VPC Container */}
        <g transform="translate(230, 10)">
          <rect x="0" y="0" width="1060" height="730" rx="10" fill="none" stroke="#3b82f6" strokeWidth="2" />
          <rect x="0" y="0" width="1060" height="32" rx="10" fill="#1e3a5f" />
          <text x="20" y="22" fill="#60a5fa" fontSize="15" fontWeight="bold">VPC: {network?.vpcName || (appConfig?.serviceNaming?.prefix || 'app') + '-' + env}</text>
          <text x="1050" y="22" fill="#93c5fd" fontSize="13" textAnchor="end">{network?.cidr || '10.x.0.0/16'}</text>

          {/* AZ Columns */}
          {(() => {
            const azs = network?.availabilityZones || getDefaultAzs()
            const azWidth = 515
            const azGap = 20

            return azs.map((az, azIndex) => {
              const azX = 10 + azIndex * (azWidth + azGap)

              return (
                <g key={az} transform={`translate(${azX}, 42)`}>
                  {/* AZ Container */}
                  <rect x="0" y="0" width={azWidth} height="680" rx="8" fill="#0f172a" stroke="#334155" strokeWidth="1" />
                  <rect x="0" y="0" width={azWidth} height="28" rx="8" fill="#1e293b" />
                  <text x={azWidth/2} y="19" fill="#94a3b8" fontSize="13" textAnchor="middle" fontWeight="bold">{az}</text>

                  {/* Public Subnet Layer - for ALB */}
                  <g transform="translate(5, 35)">
                    <rect x="0" y="0" width={azWidth - 10} height="80" rx="6" fill="#052e16" stroke="#22c55e" strokeWidth="1" strokeOpacity="0.5" />
                    <text x="10" y="18" fill="#4ade80" fontSize="12" fontWeight="bold">Public Subnet</text>
                    <text x={azWidth - 20} y="18" fill="#4ade80" fontSize="11" textAnchor="end">{network?.subnetsByAz?.[az]?.find(s => s.type === 'public')?.cidr || ''}</text>
                  </g>

                  {/* Private Subnet Layer - ECS Tasks */}
                  <g transform="translate(5, 125)">
                    <rect x="0" y="0" width={azWidth - 10} height="320" rx="6" fill="#172554" stroke="#3b82f6" strokeWidth="1" strokeOpacity="0.5" />
                    <text x="10" y="18" fill="#60a5fa" fontSize="12" fontWeight="bold">Private Subnet (ECS)</text>
                    <text x={azWidth - 20} y="18" fill="#60a5fa" fontSize="11" textAnchor="end">{network?.subnetsByAz?.[az]?.find(s => s.type === 'private')?.cidr || ''}</text>

                    {/* Services and Tasks */}
                    {SERVICES.map((svc, svcIndex) => {
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
                  </g>

                  {/* Database Subnet Layer */}
                  <g transform="translate(5, 455)">
                    <rect x="0" y="0" width={azWidth - 10} height="130" rx="6" fill="#3b0764" stroke="#a855f7" strokeWidth="1" strokeOpacity="0.5" />
                    <text x="10" y="18" fill="#c084fc" fontSize="12" fontWeight="bold">Database Subnet</text>
                    <text x={azWidth - 20} y="18" fill="#c084fc" fontSize="11" textAnchor="end">{network?.subnetsByAz?.[az]?.find(s => s.type === 'database')?.cidr || ''}</text>

                    {/* RDS - show only in its actual AZ, or both if Multi-AZ */}
                    {rds && !rds.error && (rds.multiAz || rds.availabilityZone === az) && (
                      <g transform="translate(10, 28)" className="cursor-pointer" onClick={() => onComponentSelect?.('rds', env, rds)}>
                        <rect x="0" y="0" width="170" height="95" rx="6" fill={isSelected('rds') ? '#1e3a5f' : '#1e293b'} stroke="#06b6d4" strokeWidth={isSelected('rds') ? 3 : 2} />
                        <rect x="0" y="0" width="170" height="22" rx="6" fill="#06b6d4" />
                        <text x="85" y="16" fill="white" fontSize="11" textAnchor="middle" fontWeight="bold">RDS PostgreSQL</text>
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

          {/* ALB - Spanning both Public Subnets */}
          {alb && (
            <g transform="translate(20, 100)">
              <rect x="0" y="0" width="1020" height="40" rx="6" fill={isSelected('alb') ? '#1e3a5f' : '#1e293b'} stroke={alb.state === 'active' ? '#3b82f6' : '#fbbf24'} strokeWidth={isSelected('alb') ? 3 : 2} className="cursor-pointer" onClick={() => onComponentSelect?.('alb', env, alb)} />
              <foreignObject x="8" y="6" width="28" height="28" className="cursor-pointer" onClick={() => onComponentSelect?.('alb', env, alb)}>
                <AwsALB style={{ width: 28, height: 28 }} />
              </foreignObject>
              <text x="510" y="18" fill="white" fontSize="12" textAnchor="middle" fontWeight="bold" className="cursor-pointer" onClick={() => onComponentSelect?.('alb', env, alb)}>Application Load Balancer (Multi-AZ)</text>
              <text x="510" y="33" fill={alb.state === 'active' ? '#4ade80' : '#fbbf24'} fontSize="11" textAnchor="middle" className="cursor-pointer" onClick={() => onComponentSelect?.('alb', env, alb)}>{alb.name} • {alb.state}</text>

              {/* Target Group Badges */}
              {alb.targetGroups?.map((tg, idx) => {
                const health = tg?.health?.status
                const healthColor = health === 'healthy' ? '#22c55e' : health === 'unhealthy' ? '#ef4444' : '#fbbf24'
                const svcColor = serviceColors[tg.service] || '#6b7280'
                const xPos = 750 + idx * 90

                return (
                  <g key={idx} transform={`translate(${xPos}, 8)`}>
                    <rect x="0" y="0" width="85" height="24" rx="4" fill="#0f172a" stroke={svcColor} strokeWidth="1.5" />
                    <circle cx="14" cy="12" r="5" fill={healthColor}>
                      {health !== 'healthy' && (
                        <animate attributeName="opacity" values="1;0.5;1" dur="1s" repeatCount="indefinite" />
                      )}
                    </circle>
                    <text x="50" y="16" fill={svcColor} fontSize="10" textAnchor="middle" fontWeight="bold">{tg.service}</text>
                  </g>
                )
              })}
            </g>
          )}

          {/* ALB to Task flow lines */}
          {alb && showAlbFlows && (() => {
            const azs = network?.availabilityZones || getDefaultAzs()
            const azWidth = 515
            const azGap = 20
            const flows = []

            alb.targetGroups?.forEach((tg, tgIndex) => {
              const svc = tg.service
              const svcIndex = SERVICES.indexOf(svc)
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
            <path d="M 80 100 L 100 180" fill="none" stroke="#6b7280" strokeWidth="1" strokeDasharray="4" markerEnd="url(#arrowhead)" />
            <path d="M 170 185 L 220 185 L 245 130" fill="none" stroke={`url(#flow-${env})`} strokeWidth="2" />
            <path d="M 170 185 L 220 185 L 245 130" fill="none" stroke="#6b7280" strokeWidth="1" strokeDasharray="4" markerEnd="url(#arrowhead)" />
            {hasS3 && <path d="M 100 230 L 100 285" fill="none" stroke="#a855f7" strokeWidth="1" strokeDasharray="4" markerEnd="url(#arrowhead)" />}
          </>
        ) : (
          <path d="M 80 100 L 245 130" fill="none" stroke="#6b7280" strokeWidth="1" strokeDasharray="4" markerEnd="url(#arrowhead)" />
        )}

      </svg>

      {/* Legend and Controls */}
      <div className="flex items-start gap-4 mt-3 px-2">
        {/* Task Legend */}
        <div className="bg-gray-800 rounded-lg border border-gray-700 p-3">
          <div className="text-gray-400 text-xs font-bold mb-2 text-center">Task Legend</div>
          <div className="flex flex-col gap-1.5">
            <div className="flex items-center gap-2">
              <div className="w-8 h-4 rounded bg-gradient-to-br from-green-500 to-green-600"></div>
              <span className="text-gray-400 text-xs">New (latest revision)</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-8 h-4 rounded bg-gradient-to-br from-orange-500 to-orange-600"></div>
              <span className="text-gray-400 text-xs">Old (draining)</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-8 h-4 rounded bg-gradient-to-br from-yellow-500 to-yellow-600 animate-pulse"></div>
              <span className="text-gray-400 text-xs">Starting</span>
            </div>
          </div>
        </div>

        {/* ALB Flows Toggle */}
        <button
          onClick={() => setShowAlbFlows(!showAlbFlows)}
          className={`bg-gray-800 rounded-lg border px-3 py-2 flex items-center gap-2 transition-colors ${showAlbFlows ? 'border-blue-500' : 'border-gray-700'}`}
        >
          <div className={`w-8 h-4 rounded-full relative ${showAlbFlows ? 'bg-blue-500' : 'bg-gray-600'}`}>
            <div className={`absolute w-3 h-3 rounded-full bg-white top-0.5 transition-all ${showAlbFlows ? 'left-4' : 'left-0.5'}`}></div>
          </div>
          <span className={`text-xs ${showAlbFlows ? 'text-blue-400' : 'text-gray-400'}`}>Show ALB traffic flows</span>
        </button>
      </div>
    </div>
  )
}
