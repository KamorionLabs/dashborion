/**
 * ComparisonDetailPanel - Slide-over panel for detailed comparison view
 *
 * Shows full comparison details for a specific check type.
 */

import { useState, useEffect } from 'react';
import {
  X,
  CheckCircle,
  AlertTriangle,
  XCircle,
  AlertCircle,
  RefreshCw,
  ChevronDown,
  ChevronRight,
} from 'lucide-react';
import { fetchWithRetry } from '../../utils/fetch';

const STATUS_ICONS = {
  synced: { icon: CheckCircle, color: 'text-green-400', bg: 'bg-green-500/10' },
  differs: { icon: AlertTriangle, color: 'text-yellow-400', bg: 'bg-yellow-500/10' },
  only_source: { icon: AlertCircle, color: 'text-orange-400', bg: 'bg-orange-500/10' },
  only_destination: { icon: AlertCircle, color: 'text-blue-400', bg: 'bg-blue-500/10' },
  missing: { icon: XCircle, color: 'text-gray-400', bg: 'bg-gray-500/10' },
  critical: { icon: XCircle, color: 'text-red-400', bg: 'bg-red-500/10' },
};

/**
 * Collapsible section
 */
function Section({ title, count, defaultOpen = false, children }) {
  const [open, setOpen] = useState(defaultOpen);

  if (!children || (Array.isArray(children) && children.length === 0)) {
    return null;
  }

  return (
    <div className="border border-gray-700 rounded-lg overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between p-3 bg-gray-800 hover:bg-gray-700 transition-colors"
      >
        <div className="flex items-center gap-2">
          {open ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
          <span className="font-medium text-gray-200">{title}</span>
          {count !== undefined && (
            <span className="text-xs text-gray-500">({count})</span>
          )}
        </div>
      </button>
      {open && (
        <div className="p-3 bg-gray-900/50 space-y-2">
          {children}
        </div>
      )}
    </div>
  );
}

/**
 * Status badge for individual items
 */
function StatusBadge({ status }) {
  const config = STATUS_ICONS[status] || STATUS_ICONS.synced;
  const Icon = config.icon;

  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs ${config.bg} ${config.color}`}>
      <Icon className="w-3 h-3" />
      <span className="capitalize">{status?.replace('_', ' ') || 'unknown'}</span>
    </span>
  );
}

/**
 * K8s summary item row (for format 2: status strings per item)
 */
function SummaryItemRow({ name, status }) {
  return (
    <div className="flex items-center justify-between py-2 px-3 bg-gray-800/50 rounded">
      <span className="text-gray-300 font-medium capitalize">{name}</span>
      <StatusBadge status={status} />
    </div>
  );
}

/**
 * K8s Rules comparison (for ingress)
 */
function RulesComparison({ data, sourceLabel, destinationLabel }) {
  if (!data) return null;

  const { sameRules = [], differentRules = [], onlySource = [], onlyDestination = [] } = data;

  return (
    <div className="space-y-3">
      {sameRules.length > 0 && (
        <Section title="Matching Rules" count={sameRules.length} defaultOpen={false}>
          {sameRules.map((rule, i) => (
            <div key={i} className="flex items-center gap-2 text-sm text-gray-400">
              <CheckCircle className="w-3.5 h-3.5 text-green-400" />
              <span>{rule.host}{rule.path}</span>
            </div>
          ))}
        </Section>
      )}

      {differentRules.length > 0 && (
        <Section title="Different Rules" count={differentRules.length} defaultOpen={true}>
          {differentRules.map((rule, i) => (
            <div key={i} className="p-2 bg-gray-800/50 rounded space-y-1">
              <div className="flex items-center gap-2">
                {rule.expected ? (
                  <CheckCircle className="w-3.5 h-3.5 text-yellow-400" />
                ) : (
                  <AlertTriangle className="w-3.5 h-3.5 text-yellow-400" />
                )}
                <span className="text-gray-200 font-medium">{rule.host}{rule.path}</span>
                {rule.expected && (
                  <span className="text-xs text-gray-500">(expected)</span>
                )}
              </div>
              <div className="grid grid-cols-2 gap-2 text-xs ml-6">
                <div>
                  <span className="text-gray-500">{sourceLabel}:</span>{' '}
                  <span className="text-gray-400">{rule.source?.backend}</span>
                </div>
                <div>
                  <span className="text-gray-500">{destinationLabel}:</span>{' '}
                  <span className="text-gray-400">{rule.destination?.backend}</span>
                </div>
              </div>
              {rule.reason && (
                <div className="text-xs text-gray-500 ml-6">{rule.reason}</div>
              )}
            </div>
          ))}
        </Section>
      )}

      {onlySource.length > 0 && (
        <Section title={`Only in ${sourceLabel}`} count={onlySource.length} defaultOpen={true}>
          {onlySource.map((rule, i) => (
            <div key={i} className="flex items-center gap-2 text-sm text-orange-400">
              <AlertCircle className="w-3.5 h-3.5" />
              <span>{rule.host}{rule.path}</span>
              <span className="text-gray-500 text-xs">({rule.backend})</span>
            </div>
          ))}
        </Section>
      )}

      {onlyDestination.length > 0 && (
        <Section title={`Only in ${destinationLabel}`} count={onlyDestination.length} defaultOpen={false}>
          {onlyDestination.map((rule, i) => (
            <div key={i} className="flex items-center gap-2 text-sm text-blue-400">
              <AlertCircle className="w-3.5 h-3.5" />
              <span>{rule.host}{rule.path}</span>
              <span className="text-gray-500 text-xs">({rule.backend})</span>
            </div>
          ))}
        </Section>
      )}
    </div>
  );
}

/**
 * Issues list
 */
function IssuesList({ issues }) {
  if (!issues?.length) return null;

  const severityColors = {
    critical: 'border-red-500/50 bg-red-500/10',
    warning: 'border-yellow-500/50 bg-yellow-500/10',
    info: 'border-blue-500/50 bg-blue-500/10',
  };

  return (
    <Section title="Issues" count={issues.length} defaultOpen={true}>
      {issues.map((issue, i) => (
        <div
          key={i}
          className={`p-3 rounded border ${severityColors[issue.severity] || severityColors.info}`}
        >
          <div className="flex items-center gap-2 text-sm font-medium text-gray-200">
            <AlertTriangle className="w-4 h-4" />
            {issue.issue}
          </div>
          <div className="mt-1 text-xs text-gray-400">{issue.message}</div>
          {issue.secrets && (
            <div className="mt-2 text-xs text-gray-500">
              {issue.secrets.slice(0, 3).join(', ')}
              {issue.secrets.length > 3 && ` +${issue.secrets.length - 3} more`}
            </div>
          )}
        </div>
      ))}
    </Section>
  );
}

/**
 * Main Detail Panel
 */
export default function ComparisonDetailPanel({
  isOpen,
  onClose,
  project,
  sourceEnv,
  destEnv,
  checkType,
  sourceLabel = 'Source',
  destinationLabel = 'Destination',
}) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [data, setData] = useState(null);

  useEffect(() => {
    if (isOpen && checkType) {
      fetchDetail();
    }
  }, [isOpen, checkType]);

  const fetchDetail = async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await fetchWithRetry(
        `/api/${project}/comparison/${sourceEnv}/${destEnv}/${checkType}`
      );

      if (!response.ok) {
        const err = await response.json();
        throw new Error(err.error || 'Failed to fetch detail');
      }

      const result = await response.json();
      setData(result);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  if (!isOpen) return null;

  // Determine if this is K8s format (summary has string statuses) or config format (summary has counts)
  const isK8sFormat = data?.summary && typeof Object.values(data.summary)[0] === 'string';

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/50 z-40"
        onClick={onClose}
      />

      {/* Panel */}
      <div className="fixed right-0 top-0 h-full w-full max-w-2xl bg-gray-900 border-l border-gray-700 z-50 flex flex-col shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-gray-700">
          <div>
            <h2 className="text-lg font-semibold text-gray-100">{data?.label || checkType}</h2>
            <p className="text-sm text-gray-500">
              {sourceLabel} vs {destinationLabel}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={fetchDetail}
              disabled={loading}
              className="p-2 hover:bg-gray-800 rounded-lg transition-colors"
            >
              <RefreshCw className={`w-5 h-5 text-gray-400 ${loading ? 'animate-spin' : ''}`} />
            </button>
            <button
              onClick={onClose}
              className="p-2 hover:bg-gray-800 rounded-lg transition-colors"
            >
              <X className="w-5 h-5 text-gray-400" />
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <RefreshCw className="w-8 h-8 text-blue-500 animate-spin" />
            </div>
          ) : error ? (
            <div className="text-center py-12">
              <AlertCircle className="w-12 h-12 text-red-500 mx-auto mb-4" />
              <p className="text-red-400">{error}</p>
              <button
                onClick={fetchDetail}
                className="mt-4 px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg text-sm"
              >
                Retry
              </button>
            </div>
          ) : data ? (
            <>
              {/* Status header */}
              <div className="p-4 bg-gray-800 rounded-lg space-y-3">
                <div className="flex items-center justify-between">
                  <StatusBadge status={data.comparisonStatus} />
                  {data.lastUpdated && (
                    <span className="text-xs text-gray-500">
                      Comparison: {new Date(data.lastUpdated).toLocaleString()}
                    </span>
                  )}
                </div>
                {/* Data timestamps - when source/dest data was collected */}
                {(data.timestamp || data.sourceTimestamp || data.destinationTimestamp) && (
                  <div className="flex items-center justify-between text-xs border-t border-gray-700 pt-2">
                    {data.sourceTimestamp && (
                      <span className="text-gray-500">
                        {sourceLabel} data: {new Date(data.sourceTimestamp).toLocaleString()}
                      </span>
                    )}
                    {data.destinationTimestamp && (
                      <span className="text-gray-500">
                        {destinationLabel} data: {new Date(data.destinationTimestamp).toLocaleString()}
                      </span>
                    )}
                    {!data.sourceTimestamp && !data.destinationTimestamp && data.timestamp && (
                      <span className="text-gray-500">
                        Data from: {new Date(data.timestamp).toLocaleString()}
                      </span>
                    )}
                  </div>
                )}
              </div>

              {/* K8s format: show summary items */}
              {isK8sFormat && data.summary && (
                <Section title="Summary" defaultOpen={true}>
                  {Object.entries(data.summary).map(([key, status]) => (
                    <SummaryItemRow key={key} name={key} status={status} />
                  ))}
                </Section>
              )}

              {/* Config format: show counts */}
              {!isK8sFormat && data.summary && (
                <div className="grid grid-cols-2 gap-4">
                  <div className="p-4 bg-gray-800 rounded-lg">
                    <div className="text-2xl font-bold text-gray-100">{data.summary.sourceCount || 0}</div>
                    <div className="text-sm text-gray-500">{sourceLabel} items</div>
                  </div>
                  <div className="p-4 bg-gray-800 rounded-lg">
                    <div className="text-2xl font-bold text-gray-100">{data.summary.destinationCount || 0}</div>
                    <div className="text-sm text-gray-500">{destinationLabel} items</div>
                  </div>
                  <div className="p-4 bg-green-500/10 rounded-lg">
                    <div className="text-2xl font-bold text-green-400">
                      {(data.summary.synced || 0) + (data.summary.differs_expected || 0)}
                    </div>
                    <div className="text-sm text-gray-500">Synced</div>
                  </div>
                  <div className="p-4 bg-yellow-500/10 rounded-lg">
                    <div className="text-2xl font-bold text-yellow-400">
                      {(data.summary.only_source_unexpected || 0) + (data.summary.only_destination_unexpected || 0)}
                    </div>
                    <div className="text-sm text-gray-500">Missing</div>
                  </div>
                </div>
              )}

              {/* K8s ingress: rules comparison */}
              {data.rulesComparison && (
                <div className="space-y-3">
                  {Object.entries(data.rulesComparison).map(([type, comparison]) => (
                    <div key={type} className="space-y-2">
                      <h4 className="text-sm font-medium text-gray-300 capitalize flex items-center gap-2">
                        {type} Ingress
                        <StatusBadge status={comparison.status} />
                      </h4>
                      <RulesComparison
                        data={comparison}
                        sourceLabel={sourceLabel}
                        destinationLabel={destinationLabel}
                      />
                    </div>
                  ))}
                </div>
              )}

              {/* Hosts comparison */}
              {data.hostsComparison && (
                <Section title="Hosts" defaultOpen={false}>
                  <div className="grid grid-cols-2 gap-4 text-sm">
                    <div>
                      <div className="text-gray-500 mb-1">{sourceLabel}</div>
                      {data.hostsComparison.source?.map((h, i) => (
                        <div key={i} className="text-gray-400">{h}</div>
                      ))}
                    </div>
                    <div>
                      <div className="text-gray-500 mb-1">{destinationLabel}</div>
                      {data.hostsComparison.destination?.map((h, i) => (
                        <div key={i} className="text-gray-400">{h}</div>
                      ))}
                    </div>
                  </div>
                  {data.hostsComparison.onlySource?.length > 0 && (
                    <div className="mt-2 pt-2 border-t border-gray-700">
                      <div className="text-orange-400 text-xs mb-1">Only in {sourceLabel}:</div>
                      {data.hostsComparison.onlySource.map((h, i) => (
                        <div key={i} className="text-orange-400/70 text-sm">{h}</div>
                      ))}
                    </div>
                  )}
                </Section>
              )}

              {/* Config format: details sections */}
              {data.details && (
                <>
                  {data.details.synced?.length > 0 && (
                    <Section title="Synced Items" count={data.details.synced.length} defaultOpen={false}>
                      {data.details.synced.map((item, i) => (
                        <div key={i} className="flex items-center gap-2 text-sm text-green-400">
                          <CheckCircle className="w-3.5 h-3.5" />
                          <span className="text-gray-400">{item.sourceSecret || item.secret}</span>
                        </div>
                      ))}
                    </Section>
                  )}

                  {data.details.differs_expected?.length > 0 && (
                    <Section title="Expected Differences" count={data.details.differs_expected.length} defaultOpen={false}>
                      {data.details.differs_expected.map((item, i) => (
                        <div key={i} className="p-2 bg-gray-800/50 rounded">
                          <div className="text-sm text-gray-300">{item.sourceSecret}</div>
                          {item.transformationApplied && (
                            <div className="text-xs text-gray-500 mt-1">{item.transformationApplied}</div>
                          )}
                        </div>
                      ))}
                    </Section>
                  )}

                  {data.details.only_source_unexpected?.length > 0 && (
                    <Section title={`Only in ${sourceLabel}`} count={data.details.only_source_unexpected.length} defaultOpen={true}>
                      {data.details.only_source_unexpected.map((item, i) => (
                        <div key={i} className="flex items-center gap-2 text-sm text-orange-400">
                          <AlertCircle className="w-3.5 h-3.5" />
                          <span>{item.secret}</span>
                        </div>
                      ))}
                    </Section>
                  )}

                  {data.details.only_destination_unexpected?.length > 0 && (
                    <Section title={`Only in ${destinationLabel}`} count={data.details.only_destination_unexpected.length} defaultOpen={false}>
                      {data.details.only_destination_unexpected.map((item, i) => (
                        <div key={i} className="flex items-center gap-2 text-sm text-blue-400">
                          <AlertCircle className="w-3.5 h-3.5" />
                          <span>{item.secret}</span>
                        </div>
                      ))}
                    </Section>
                  )}
                </>
              )}

              {/* Issues */}
              <IssuesList issues={data.issues} />

              {/* Raw data for debugging (collapsed) */}
              <Section title="Raw Data" defaultOpen={false}>
                <pre className="text-xs text-gray-500 overflow-auto max-h-96">
                  {JSON.stringify(data, null, 2)}
                </pre>
              </Section>
            </>
          ) : (
            <div className="text-center py-12 text-gray-500">
              No data available
            </div>
          )}
        </div>
      </div>
    </>
  );
}
