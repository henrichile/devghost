import { useMemo, useState, useCallback } from 'react';
import {
  ReactFlow,
  Controls,
  Background,
  MarkerType,
  type Node,
  type Edge,
  type NodeProps,
  Handle,
  Position,
  BackgroundVariant,
  MiniMap,
} from '@xyflow/react';
import Dagre from '@dagrejs/dagre';
import '@xyflow/react/dist/style.css';
import type { CodeFlowNode, CodeFlowEdge, NodeType } from '../types';

interface CodeFlowGraphProps {
  data: { nodes: CodeFlowNode[]; edges: CodeFlowEdge[] } | null;
}

export function getNodeStyle(type: NodeType): { backgroundColor: string } {
  switch (type) {
    case 'Controller':
      return { backgroundColor: '#1d4ed8' };
    case 'Service':
      return { backgroundColor: '#047857' };
    case 'Route':
      return { backgroundColor: '#6d28d9' };
    case 'Middleware':
      return { backgroundColor: '#b45309' };
    case 'Repository':
      return { backgroundColor: '#0f766e' };
    case 'Utility':
      return { backgroundColor: '#374151' };
  }
}

function getNodeTypeLabel(type: NodeType): string {
  switch (type) {
    case 'Controller':
      return 'CONTROLLER';
    case 'Service':
      return 'SERVICE';
    case 'Route':
      return 'ROUTE';
    case 'Middleware':
      return 'MIDDLEWARE';
    case 'Repository':
      return 'REPOSITORY';
    case 'Utility':
      return 'UTILITY';
  }
}

function getNodeIcon(type: NodeType): string {
  switch (type) {
    case 'Controller':
      return '🎮';
    case 'Service':
      return '⚙️';
    case 'Route':
      return '🛤️';
    case 'Middleware':
      return '🔗';
    case 'Repository':
      return '🗄️';
    case 'Utility':
      return '🔧';
  }
}

function getNodeRank(type: NodeType): number {
  switch (type) {
    case 'Controller':
      return 0;
    case 'Route':
      return 1;
    case 'Middleware':
      return 2;
    case 'Service':
      return 3;
    case 'Repository':
      return 4;
    case 'Utility':
      return 5;
  }
}

function getEdgeColor(relation: string): string {
  switch (relation) {
    case 'imports':
      return '#64748b';
    case 'calls':
      return '#d97706';
    case 'depends_on':
      return '#7c3aed';
    default:
      return '#64748b';
  }
}

type CodeFlowNodeData = {
  label: string;
  nodeType: NodeType;
  typeLabel: string;
  icon: string;
  bgColor: string;
  connectionCount: number;
};

function CustomNode({ data }: NodeProps<Node<CodeFlowNodeData>>) {
  return (
    <div
      className="rounded-xl shadow-md min-w-[160px] max-w-[220px] transition-all duration-200 hover:shadow-xl hover:scale-[1.02] cursor-pointer"
      style={{
        backgroundColor: data.bgColor,
        border: '2px solid rgba(255,255,255,0.15)',
      }}
    >
      <Handle type="target" position={Position.Top} className="!bg-white/40 !w-2.5 !h-2.5 !border-white/60 !border" />
      <div className="px-3.5 py-3">
        <div className="flex items-center justify-between mb-1.5">
          <span className="text-[9px] text-white/60 font-bold uppercase tracking-widest">
            {data.icon} {data.typeLabel}
          </span>
          {data.connectionCount > 0 && (
            <span className="text-[8px] bg-white/15 text-white/70 px-1.5 py-0.5 rounded-full">
              {data.connectionCount}→
            </span>
          )}
        </div>
        <div className="text-[12px] text-white font-bold leading-snug">
          {data.label}
        </div>
      </div>
      <Handle type="source" position={Position.Bottom} className="!bg-white/40 !w-2.5 !h-2.5 !border-white/60 !border" />
    </div>
  );
}

const nodeTypes = { codeflow: CustomNode };

const NODE_WIDTH = 180;
const NODE_HEIGHT = 65;

