/**
 * AccountForm - Create/Edit AWS Account
 *
 * Form to configure AWS account with cross-account roles and test connection.
 */
import { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import {
  Cloud,
  Save,
  ArrowLeft,
  RefreshCw,
  AlertCircle,
  CheckCircle,
  XCircle,
  Zap,
} from 'lucide-react';
import { fetchWithRetry } from '../../utils/fetch';

const AWS_REGIONS = [
  { value: 'eu-central-1', label: 'EU (Frankfurt)' },
  { value: 'eu-west-1', label: 'EU (Ireland)' },
  { value: 'eu-west-2', label: 'EU (London)' },
  { value: 'eu-west-3', label: 'EU (Paris)' },
  { value: 'us-east-1', label: 'US East (N. Virginia)' },
  { value: 'us-west-2', label: 'US West (Oregon)' },
  { value: 'ap-southeast-1', label: 'Asia Pacific (Singapore)' },
];

export default function AccountForm() {
  const { accountId } = useParams();
  const navigate = useNavigate();
  const isEdit = Boolean(accountId);

  const [loading, setLoading] = useState(isEdit);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  const [form, setForm] = useState({
    accountId: '',
    displayName: '',
    defaultRegion: 'eu-central-1',
    readRoleArn: '',
    actionRoleArn: '',
  });

  // Separate test states for read and action roles
  const [testingRead, setTestingRead] = useState(false);
  const [testingAction, setTestingAction] = useState(false);
  const [readTestResult, setReadTestResult] = useState(null);
  const [actionTestResult, setActionTestResult] = useState(null);

  // Load existing account for edit
  useEffect(() => {
    if (isEdit) {
      loadAccount();
    }
  }, [accountId]);

  // Reset test results when role ARN changes
  useEffect(() => {
    setReadTestResult(null);
  }, [form.readRoleArn]);

  useEffect(() => {
    setActionTestResult(null);
  }, [form.actionRoleArn]);

  const loadAccount = async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await fetchWithRetry(`/api/config/aws-accounts/${accountId}`);

      if (!response.ok) {
        if (response.status === 404) {
          throw new Error('Account not found');
        }
        throw new Error('Failed to load account');
      }

      const data = await response.json();
      setForm({
        accountId: data.accountId || '',
        displayName: data.displayName || '',
        defaultRegion: data.defaultRegion || 'eu-central-1',
        readRoleArn: data.readRoleArn || '',
        actionRoleArn: data.actionRoleArn || '',
      });
    } catch (err) {
      console.error('Error loading account:', err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (!form.accountId || !form.readRoleArn) {
      setError('Account ID and Read Role ARN are required');
      return;
    }

    setSaving(true);
    setError(null);

    try {
      const method = isEdit ? 'PUT' : 'POST';
      const url = isEdit
        ? `/api/config/aws-accounts/${accountId}`
        : '/api/config/aws-accounts';

      const response = await fetchWithRetry(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.message || 'Failed to save account');
      }

      navigate('/admin/config/accounts');
    } catch (err) {
      console.error('Error saving account:', err);
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  /**
   * Test a role ARN directly using form values (not saved config)
   */
  const testRole = async (roleArn, setTesting, setResult) => {
    if (!roleArn) return;

    setTesting(true);
    setResult(null);

    try {
      const response = await fetchWithRetry(
        `/api/config/discovery/test-role?roleArn=${encodeURIComponent(roleArn)}`
      );

      const data = await response.json();
      setResult(data);
    } catch (err) {
      console.error('Test role error:', err);
      setResult({ success: false, error: err.message });
    } finally {
      setTesting(false);
    }
  };

  const handleTestReadRole = () => {
    testRole(form.readRoleArn, setTestingRead, setReadTestResult);
  };

  const handleTestActionRole = () => {
    testRole(form.actionRoleArn, setTestingAction, setActionTestResult);
  };

  /**
   * Render test result badge
   */
  const TestResultBadge = ({ result, testing }) => {
    if (testing) {
      return <RefreshCw size={14} className="animate-spin text-gray-400" />;
    }
    if (!result) return null;
    if (result.success) {
      return <CheckCircle size={14} className="text-green-400" />;
    }
    return <XCircle size={14} className="text-red-400" />;
  };

  if (loading) {
    return (
      <div className="p-6">
        <div className="flex items-center justify-center h-64">
          <RefreshCw size={24} className="animate-spin text-gray-500" />
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 max-w-2xl">
      {/* Header */}
      <div className="mb-6">
        <Link
          to="/admin/config/accounts"
          className="flex items-center gap-1 text-sm text-gray-400 hover:text-white mb-4"
        >
          <ArrowLeft size={16} />
          Back to Accounts
        </Link>
        <h1 className="text-2xl font-semibold text-white">
          {isEdit ? 'Edit AWS Account' : 'Add AWS Account'}
        </h1>
        <p className="text-gray-500">
          Configure cross-account access for resource discovery
        </p>
      </div>

      {/* Error */}
      {error && (
        <div className="mb-6 p-4 bg-red-900/20 border border-red-800 rounded-lg flex items-center gap-3">
          <AlertCircle size={20} className="text-red-400" />
          <span className="text-red-400">{error}</span>
        </div>
      )}

      {/* Form */}
      <form onSubmit={handleSubmit} className="space-y-6">
        {/* Account ID */}
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">
            AWS Account ID <span className="text-red-400">*</span>
          </label>
          <input
            type="text"
            value={form.accountId}
            onChange={(e) => setForm({ ...form, accountId: e.target.value })}
            disabled={isEdit}
            placeholder="123456789012"
            pattern="[0-9]{12}"
            className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none disabled:opacity-50"
          />
          <p className="mt-1 text-xs text-gray-500">12-digit AWS account ID</p>
        </div>

        {/* Display Name */}
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">
            Display Name
          </label>
          <input
            type="text"
            value={form.displayName}
            onChange={(e) => setForm({ ...form, displayName: e.target.value })}
            placeholder="Production Account"
            className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
          />
        </div>

        {/* Default Region */}
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">
            Default Region
          </label>
          <select
            value={form.defaultRegion}
            onChange={(e) => setForm({ ...form, defaultRegion: e.target.value })}
            className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white focus:border-blue-500 focus:outline-none"
          >
            {AWS_REGIONS.map((region) => (
              <option key={region.value} value={region.value}>
                {region.label} ({region.value})
              </option>
            ))}
          </select>
          <p className="mt-1 text-xs text-gray-500">
            Default region for resource discovery (can be overridden per environment)
          </p>
        </div>

        {/* Read Role ARN */}
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">
            Read Role ARN <span className="text-red-400">*</span>
          </label>
          <div className="flex gap-2">
            <input
              type="text"
              value={form.readRoleArn}
              onChange={(e) => setForm({ ...form, readRoleArn: e.target.value })}
              placeholder="arn:aws:iam::123456789012:role/dashboard-read"
              className="flex-1 px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
            />
            <button
              type="button"
              onClick={handleTestReadRole}
              disabled={!form.readRoleArn || testingRead}
              className="flex items-center gap-2 px-3 py-2 text-sm bg-gray-700 hover:bg-gray-600 text-white rounded-lg disabled:opacity-50"
              title="Test role assumption"
            >
              {testingRead ? (
                <RefreshCw size={14} className="animate-spin" />
              ) : (
                <Zap size={14} />
              )}
              Test
              <TestResultBadge result={readTestResult} testing={testingRead} />
            </button>
          </div>
          <p className="mt-1 text-xs text-gray-500">
            IAM role ARN for read-only access (discovery, listing resources)
          </p>
          {readTestResult && (
            <div className={`mt-2 p-2 rounded text-xs ${
              readTestResult.success
                ? 'bg-green-900/20 text-green-400'
                : 'bg-red-900/20 text-red-400'
            }`}>
              {readTestResult.success
                ? `Assumed: ${readTestResult.arn}`
                : `Error: ${readTestResult.error}`}
            </div>
          )}
        </div>

        {/* Action Role ARN */}
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">
            Action Role ARN
          </label>
          <div className="flex gap-2">
            <input
              type="text"
              value={form.actionRoleArn}
              onChange={(e) => setForm({ ...form, actionRoleArn: e.target.value })}
              placeholder="arn:aws:iam::123456789012:role/dashboard-write"
              className="flex-1 px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
            />
            <button
              type="button"
              onClick={handleTestActionRole}
              disabled={!form.actionRoleArn || testingAction}
              className="flex items-center gap-2 px-3 py-2 text-sm bg-gray-700 hover:bg-gray-600 text-white rounded-lg disabled:opacity-50"
              title="Test role assumption"
            >
              {testingAction ? (
                <RefreshCw size={14} className="animate-spin" />
              ) : (
                <Zap size={14} />
              )}
              Test
              <TestResultBadge result={actionTestResult} testing={testingAction} />
            </button>
          </div>
          <p className="mt-1 text-xs text-gray-500">
            IAM role ARN for write operations (optional)
          </p>
          {actionTestResult && (
            <div className={`mt-2 p-2 rounded text-xs ${
              actionTestResult.success
                ? 'bg-green-900/20 text-green-400'
                : 'bg-red-900/20 text-red-400'
            }`}>
              {actionTestResult.success
                ? `Assumed: ${actionTestResult.arn}`
                : `Error: ${actionTestResult.error}`}
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="flex items-center gap-3 pt-4 border-t border-gray-800">
          <button
            type="submit"
            disabled={saving}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg disabled:opacity-50"
          >
            {saving ? (
              <RefreshCw size={16} className="animate-spin" />
            ) : (
              <Save size={16} />
            )}
            {isEdit ? 'Save Changes' : 'Create Account'}
          </button>
          <Link
            to="/admin/config/accounts"
            className="px-4 py-2 text-gray-400 hover:text-white"
          >
            Cancel
          </Link>
        </div>
      </form>
    </div>
  );
}
