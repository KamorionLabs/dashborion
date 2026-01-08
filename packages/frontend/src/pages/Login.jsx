/**
 * Login Page
 *
 * Supports both SAML SSO and simple email/password login.
 * Stores auth method in localStorage for proper logout handling.
 */

import { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';

export default function Login() {
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [showCredentials, setShowCredentials] = useState(false);

  // Get return URL
  const returnUrl = new URLSearchParams(location.search).get('returnUrl') || '/';

  // Check if already logged in - validate token before redirecting
  useEffect(() => {
    const token = localStorage.getItem('dashborion_token');
    if (token) {
      // Validate token with API before redirecting
      fetch('/api/auth/me', {
        headers: { 'Authorization': `Bearer ${token}` }
      })
        .then(res => {
          if (res.ok) {
            // Token is valid, redirect
            navigate(returnUrl, { replace: true });
          } else {
            // Token is invalid, clear it to prevent redirect loop
            console.log('Invalid token detected, clearing localStorage');
            localStorage.removeItem('dashborion_token');
            localStorage.removeItem('dashborion_refresh_token');
            localStorage.removeItem('dashborion_user');
            localStorage.removeItem('dashborion_auth_method');
          }
        })
        .catch(() => {
          // Network error, clear tokens to be safe
          localStorage.removeItem('dashborion_token');
          localStorage.removeItem('dashborion_refresh_token');
          localStorage.removeItem('dashborion_user');
          localStorage.removeItem('dashborion_auth_method');
        });
    }
  }, [navigate, returnUrl]);

  // Handle SSO login
  const handleSsoLogin = () => {
    // Store that we're using SAML auth
    localStorage.setItem('dashborion_auth_method', 'saml');
    // Redirect to SAML login
    window.location.href = '/saml/login?returnUrl=' + encodeURIComponent(returnUrl);
  };

  // Handle credentials login
  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      const response = await fetch('/api/auth/login', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ email, password }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.error_description || data.error || 'Login failed');
      }

      // Store tokens and auth method
      localStorage.setItem('dashborion_token', data.access_token);
      localStorage.setItem('dashborion_refresh_token', data.refresh_token);
      localStorage.setItem('dashborion_user', JSON.stringify(data.user));
      localStorage.setItem('dashborion_auth_method', 'simple');

      // Redirect to return URL or home
      navigate(returnUrl, { replace: true });

      // Force page reload to reset auth state
      window.location.reload();
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-950 px-4">
      <div className="max-w-md w-full space-y-8">
        {/* Logo / Header */}
        <div className="text-center">
          <h1 className="text-3xl font-bold text-white">Dashborion</h1>
          <p className="mt-2 text-gray-400">Operations Dashboard</p>
        </div>

        {/* Login Options */}
        <div className="bg-gray-900 rounded-lg shadow-xl p-8 border border-gray-800">
          {!showCredentials ? (
            /* SSO + Switch to credentials */
            <div className="space-y-6">
              {/* SSO Button */}
              <button
                onClick={handleSsoLogin}
                className="w-full flex items-center justify-center gap-3 py-3 px-4 border border-gray-700 rounded-lg text-white bg-gray-800 hover:bg-gray-700 transition-colors"
              >
                <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M10 9a3 3 0 100-6 3 3 0 000 6zm-7 9a7 7 0 1114 0H3z" clipRule="evenodd" />
                </svg>
                Sign in with SSO
              </button>

              {/* Divider */}
              <div className="relative">
                <div className="absolute inset-0 flex items-center">
                  <div className="w-full border-t border-gray-700"></div>
                </div>
                <div className="relative flex justify-center text-sm">
                  <span className="px-2 bg-gray-900 text-gray-500">or</span>
                </div>
              </div>

              {/* Switch to credentials */}
              <button
                onClick={() => setShowCredentials(true)}
                className="w-full py-3 px-4 border border-transparent rounded-lg text-sm font-medium text-blue-400 hover:text-blue-300 transition-colors"
              >
                Sign in with email and password
              </button>
            </div>
          ) : (
            /* Credentials Form */
            <form onSubmit={handleSubmit} className="space-y-6">
              {/* Back button */}
              <button
                type="button"
                onClick={() => setShowCredentials(false)}
                className="flex items-center gap-2 text-sm text-gray-400 hover:text-gray-300"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                </svg>
                Back to login options
              </button>

              {/* Error Message */}
              {error && (
                <div className="bg-red-900/50 border border-red-700 text-red-200 px-4 py-3 rounded-lg text-sm">
                  {error}
                </div>
              )}

              {/* Email Field */}
              <div>
                <label htmlFor="email" className="block text-sm font-medium text-gray-300">
                  Email
                </label>
                <input
                  id="email"
                  name="email"
                  type="email"
                  autoComplete="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="mt-1 block w-full px-4 py-3 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  placeholder="user@example.com"
                />
              </div>

              {/* Password Field */}
              <div>
                <label htmlFor="password" className="block text-sm font-medium text-gray-300">
                  Password
                </label>
                <input
                  id="password"
                  name="password"
                  type="password"
                  autoComplete="current-password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="mt-1 block w-full px-4 py-3 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  placeholder="Enter your password"
                />
              </div>

              {/* Submit Button */}
              <button
                type="submit"
                disabled={loading}
                className={`w-full flex justify-center py-3 px-4 border border-transparent rounded-lg text-sm font-medium text-white transition-colors ${
                  loading
                    ? 'bg-blue-700 cursor-not-allowed'
                    : 'bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500'
                }`}
              >
                {loading ? (
                  <>
                    <svg
                      className="animate-spin -ml-1 mr-3 h-5 w-5 text-white"
                      xmlns="http://www.w3.org/2000/svg"
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
                      ></circle>
                      <path
                        className="opacity-75"
                        fill="currentColor"
                        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                      ></path>
                    </svg>
                    Signing in...
                  </>
                ) : (
                  'Sign in'
                )}
              </button>
            </form>
          )}
        </div>

        {/* Footer */}
        <p className="text-center text-sm text-gray-500">
          Homebox Operations Dashboard
        </p>
      </div>
    </div>
  );
}
