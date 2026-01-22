/**
 * Pipeline Discovery Modal
 *
 * Modal for browsing Jenkins jobs or ArgoCD applications
 */
import {
  AlertCircle,
  ChevronRight,
  Folder,
  FolderOpen,
  GitBranch,
  RefreshCw,
  Search,
  X,
} from 'lucide-react';

export default function PipelineDiscoveryModal({
  discovery,
  onClose,
  onFilterChange,
  onNavigate,
  onSelect,
  onRetry,
}) {
  if (!discovery.open) return null;

  const filterText = discovery.filter?.toLowerCase() || '';
  const filteredItems = filterText
    ? discovery.items.filter(item =>
        item.name.toLowerCase().includes(filterText) ||
        (item.path && item.path.toLowerCase().includes(filterText))
      )
    : discovery.items;

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50">
      <div className="bg-gray-900 border border-gray-800 rounded-lg w-full max-w-2xl max-h-[80vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-gray-800">
          <div>
            <h3 className="text-lg font-semibold text-white">
              Browse {discovery.provider === 'jenkins' ? 'Jenkins Jobs' : 'ArgoCD Applications'}
            </h3>
            <p className="text-xs text-gray-500 mt-1">
              Path: {discovery.currentPath || '/'}
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-1 hover:bg-gray-800 rounded"
          >
            <X size={20} className="text-gray-400" />
          </button>
        </div>

        {/* Search filter */}
        <div className="px-4 py-2 border-b border-gray-700">
          <div className="relative">
            <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
            <input
              type="text"
              value={discovery.filter || ''}
              onChange={(e) => onFilterChange(e.target.value)}
              placeholder="Filter items..."
              className="w-full pl-9 pr-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-sm text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
            />
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-auto p-4">
          {discovery.loading ? (
            <div className="flex items-center justify-center py-12">
              <RefreshCw size={24} className="animate-spin text-gray-500" />
            </div>
          ) : discovery.error ? (
            <div className="text-center py-8">
              <AlertCircle size={32} className="mx-auto text-red-400 mb-2" />
              <p className="text-red-400">{discovery.error}</p>
              <button
                onClick={onRetry}
                className="mt-4 px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded"
              >
                Retry
              </button>
            </div>
          ) : discovery.items.length === 0 ? (
            <div className="text-center py-8 text-gray-500">
              No items found
            </div>
          ) : filteredItems.length === 0 ? (
            <div className="text-center py-8 text-gray-500">
              No items match "{discovery.filter}"
            </div>
          ) : (
            <div className="space-y-1">
              {/* Back button for Jenkins folders */}
              {discovery.provider === 'jenkins' && discovery.currentPath !== '/' && (
                <button
                  onClick={() => {
                    const parts = discovery.currentPath.split('/').filter(Boolean);
                    parts.pop();
                    onNavigate(parts.length ? '/' + parts.join('/') : '/');
                  }}
                  className="flex items-center gap-2 w-full px-3 py-2 text-left hover:bg-gray-800 rounded"
                >
                  <Folder size={16} className="text-gray-500" />
                  <span className="text-gray-400">..</span>
                </button>
              )}

              {/* Items list */}
              {filteredItems.map((item, index) => (
                <DiscoveryItem
                  key={`${item.path}-${index}`}
                  item={item}
                  onNavigate={onNavigate}
                  onSelect={onSelect}
                />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function DiscoveryItem({ item, onNavigate, onSelect }) {
  const handleClick = () => {
    if (item.type === 'folder') {
      onNavigate(item.path);
    } else {
      onSelect(item);
    }
  };

  return (
    <div
      className="flex items-center gap-2 px-3 py-2 hover:bg-gray-800 rounded cursor-pointer group"
      onClick={handleClick}
    >
      {item.type === 'folder' ? (
        <FolderOpen size={16} className="text-amber-400" />
      ) : (
        <GitBranch size={16} className="text-green-400" />
      )}
      <div className="flex-1 min-w-0">
        <div className="text-sm text-white truncate">{item.name}</div>
        {item.path && item.type !== 'folder' && (
          <div className="text-xs text-gray-500 truncate">{item.path}</div>
        )}
        {/* ArgoCD status */}
        {item.status && (
          <div className="flex items-center gap-2 mt-1 text-xs">
            <span className={item.status.health === 'Healthy' ? 'text-green-400' : 'text-amber-400'}>
              {item.status.health}
            </span>
            <span className={item.status.sync === 'Synced' ? 'text-green-400' : 'text-yellow-400'}>
              {item.status.sync}
            </span>
          </div>
        )}
        {/* Jenkins parameters preview */}
        {item.parameters?.length > 0 && (
          <div className="flex items-center gap-1 mt-1 text-[10px] text-gray-500">
            <span>{item.parameters.length} params:</span>
            <span className="text-gray-400 truncate">
              {item.parameters.slice(0, 3).map(p => p.name).join(', ')}
              {item.parameters.length > 3 ? '...' : ''}
            </span>
          </div>
        )}
      </div>
      {item.type === 'folder' ? (
        <ChevronRight size={16} className="text-gray-500 opacity-0 group-hover:opacity-100" />
      ) : (
        <span className="text-xs text-blue-400 opacity-0 group-hover:opacity-100">Select</span>
      )}
    </div>
  );
}
