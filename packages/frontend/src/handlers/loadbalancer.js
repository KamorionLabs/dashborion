/**
 * Load Balancer Resource Handlers (ALB)
 */
import { registerResourceHandler } from '../utils/infraResourceHandlers'

registerResourceHandler('alb', {
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
    if (alb) {
      const albId = alb.arn?.match(/loadbalancer\/app\/([^/]+)/)?.[1] || alb.name
      return albId === id || alb.arn === id ? alb : null
    }
    return null
  },
  findAll: (infraData) => infraData?.alb,
})
