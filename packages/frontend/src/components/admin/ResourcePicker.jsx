/**
 * ResourcePicker Component
 *
 * Dropdown selector with AWS resource discovery.
 * Auto-discovers resources when accountId is provided.
 */
import { useState, useEffect, useRef } from 'react';
import { ChevronDown, RefreshCw, AlertCircle, Search, Check } from 'lucide-react';
import { useDiscovery } from '../../hooks/useDiscovery';

/**
 * Resource type configurations
 */
const RESOURCE_CONFIGS = {
  vpc: {
    label: 'VPC',
    displayField: 'name',
    secondaryField: 'cidr',
    idField: 'id',
  },
  route53: {
    label: 'Hosted Zone',
    displayField: 'name',
    secondaryField: 'id',
    idField: 'id',
  },
  eks: {
    label: 'EKS Cluster',
    displayField: 'name',
    secondaryField: 'version',
    idField: 'name',
  },
  ecs: {
    label: 'ECS Cluster',
    displayField: 'name',
    secondaryField: 'status',
    idField: 'name',
  },
  rds: {
    label: 'RDS/Aurora',
    displayField: 'name',
    secondaryField: 'engine',
    idField: 'id',
  },
  documentdb: {
    label: 'DocumentDB',
    displayField: 'name',
    secondaryField: 'engine',
    idField: 'id',
  },
  elasticache: {
    label: 'ElastiCache',
    displayField: 'name',
    secondaryField: 'engine',
    idField: 'id',
  },
  efs: {
    label: 'EFS',
    displayField: 'name',
    secondaryField: 'id',
    idField: 'id',
  },
  alb: {
    label: 'ALB',
    displayField: 'name',
    secondaryField: 'dnsName',
    idField: 'arn',
  },
  sg: {
    label: 'Security Group',
    displayField: 'name',
    secondaryField: 'id',
    idField: 'id',
  },
  s3: {
    label: 'S3 Bucket',
    displayField: 'name',
    secondaryField: 'region',
    idField: 'name',
  },
  cloudfront: {
    label: 'CloudFront',
    displayField: 'id',
    secondaryField: 'domainName',
    idField: 'id',
  },
  'ecs-services': {
    label: 'ECS Service',
    displayField: 'name',
    secondaryField: 'status',
    idField: 'name',
  },
  'eks-workloads': {
    label: 'EKS Workload',
    displayField: 'name',
    secondaryField: 'type',
    idField: 'name',
  },
};

/**
 * ResourcePicker component
 *
 * @param {string} accountId - AWS account ID for discovery
 * @param {string} resourceType - Resource type (vpc, eks, rds, etc.)
 * @param {string} value - Selected value
 * @param {function} onChange - Callback when value changes
 * @param {string} placeholder - Placeholder text
 * @param {string} region - AWS region (optional)
 * @param {string} vpc - VPC ID filter (for sg)
 * @param {string} tags - Tags filter (for alb)
 * @param {string} cluster - Cluster name filter (for ecs-services / eks-workloads)
 * @param {string} namespace - Namespace filter (for eks-workloads)
 * @param {boolean} disabled - Disable the picker
 * @param {boolean} allowManual - Allow manual input
 * @param {string} className - Additional CSS classes
 */
