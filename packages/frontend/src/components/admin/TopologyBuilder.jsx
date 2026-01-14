import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import ReactFlow, {
  addEdge,
  Background,
  Controls,
  MiniMap,
  useEdgesState,
  useNodesState
} from 'reactflow'
import 'reactflow/dist/style.css'
import { LayoutGrid, Link2, Plus, RotateCcw, Trash2 } from 'lucide-react'

const DEFAULT_LAYERS = ['edge', 'ingress', 'frontend', 'proxy', 'application', 'search', 'data']
const LAYER_LABELS = {
  edge: 'Edge',
  ingress: 'Ingress',
  frontend: 'Frontend',
  proxy: 'Proxy',
  application: 'Application',
  search: 'Search',
  data: 'Data'
}

const LAYER_COLORS = {
  edge: '#f97316',
  ingress: '#3b82f6',
  frontend: '#8b5cf6',
  proxy: '#06b6d4',
  application: '#10b981',
  search: '#f59e0b',
  data: '#06b6d4'
}

const COMPONENT_TYPES = [
  { value: 'cdn', label: 'CDN' },
  { value: 'loadbalancer', label: 'Load Balancer' },
  { value: 'ecs-service', label: 'ECS Service' },
  { value: 'k8s-deployment', label: 'K8s Deployment' },
  { value: 'k8s-statefulset', label: 'K8s StatefulSet' },
  { value: 'rds', label: 'RDS' },
  { value: 'elasticache', label: 'ElastiCache' },
  { value: 'efs', label: 'EFS' },
  { value: 's3', label: 'S3' },
  { value: 'custom', label: 'Custom' }
]

const INFRA_TEMPLATES = [
  { id: 'cloudfront', label: 'CloudFront', type: 'cdn', layer: 'edge' },
  { id: 'alb', label: 'ALB', type: 'loadbalancer', layer: 'ingress' },
  { id: 'rds', label: 'RDS', type: 'rds', layer: 'data' },
  { id: 'redis', label: 'Redis', type: 'elasticache', layer: 'data' },
  { id: 'efs', label: 'EFS', type: 'efs', layer: 'data' },
  { id: 's3', label: 'S3', type: 's3', layer: 'data' }
]

const getDefaultServiceType = (orchestratorType) => {
  if (orchestratorType === 'eks') return 'k8s-deployment'
  return 'ecs-service'
}

const guessLayer = (name, componentType) => {
  if (componentType === 'cdn') return 'edge'
  if (componentType === 'loadbalancer') return 'ingress'
  if (['rds', 'elasticache', 'efs', 's3'].includes(componentType)) return 'data'
  const lower = name.toLowerCase()
  if (lower.includes('next') || lower.includes('front')) return 'frontend'
  if (lower.includes('proxy') || lower.includes('nginx') || lower.includes('apache') || lower.includes('haproxy')) return 'proxy'
  if (lower.includes('search') || lower.includes('solr') || lower.includes('elastic')) return 'search'
  return 'application'
}

const buildLayout = (nodes) => {
  const layerMap = {}
  nodes.forEach((node) => {
    const layer = node.data?.layer || 'application'
    if (!layerMap[layer]) layerMap[layer] = []
    layerMap[layer].push(node)
  })

  const orderedLayers = DEFAULT_LAYERS.filter((layer) => layerMap[layer]?.length)
  const nodeWidth = 170
  const nodeHeight = 70
  const layerGap = 220
  const nodeGap = 110

  const positioned = []
  orderedLayers.forEach((layer, layerIndex) => {
    const layerNodes = layerMap[layer] || []
    layerNodes.forEach((node, nodeIndex) => {
      positioned.push({
        ...node,
        position: {
          x: 40 + layerIndex * layerGap,
          y: 40 + nodeIndex * nodeGap
        },
        style: node.style || {
          width: nodeWidth,
          border: `1px solid ${LAYER_COLORS[layer] || '#334155'}`
        }
      })
    })
  })

  return positioned
}

const normalizeId = (value) => value.trim().replace(/\s+/g, '-')

const buildNodesFromTopology = (topology) => {
  const components = topology?.components || {}
  const layout = topology?.layout?.nodes || {}
  const hasLayout = Object.keys(layout).length > 0
  const nodes = Object.entries(components).map(([id, component]) => {
    const layer = component.layer || guessLayer(id, component.type || 'custom')
    const color = LAYER_COLORS[layer] || '#334155'
    return {
      id,
      data: {
        label: component.label || id,
        componentType: component.type || 'custom',
        layer
      },
      position: layout[id] || { x: 40, y: 40 },
      style: {
        width: 170,
        border: `1px solid ${color}`,
        background: '#0f172a',
        color: '#e2e8f0'
      }
    }
  })

  if (!nodes.length) return []
  if (hasLayout) return nodes
  return buildLayout(nodes)
}

