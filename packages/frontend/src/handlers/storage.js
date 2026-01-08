/**
 * Storage Resource Handlers (S3)
 */
import { registerResourceHandler } from '../utils/infraResourceHandlers'

registerResourceHandler('s3', {
  getId: (data) => {
    if (Array.isArray(data)) return 's3-all'
    return data?.name || data?.bucketName
  },
  findInInfra: (id, infraData) => {
    const buckets = infraData?.s3Buckets
    if (!buckets) return null
    if (id === 's3-all') return buckets
    return buckets.find(b => b.name === id || b.bucketName === id)
  },
  findAll: (infraData) => infraData?.s3Buckets,
})
