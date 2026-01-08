/**
 * Device Authorization Page
 *
 * Allows users to verify device codes for CLI authentication.
 * Accessed via /auth/device?code=XXXX-XXXX
 */

import React, { useState, useEffect } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';

const DeviceAuth = () => {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { isAuthenticated, isLoading: authLoading } = useAuth();

  const [userCode, setUserCode] = useState(searchParams.get('code') || '');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(false);

  // Auto-submit if code is in URL and user is authenticated
  useEffect(() => {
    const codeFromUrl = searchParams.get('code');
    if (codeFromUrl && isAuthenticated && !authLoading) {
      setUserCode(codeFromUrl);
      handleSubmit(codeFromUrl);
    }
  }, [searchParams, isAuthenticated, authLoading]);

  // Redirect to login if not authenticated
  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      // Save the current URL to redirect back after login
      const returnUrl = window.location.pathname + window.location.search;
      sessionStorage.setItem('authReturnUrl', returnUrl);
      // Redirect to login page (user can choose SSO or credentials)
      window.location.href = '/login?returnUrl=' + encodeURIComponent(returnUrl);
    }
  }, [authLoading, isAuthenticated]);

  const formatCode = (input) => {
    // Remove non-alphanumeric characters and uppercase
    const clean = input.replace(/[^a-zA-Z0-9]/g, '').toUpperCase();

    // Format as XXXX-XXXX
    if (clean.length <= 4) {
      return clean;
    }
    return clean.slice(0, 4) + '-' + clean.slice(4, 8);
  };

  const handleCodeChange = (e) => {
    const formatted = formatCode(e.target.value);
    setUserCode(formatted);
    setError(null);
  };

  const handleSubmit = async (code = userCode) => {
    const cleanCode = code.replace(/[^a-zA-Z0-9]/g, '').toUpperCase();

    if (cleanCode.length !== 8) {
      setError('Please enter a valid 8-character code');
      return;
    }

    setIsSubmitting(true);
    setError(null);

    try {
      const response = await fetch('/api/auth/device/verify', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          user_code: formatCode(cleanCode),
        }),
      });

      const data = await response.json();

      if (response.ok && data.success) {
        setSuccess(true);
      } else {
        setError(data.error_description || data.error || 'Verification failed');
      }
    } catch (err) {
      setError('Network error. Please try again.');
    } finally {
      setIsSubmitting(false);
    }
  };

  // Show loading while checking auth
  if (authLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  // Success state
  if (success) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="max-w-md w-full bg-white rounded-lg shadow-lg p-8 text-center">
          <div className="mb-6">
            <svg
              className="mx-auto h-16 w-16 text-green-500"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
              />
            </svg>
          </div>

          <h1 className="text-2xl font-bold text-gray-900 mb-2">
            Device Authorized
          </h1>

          <p className="text-gray-600 mb-6">
            Your CLI has been successfully authenticated.
            You can close this window and return to your terminal.
          </p>

          <button
            onClick={() => window.close()}
            className="inline-flex items-center px-4 py-2 border border-gray-300 rounded-md shadow-sm text-sm font-medium text-gray-700 bg-white hover:bg-gray-50"
          >
            Close Window
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 py-12 px-4">
      <div className="max-w-md w-full">
        <div className="bg-white rounded-lg shadow-lg p-8">
          {/* Header */}
          <div className="text-center mb-8">
            <svg
              className="mx-auto h-12 w-12 text-blue-600"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"
              />
            </svg>

            <h1 className="mt-4 text-2xl font-bold text-gray-900">
              Authorize Device
            </h1>

            <p className="mt-2 text-gray-600">
              Enter the code shown in your terminal to authorize the Dashborion CLI.
            </p>
          </div>

          {/* Code Input */}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleSubmit();
            }}
          >
            <div className="mb-6">
              <label
                htmlFor="code"
                className="block text-sm font-medium text-gray-700 mb-2"
              >
                Device Code
              </label>

              <input
                id="code"
                type="text"
                value={userCode}
                onChange={handleCodeChange}
                placeholder="XXXX-XXXX"
                maxLength={9}
                className={`
                  block w-full px-4 py-3 text-center text-2xl font-mono tracking-widest
                  border rounded-md shadow-sm
                  placeholder-gray-400
                  focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500
                  ${error ? 'border-red-300' : 'border-gray-300'}
                `}
                autoComplete="off"
                autoFocus
              />

              {error && (
                <p className="mt-2 text-sm text-red-600">{error}</p>
              )}
            </div>

            <button
              type="submit"
              disabled={isSubmitting || userCode.length < 9}
              className={`
                w-full flex justify-center py-3 px-4 border border-transparent
                rounded-md shadow-sm text-sm font-medium text-white
                focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500
                ${
                  isSubmitting || userCode.length < 9
                    ? 'bg-blue-400 cursor-not-allowed'
                    : 'bg-blue-600 hover:bg-blue-700'
                }
              `}
            >
              {isSubmitting ? (
                <>
                  <svg
                    className="animate-spin -ml-1 mr-2 h-5 w-5 text-white"
                    fill="none"
                    viewBox="0 0 24 24"
                  >
                    <circle
                      className="opacity-25"
                      cx="12"
                      cy="12"
                      r="10"
                      stroke="currentColor"
                      strokeWidth="4"
                    />
                    <path
                      className="opacity-75"
                      fill="currentColor"
                      d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                    />
                  </svg>
                  Authorizing...
                </>
              ) : (
                'Authorize Device'
              )}
            </button>
          </form>

          {/* Help Text */}
          <div className="mt-6 text-center">
            <p className="text-sm text-gray-500">
              The code expires in 10 minutes.
              If you didn't request this, you can safely close this window.
            </p>
          </div>
        </div>

        {/* Security Notice */}
        <div className="mt-4 text-center">
          <p className="text-xs text-gray-400">
            Only authorize devices you trust.
            This will grant the CLI access to your Dashborion account.
          </p>
        </div>
      </div>
    </div>
  );
};

export default DeviceAuth;