const buildEdgesFromTopology = (topology) => {
  const connections = topology?.connections || []
  return connections.map((conn, idx) => ({
    id: `${conn.from}-${conn.to}-${idx}`,
    source: conn.from,
    target: conn.to,
    label: conn.protocol || '',
    data: { protocol: conn.protocol || '' },
    type: 'smoothstep',
    animated: false
  }))
}

const buildTopologyFromFlow = (nodes, edges, existing) => {
  const components = {}
  nodes.forEach((node) => {
    components[node.id] = {
      type: node.data?.componentType || 'custom',
      layer: node.data?.layer || 'application',
      label: node.data?.label || node.id
    }
  })

  const connections = edges.map((edge) => ({
    from: edge.source,
    to: edge.target,
    protocol: edge.data?.protocol || undefined
  }))

  const layout = {
    nodes: nodes.reduce((acc, node) => {
      acc[node.id] = node.position
      return acc
    }, {})
  }

  const layers = existing?.layers?.length ? existing.layers : DEFAULT_LAYERS
  return { components, connections, layers, layout }
}

export default function TopologyBuilder({ value, onChange, services = [], orchestratorType, suggestedNodes = [] }) {
  const [nodes, setNodes, onNodesChange] = useNodesState([])
  const [edges, setEdges, onEdgesChange] = useEdgesState([])
  const [selectedNodeId, setSelectedNodeId] = useState(null)
  const [selectedEdgeId, setSelectedEdgeId] = useState(null)
  const [serviceToAdd, setServiceToAdd] = useState('')
  const [customNode, setCustomNode] = useState({ id: '', label: '', type: 'custom', layer: 'application' })
  const [edgeProtocol, setEdgeProtocol] = useState('')
  const syncingRef = useRef(false)
  const lastValueRef = useRef('')

  const availableServices = useMemo(() => services.filter(Boolean), [services])
  const defaultServiceType = getDefaultServiceType(orchestratorType)

  useEffect(() => {
    const incoming = JSON.stringify(value || {})
    if (incoming && incoming === lastValueRef.current) return
    syncingRef.current = true
    lastValueRef.current = incoming
    const nextNodes = buildNodesFromTopology(value || {})
    const nextEdges = buildEdgesFromTopology(value || {})
    setNodes(nextNodes)
    setEdges(nextEdges)
    const timer = setTimeout(() => {
      syncingRef.current = false
    }, 0)
    return () => clearTimeout(timer)
  }, [value, setNodes, setEdges])

  useEffect(() => {
    if (syncingRef.current) return
    const next = buildTopologyFromFlow(nodes, edges, value)
    const serialized = JSON.stringify(next)
    if (serialized === lastValueRef.current) return
    lastValueRef.current = serialized
    onChange?.(next)
  }, [nodes, edges, onChange, value])

  const handleConnect = useCallback(
    (params) => setEdges((eds) => addEdge({ ...params, type: 'smoothstep', data: { protocol: '' } }, eds)),
    [setEdges]
  )

  const handleSelectionChange = useCallback((selection) => {
    const node = selection?.nodes?.[0]
    const edge = selection?.edges?.[0]
    setSelectedNodeId(node?.id || null)
    setSelectedEdgeId(edge?.id || null)
    setEdgeProtocol(edge?.data?.protocol || '')
  }, [])

  const addNode = useCallback((node) => {
    setNodes((prev) => {
      if (prev.find((existing) => existing.id === node.id)) return prev
      const layer = node.data?.layer || 'application'
      const color = LAYER_COLORS[layer] || '#334155'
      return [
        ...prev,
        {
          ...node,
          position: node.position || { x: 40, y: 40 },
          style: {
            width: 170,
            border: `1px solid ${color}`,
            background: '#0f172a',
            color: '#e2e8f0'
          }
        }
      ]
    })
  }, [setNodes])

  const handleAddService = () => {
    if (!serviceToAdd) return
    const layer = guessLayer(serviceToAdd, defaultServiceType)
    addNode({
      id: serviceToAdd,
      data: {
        label: serviceToAdd,
        componentType: defaultServiceType,
        layer
      }
    })
    setServiceToAdd('')
  }

  const handleAddCustomNode = () => {
    const id = normalizeId(customNode.id)
    if (!id) return
    addNode({
      id,
      data: {
        label: customNode.label || id,
        componentType: customNode.type || 'custom',
        layer: customNode.layer || guessLayer(id, customNode.type || 'custom')
      }
    })
    setCustomNode({ id: '', label: '', type: 'custom', layer: 'application' })
  }

  const handleAddInfraNodes = () => {
    INFRA_TEMPLATES.forEach((template) => {
      addNode({
        id: template.id,
        data: {
          label: template.label,
          componentType: template.type,
          layer: template.layer
        }
      })
    })
  }

  const handleSyncServices = () => {
    availableServices.forEach((service) => {
      const layer = guessLayer(service, defaultServiceType)
      addNode({
        id: service,
        data: {
          label: service,
          componentType: defaultServiceType,
          layer
        }
      })
    })
  }

  const handleAutoLayout = () => {
    setNodes((prev) => buildLayout(prev))
  }

  const handleRemoveSelected = () => {
    if (selectedNodeId) {
      setNodes((prev) => prev.filter((node) => node.id !== selectedNodeId))
      setEdges((prev) => prev.filter((edge) => edge.source !== selectedNodeId && edge.target !== selectedNodeId))
      setSelectedNodeId(null)
    }
    if (selectedEdgeId) {
      setEdges((prev) => prev.filter((edge) => edge.id !== selectedEdgeId))
      setSelectedEdgeId(null)
    }
  }

  const selectedNode = nodes.find((node) => node.id === selectedNodeId)

  const updateSelectedNode = (updates) => {
    if (!selectedNodeId) return
    setNodes((prev) =>
      prev.map((node) => {
        if (node.id !== selectedNodeId) return node
        const layer = updates.layer || node.data.layer
        const color = LAYER_COLORS[layer] || '#334155'
        return {
          ...node,
          data: { ...node.data, ...updates },
          style: { ...node.style, border: `1px solid ${color}` }
        }
      })
    )
  }

  const updateSelectedEdge = (protocol) => {
    if (!selectedEdgeId) return
    setEdges((prev) =>
      prev.map((edge) => {
        if (edge.id !== selectedEdgeId) return edge
        return {
          ...edge,
          label: protocol || '',
          data: { ...(edge.data || {}), protocol }
        }
      })
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={handleSyncServices}
          className="inline-flex items-center gap-2 px-3 py-1.5 rounded-md bg-gray-800 text-gray-200 hover:bg-gray-700 text-sm"
        >
          <LayoutGrid size={14} />
          Sync services
        </button>
        <button
          type="button"
          onClick={handleAddInfraNodes}
          className="inline-flex items-center gap-2 px-3 py-1.5 rounded-md bg-gray-800 text-gray-200 hover:bg-gray-700 text-sm"
        >
          <Plus size={14} />
          Add infra nodes
        </button>
        <button
          type="button"
          onClick={handleAutoLayout}
          className="inline-flex items-center gap-2 px-3 py-1.5 rounded-md bg-gray-800 text-gray-200 hover:bg-gray-700 text-sm"
        >
          <RotateCcw size={14} />
          Auto layout
        </button>
        <button
          type="button"
          onClick={handleRemoveSelected}
          className="inline-flex items-center gap-2 px-3 py-1.5 rounded-md bg-gray-800 text-gray-200 hover:bg-gray-700 text-sm"
        >
          <Trash2 size={14} />
          Remove selected
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr,320px] gap-4">
        <div className="h-[560px] rounded-lg border border-gray-800 bg-gray-950 overflow-hidden">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={handleConnect}
            onSelectionChange={handleSelectionChange}
            fitView
            fitViewOptions={{ padding: 0.2 }}
          >
            <Background gap={16} color="#1f2937" />
            <MiniMap
              nodeColor={(node) => LAYER_COLORS[node.data?.layer] || '#334155'}
              maskColor="rgba(15, 23, 42, 0.8)"
            />
            <Controls />
          </ReactFlow>
        </div>

        <div className="space-y-4">
          {suggestedNodes.length > 0 && (
            <div className="rounded-lg border border-gray-800 bg-gray-900 p-4">
              <h3 className="text-sm font-semibold text-white mb-3">Suggested nodes</h3>
              <div className="space-y-2">
                {suggestedNodes.map((node) => (
                  <div key={node.id} className="flex items-center justify-between bg-gray-800 rounded-md px-2 py-1.5">
                    <div>
                      <div className="text-sm text-gray-200">{node.label}</div>
                      <div className="text-xs text-gray-500">{node.componentType} · {node.layer}</div>
                    </div>
                    <button
                      type="button"
                      onClick={() => addNode({ id: node.id, data: { label: node.label, componentType: node.componentType, layer: node.layer } })}
                      className="px-2 py-1 text-xs rounded-md bg-gray-700 text-gray-200 hover:bg-gray-600"
                    >
                      Add
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}
          <div className="rounded-lg border border-gray-800 bg-gray-900 p-4">
            <h3 className="text-sm font-semibold text-white mb-3">Add service</h3>
            <div className="flex gap-2">
              <select
                value={serviceToAdd}
                onChange={(e) => setServiceToAdd(e.target.value)}
                className="flex-1 px-2 py-1.5 bg-gray-800 border border-gray-700 rounded-md text-sm text-gray-200"
              >
                <option value="">Select service</option>
                {availableServices.map((service) => (
                  <option key={service} value={service}>{service}</option>
                ))}
              </select>
              <button
                type="button"
                onClick={handleAddService}
                className="px-2.5 py-1.5 rounded-md bg-gray-800 text-gray-200 hover:bg-gray-700"
              >
                <Plus size={14} />
              </button>
            </div>
          </div>

          <div className="rounded-lg border border-gray-800 bg-gray-900 p-4 space-y-3">
            <h3 className="text-sm font-semibold text-white">Add custom node</h3>
            <input
              type="text"
              value={customNode.id}
              onChange={(e) => setCustomNode((prev) => ({ ...prev, id: e.target.value }))}
              placeholder="node-id"
              className="w-full px-2 py-1.5 bg-gray-800 border border-gray-700 rounded-md text-sm text-gray-200"
            />
            <input
              type="text"
              value={customNode.label}
              onChange={(e) => setCustomNode((prev) => ({ ...prev, label: e.target.value }))}
              placeholder="Label"
              className="w-full px-2 py-1.5 bg-gray-800 border border-gray-700 rounded-md text-sm text-gray-200"
            />
            <select
              value={customNode.type}
              onChange={(e) => setCustomNode((prev) => ({ ...prev, type: e.target.value }))}
              className="w-full px-2 py-1.5 bg-gray-800 border border-gray-700 rounded-md text-sm text-gray-200"
            >
              {COMPONENT_TYPES.map((type) => (
                <option key={type.value} value={type.value}>{type.label}</option>
              ))}
            </select>
            <select
              value={customNode.layer}
              onChange={(e) => setCustomNode((prev) => ({ ...prev, layer: e.target.value }))}
              className="w-full px-2 py-1.5 bg-gray-800 border border-gray-700 rounded-md text-sm text-gray-200"
            >
              {DEFAULT_LAYERS.map((layer) => (
                <option key={layer} value={layer}>{LAYER_LABELS[layer]}</option>
              ))}
            </select>
            <button
              type="button"
              onClick={handleAddCustomNode}
              className="w-full inline-flex items-center justify-center gap-2 px-3 py-1.5 rounded-md bg-gray-800 text-gray-200 hover:bg-gray-700 text-sm"
            >
              <Plus size={14} />
              Add node
            </button>
          </div>

          <div className="rounded-lg border border-gray-800 bg-gray-900 p-4 space-y-3">
            <h3 className="text-sm font-semibold text-white">Selection</h3>

            {selectedNode ? (
              <div className="space-y-2">
                <label className="text-xs text-gray-400">Label</label>
                <input
                  type="text"
                  value={selectedNode.data?.label || ''}
                  onChange={(e) => updateSelectedNode({ label: e.target.value })}
                  className="w-full px-2 py-1.5 bg-gray-800 border border-gray-700 rounded-md text-sm text-gray-200"
                />
                <label className="text-xs text-gray-400">Component Type</label>
                <select
                  value={selectedNode.data?.componentType || 'custom'}
                  onChange={(e) => updateSelectedNode({ componentType: e.target.value })}
                  className="w-full px-2 py-1.5 bg-gray-800 border border-gray-700 rounded-md text-sm text-gray-200"
                >
                  {COMPONENT_TYPES.map((type) => (
                    <option key={type.value} value={type.value}>{type.label}</option>
                  ))}
                </select>
                <label className="text-xs text-gray-400">Layer</label>
                <select
                  value={selectedNode.data?.layer || 'application'}
                  onChange={(e) => updateSelectedNode({ layer: e.target.value })}
                  className="w-full px-2 py-1.5 bg-gray-800 border border-gray-700 rounded-md text-sm text-gray-200"
                >
                  {DEFAULT_LAYERS.map((layer) => (
                    <option key={layer} value={layer}>{LAYER_LABELS[layer]}</option>
                  ))}
                </select>
              </div>
            ) : selectedEdgeId ? (
              <div className="space-y-2">
                <label className="text-xs text-gray-400">Protocol</label>
                <input
                  type="text"
                  value={edgeProtocol}
                  onChange={(e) => {
                    setEdgeProtocol(e.target.value)
                    updateSelectedEdge(e.target.value)
                  }}
                  placeholder="https, jdbc, redis..."
                  className="w-full px-2 py-1.5 bg-gray-800 border border-gray-700 rounded-md text-sm text-gray-200"
                />
                <div className="flex items-center gap-2 text-xs text-gray-400">
                  <Link2 size={12} />
                  Edge selected
                </div>
              </div>
            ) : (
              <p className="text-sm text-gray-500">Select a node or edge to edit</p>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
