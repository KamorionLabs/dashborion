/**
 * Fetch utilities with SSO session handling
 *
 * Supports two authentication modes:
 * 1. Bearer token (stored in localStorage) - for CLI and after SSO token exchange
 * 2. Cookie auth (withCredentials) - for initial SSO session validation
 *
 * After SAML SSO, the cookie is exchanged for a Bearer token via /api/auth/token/issue.
 * Automatic token refresh on 401/403 errors.
 */

// Direct API URL - for authenticated requests with Bearer token
const API_BASE_URL = import.meta.env.VITE_API_URL || ''

// Track if we're currently refreshing to prevent multiple simultaneous refreshes
let isRefreshing = false
let refreshPromise = null

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
  localStorage.removeItem('dashborion_token_expires_at')
  localStorage.removeItem('dashborion_user')
  localStorage.removeItem('dashborion_auth_method')
}

/**
 * Get token expiration timestamp
 */
export const getTokenExpiresAt = () => {
  const expiresAt = localStorage.getItem('dashborion_token_expires_at')
  return expiresAt ? parseInt(expiresAt, 10) : null
}

/**
 * Store token with expiration
 */
export const storeToken = (accessToken, refreshToken, expiresIn, user) => {
  const expiresAt = Math.floor(Date.now() / 1000) + expiresIn
  localStorage.setItem('dashborion_token', accessToken)
  localStorage.setItem('dashborion_refresh_token', refreshToken)
  localStorage.setItem('dashborion_token_expires_at', expiresAt.toString())
  if (user) {
    localStorage.setItem('dashborion_user', JSON.stringify(user))
  }
}

/**
 * Refresh access token using refresh token
 * Returns true if successful, false otherwise
 */
export const refreshAccessToken = async () => {
  // Prevent multiple simultaneous refresh attempts
  if (isRefreshing) {
    return refreshPromise
  }

  const refreshToken = localStorage.getItem('dashborion_refresh_token')
  if (!refreshToken) {
    return false
  }

  isRefreshing = true
  refreshPromise = (async () => {
    try {
      const response = await fetch(apiUrl('/api/auth/token/refresh'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          grant_type: 'refresh_token',
          refresh_token: refreshToken,
        }),
      })

      if (response.ok) {
        const data = await response.json()
        storeToken(data.access_token, data.refresh_token, data.expires_in, data.user)
        console.log('Token refreshed successfully')
        return true
      } else {
        console.warn('Token refresh failed:', response.status)
        return false
      }
    } catch (err) {
      console.error('Token refresh error:', err)
      return false
    } finally {
      isRefreshing = false
      refreshPromise = null
    }
  })()

  return refreshPromise
}

/**
 * Redirect to login page
 */
export const redirectToLogin = () => {
  clearAuthTokens()
  const returnUrl = window.location.pathname + window.location.search
  window.location.href = '/login?returnUrl=' + encodeURIComponent(returnUrl)
}

/**
 * Fetch with automatic retry for transient errors (503, 502, etc.)
 * Also detects SSO session expiration and includes JWT token
 * Automatically refreshes token on 401/403 errors
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

      // Handle 401/403 - try to refresh token (only on first attempt, not for auth endpoints)
      if ((response.status === 401 || response.status === 403) && attempt === 0 && !withCredentials) {
        // Don't try to refresh for auth endpoints themselves
        if (!url.includes('/api/auth/')) {
          const refreshed = await refreshAccessToken()
          if (refreshed) {
            // Retry with new token
            const newAuthHeaders = getAuthHeaders()
            const retryOptions = {
              ...options,
              headers: {
                ...newAuthHeaders,
                ...options.headers,
              },
            }
            const retryResponse = await fetch(fullUrl, retryOptions)
            return retryResponse
          } else {
            // Refresh failed - redirect to login
            redirectToLogin()
            throw new Error('Session expired')
          }
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
