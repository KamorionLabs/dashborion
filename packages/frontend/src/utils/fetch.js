/**
 * Fetch utilities with SSO session handling
 *
 * Supports two API access modes:
 * 1. Direct API URL (VITE_API_URL) - for Bearer token authenticated requests
 * 2. CloudFront proxy (relative URL) - for SSO cookie-based auth requests
 *
 * SSO users must first exchange their cookie for a Bearer token via CloudFront,
 * then all subsequent requests can go directly to the API.
 */

// Direct API URL - for authenticated requests with Bearer token
const API_BASE_URL = import.meta.env.VITE_API_URL || ''

/**
 * Build full API URL by prepending base URL to path
 * Uses direct API URL if configured and we have a Bearer token,
 * otherwise falls back to relative URL (CloudFront proxy)
 *
 * @param {string} path - API path (e.g., '/api/health')
 * @param {boolean} forceProxy - Force use of CloudFront proxy (for SSO auth)
 * @returns {string} Full URL
 */
export const apiUrl = (path, forceProxy = false) => {
  // If path is already absolute URL, return as-is
  if (path.startsWith('http://') || path.startsWith('https://')) {
    return path
  }

  const cleanPath = path.startsWith('/') ? path : `/${path}`

  // Force proxy mode (for SSO auth endpoints that need Lambda@Edge)
  if (forceProxy) {
    return cleanPath
  }

  // Use direct API URL if configured
  if (API_BASE_URL) {
    const base = API_BASE_URL.endsWith('/') ? API_BASE_URL.slice(0, -1) : API_BASE_URL
    return `${base}${cleanPath}`
  }

  // Fallback to relative URL (CloudFront proxy)
  return cleanPath
}

/**
 * Get the CloudFront proxy URL (always relative)
 * Use this for SSO-related endpoints that require Lambda@Edge processing
 */
export const proxyUrl = (path) => {
  const cleanPath = path.startsWith('/') ? path : `/${path}`
  return cleanPath
}

// Session expiration event for SSO token expiry detection
export const sessionExpiredEvent = new EventTarget()

export const notifySessionExpired = () => {
  sessionExpiredEvent.dispatchEvent(new CustomEvent('sessionExpired'))
}

/**
 * Get auth headers from stored token
 */
const getAuthHeaders = () => {
  const token = localStorage.getItem('dashborion_token')
  if (token) {
    return { Authorization: `Bearer ${token}` }
  }
  return {}
}

/**
 * Clear stored auth tokens (logout)
 */
export const clearAuthTokens = () => {
  localStorage.removeItem('dashborion_token')
  localStorage.removeItem('dashborion_refresh_token')
  localStorage.removeItem('dashborion_user')
  localStorage.removeItem('dashborion_auth_method')
}

/**
 * Fetch with automatic retry for transient errors (503, 502, etc.)
 * Also detects SSO session expiration and includes JWT token
 *
 * @param {string} url - API path
 * @param {object} options - Fetch options
 * @param {number} maxRetries - Max retry attempts
 * @param {boolean} forceProxy - Force CloudFront proxy (for SSO auth endpoints)
 */
export const fetchWithRetry = async (url, options = {}, maxRetries = 3, forceProxy = false) => {
  const fullUrl = apiUrl(url, forceProxy)
  let lastError

  // Add auth headers (unless forcing proxy for SSO cookie auth)
  const authHeaders = forceProxy ? {} : getAuthHeaders()
  const mergedOptions = {
    ...options,
    headers: {
      ...authHeaders,
      ...options.headers,
    },
    // Include credentials for SSO cookie when using proxy
    ...(forceProxy && { credentials: 'include' }),
  }

  for (let attempt = 0; attempt < maxRetries; attempt++) {
    try {
      const response = await fetch(fullUrl, mergedOptions)
      // Detect SSO redirect (307 to SSO portal)
      if (response.status === 307 || response.redirected) {
        const location = response.headers.get('location') || response.url
        if (location && location.includes('sso') || location.includes('awsapps.com')) {
          notifySessionExpired()
          throw new Error('SSO session expired')
        }
      }
      // Retry on 502/503/504 errors
      if (response.status >= 500 && response.status <= 504 && attempt < maxRetries - 1) {
        await new Promise(r => setTimeout(r, 500 * (attempt + 1))) // Exponential backoff
        continue
      }
      return response
    } catch (error) {
      lastError = error
      // Detect CORS error (typical when SSO redirect happens)
      if (error.name === 'TypeError' && error.message.includes('Failed to fetch')) {
        // After a few CORS errors, assume session expired
        if (attempt >= 1) {
          notifySessionExpired()
        }
      }
      if (attempt < maxRetries - 1) {
        await new Promise(r => setTimeout(r, 500 * (attempt + 1)))
        continue
      }
    }
  }
  throw lastError || new Error('Fetch failed after retries')
}
