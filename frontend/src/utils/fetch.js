/**
 * Fetch utilities with SSO session handling
 */

// Session expiration event for SSO token expiry detection
export const sessionExpiredEvent = new EventTarget()

export const notifySessionExpired = () => {
  sessionExpiredEvent.dispatchEvent(new CustomEvent('sessionExpired'))
}

/**
 * Fetch with automatic retry for transient errors (503, 502, etc.)
 * Also detects SSO session expiration
 */
export const fetchWithRetry = async (url, options = {}, maxRetries = 3) => {
  let lastError
  for (let attempt = 0; attempt < maxRetries; attempt++) {
    try {
      const response = await fetch(url, options)
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
