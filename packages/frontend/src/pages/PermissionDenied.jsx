/**
 * Permission Denied Page (403)
 *
 * Displayed when user lacks required permissions for a resource.
 */

import React from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';

const PermissionDenied = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, logout, getRoleFor, getAccessibleProjects } = useAuth();

  // Get error details from location state if available
  const errorDetails = location.state || {};
  const {
    requiredPermission = 'access',
    project = null,
    environment = null,
    resource = null,
  } = errorDetails;

  const userRole = project ? getRoleFor(project, environment) : null;
  const accessibleProjects = getAccessibleProjects();

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 py-12 px-4">
      <div className="max-w-lg w-full">
        <div className="bg-white rounded-lg shadow-lg p-8 text-center">
          {/* Icon */}
          <div className="mb-6">
            <svg
              className="mx-auto h-16 w-16 text-red-500"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
              />
            </svg>
          </div>

          {/* Title */}
          <h1 className="text-2xl font-bold text-gray-900 mb-2">
            Access Denied
          </h1>

          {/* Message */}
          <p className="text-gray-600 mb-6">
            You don't have permission to access this resource.
          </p>

          {/* Details */}
          {(project || requiredPermission !== 'access') && (
            <div className="bg-gray-50 rounded-md p-4 mb-6 text-left">
              <h3 className="text-sm font-medium text-gray-700 mb-2">
                Details
              </h3>
              <dl className="text-sm space-y-1">
                {project && (
                  <div className="flex justify-between">
                    <dt className="text-gray-500">Project:</dt>
                    <dd className="font-mono text-gray-900">{project}</dd>
                  </div>
                )}
                {environment && (
                  <div className="flex justify-between">
                    <dt className="text-gray-500">Environment:</dt>
                    <dd className="font-mono text-gray-900">{environment}</dd>
                  </div>
                )}
                {resource && (
                  <div className="flex justify-between">
                    <dt className="text-gray-500">Resource:</dt>
                    <dd className="font-mono text-gray-900">{resource}</dd>
                  </div>
                )}
                <div className="flex justify-between">
                  <dt className="text-gray-500">Required:</dt>
                  <dd className="font-mono text-gray-900">{requiredPermission}</dd>
                </div>
                {userRole && (
                  <div className="flex justify-between">
                    <dt className="text-gray-500">Your role:</dt>
                    <dd className="font-mono text-gray-900">{userRole}</dd>
                  </div>
                )}
              </dl>
            </div>
          )}

          {/* User Info */}
          {user && (
            <div className="text-sm text-gray-500 mb-6">
              Logged in as <span className="font-medium">{user.email}</span>
            </div>
          )}

          {/* Actions */}
          <div className="space-y-3">
            <button
              onClick={() => navigate(-1)}
              className="w-full flex justify-center py-2 px-4 border border-gray-300 rounded-md shadow-sm text-sm font-medium text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
            >
              Go Back
            </button>

            {accessibleProjects.length > 0 && (
              <button
                onClick={() => navigate('/')}
                className="w-full flex justify-center py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
              >
                Go to Dashboard
              </button>
            )}
          </div>

          {/* Help text */}
          <div className="mt-6 pt-6 border-t border-gray-200">
            <p className="text-sm text-gray-500">
              Need access? Contact your administrator to request the required permissions.
            </p>
          </div>
        </div>

        {/* Additional Info */}
        <div className="mt-4 text-center">
          <button
            onClick={logout}
            className="text-sm text-gray-500 hover:text-gray-700"
          >
            Sign out and use a different account
          </button>
        </div>
      </div>
    </div>
  );
};

export default PermissionDenied;
