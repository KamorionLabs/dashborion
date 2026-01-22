/**
 * SessionMonitor - Monitors token expiration and prompts user before session expires
 *
 * Shows a "Session expiring soon" prompt 5 minutes before token expiration.
 * Automatically refreshes the token when user confirms.
 */
import { useState, useEffect, useCallback } from 'react';
import { Clock, RefreshCw, LogOut } from 'lucide-react';
import { getTokenExpiresAt, refreshAccessToken, redirectToLogin } from '../../utils/fetch';

// Warning time: 5 minutes before expiration
const WARNING_THRESHOLD_SECONDS = 5 * 60;
// Check interval: every 30 seconds
const CHECK_INTERVAL_MS = 30 * 1000;

export default function SessionMonitor() {
  const [showWarning, setShowWarning] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [timeLeft, setTimeLeft] = useState(null);

  // Check token expiration periodically
  useEffect(() => {
    const checkExpiration = () => {
      const expiresAt = getTokenExpiresAt();
      if (!expiresAt) {
        setShowWarning(false);
        return;
      }

      const now = Math.floor(Date.now() / 1000);
      const secondsLeft = expiresAt - now;

      // Token already expired
      if (secondsLeft <= 0) {
        setShowWarning(false);
        redirectToLogin();
        return;
      }

      // Show warning if within threshold
      if (secondsLeft <= WARNING_THRESHOLD_SECONDS) {
        setShowWarning(true);
        setTimeLeft(secondsLeft);
      } else {
        setShowWarning(false);
        setTimeLeft(null);
      }
    };

    // Check immediately and then periodically
    checkExpiration();
    const interval = setInterval(checkExpiration, CHECK_INTERVAL_MS);

    return () => clearInterval(interval);
  }, []);

  // Update countdown every second when warning is shown
  useEffect(() => {
    if (!showWarning || timeLeft === null) return;

    const timer = setInterval(() => {
      setTimeLeft((prev) => {
        if (prev === null || prev <= 1) {
          // Time's up - redirect to login
          redirectToLogin();
          return null;
        }
        return prev - 1;
      });
    }, 1000);

    return () => clearInterval(timer);
  }, [showWarning, timeLeft]);

  // Handle stay connected
  const handleStayConnected = useCallback(async () => {
    setRefreshing(true);
    try {
      const success = await refreshAccessToken();
      if (success) {
        setShowWarning(false);
        setTimeLeft(null);
      } else {
        // Refresh failed - redirect to login
        redirectToLogin();
      }
    } catch (err) {
      console.error('Session refresh failed:', err);
      redirectToLogin();
    } finally {
      setRefreshing(false);
    }
  }, []);

  // Handle logout
  const handleLogout = useCallback(() => {
    redirectToLogin();
  }, []);

  // Format time left
  const formatTimeLeft = (seconds) => {
    if (seconds === null) return '';
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    if (mins > 0) {
      return `${mins}m ${secs}s`;
    }
    return `${secs}s`;
  };

  if (!showWarning) {
    return null;
  }

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-[100]">
      <div className="bg-gray-800 border border-yellow-500/50 rounded-lg p-6 max-w-md mx-4 shadow-2xl">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-12 h-12 rounded-full bg-yellow-500/20 flex items-center justify-center">
            <Clock className="w-6 h-6 text-yellow-400" />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-white">Still there?</h2>
            <p className="text-sm text-gray-400">
              Session expiring in {formatTimeLeft(timeLeft)}
            </p>
          </div>
        </div>
        <p className="text-gray-300 mb-6">
          Your session is about to expire. Would you like to stay connected?
        </p>
        <div className="flex gap-3">
          <button
            onClick={handleStayConnected}
            disabled={refreshing}
            className="flex-1 flex items-center justify-center gap-2 px-4 py-2 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg font-medium transition-colors"
          >
            {refreshing ? (
              <>
                <RefreshCw className="w-4 h-4 animate-spin" />
                Refreshing...
              </>
            ) : (
              <>
                <RefreshCw className="w-4 h-4" />
                Stay Connected
              </>
            )}
          </button>
          <button
            onClick={handleLogout}
            disabled={refreshing}
            className="px-4 py-2 bg-gray-700 hover:bg-gray-600 disabled:opacity-50 rounded-lg font-medium transition-colors flex items-center gap-2"
          >
            <LogOut className="w-4 h-4" />
            Log Out
          </button>
        </div>
      </div>
    </div>
  );
}
