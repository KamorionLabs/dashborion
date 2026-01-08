/**
 * CDN Resource Handlers (CloudFront)
 */
import { registerResourceHandler } from '../utils/infraResourceHandlers'

registerResourceHandler('cloudfront', {
  getId: (data) => data?.id,
  findInInfra: (id, infraData) => {
    const cf = infraData?.cloudfront
    if (Array.isArray(cf)) {
      return cf.find(c => c.id === id)
    }
    return cf?.id === id ? cf : null
  },
  findAll: (infraData) => infraData?.cloudfront,
})
