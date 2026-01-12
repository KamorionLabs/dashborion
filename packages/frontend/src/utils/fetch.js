/**
 * Fetch utilities with SSO session handling
 *
 * Supports two authentication modes:
 * 1. Bearer token (stored in localStorage) - for CLI and after SSO token exchange
 * 2. Cookie auth (withCredentials) - for initial SSO session validation
 *
 * After SAML SSO, the cookie is exchanged for a Bearer token via /api/auth/token/issue.
 */

// Direct API URL - for authenticated requests with Bearer token
const API_BASE_URL = import.meta.env.VITE_API_URL || ''

/**
 * Build full API URL by prepending base URL to path
 *
 * @param {string} path - API path (e.g., '/api/health')
 * @returns {string} Full URL
 */
export const apiUrl = (path) => {
  // If path is already absolute URL, return as-is
  if (path.startsWith('http://') || path.startsWith('https://')) {
    return path
  }

  const cleanPath = path.startsWith('/') ? path : `/${path}`

  // Use direct API URL if configured
  if (API_BASE_URL) {
    const base = API_BASE_URL.endsWith('/') ? API_BASE_URL.slice(0, -1) : API_BASE_URL
    return `${base}${cleanPath}`
  }

  // Fallback to relative URL
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
 * @param {boolean} withCredentials - Include cookies for cross-origin requests (SAML cookie auth)
 */
export const fetchWithRetry = async (url, options = {}, maxRetries = 3, withCredentials = false) => {
  const fullUrl = apiUrl(url)
  let lastError

  // Add auth headers (unless using cookie auth with credentials)
  const authHeaders = withCredentials ? {} : getAuthHeaders()
  const mergedOptions = {
    ...options,
    headers: {
      ...authHeaders,
      ...options.headers,
    },
    // Include credentials for SSO cookie auth (cross-origin)
    ...(withCredentials && { credentials: 'include' }),
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
