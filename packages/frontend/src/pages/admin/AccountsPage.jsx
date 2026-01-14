/**
 * AccountsPage - AWS Accounts Management
 *
 * List and manage AWS accounts for cross-account access.
 */
import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import {
  Cloud,
  Plus,
  RefreshCw,
  AlertCircle,
  Trash2,
  Edit,
  CheckCircle,
  XCircle,
} from 'lucide-react';
import { fetchWithRetry } from '../../utils/fetch';

export default function AccountsPage() {
  const [accounts, setAccounts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [deleting, setDeleting] = useState(null);

  const fetchAccounts = async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await fetchWithRetry('/api/config/aws-accounts');

      if (!response.ok) {
        throw new Error('Failed to fetch accounts');
      }

      const data = await response.json();
      setAccounts(data.awsAccounts || []);
    } catch (err) {
      console.error('Error fetching accounts:', err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAccounts();
  }, []);

  const handleDelete = async (accountId) => {
    if (!confirm(`Delete AWS account ${accountId}?`)) {
      return;
    }

    setDeleting(accountId);

    try {
      const response = await fetchWithRetry(`/api/config/aws-accounts/${accountId}`, {
        method: 'DELETE',
      });

      if (!response.ok) {
        throw new Error('Failed to delete account');
      }

      setAccounts(accounts.filter((a) => a.accountId !== accountId));
    } catch (err) {
      console.error('Error deleting account:', err);
      alert(`Error: ${err.message}`);
    } finally {
      setDeleting(null);
    }
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

  if (error) {
    return (
      <div className="p-6">
        <div className="bg-red-900/20 border border-red-800 rounded-lg p-6 text-center">
          <AlertCircle size={48} className="mx-auto text-red-400 mb-4" />
          <h2 className="text-lg font-semibold text-red-400">Error Loading Accounts</h2>
          <p className="text-gray-400 mt-2">{error}</p>
          <button
            onClick={fetchAccounts}
            className="mt-4 px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg text-sm"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-white">AWS Accounts</h1>
          <p className="text-gray-500">Manage cross-account access for resource discovery</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={fetchAccounts}
            className="flex items-center gap-2 px-3 py-2 text-sm text-gray-400 hover:text-white bg-gray-800 hover:bg-gray-700 rounded-lg"
          >
            <RefreshCw size={16} />
            Refresh
          </button>
          <Link
            to="/admin/config/accounts/new"
            className="flex items-center gap-2 px-4 py-2 text-sm text-white bg-blue-600 hover:bg-blue-700 rounded-lg"
          >
            <Plus size={16} />
            Add Account
          </Link>
        </div>
      </div>

      {/* Accounts List */}
      {accounts.length === 0 ? (
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-12 text-center">
          <Cloud size={48} className="mx-auto text-gray-600 mb-4" />
          <h2 className="text-lg font-semibold text-white mb-2">No AWS Accounts</h2>
          <p className="text-gray-500 mb-4">
            Add an AWS account to enable cross-account resource discovery.
          </p>
          <Link
            to="/admin/config/accounts/new"
            className="inline-flex items-center gap-2 px-4 py-2 text-sm text-white bg-blue-600 hover:bg-blue-700 rounded-lg"
          >
            <Plus size={16} />
            Add First Account
          </Link>
        </div>
      ) : (
        <div className="bg-gray-900 border border-gray-800 rounded-lg overflow-hidden">
          <table className="w-full">
            <thead className="bg-gray-850">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                  Account
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                  Region
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                  Read Role
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                  Action Role
                </th>
                <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800">
              {accounts.map((account) => (
                <tr key={account.accountId} className="hover:bg-gray-850">
                  <td className="px-4 py-4">
                    <div className="flex items-center gap-3">
                      <div className="p-2 bg-orange-600/20 rounded-lg">
                        <Cloud size={16} className="text-orange-400" />
                      </div>
                      <div>
                        <div className="text-sm font-medium text-white">
                          {account.displayName || account.accountId}
                        </div>
                        <div className="text-xs text-gray-500">{account.accountId}</div>
                      </div>
                    </div>
                  </td>
                  <td className="px-4 py-4 text-sm text-gray-400">
                    {account.defaultRegion || 'eu-central-1'}
                  </td>
                  <td className="px-4 py-4">
                    {account.readRoleArn ? (
                      <div className="flex items-center gap-1">
                        <CheckCircle size={14} className="text-green-400" />
                        <span className="text-xs text-gray-500 truncate max-w-48">
                          {account.readRoleArn.split('/').pop()}
                        </span>
                      </div>
                    ) : (
                      <div className="flex items-center gap-1">
                        <XCircle size={14} className="text-gray-600" />
                        <span className="text-xs text-gray-600">Not configured</span>
                      </div>
                    )}
                  </td>
                  <td className="px-4 py-4">
                    {account.actionRoleArn ? (
                      <div className="flex items-center gap-1">
                        <CheckCircle size={14} className="text-green-400" />
                        <span className="text-xs text-gray-500 truncate max-w-48">
                          {account.actionRoleArn.split('/').pop()}
                        </span>
                      </div>
                    ) : (
                      <div className="flex items-center gap-1">
                        <XCircle size={14} className="text-gray-600" />
                        <span className="text-xs text-gray-600">Not configured</span>
                      </div>
                    )}
                  </td>
                  <td className="px-4 py-4 text-right">
                    <div className="flex items-center justify-end gap-2">
                      <Link
                        to={`/admin/config/accounts/${account.accountId}`}
                        className="p-2 text-gray-400 hover:text-white hover:bg-gray-700 rounded"
                      >
                        <Edit size={16} />
                      </Link>
                      <button
                        onClick={() => handleDelete(account.accountId)}
                        disabled={deleting === account.accountId}
                        className="p-2 text-gray-400 hover:text-red-400 hover:bg-gray-700 rounded disabled:opacity-50"
                      >
                        {deleting === account.accountId ? (
                          <RefreshCw size={16} className="animate-spin" />
                        ) : (
                          <Trash2 size={16} />
                        )}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