export default function ResourcePicker({
  accountId,
  resourceType,
  value,
  onChange,
  placeholder,
  region,
  vpc,
  tags,
  cluster,
  namespace,
  disabled = false,
  allowManual = true,
  className = '',
}) {
  const [isOpen, setIsOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [manualMode, setManualMode] = useState(false);
  const [manualValue, setManualValue] = useState('');
  const dropdownRef = useRef(null);
  const inputRef = useRef(null);

  const config = RESOURCE_CONFIGS[resourceType] || {
    label: resourceType,
    displayField: 'name',
    secondaryField: 'id',
    idField: 'id',
  };

  const { resources, loading, error, discover } = useDiscovery(
    accountId,
    resourceType,
    { region, vpc, tags, cluster, namespace }
  );

  // Close dropdown on outside click
  useEffect(() => {
    function handleClickOutside(event) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setIsOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Filter resources by search query
  const filteredResources = resources.filter((r) => {
    if (!searchQuery) return true;
    const query = searchQuery.toLowerCase();
    const display = String(r[config.displayField] || '').toLowerCase();
    const secondary = String(r[config.secondaryField] || '').toLowerCase();
    const id = String(r[config.idField] || '').toLowerCase();
    return display.includes(query) || secondary.includes(query) || id.includes(query);
  });

  // Find selected resource for display
  const selectedResource = resources.find(
    (r) => r[config.idField] === value || r.name === value || r.id === value
  );

  const handleSelect = (resource) => {
    onChange(resource[config.idField]);
    setIsOpen(false);
    setSearchQuery('');
    setManualMode(false);
  };

  const handleManualSubmit = () => {
    if (manualValue.trim()) {
      onChange(manualValue.trim());
      setManualMode(false);
      setManualValue('');
      setIsOpen(false);
    }
  };

  const handleOpen = () => {
    if (disabled) return;
    setIsOpen(true);
    // Auto-discover if not already loaded
    if (accountId && resources.length === 0 && !loading && !error) {
      discover();
    }
  };

  return (
    <div ref={dropdownRef} className={`relative ${className}`}>
      {/* Main button */}
      <button
        type="button"
        onClick={handleOpen}
        disabled={disabled}
        className={`w-full flex items-center justify-between px-3 py-2 text-left bg-gray-800 border border-gray-700 rounded-lg transition-colors ${
          disabled
            ? 'opacity-50 cursor-not-allowed'
            : 'hover:border-gray-600 focus:border-blue-500 focus:outline-none'
        }`}
      >
        <span className={selectedResource ? 'text-white' : 'text-gray-500'}>
          {selectedResource ? (
            <span className="flex items-center gap-2">
              <span>{selectedResource[config.displayField]}</span>
              {selectedResource[config.secondaryField] && (
                <span className="text-xs text-gray-500">
                  ({selectedResource[config.secondaryField]})
                </span>
              )}
            </span>
          ) : value ? (
            <span className="text-gray-400">{value}</span>
          ) : (
            placeholder || `Select ${config.label}...`
          )}
        </span>
        <ChevronDown size={16} className="text-gray-500" />
      </button>

      {/* Dropdown */}
      {isOpen && (
        <div className="absolute z-50 w-full mt-1 bg-gray-800 border border-gray-700 rounded-lg shadow-lg max-h-80 overflow-hidden">
          {/* Search input */}
          <div className="p-2 border-b border-gray-700">
            <div className="relative">
              <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
              <input
                ref={inputRef}
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder={`Search ${config.label}...`}
                className="w-full pl-9 pr-3 py-2 bg-gray-900 border border-gray-700 rounded text-sm text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
                autoFocus
              />
            </div>
          </div>

          {/* Actions bar */}
          <div className="flex items-center justify-between px-3 py-2 border-b border-gray-700 bg-gray-850">
            <button
              type="button"
              onClick={() => discover()}
              disabled={loading || !accountId}
              className="flex items-center gap-1 text-xs text-blue-400 hover:text-blue-300 disabled:opacity-50"
            >
              <RefreshCw size={12} className={loading ? 'animate-spin' : ''} />
              Refresh
            </button>
            {allowManual && (
              <button
                type="button"
                onClick={() => setManualMode(!manualMode)}
                className="text-xs text-gray-400 hover:text-white"
              >
                {manualMode ? 'Select from list' : 'Enter manually'}
              </button>
            )}
          </div>

          {/* Manual input mode */}
          {manualMode && allowManual && (
            <div className="p-3 border-b border-gray-700">
              <div className="flex gap-2">
                <input
                  type="text"
                  value={manualValue}
                  onChange={(e) => setManualValue(e.target.value)}
                  placeholder={`Enter ${config.label} ID...`}
                  className="flex-1 px-3 py-2 bg-gray-900 border border-gray-700 rounded text-sm text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
                  onKeyDown={(e) => e.key === 'Enter' && handleManualSubmit()}
                />
                <button
                  type="button"
                  onClick={handleManualSubmit}
                  className="px-3 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm rounded"
                >
                  Add
                </button>
              </div>
            </div>
          )}

          {/* Resource list */}
          <div className="overflow-y-auto max-h-48">
            {!accountId && (
              <div className="p-4 text-center text-gray-500 text-sm">
                Select an AWS account first
              </div>
            )}

            {accountId && loading && (
              <div className="p-4 text-center">
                <RefreshCw size={20} className="animate-spin mx-auto text-gray-500" />
                <p className="mt-2 text-sm text-gray-500">Discovering resources...</p>
              </div>
            )}

            {accountId && error && (
              <div className="p-4 text-center">
                <AlertCircle size={20} className="mx-auto text-red-400" />
                <p className="mt-2 text-sm text-red-400">{error}</p>
                <button
                  type="button"
                  onClick={() => discover()}
                  className="mt-2 text-xs text-blue-400 hover:text-blue-300"
                >
                  Retry
                </button>
              </div>
            )}

            {accountId && !loading && !error && filteredResources.length === 0 && (
              <div className="p-4 text-center text-gray-500 text-sm">
                {searchQuery ? 'No matching resources' : 'No resources found'}
              </div>
            )}

            {accountId && !loading && !error && filteredResources.map((resource) => (
              <button
                key={resource[config.idField]}
                type="button"
                onClick={() => handleSelect(resource)}
                className={`w-full flex items-center justify-between px-3 py-2 text-left hover:bg-gray-700 transition-colors ${
                  value === resource[config.idField] ? 'bg-blue-600/20' : ''
                }`}
              >
                <div className="min-w-0 flex-1">
                  <div className="text-sm text-white truncate">
                    {resource[config.displayField]}
                  </div>
                  {resource[config.secondaryField] && (
                    <div className="text-xs text-gray-500 truncate">
                      {resource[config.secondaryField]}
                    </div>
                  )}
                </div>
                {value === resource[config.idField] && (
                  <Check size={16} className="text-blue-400 ml-2 flex-shrink-0" />
                )}
              </button>
            ))}
          </div>

          {/* Footer with count */}
          {accountId && !loading && resources.length > 0 && (
            <div className="px-3 py-2 border-t border-gray-700 text-xs text-gray-500">
              {filteredResources.length} of {resources.length} {config.label}s
            </div>
          )}
        </div>
      )}
    </div>
  );
}
