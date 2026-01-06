import { Database, Network, Shield, Clock, ExternalLink } from 'lucide-react'
import SecurityGroupsPanel from './SecurityGroupsPanel'
import CollapsibleSection from '../common/CollapsibleSection'

export default function RedisDetails({ redis, env }) {
  if (!redis || redis.error) {
    return <p className="text-red-400">{redis?.error || 'Redis data not available'}</p>
  }

  return (
    <div className="space-y-4">
      {/* General Info */}
      <CollapsibleSection title="Cache Info" icon={Database} iconColor="text-red-400">
        <div className="space-y-2 text-sm">
          <div className="flex justify-between">
            <span className="text-gray-500">Cluster ID</span>
            <span className="text-gray-300 font-mono text-xs">{redis.clusterId}</span>
          </div>
          {redis.replicationGroupId && (
            <div className="flex justify-between">
              <span className="text-gray-500">Replication Group</span>
              <span className="text-gray-300 font-mono text-xs">{redis.replicationGroupId}</span>
            </div>
          )}
          <div className="flex justify-between">
            <span className="text-gray-500">Engine</span>
            <span className="text-gray-300">{redis.engine} {redis.engineVersion}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-500">Node Type</span>
            <span className="text-gray-300">{redis.cacheNodeType}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-500">Status</span>
            <span className={redis.status === 'available' ? 'text-green-400' : 'text-yellow-400'}>{redis.status}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-500">Num Nodes</span>
            <span className="text-gray-300">{redis.numCacheNodes}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-500">Availability Zone</span>
            <span className="text-gray-300">{redis.preferredAvailabilityZone}</span>
          </div>
        </div>
      </CollapsibleSection>

      {/* Connection Info */}
      {redis.endpoint && (
        <CollapsibleSection title="Connection" icon={Network} iconColor="text-gray-400">
          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-gray-500">Endpoint</span>
              <span className="text-gray-300 font-mono text-xs truncate max-w-[200px]" title={redis.endpoint.address}>{redis.endpoint.address}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Port</span>
              <span className="text-gray-300">{redis.endpoint.port}</span>
            </div>
          </div>
        </CollapsibleSection>
      )}

      {/* Security */}
      <CollapsibleSection title="Security" icon={Shield} iconColor="text-gray-400" defaultOpen={false}>
        <div className="space-y-2 text-sm">
          <div className="flex justify-between">
            <span className="text-gray-500">Transit Encryption</span>
            <span className={redis.transitEncryption ? 'text-green-400' : 'text-red-400'}>{redis.transitEncryption ? 'Enabled' : 'Disabled'}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-500">At-Rest Encryption</span>
            <span className={redis.atRestEncryption ? 'text-green-400' : 'text-red-400'}>{redis.atRestEncryption ? 'Enabled' : 'Disabled'}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-500">Auth Token</span>
            <span className={redis.authTokenEnabled ? 'text-green-400' : 'text-yellow-400'}>{redis.authTokenEnabled ? 'Enabled' : 'Disabled'}</span>
          </div>
        </div>
      </CollapsibleSection>

      {/* Security Groups (Firewalling) */}
      {redis.securityGroups?.length > 0 && (
        <SecurityGroupsPanel securityGroups={redis.securityGroups} env={env} title="Security Groups (Firewalling)" />
      )}

      {/* Maintenance & Backup */}
      <CollapsibleSection title="Maintenance & Backup" icon={Clock} iconColor="text-gray-400" defaultOpen={false}>
        <div className="space-y-2 text-sm">
          <div className="flex justify-between">
            <span className="text-gray-500">Snapshot Retention</span>
            <span className="text-gray-300">{redis.snapshotRetentionLimit} days</span>
          </div>
          {redis.snapshotWindow && (
            <div className="flex justify-between">
              <span className="text-gray-500">Snapshot Window</span>
              <span className="text-gray-300">{redis.snapshotWindow}</span>
            </div>
          )}
          {redis.maintenanceWindow && (
            <div className="flex justify-between">
              <span className="text-gray-500">Maintenance Window</span>
              <span className="text-gray-300">{redis.maintenanceWindow}</span>
            </div>
          )}
          {redis.parameterGroup && (
            <div className="flex justify-between">
              <span className="text-gray-500">Parameter Group</span>
              <span className="text-gray-300 text-xs">{redis.parameterGroup}</span>
            </div>
          )}
        </div>
      </CollapsibleSection>

      {/* Console Link */}
      {redis.consoleUrl && (
        <a href={redis.consoleUrl} target="_blank" rel="noopener noreferrer"
           className="block w-full bg-red-500/20 hover:bg-red-500/30 text-red-400 text-center py-2 rounded-lg text-sm font-medium transition-colors">
          <ExternalLink className="w-4 h-4 inline mr-2" />
          Open in AWS Console
        </a>
      )}
    </div>
  )
}
