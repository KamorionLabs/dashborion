import { useState } from 'react'
import { Search, X, Eye, EyeOff, Key } from 'lucide-react'
import CollapsibleSection from './CollapsibleSection'

/**
 * Unified panel for displaying environment variables and secrets
 * Used in both ServiceDetailsPanel and TaskDetails
 */
export default function EnvVarsSecretsPanel({
  environmentVariables = [],
  secrets = [],
  consoleUrls = null,
  title = 'Environment Variables & Secrets',
  className = '',
  variant = 'panel',
  showTitle = true,
  emptyMessage = null,
  collapsible = false,
  defaultOpen = true
}) {
  const [search, setSearch] = useState('')
  const [showSecrets, setShowSecrets] = useState({})

  // Combine and sort all variables
  const allVars = [
    ...environmentVariables.map(v => ({ ...v, type: 'plain' })),
    ...secrets.map(s => ({ ...s, type: 'secret' }))
  ].sort((a, b) => a.name.localeCompare(b.name))

  // Filter based on search
  const filteredVars = allVars.filter(v =>
    v.name.toLowerCase().includes(search.toLowerCase()) ||
    (v.value && v.value.toLowerCase().includes(search.toLowerCase()))
  )

  const toggleSecret = (name) => {
    setShowSecrets(prev => ({ ...prev, [name]: !prev[name] }))
  }

  // Handle empty state
  if (allVars.length === 0) {
    if (emptyMessage) {
      return <p className="text-gray-500 text-sm">{emptyMessage}</p>
    }
    return null
  }

  const itemClass = variant === 'panel' ? 'bg-gray-800' : 'bg-gray-900'

  const content = (
    <>
      {/* Search field */}
      <div className="relative mb-3">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search variables..."
          className="w-full pl-9 pr-8 py-2 bg-gray-800 border border-gray-700 rounded text-sm text-gray-300 placeholder-gray-500 focus:outline-none focus:border-brand-500"
        />
        {search && (
          <button
            onClick={() => setSearch('')}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 hover:text-white"
          >
            <X className="w-4 h-4" />
          </button>
        )}
      </div>

      {/* Variables list */}
      <div className="space-y-2 max-h-60 overflow-y-auto scrollbar-brand">
        {filteredVars.length === 0 && search ? (
          <p className="text-gray-500 text-sm text-center py-4">No variables matching "{search}"</p>
        ) : (
          filteredVars.map((v, i) => (
            <div key={i} className={`${itemClass} rounded p-2`}>
              <div className="flex items-center justify-between">
                <span className="text-sm font-mono text-brand-400">{v.name}</span>
                <div className="flex items-center gap-2">
                  {v.type === 'secret' ? (
                    <span className="px-1.5 py-0.5 bg-purple-500/20 text-purple-400 text-xs rounded">secret</span>
                  ) : (
                    <span className="px-1.5 py-0.5 bg-blue-500/20 text-blue-400 text-xs rounded">plain</span>
                  )}
                  {v.type === 'plain' && (
                    <button
                      onClick={() => toggleSecret(v.name)}
                      className="text-gray-400 hover:text-white"
                    >
                      {showSecrets[v.name] ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                  )}
                </div>
              </div>
              <div className="mt-1 text-xs font-mono text-gray-500 break-all">
                {v.type === 'secret' ? (
                  v.secretName && consoleUrls?.ssoPortalUrl ? (
                    <a
                      href={`${consoleUrls.ssoPortalUrl}/#/console?account_id=${consoleUrls.accountId}&destination=${encodeURIComponent(`https://${consoleUrls.region}.console.aws.amazon.com/secretsmanager/secret?name=${encodeURIComponent(v.secretName)}&region=${consoleUrls.region}`)}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="italic text-purple-400 hover:text-purple-300 hover:underline"
                      title={`Open ${v.secretName} in Secrets Manager`}
                    >
                      {v.valueFrom}
                    </a>
                  ) : (
                    <span className="italic">{v.valueFrom}</span>
                  )
                ) : (
                  <span className={v.value === '***MASKED***' ? 'text-yellow-400' : 'text-gray-300'}>
                    {showSecrets[v.name] ? v.value : '••••••••'}
                  </span>
                )}
              </div>
            </div>
          ))
        )}
      </div>
    </>
  )

  // Collapsible mode: use CollapsibleSection
  if (collapsible) {
    return (
      <CollapsibleSection
        title={`${title} (${allVars.length})`}
        icon={Key}
        iconColor="text-green-400"
        defaultOpen={defaultOpen}
        className={className}
      >
        {content}
      </CollapsibleSection>
    )
  }

  // Inline mode (for tabs): no wrapper
  if (variant === 'inline') {
    return <div className={`space-y-4 ${className}`}>{content}</div>
  }

  // Panel mode: with wrapper and title
  return (
    <div className={`bg-gray-900 rounded-lg p-4 ${className}`}>
      {showTitle && (
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-medium text-gray-300 flex items-center gap-2">
            <Key className="w-4 h-4 text-green-400" />
            {title}
            <span className="text-gray-500 text-xs">({allVars.length})</span>
          </h3>
        </div>
      )}
      {content}
    </div>
  )
}