function layoutNodes(apiNodes: CodeFlowNode[], apiEdges: CodeFlowEdge[]) {
  // Count connections per node
  const connCounts = new Map<string, number>();
  apiEdges.forEach((e) => {
    connCounts.set(e.source, (connCounts.get(e.source) || 0) + 1);
    connCounts.set(e.target, (connCounts.get(e.target) || 0) + 1);
  });

  const useDagre = apiNodes.length <= 60 && apiEdges.length > 0;

  if (useDagre) {
    const g = new Dagre.graphlib.Graph().setDefaultEdgeLabel(() => ({}));
    g.setGraph({ rankdir: 'TB', nodesep: 60, ranksep: 120, edgesep: 30 });

    apiNodes.forEach((node) => {
      g.setNode(node.id, { width: NODE_WIDTH, height: NODE_HEIGHT });
    });
    apiEdges.forEach((edge) => {
      g.setEdge(edge.source, edge.target);
    });

    Dagre.layout(g);

    return apiNodes.map((node) => {
      const pos = g.node(node.id);
      const style = getNodeStyle(node.type);
      return {
        id: node.id,
        type: 'codeflow' as const,
        position: { x: pos.x - NODE_WIDTH / 2, y: pos.y - NODE_HEIGHT / 2 },
        data: {
          label: node.label,
          nodeType: node.type,
          typeLabel: getNodeTypeLabel(node.type),
          icon: getNodeIcon(node.type),
          bgColor: style.backgroundColor,
          connectionCount: connCounts.get(node.id) || 0,
        },
      };
    });
  }

  // Grid layout sorted by type rank
  const sorted = [...apiNodes].sort((a, b) => getNodeRank(a.type) - getNodeRank(b.type));
  const cols = Math.min(7, Math.ceil(Math.sqrt(sorted.length * 1.4)));

  return sorted.map((node, index) => {
    const col = index % cols;
    const row = Math.floor(index / cols);
    const style = getNodeStyle(node.type);
    return {
      id: node.id,
      type: 'codeflow' as const,
      position: { x: col * (NODE_WIDTH + 50), y: row * (NODE_HEIGHT + 50) },
      data: {
        label: node.label,
        nodeType: node.type,
        typeLabel: getNodeTypeLabel(node.type),
        icon: getNodeIcon(node.type),
        bgColor: style.backgroundColor,
        connectionCount: connCounts.get(node.id) || 0,
      },
    };
  });
}

function buildEdges(apiEdges: CodeFlowEdge[], nodeIds: Set<string>): Edge[] {
  return apiEdges
    .filter((e) => nodeIds.has(e.source) && nodeIds.has(e.target))
    .map((edge, index) => {
      const color = getEdgeColor(edge.relation);
      return {
        id: `e-${index}`,
        source: edge.source,
        target: edge.target,
        style: { stroke: color, strokeWidth: 2 },
        markerEnd: { type: MarkerType.ArrowClosed, color, width: 15, height: 15 },
        type: 'smoothstep',
        animated: edge.relation === 'calls',
      };
    });
}

const PAGE_SIZE = 50;

