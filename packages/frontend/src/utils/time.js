/**
 * Time formatting utilities
 */

/**
 * Clean timestamp with double timezone issue
 * Fix "2025-12-15T14:32:00.625000+00:00Z" -> remove trailing Z if +offset exists
 */
export const cleanTimestamp = (dateString) => {
  if (!dateString) return null
  let cleanDate = String(dateString)
  if (cleanDate.match(/[+-]\d{2}:\d{2}Z$/)) {
    cleanDate = cleanDate.slice(0, -1)
  }
  return cleanDate
}

/**
 * Format relative time (e.g., "5m ago", "2h ago")
 */
export const formatRelativeTime = (dateString) => {
  if (!dateString) return 'N/A'
  const date = new Date(cleanTimestamp(dateString))
  if (isNaN(date.getTime())) return 'N/A'
  const now = new Date()
  const diffMs = now - date
  const diffMins = Math.floor(diffMs / 60000)
  const diffHours = Math.floor(diffMs / 3600000)
  const diffDays = Math.floor(diffMs / 86400000)

  if (diffMins < 1) return 'just now'
  if (diffMins < 60) return `${diffMins}m ago`
  if (diffHours < 24) return `${diffHours}h ago`
  return `${diffDays}d ago`
}

/**
 * Format time for timeline display (HH:MM)
 */
export const formatTimeHHMM = (dateString) => {
  if (!dateString) return ''
  const date = new Date(cleanTimestamp(dateString))
  if (isNaN(date.getTime())) return ''
  return date.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })
}

/**
 * Format duration in human readable format
 */
export const formatDuration = (seconds) => {
  if (!seconds || seconds < 0) return null
  if (seconds < 60) return `${seconds}s`
  const mins = Math.floor(seconds / 60)
  const secs = seconds % 60
  if (mins < 60) return secs > 0 ? `${mins}m ${secs}s` : `${mins}m`
  const hours = Math.floor(mins / 60)
  const remainMins = mins % 60
  return remainMins > 0 ? `${hours}h ${remainMins}m` : `${hours}h`
}

/**
 * Calculate duration from start and end times
 */
export const calculateDuration = (startTime, endTime) => {
  if (!startTime || !endTime) return null
  const start = new Date(startTime)
  const end = new Date(endTime)
  if (isNaN(start.getTime()) || isNaN(end.getTime())) return null
  return Math.floor((end - start) / 1000)
}
