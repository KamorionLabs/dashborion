import { Database, Network, HardDrive, Clock, RefreshCw, Play, Square, ExternalLink, Lock } from 'lucide-react'
import SecurityGroupsPanel from './SecurityGroupsPanel'
import CollapsibleSection from '../common/CollapsibleSection'
import { useAuth } from '../../hooks/useAuth'
import { useConfig } from '../../ConfigContext'

export default function RDSDetails({ rds, env, onControlRds, actionLoading }) {
  const { hasPermission } = useAuth()
  const appConfig = useConfig()
  const currentProjectId = appConfig.currentProjectId

  if (!rds || rds.error) {
    return <p className="text-red-400">{rds?.error || 'RDS data not available'}</p>
  }

  const isStopped = rds.status === 'stopped'
  const isLoading = actionLoading?.[`rds-${env}`]
  // RDS control requires admin role
  const canControlRds = hasPermission('rds-control', currentProjectId, env, 'rds')

  return (
    <div className="space-y-4">
      {/* General Info */}
      <CollapsibleSection title="Database Info" icon={Database} iconColor="text-cyan-400">
        <div className="space-y-2 text-sm">
          <div className="flex justify-between">
            <span className="text-gray-500">Identifier</span>
            <span className="text-gray-300 font-mono">{rds.identifier}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-500">Engine</span>
            <span className="text-gray-300">{rds.engine} {rds.engineVersion}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-500">Instance Class</span>
            <span className="text-gray-300">{rds.instanceClass}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-500">Status</span>
            <span className={rds.status === 'available' ? 'text-green-400' : 'text-yellow-400'}>{rds.status}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-500">Multi-AZ</span>
            <span className={rds.multiAz ? 'text-green-400' : 'text-gray-400'}>{rds.multiAz ? 'Yes' : 'No'}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-500">Availability Zone</span>
            <span className="text-gray-300">{rds.availabilityZone}</span>
          </div>
        </div>
      </CollapsibleSection>

      {/* Connection Info */}
      <CollapsibleSection title="Connection" icon={Network} iconColor="text-gray-400">
        <div className="space-y-2 text-sm">
          <div className="flex justify-between">
            <span className="text-gray-500">Endpoint</span>
            <span className="text-gray-300 font-mono text-xs truncate max-w-[200px]" title={rds.endpoint}>{rds.endpoint}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-500">Port</span>
            <span className="text-gray-300">{rds.port}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-500">Database Name</span>
            <span className="text-gray-300">{rds.dbName || '-'}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-500">Master Username</span>
            <span className="text-gray-300">{rds.masterUsername}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-500">Public Access</span>
            <span className={rds.publiclyAccessible ? 'text-red-400' : 'text-green-400'}>{rds.publiclyAccessible ? 'Yes' : 'No'}</span>
          </div>
        </div>
      </CollapsibleSection>

      {/* Storage Info */}
      <CollapsibleSection title="Storage" icon={HardDrive} iconColor="text-gray-400" defaultOpen={false}>
        <div className="space-y-2 text-sm">
          <div className="flex justify-between">
            <span className="text-gray-500">Allocated</span>
            <span className="text-gray-300">{rds.storage?.allocated} GB</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-500">Type</span>
            <span className="text-gray-300">{rds.storage?.type}</span>
          </div>
          {rds.storage?.iops && (
            <div className="flex justify-between">
              <span className="text-gray-500">IOPS</span>
              <span className="text-gray-300">{rds.storage.iops}</span>
            </div>
          )}
          <div className="flex justify-between">
            <span className="text-gray-500">Encrypted</span>
            <span className={rds.storage?.encrypted ? 'text-green-400' : 'text-red-400'}>{rds.storage?.encrypted ? 'Yes' : 'No'}</span>
          </div>
        </div>
      </CollapsibleSection>

      {/* Maintenance & Backup */}
      <CollapsibleSection title="Maintenance & Backup" icon={Clock} iconColor="text-gray-400" defaultOpen={false}>
        <div className="space-y-2 text-sm">
          <div className="flex justify-between">
            <span className="text-gray-500">Backup Retention</span>
            <span className="text-gray-300">{rds.backupRetention} days</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-500">Backup Window</span>
            <span className="text-gray-300">{rds.preferredBackupWindow || '-'}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-500">Maintenance Window</span>
            <span className="text-gray-300">{rds.preferredMaintenanceWindow || '-'}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-500">Parameter Group</span>
            <span className="text-gray-300 text-xs">{rds.parameterGroup || '-'}</span>
          </div>
        </div>
      </CollapsibleSection>

      {/* Security Groups */}
      {rds.securityGroups?.length > 0 && (
        <SecurityGroupsPanel securityGroups={rds.securityGroups} env={env} title="Security Groups (Firewalling)" />
      )}

      {/* Actions - requires admin role */}
      {onControlRds && (
        <div className="flex gap-2">
          {!canControlRds ? (
            <div className="flex-1 flex items-center justify-center gap-2 py-2 text-gray-500 text-sm">
              <Lock className="w-4 h-4" />
              <span>Admin access required for RDS control</span>
            </div>
          ) : isStopped ? (
            <button
              onClick={() => onControlRds(env, 'start')}
              disabled={isLoading}
              className="flex-1 flex items-center justify-center gap-2 bg-green-600 hover:bg-green-500 disabled:bg-gray-600 text-white py-2 px-4 rounded-lg text-sm font-medium transition-colors"
            >
              {isLoading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
              Start Database
            </button>
          ) : (
            <button
              onClick={() => onControlRds(env, 'stop')}
              disabled={isLoading || rds.status !== 'available'}
              className="flex-1 flex items-center justify-center gap-2 bg-red-600 hover:bg-red-500 disabled:bg-gray-600 text-white py-2 px-4 rounded-lg text-sm font-medium transition-colors"
            >
              {isLoading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Square className="w-4 h-4" />}
              Stop Database
            </button>
          )}
        </div>
      )}

      {/* Console Link */}
      {rds.consoleUrl && (
        <a href={rds.consoleUrl} target="_blank" rel="noopener noreferrer"
           className="block w-full bg-cyan-500/20 hover:bg-cyan-500/30 text-cyan-400 text-center py-2 rounded-lg text-sm font-medium transition-colors">
          <ExternalLink className="w-4 h-4 inline mr-2" />
          Open in AWS Console
        </a>
      )}
    </div>
  )
}
