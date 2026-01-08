/**
 * Infrastructure resource handlers for deep-linking
 *
 * Each handler defines how to:
 * - getId(data): Extract a stable ID from a resource object
 * - findInInfra(id, infraData): Find the resource in infrastructure data by ID
 * - findAll(infraData): Get all resources of this type (for direct access without ID)
 *
 * To add a new resource type, simply add a new handler to this map.
 */

export const resourceHandlers = {
  // CDN
  cloudfront: {
    getId: (data) => data?.id,
    findInInfra: (id, infraData) => {
      // Support both single object and array
      const cf = infraData?.cloudfront
      if (Array.isArray(cf)) {
        return cf.find(c => c.id === id)
      }
      return cf?.id === id ? cf : null
    },
    findAll: (infraData) => infraData?.cloudfront,
  },

  // Load Balancer
  alb: {
    getId: (data) => {
      // Use short name from ARN if available, otherwise full ARN
      if (data?.arn) {
        const match = data.arn.match(/loadbalancer\/app\/([^/]+)/)
        return match ? match[1] : data.arn
      }
      return data?.name || null
    },
    findInInfra: (id, infraData) => {
      const alb = infraData?.alb
      if (Array.isArray(alb)) {
        return alb.find(a => {
          const albId = a.arn?.match(/loadbalancer\/app\/([^/]+)/)?.[1] || a.name
          return albId === id || a.arn === id
        })
      }
      // Single ALB - check if ID matches
      if (alb) {
        const albId = alb.arn?.match(/loadbalancer\/app\/([^/]+)/)?.[1] || alb.name
        return albId === id || alb.arn === id ? alb : null
      }
      return null
    },
    findAll: (infraData) => infraData?.alb,
  },

  // Database
  rds: {
    getId: (data) => data?.identifier || data?.dbInstanceIdentifier,
    findInInfra: (id, infraData) => {
      const rds = infraData?.rds
      if (Array.isArray(rds)) {
        return rds.find(r => r.identifier === id || r.dbInstanceIdentifier === id)
      }
      if (rds?.identifier === id || rds?.dbInstanceIdentifier === id) {
        return rds
      }
      return null
    },
    findAll: (infraData) => infraData?.rds,
  },

  // Cache
  redis: {
    getId: (data) => data?.cacheClusterId || data?.replicationGroupId || data?.id,
    findInInfra: (id, infraData) => {
      const redis = infraData?.redis
      if (Array.isArray(redis)) {
        return redis.find(r =>
          r.cacheClusterId === id || r.replicationGroupId === id || r.id === id
        )
      }
      if (redis) {
        const redisId = redis.cacheClusterId || redis.replicationGroupId || redis.id
        return redisId === id ? redis : null
      }
      return null
    },
    findAll: (infraData) => infraData?.redis,
  },

  // S3 Buckets (always an array)
  s3: {
    getId: (data) => {
      // If it's an array (all buckets), use a marker
      if (Array.isArray(data)) return 's3-all'
      return data?.name || data?.bucketName
    },
    findInInfra: (id, infraData) => {
      const buckets = infraData?.s3Buckets
      if (!buckets) return null
      // Special case: 's3-all' means show all buckets
      if (id === 's3-all') return buckets
      // Find specific bucket by name
      return buckets.find(b => b.name === id || b.bucketName === id)
    },
    findAll: (infraData) => infraData?.s3Buckets,
  },

  // Network - Subnets (array)
  subnet: {
    getId: (data) => data?.subnetId || data?.id,
    findInInfra: (id, infraData) => {
      const subnets = infraData?.network?.subnets
      return subnets?.find(s => s.subnetId === id || s.id === id)
    },
    findAll: (infraData) => infraData?.network?.subnets,
  },

  // Network - Route Tables (array)
  routeTable: {
    getId: (data) => data?.routeTableId || data?.id,
    findInInfra: (id, infraData) => {
      const tables = infraData?.network?.routeTables
      return tables?.find(r => r.routeTableId === id || r.id === id)
    },
    findAll: (infraData) => infraData?.network?.routeTables,
  },

  // Network - VPC Endpoints (array)
  endpoint: {
    getId: (data) => data?.vpcEndpointId || data?.id,
    findInInfra: (id, infraData) => {
      const endpoints = infraData?.network?.endpoints
      return endpoints?.find(e => e.vpcEndpointId === id || e.id === id)
    },
    findAll: (infraData) => infraData?.network?.endpoints,
  },

  // Network - VPC (single)
  vpc: {
    getId: (data) => data?.vpcId || data?.id,
    findInInfra: (id, infraData) => {
      const vpc = infraData?.network?.vpc
      return vpc?.vpcId === id || vpc?.id === id ? vpc : null
    },
    findAll: (infraData) => infraData?.network?.vpc,
  },

  // Network - Internet Gateway (single)
  igw: {
    getId: (data) => data?.internetGatewayId || data?.id,
    findInInfra: (id, infraData) => {
      const igw = infraData?.network?.igw
      return igw?.internetGatewayId === id || igw?.id === id ? igw : null
    },
    findAll: (infraData) => infraData?.network?.igw,
  },

  // Network - VPC Peerings (array)
  peering: {
    getId: (data) => data?.vpcPeeringConnectionId || data?.id,
    findInInfra: (id, infraData) => {
      const peerings = infraData?.network?.peerings
      return peerings?.find(p => p.vpcPeeringConnectionId === id || p.id === id)
    },
    findAll: (infraData) => infraData?.network?.peerings,
  },

  // Network - VPN Connections (array)
  vpn: {
    getId: (data) => data?.vpnConnectionId || data?.id,
    findInInfra: (id, infraData) => {
      const vpns = infraData?.network?.vpns
      return vpns?.find(v => v.vpnConnectionId === id || v.id === id)
    },
    findAll: (infraData) => infraData?.network?.vpns,
  },

  // Network - Transit Gateway (single)
  tgw: {
    getId: (data) => data?.transitGatewayId || data?.id,
    findInInfra: (id, infraData) => {
      const tgw = infraData?.network?.tgw
      return tgw?.transitGatewayId === id || tgw?.id === id ? tgw : null
    },
    findAll: (infraData) => infraData?.network?.tgw,
  },

  // ECS Task (from tasks array in services)
  task: {
    getId: (data) => data?.taskId || data?.taskArn?.split('/').pop() || data?.id,
    findInInfra: (id, infraData) => {
      // Tasks are typically fetched separately, not from infra
      // Return null to let the component fetch them
      return null
    },
    findAll: (infraData) => null,
  },
}

/**
 * Get the resource ID from data using the appropriate handler
 */
export function getResourceId(type, data) {
  const handler = resourceHandlers[type]
  if (!handler) return data?.id || null
  return handler.getId(data)
}

/**
 * Find a resource in infrastructure data by type and ID
 */
export function findResource(type, id, infraData) {
  const handler = resourceHandlers[type]
  if (!handler) return null
  return handler.findInInfra(id, infraData)
}

/**
 * Get all resources of a type from infrastructure data
 */
export function findAllResources(type, infraData) {
  const handler = resourceHandlers[type]
  if (!handler) return null
  return handler.findAll(infraData)
}

/**
 * Register a new resource handler
 * Use this to add handlers from components
 */
export function registerResourceHandler(type, handler) {
  resourceHandlers[type] = handler
}

export default resourceHandlers
