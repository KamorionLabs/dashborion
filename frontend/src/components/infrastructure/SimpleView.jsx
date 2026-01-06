import AwsCloudFront from 'aws-react-icons/lib/icons/ArchitectureServiceAmazonCloudFront'
import AwsS3 from 'aws-react-icons/lib/icons/ArchitectureServiceAmazonSimpleStorageService'
import AwsALB from 'aws-react-icons/lib/icons/ArchitectureServiceElasticLoadBalancing'
import AwsRDS from 'aws-react-icons/lib/icons/ArchitectureServiceAmazonRDS'
import AwsElastiCache from 'aws-react-icons/lib/icons/ArchitectureServiceAmazonElastiCache'

/**
 * Simple infrastructure flow diagram (Users -> CloudFront -> ALB -> ECS -> Data)
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
  domains
}) {
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
    <div className="p-4">
      <svg viewBox="0 0 1150 380" className="w-full h-auto" style={{ minHeight: '360px' }}>
        <defs>
          <marker id={`arrow-${env}`} markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
            <polygon points="0 0, 10 3.5, 0 7" fill="#6b7280" />
          </marker>
        </defs>

        {/* Users */}
        <g transform={hasCloudFront ? "translate(15, 130)" : "translate(15, 200)"}>
          <circle cx="30" cy="30" r="28" fill="#334155" stroke="#64748b" strokeWidth="2" />
          <circle cx="30" cy="22" r="9" fill="#94a3b8" />
          <path d="M 30 33 L 30 48 M 20 40 L 40 40 M 30 48 L 22 60 M 30 48 L 38 60" stroke="#94a3b8" strokeWidth="2.5" fill="none" />
          <text x="30" y="78" fill="#94a3b8" fontSize="12" textAnchor="middle">Users</text>
        </g>

        {hasCloudFront ? (
          <>
            {/* Arrow Users -> CloudFront */}
            <line x1="75" y1="160" x2="120" y2="160" stroke="#6b7280" strokeWidth="2" markerEnd={`url(#arrow-${env})`} />

            {/* CloudFront */}
            <g transform="translate(130, 95)" className="cursor-pointer" onClick={() => onComponentSelect?.('cloudfront', env, cloudfront)}>
              <rect x="0" y="0" width="140" height="130" rx="10" fill={isSelected('cloudfront') ? '#334155' : '#1f2937'} stroke="#f97316" strokeWidth={isSelected('cloudfront') ? 3 : 2} />
              <rect x="0" y="0" width="140" height="28" rx="10" fill="#f97316" />
              <text x="70" y="19" fill="white" fontSize="13" textAnchor="middle" fontWeight="bold">CloudFront</text>
              <foreignObject x="50" y="34" width="40" height="40">
                <AwsCloudFront style={{ width: 40, height: 40 }} />
              </foreignObject>
              <text x="70" y="90" fill={cloudfront?.status === 'Deployed' ? '#4ade80' : '#fbbf24'} fontSize="12" textAnchor="middle" fontWeight="500">{cloudfront?.status || 'Loading...'}</text>
              <text x="70" y="108" fill="#6b7280" fontSize="10" textAnchor="middle">{cloudfront?.id?.substring(0, 14)}</text>
              <text x="70" y="122" fill="#6b7280" fontSize="9" textAnchor="middle">{domains?.frontend?.replace('https://', '')?.substring(0, 20)}</text>
            </g>

            {/* Arrows CloudFront -> Origins */}
            {hasS3 && <path d="M 270 130 Q 320 130, 360 80" stroke="#6b7280" strokeWidth="2" fill="none" markerEnd={`url(#arrow-${env})`} />}
            <path d="M 270 190 Q 320 190, 360 250" stroke="#6b7280" strokeWidth="2" fill="none" markerEnd={`url(#arrow-${env})`} />

            {/* S3 Origin - only if S3 exists */}
            {hasS3 && (
              <g transform="translate(370, 20)" className="cursor-pointer" onClick={() => onComponentSelect?.('s3', env, s3Buckets)}>
                <rect x="0" y="0" width="130" height="105" rx="10" fill={isSelected('s3') ? '#334155' : '#1f2937'} stroke="#a855f7" strokeWidth={isSelected('s3') ? 3 : 2} />
                <rect x="0" y="0" width="130" height="26" rx="10" fill="#a855f7" />
                <text x="65" y="18" fill="white" fontSize="12" textAnchor="middle" fontWeight="bold">S3 Buckets</text>
                <foreignObject x="45" y="30" width="40" height="40">
                  <AwsS3 style={{ width: 40, height: 40 }} />
                </foreignObject>
                <text x="65" y="85" fill="#9ca3af" fontSize="10" textAnchor="middle">Frontend</text>
                <text x="65" y="98" fill="#9ca3af" fontSize="10" textAnchor="middle">Assets</text>
              </g>
            )}
          </>
        ) : (
          /* Arrow Users -> ALB directly (no CloudFront) */
          <line x1="75" y1="230" x2="360" y2="230" stroke="#6b7280" strokeWidth="2" markerEnd={`url(#arrow-${env})`} />
        )}

        {/* ALB Origin */}
        <g transform={hasCloudFront ? "translate(370, 210)" : "translate(370, 180)"} className="cursor-pointer" onClick={() => onComponentSelect?.('alb', env, alb)}>
          <rect x="0" y="0" width="130" height="105" rx="10" fill={isSelected('alb') ? '#334155' : '#1f2937'} stroke="#3b82f6" strokeWidth={isSelected('alb') ? 3 : 2} />
          <rect x="0" y="0" width="130" height="26" rx="10" fill="#3b82f6" />
          <text x="65" y="18" fill="white" fontSize="12" textAnchor="middle" fontWeight="bold">Load Balancer</text>
          <foreignObject x="45" y="30" width="40" height="40">
            <AwsALB style={{ width: 40, height: 40 }} />
          </foreignObject>
          <text x="65" y="85" fill={alb?.status === 'active' ? '#4ade80' : '#9ca3af'} fontSize="11" textAnchor="middle" fontWeight="500">{alb?.status || 'active'}</text>
          <text x="65" y="98" fill="#6b7280" fontSize="9" textAnchor="middle">{alb?.targetGroups?.length || 0} targets</text>
        </g>

        {/* Arrow ALB -> Services */}
        <line x1="500" y1={hasCloudFront ? "262" : "232"} x2="540" y2="190" stroke="#6b7280" strokeWidth="2" markerEnd={`url(#arrow-${env})`} />

        {/* ECS Services */}
        <g transform="translate(550, 10)">
          <rect x="0" y="0" width="300" height="360" rx="10" fill="#1e293b" stroke="#10b981" strokeWidth="2" />
          <rect x="0" y="0" width="300" height="28" rx="10" fill="#10b981" />
          <text x="150" y="19" fill="white" fontSize="13" textAnchor="middle" fontWeight="bold">ECS Services</text>

          {/* Service boxes - clickable */}
          {SERVICES.map((svc, idx) => {
            // Prefer envServices (has taskDefinition), fallback to data.services (has currentRevision)
            const svcFromEnv = envServices?.services?.[svc]
            const svcFromData = services?.[svc]
            const service = svcFromEnv || svcFromData
            if (!service) return null
            const tg = alb?.targetGroups?.find(t => t.service === svc)
            const health = tg?.health?.status || service?.health || 'UNKNOWN'
            const isHealthy = health === 'healthy' || health === 'HEALTHY'
            const svcColor = serviceColors[svc]
            // Get revision from either source
            const revision = svcFromEnv?.taskDefinition || svcFromData?.currentRevision || '?'
            const image = svcFromEnv?.image || 'latest'
            // Merge service data with name for proper panel handling
            const serviceWithName = { ...service, name: svcFromData?.name || getServiceName(env, svc) }

            return (
              <g key={svc} transform={`translate(12, ${38 + idx * 108})`} className="cursor-pointer" onClick={() => onComponentSelect?.('service', env, serviceWithName)}>
                <rect x="0" y="0" width="276" height="100" rx="8" fill="#1f2937" stroke={isHealthy ? '#22c55e' : '#fbbf24'} strokeWidth="1.5" />
                <rect x="0" y="0" width="276" height="26" rx="8" fill={svcColor} fillOpacity="0.4" />
                <circle cx="16" cy="13" r="6" fill={isHealthy ? '#22c55e' : '#fbbf24'} />
                <text x="32" y="18" fill="white" fontSize="13" fontWeight="bold">{svc}</text>
                <text x="264" y="18" fill={isHealthy ? '#4ade80' : '#fbbf24'} fontSize="12" textAnchor="end" fontWeight="500">{service.runningCount}/{service.desiredCount}</text>
                <text x="12" y="46" fill="#d1d5db" fontSize="11">Task Definition: <tspan fill="#60a5fa">rev {revision}</tspan></text>
                <text x="12" y="64" fill="#d1d5db" fontSize="11">Image: <tspan fill="#9ca3af">{image}</tspan></text>
                <text x="12" y="82" fill="#d1d5db" fontSize="11">Status: <tspan fill={service.status === 'ACTIVE' ? '#4ade80' : '#fbbf24'}>{service.status}</tspan></text>
              </g>
            )
          })}
        </g>

        {/* Arrow Services -> Data Stores */}
        <line x1="850" y1="190" x2="880" y2="190" stroke="#6b7280" strokeWidth="2" markerEnd={`url(#arrow-${env})`} />

        {/* Data Stores (RDS + Redis) */}
        <g transform="translate(890, 10)">
          <rect x="0" y="0" width="160" height="360" rx="10" fill="#1e293b" stroke="#06b6d4" strokeWidth="2" />
          <rect x="0" y="0" width="160" height="28" rx="10" fill="#06b6d4" />
          <text x="80" y="19" fill="white" fontSize="13" textAnchor="middle" fontWeight="bold">Data Stores</text>

          {/* RDS */}
          {rds && !rds.error && (
            <g transform="translate(12, 38)" className="cursor-pointer" onClick={() => onComponentSelect?.('rds', env, rds)}>
              <rect x="0" y="0" width="136" height="150" rx="8" fill="#1f2937" stroke="#22d3ee" strokeWidth="1.5" />
              <rect x="0" y="0" width="136" height="24" rx="8" fill="#0891b2" fillOpacity="0.5" />
              <text x="68" y="17" fill="white" fontSize="11" textAnchor="middle" fontWeight="bold">RDS PostgreSQL</text>
              <foreignObject x="48" y="28" width="40" height="40">
                <AwsRDS style={{ width: 40, height: 40 }} />
              </foreignObject>
              <text x="68" y="82" fill={rds.status === 'available' ? '#4ade80' : rds.status === 'stopped' ? '#ef4444' : '#fbbf24'} fontSize="12" textAnchor="middle" fontWeight="500">{rds.status}</text>
              <text x="12" y="102" fill="#d1d5db" fontSize="10">{rds.instanceClass}</text>
              <text x="12" y="118" fill="#d1d5db" fontSize="10">{rds.storage?.allocated}GB {rds.storage?.type}</text>
              <text x="12" y="134" fill="#9ca3af" fontSize="10">{rds.multiAz ? 'Multi-AZ' : 'Single-AZ'}</text>
            </g>
          )}

          {/* Redis */}
          {redis && !redis.error && (
            <g transform="translate(12, 198)" className="cursor-pointer" onClick={() => onComponentSelect?.('redis', env, redis)}>
              <rect x="0" y="0" width="136" height="150" rx="8" fill="#1f2937" stroke="#ef4444" strokeWidth="1.5" />
              <rect x="0" y="0" width="136" height="24" rx="8" fill="#dc2626" fillOpacity="0.5" />
              <text x="68" y="17" fill="white" fontSize="11" textAnchor="middle" fontWeight="bold">Redis</text>
              <foreignObject x="48" y="28" width="40" height="40">
                <AwsElastiCache style={{ width: 40, height: 40 }} />
              </foreignObject>
              <text x="68" y="82" fill={redis.status === 'available' ? '#4ade80' : '#fbbf24'} fontSize="12" textAnchor="middle" fontWeight="500">{redis.status}</text>
              <text x="12" y="102" fill="#d1d5db" fontSize="10">{redis.cacheNodeType}</text>
              <text x="12" y="118" fill="#d1d5db" fontSize="10">{redis.engine} {redis.engineVersion}</text>
              <text x="12" y="134" fill="#9ca3af" fontSize="10">{redis.numCacheNodes} node(s)</text>
            </g>
          )}
        </g>
      </svg>
    </div>
  )
}
