import { Cloud, Box, Database, Server, GitBranch, X, HardDrive as Bucket, Route, Network, Globe, Shield, Link2, Workflow } from 'lucide-react'
import { useConfig } from '../../ConfigContext'
import RDSDetails from './RDSDetails'
import RedisDetails from './RedisDetails'
import CloudFrontDetails from './CloudFrontDetails'
import ALBDetails from './ALBDetails'
import S3Details from './S3Details'
import { PipelineDetails } from '../pipelines'
import { RouteTableDetails, SubnetDetails, IGWDetails, EndpointDetails, PeeringDetails, VPNDetails, TGWDetails, VPCDetails } from './RoutingDetails'

// TaskDetails will be passed as a prop to avoid circular dependency
export default function InfrastructureDetailsPanel({ component, infrastructure, onClose, onControlRds, onInvalidateCloudfront, actionLoading, onOpenLogsPanel, TaskDetails }) {
  // Get config from context
  const appConfig = useConfig()
  const currentProjectId = appConfig.currentProjectId
  const ENV_COLORS = appConfig.envColors || {}

  const { type, env, data } = component
  const colors = ENV_COLORS[env] || { bg: 'bg-gray-500', text: 'text-gray-400', border: 'border-gray-500' }

  const getTitle = () => {
    switch (type) {
      case 'cloudfront': return 'CloudFront Distribution'
      case 'alb': return 'Application Load Balancer'
      case 's3': return 'S3 Buckets'
      case 'rds': return 'RDS Database'
      case 'redis': return 'Redis Cache'
      case 'task': return `Task ${data?.taskId || ''}`
      case 'pipeline': return `Pipeline ${data?.service || ''}`
      // Routing types
      case 'routeTable': return 'Route Table'
      case 'subnet': return 'Subnet'
      case 'igw': return 'Internet Gateway'
      case 'endpoint': return 'VPC Endpoint'
      case 'peering': return 'VPC Peering'
      case 'vpn': return 'VPN Connection'
      case 'tgw': return 'Transit Gateway'
      case 'vpc': return 'VPC Network'
      default: return 'Infrastructure Details'
    }
  }

  const getIcon = () => {
    switch (type) {
      case 'cloudfront': return <Cloud className="w-5 h-5 text-orange-400" />
      case 'alb': return <Box className="w-5 h-5 text-blue-400" />
      case 's3': return <Bucket className="w-5 h-5 text-purple-400" />
      case 'rds': return <Database className="w-5 h-5 text-cyan-400" />
      case 'redis': return <Database className="w-5 h-5 text-red-400" />
      case 'task': return <Server className={`w-5 h-5 ${data?.isLatest ? 'text-green-400' : 'text-orange-400'}`} />
      case 'pipeline': return <GitBranch className="w-5 h-5 text-purple-400" />
      // Routing types
      case 'routeTable': return <Route className="w-5 h-5 text-cyan-400" />
      case 'subnet': return <Network className="w-5 h-5 text-blue-400" />
      case 'igw': return <Globe className="w-5 h-5 text-green-400" />
      case 'endpoint': return <Shield className="w-5 h-5 text-cyan-400" />
      case 'peering': return <Link2 className="w-5 h-5 text-purple-400" />
      case 'vpn': return <Shield className="w-5 h-5 text-orange-400" />
      case 'tgw': return <Workflow className="w-5 h-5 text-yellow-400" />
      case 'vpc': return <Network className="w-5 h-5 text-indigo-400" />
      default: return <Server className="w-5 h-5 text-gray-400" />
    }
  }

  return (
    <div className="fixed right-0 top-[73px] h-[calc(100vh-73px)] w-[500px] bg-gray-800 border-l border-gray-700 shadow-xl z-40 overflow-y-auto">
      {/* Header */}
      <div className="sticky top-0 bg-gray-800 border-b border-gray-700 p-4 z-10">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            {getIcon()}
            <div>
              <h2 className="text-lg font-semibold">{getTitle()}</h2>
              <span className={`text-sm ${colors?.text}`}>{env}</span>
            </div>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-white">
            <X className="w-5 h-5" />
          </button>
        </div>
      </div>

      {/* Content */}
      <div className="p-4">
        {type === 'cloudfront' && <CloudFrontDetails cloudfront={data} infrastructure={infrastructure} env={env} onInvalidate={onInvalidateCloudfront} actionLoading={actionLoading} />}
        {type === 'alb' && <ALBDetails alb={data} infrastructure={infrastructure} env={env} />}
        {type === 's3' && <S3Details buckets={data} infrastructure={infrastructure} env={env} />}
        {type === 'rds' && <RDSDetails rds={data} env={env} onControlRds={onControlRds} actionLoading={actionLoading} />}
        {type === 'redis' && <RedisDetails redis={data} env={env} />}
        {type === 'task' && TaskDetails && <TaskDetails task={data} env={env} onOpenLogsPanel={onOpenLogsPanel} />}
        {type === 'pipeline' && <PipelineDetails data={data} onOpenLogsPanel={onOpenLogsPanel} />}
        {/* Routing types */}
        {type === 'routeTable' && <RouteTableDetails routeTable={data} env={env} />}
        {type === 'subnet' && <SubnetDetails subnet={data} env={env} currentProjectId={currentProjectId} />}
        {type === 'igw' && <IGWDetails igw={data} env={env} />}
        {type === 'endpoint' && <EndpointDetails endpoint={data} env={env} />}
        {type === 'peering' && <PeeringDetails peering={data} env={env} />}
        {type === 'vpn' && <VPNDetails vpn={data} env={env} />}
        {type === 'tgw' && <TGWDetails tgw={data} env={env} />}
        {type === 'vpc' && <VPCDetails vpc={data} env={env} currentProjectId={currentProjectId} />}
      </div>
    </div>
  )
}
