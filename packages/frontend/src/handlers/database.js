/**
 * Database Resource Handlers (RDS, ElastiCache)
 */
import { registerResourceHandler } from '../utils/infraResourceHandlers'

// RDS
registerResourceHandler('rds', {
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
})

// ElastiCache (Redis/Valkey)
registerResourceHandler('redis', {
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
})
