/**
 * Network Resource Handlers (VPC, Subnets, Route Tables, Endpoints, etc.)
 */
import { registerResourceHandler } from '../utils/infraResourceHandlers'

// Subnets
registerResourceHandler('subnet', {
  getId: (data) => data?.subnetId || data?.id,
  findInInfra: (id, infraData) => {
    const subnets = infraData?.network?.subnets
    return subnets?.find(s => s.subnetId === id || s.id === id)
  },
  findAll: (infraData) => infraData?.network?.subnets,
})

// Route Tables
registerResourceHandler('routeTable', {
  getId: (data) => data?.routeTableId || data?.id,
  findInInfra: (id, infraData) => {
    const tables = infraData?.network?.routeTables
    return tables?.find(r => r.routeTableId === id || r.id === id)
  },
  findAll: (infraData) => infraData?.network?.routeTables,
})

// VPC Endpoints
registerResourceHandler('endpoint', {
  getId: (data) => data?.vpcEndpointId || data?.id,
  findInInfra: (id, infraData) => {
    const endpoints = infraData?.network?.endpoints
    return endpoints?.find(e => e.vpcEndpointId === id || e.id === id)
  },
  findAll: (infraData) => infraData?.network?.endpoints,
})

// VPC
registerResourceHandler('vpc', {
  getId: (data) => data?.vpcId || data?.id,
  findInInfra: (id, infraData) => {
    const vpc = infraData?.network?.vpc
    return vpc?.vpcId === id || vpc?.id === id ? vpc : null
  },
  findAll: (infraData) => infraData?.network?.vpc,
})

// Internet Gateway
registerResourceHandler('igw', {
  getId: (data) => data?.internetGatewayId || data?.id,
  findInInfra: (id, infraData) => {
    const igw = infraData?.network?.igw
    return igw?.internetGatewayId === id || igw?.id === id ? igw : null
  },
  findAll: (infraData) => infraData?.network?.igw,
})

// VPC Peerings
registerResourceHandler('peering', {
  getId: (data) => data?.vpcPeeringConnectionId || data?.id,
  findInInfra: (id, infraData) => {
    const peerings = infraData?.network?.peerings
    return peerings?.find(p => p.vpcPeeringConnectionId === id || p.id === id)
  },
  findAll: (infraData) => infraData?.network?.peerings,
})

// VPN Connections
registerResourceHandler('vpn', {
  getId: (data) => data?.vpnConnectionId || data?.id,
  findInInfra: (id, infraData) => {
    const vpns = infraData?.network?.vpns
    return vpns?.find(v => v.vpnConnectionId === id || v.id === id)
  },
  findAll: (infraData) => infraData?.network?.vpns,
})

// Transit Gateway
registerResourceHandler('tgw', {
  getId: (data) => data?.transitGatewayId || data?.id,
  findInInfra: (id, infraData) => {
    const tgw = infraData?.network?.tgw
    return tgw?.transitGatewayId === id || tgw?.id === id ? tgw : null
  },
  findAll: (infraData) => infraData?.network?.tgw,
})
