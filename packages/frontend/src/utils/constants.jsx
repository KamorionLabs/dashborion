/**
 * UI Constants - status icons and colors
 */
import { CheckCircle, XCircle, AlertCircle } from 'lucide-react'

export const STATUS_ICONS = {
  HEALTHY: <CheckCircle className="w-4 h-4 text-green-400" />,
  UNHEALTHY: <XCircle className="w-4 h-4 text-red-400" />,
  UNKNOWN: <AlertCircle className="w-4 h-4 text-gray-400" />
}

export const PIPELINE_STATUS_COLORS = {
  // Lowercase keys to match API response (.lower() in Python)
  succeeded: 'bg-green-500',
  failed: 'bg-red-500',
  inprogress: 'bg-yellow-500 animate-pulse',
  stopped: 'bg-gray-500',
  unknown: 'bg-gray-600',
  // Keep capitalized keys for backward compatibility
  Succeeded: 'bg-green-500',
  Failed: 'bg-red-500',
  InProgress: 'bg-yellow-500 animate-pulse',
  Stopped: 'bg-gray-500',
  Unknown: 'bg-gray-600'
}