export function CodeFlowGraph({ data }: CodeFlowGraphProps) {
  const [page, setPage] = useState(0);
  const [filterType, setFilterType] = useState<NodeType | 'all'>('all');
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);

  const onNodeMouseEnter = useCallback((_: unknown, node: Node) => {
    setHoveredNode(node.id);
  }, []);

  const onNodeMouseLeave = useCallback(() => {
    setHoveredNode(null);
  }, []);

  if (!data) {
    return (
      <div className="flex items-center justify-center h-[650px] text-gray-500">
        <p>No hay datos de flujo de código disponibles para este repositorio.</p>
      </div>
    );
  }

  const typeCounts = useMemo(() => data.nodes.reduce((acc, n) => {
    acc[n.type] = (acc[n.type] || 0) + 1;
    return acc;
  }, {} as Record<string, number>), [data.nodes]);

  // Filter
  const filteredNodes = useMemo(() => {
    if (filterType === 'all') return data.nodes;
    return data.nodes.filter((n) => n.type === filterType);
  }, [data.nodes, filterType]);

  // When filtering by type, also include connected nodes from edges
  const filteredWithConnected = useMemo(() => {
    if (filterType === 'all') return filteredNodes;
    const filteredIds = new Set(filteredNodes.map((n) => n.id));
    // Find nodes connected to filtered nodes
    const connectedIds = new Set<string>();
    data.edges.forEach((e) => {
      if (filteredIds.has(e.source)) connectedIds.add(e.target);
      if (filteredIds.has(e.target)) connectedIds.add(e.source);
    });
    // Add connected nodes that aren't already in the filtered set
    const connected = data.nodes.filter((n) => connectedIds.has(n.id) && !filteredIds.has(n.id));
    return [...filteredNodes, ...connected];
  }, [filteredNodes, filterType, data.nodes, data.edges]);

  const totalPages = Math.ceil(filteredWithConnected.length / PAGE_SIZE);
  const isLarge = filteredWithConnected.length > PAGE_SIZE;

  // Paginate
  const visibleNodes = useMemo(() => {
    if (!isLarge) return filteredWithConnected;
    return filteredWithConnected.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);
  }, [filteredWithConnected, page, isLarge]);

  // Edges for visible nodes
  const visibleEdges = useMemo(() => {
    const ids = new Set(visibleNodes.map((n) => n.id));
    return data.edges.filter((e) => ids.has(e.source) && ids.has(e.target));
  }, [data.edges, visibleNodes]);

  // Highlight edges connected to hovered node
  const styledEdges = useMemo(() => {
    const baseEdges = buildEdges(visibleEdges, new Set(visibleNodes.map((n) => n.id)));
    if (!hoveredNode) return baseEdges;
    return baseEdges.map((edge) => {
      const isConnected = edge.source === hoveredNode || edge.target === hoveredNode;
      return {
        ...edge,
        style: {
          ...edge.style,
          strokeWidth: isConnected ? 3.5 : 1,
          opacity: isConnected ? 1 : 0.2,
        },
      };
    });
  }, [visibleEdges, visibleNodes, hoveredNode]);

  const flowNodes = useMemo(() => layoutNodes(visibleNodes, visibleEdges), [visibleNodes, visibleEdges]);

  // Dim non-connected nodes on hover
  const styledNodes = useMemo(() => {
    if (!hoveredNode) return flowNodes;
    const connectedIds = new Set<string>([hoveredNode]);
    visibleEdges.forEach((e) => {
      if (e.source === hoveredNode) connectedIds.add(e.target);
      if (e.target === hoveredNode) connectedIds.add(e.source);
    });
    return flowNodes.map((node) => ({
      ...node,
      style: connectedIds.has(node.id) ? {} : { opacity: 0.3 },
    }));
  }, [flowNodes, hoveredNode, visibleEdges]);

  return (
    <div className="flex flex-col h-[650px]">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-1.5 px-3 py-2 border-b bg-white/80 backdrop-blur-sm text-[11px] sticky top-0 z-10">
        <button
          onClick={() => { setFilterType('all'); setPage(0); }}
          className={`px-3 py-1.5 rounded-full font-medium transition-all ${filterType === 'all' ? 'bg-gray-900 text-white shadow-md' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'}`}
        >
          Todos ({data.nodes.length})
        </button>
        {Object.entries(typeCounts)
          .sort(([a], [b]) => getNodeRank(a as NodeType) - getNodeRank(b as NodeType))
          .map(([type, count]) => (
          <button
            key={type}
            onClick={() => { setFilterType(type as NodeType); setPage(0); }}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full font-medium transition-all ${filterType === type ? 'text-white shadow-md scale-105' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'}`}
            style={filterType === type ? { backgroundColor: getNodeStyle(type as NodeType).backgroundColor } : {}}
          >
            <span
              className="w-2.5 h-2.5 rounded-full inline-block shadow-sm"
              style={{ backgroundColor: getNodeStyle(type as NodeType).backgroundColor }}
            />
            {type} ({count})
          </button>
        ))}

        <div className="ml-auto flex items-center gap-3 text-gray-400">
          {isLarge && (
            <div className="flex items-center gap-1.5">
              <button
                onClick={() => setPage((p) => Math.max(0, p - 1))}
                disabled={page === 0}
                className="w-7 h-7 flex items-center justify-center rounded-lg bg-gray-100 text-gray-600 disabled:opacity-30 hover:bg-gray-200 font-bold"
              >
                ‹
              </button>
              <span className="text-[10px] text-gray-500 min-w-[40px] text-center">{page + 1} / {totalPages}</span>
              <button
                onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
                disabled={page >= totalPages - 1}
                className="w-7 h-7 flex items-center justify-center rounded-lg bg-gray-100 text-gray-600 disabled:opacity-30 hover:bg-gray-200 font-bold"
              >
                ›
              </button>
            </div>
          )}
          <span className="text-[10px]">{visibleNodes.length} nodos · {visibleEdges.length} relaciones</span>
        </div>
      </div>

      {/* Edge legend */}
      {visibleEdges.length > 0 && (
        <div className="flex items-center gap-5 px-3 py-1.5 bg-gray-50/80 border-b text-[10px] text-gray-500">
          <span className="flex items-center gap-1.5">
            <span className="w-5 h-[2px] inline-block rounded" style={{ backgroundColor: '#64748b' }} />
            <span>imports</span>
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-5 h-[2px] inline-block rounded" style={{ backgroundColor: '#d97706' }} />
            <span>calls</span>
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-5 h-[2px] inline-block rounded" style={{ backgroundColor: '#7c3aed' }} />
            <span>depends_on</span>
          </span>
          <span className="ml-auto text-gray-400 italic">Pasa el cursor sobre un nodo para ver sus conexiones</span>
        </div>
      )}

      {/* Graph */}
      <div className="flex-1 overflow-hidden bg-gradient-to-br from-slate-50 to-slate-100">
        <ReactFlow
          nodes={styledNodes}
          edges={styledEdges}
          nodeTypes={nodeTypes}
          onNodeMouseEnter={onNodeMouseEnter}
          onNodeMouseLeave={onNodeMouseLeave}
          fitView
          fitViewOptions={{ padding: 0.2 }}
          minZoom={0.15}
          maxZoom={3}
          proOptions={{ hideAttribution: true }}
        >
          <Controls position="bottom-left" showInteractive={false} />
          <Background variant={BackgroundVariant.Dots} gap={24} size={1} color="#cbd5e1" />
          <MiniMap
            nodeColor={(node) => (node.data as CodeFlowNodeData)?.bgColor || '#6B7280'}
            maskColor="rgba(0,0,0,0.08)"
            position="bottom-right"
            style={{ width: 120, height: 80 }}
          />
        </ReactFlow>
      </div>
    </div>
  );
}
