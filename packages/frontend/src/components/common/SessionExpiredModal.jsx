import { RefreshCw, AlertTriangle } from 'lucide-react'

export default function SessionExpiredModal({ onReconnect }) {
  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-[100]">
      <div className="bg-gray-800 border border-red-500/50 rounded-lg p-6 max-w-md mx-4 shadow-2xl">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-12 h-12 rounded-full bg-red-500/20 flex items-center justify-center">
            <AlertTriangle className="w-6 h-6 text-red-400" />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-white">Session Expired</h2>
            <p className="text-sm text-gray-400">Your SSO session has expired</p>
          </div>
        </div>
        <p className="text-gray-300 mb-6">
          Your authentication token has expired. Please reconnect to continue using the dashboard.
        </p>
        <div className="flex gap-3">
          <button
            onClick={onReconnect}
            className="flex-1 flex items-center justify-center gap-2 px-4 py-2 bg-brand-600 hover:bg-brand-500 rounded-lg font-medium transition-colors"
          >
            <RefreshCw className="w-4 h-4" />
            Reconnect
          </button>
        </div>
      </div>
    </div>
  )
}
