import { useMemo, useState, useCallback, useEffect } from 'react';
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
  useReactFlow,
} from '@xyflow/react';
import Dagre from '@dagrejs/dagre';
import '@xyflow/react/dist/style.css';
import type { CodeFlowNode, CodeFlowEdge, NodeType } from '../types';
import { useGraphStore } from '../store/useGraphStore';

interface CodeFlowGraphProps {
  data: { nodes: CodeFlowNode[]; edges: CodeFlowEdge[] } | null;
}

export function getNodeStyle(type: NodeType): { bg: string; border: string; glow: string; badge: string } {
  switch (type) {
    case 'Controller':
      return { bg: '#0F1420', border: 'rgba(59, 130, 246, 0.25)', glow: 'rgba(59, 130, 246, 0.08)', badge: '#3B82F6' };
    case 'Service':
      return { bg: '#0F1420', border: 'rgba(16, 185, 129, 0.25)', glow: 'rgba(16, 185, 129, 0.08)', badge: '#10B981' };
    case 'Route':
      return { bg: '#0F1420', border: 'rgba(139, 92, 246, 0.25)', glow: 'rgba(139, 92, 246, 0.08)', badge: '#8B5CF6' };
    case 'Middleware':
      return { bg: '#0F1420', border: 'rgba(245, 158, 11, 0.25)', glow: 'rgba(245, 158, 11, 0.08)', badge: '#F59E0B' };
    case 'Repository':
      return { bg: '#0F1420', border: 'rgba(20, 184, 166, 0.25)', glow: 'rgba(20, 184, 166, 0.08)', badge: '#14B8A6' };
    case 'Utility':
      return { bg: '#0F1420', border: 'rgba(245, 158, 11, 0.25)', glow: 'rgba(245, 158, 11, 0.08)', badge: '#F59E0B' };
    case 'Config':
      return { bg: '#0F1420', border: 'rgba(168, 85, 247, 0.25)', glow: 'rgba(168, 85, 247, 0.08)', badge: '#A855F7' };
  }
}

function getNodeTypeLabel(type: NodeType): string {
  return type.toUpperCase();
}

function getNodeRank(type: NodeType): number {
  switch (type) {
    case 'Controller': return 0;
    case 'Route': return 1;
    case 'Middleware': return 2;
    case 'Service': return 3;
    case 'Repository': return 4;
    case 'Utility': return 5;
    case 'Config': return 6;
  }
}

function getEdgeColor(relation: string): string {
  switch (relation) {
    case 'imports': return '#475569';
    case 'calls': return '#F59E0B';
    case 'depends_on': return '#8B5CF6';
    default: return '#475569';
  }
}

type CodeFlowNodeData = {
  label: string;
  nodeType: NodeType;
  typeLabel: string;
  bgColor: string;
  borderColor: string;
  glowColor: string;
  badgeColor: string;
  description: string;
  nodeId: string;
  methods: string[];
  methodCount: number;
};

function CustomNode({ data }: NodeProps<Node<CodeFlowNodeData>>) {
  const highlightedNodeId = useGraphStore((s) => s.highlightedNodeId);
  const selectedNode = useGraphStore((s) => s.selectedNode);
  const isHighlighted = data.nodeId === highlightedNodeId;
  const isSelected = data.nodeId === selectedNode?.id;

  const handleClick = useCallback(() => {
    const node: CodeFlowNode = {
      id: data.nodeId,
      label: data.label,
      type: data.nodeType,
      description: data.description,
      methods: data.methods,
    };
    useGraphStore.getState().selectNode(node);
  }, [data.nodeId, data.label, data.nodeType, data.description, data.methods]);

  return (
    <div
      onClick={handleClick}
      className="relative rounded-lg min-w-[160px] max-w-[240px] transition-all duration-200 cursor-pointer"
      style={{
        backgroundColor: '#0F1420',
        border: isSelected
          ? '1.5px solid rgba(6, 182, 212, 0.7)'
          : isHighlighted
          ? '1.5px solid rgba(99, 102, 241, 0.6)'
          : `1px solid ${data.borderColor}`,
        boxShadow: isHighlighted
          ? `0 0 24px 6px rgba(99,102,241,0.2)`
          : isSelected
          ? `0 0 16px 4px rgba(6,182,212,0.15)`
          : `0 2px 8px rgba(0,0,0,0.3)`,
      }}
    >
      {/* SELECTED badge */}
      {isSelected && (
        <div className="absolute -top-2.5 left-1/2 -translate-x-1/2 px-2 py-0.5 rounded text-[7px] font-bold uppercase tracking-widest text-white bg-cyan-500 shadow-lg shadow-cyan-500/30 z-10">
          SELECTED
        </div>
      )}

      <Handle type="target" position={Position.Top} className="!bg-slate-600 !w-1.5 !h-1.5 !border-0 !-top-[3px]" />

      <div className="px-3.5 py-3">
        {/* Type badge: colored dot + uppercase label */}
        <div className="flex items-center gap-1.5 mb-1.5">
          <span className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: data.badgeColor }} />
          <span
            className="text-[9px] font-bold uppercase tracking-wider"
            style={{ color: data.badgeColor }}
          >
            {data.typeLabel}
          </span>
        </div>

        {/* Filename / Label */}
        <div className="text-[13px] text-white font-semibold leading-snug">
          {data.label}
        </div>

        {/* Sublabel (description as path) */}
        {data.description && (
          <div className="text-[10px] text-slate-500 mt-0.5 leading-snug line-clamp-2 overflow-hidden">
            {data.description.length > 80 ? data.description.slice(0, 80) + '...' : data.description}
          </div>
        )}
      </div>

      <Handle type="source" position={Position.Bottom} className="!bg-slate-600 !w-1.5 !h-1.5 !border-0 !-bottom-[3px]" />
    </div>
  );
}

const nodeTypes = { codeflow: CustomNode };

const NODE_WIDTH = 200;
const NODE_HEIGHT = 80;

function layoutNodes(apiNodes: CodeFlowNode[], apiEdges: CodeFlowEdge[]) {
  const connCounts = new Map<string, number>();
  apiEdges.forEach((e) => {
    connCounts.set(e.source, (connCounts.get(e.source) || 0) + 1);
    connCounts.set(e.target, (connCounts.get(e.target) || 0) + 1);
  });

  const useDagre = apiNodes.length <= 60 && apiEdges.length > 0;

  if (useDagre) {
    const g = new Dagre.graphlib.Graph().setDefaultEdgeLabel(() => ({}));
    g.setGraph({ rankdir: 'TB', nodesep: 100, ranksep: 140, edgesep: 50 });

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
          bgColor: style.bg,
          borderColor: style.border,
          glowColor: style.glow,
          badgeColor: style.badge,
          description: node.description || '',
          nodeId: node.id,
          methods: node.methods || [],
          methodCount: node.methods?.length || 0,
        },
      };
    });
  }

  const sorted = [...apiNodes].sort((a, b) => getNodeRank(a.type) - getNodeRank(b.type));
  const cols = Math.min(7, Math.ceil(Math.sqrt(sorted.length * 1.4)));

  return sorted.map((node, index) => {
    const col = index % cols;
    const row = Math.floor(index / cols);
    const style = getNodeStyle(node.type);
    return {
      id: node.id,
      type: 'codeflow' as const,
      position: { x: col * (NODE_WIDTH + 120), y: row * (NODE_HEIGHT + 120) },
      data: {
        label: node.label,
        nodeType: node.type,
        typeLabel: getNodeTypeLabel(node.type),
        bgColor: style.bg,
        borderColor: style.border,
        glowColor: style.glow,
        badgeColor: style.badge,
        description: node.description || '',
        nodeId: node.id,
        methods: node.methods || [],
        methodCount: node.methods?.length || 0,
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
        style: { stroke: color, strokeWidth: 1.5 },
        markerEnd: { type: MarkerType.ArrowClosed, color, width: 12, height: 12 },
        type: 'smoothstep',
        animated: edge.relation === 'calls',
      };
    });
}

function ViewportPanner({ nodeCount }: { nodeCount: number }) {
  const { fitView } = useReactFlow();
  const highlightedNodeId = useGraphStore((s) => s.highlightedNodeId);

  useEffect(() => {
    if (nodeCount > 0) {
      const timer = setTimeout(() => {
        fitView({ padding: 0.15, duration: 800, minZoom: 0.6 });
      }, 150);
      return () => clearTimeout(timer);
    }
  }, [nodeCount, fitView]);

  useEffect(() => {
    if (highlightedNodeId) {
      try {
        fitView({ nodes: [{ id: highlightedNodeId }], duration: 800, padding: 0.5 });
      } catch { /* graceful fallback */ }
    }
  }, [highlightedNodeId, fitView]);

  return null;
}

export function CodeFlowGraph({ data }: CodeFlowGraphProps) {
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);

  const onNodeMouseEnter = useCallback((_: unknown, node: Node) => {
    setHoveredNode(node.id);
  }, []);

  const onNodeMouseLeave = useCallback(() => {
    setHoveredNode(null);
  }, []);

  if (!data) {
    return (
      <div className="flex items-center justify-center h-full text-slate-500 text-sm font-medium">
        <div className="text-center space-y-3">
          <div className="w-12 h-12 mx-auto rounded-xl bg-slate-800/50 flex items-center justify-center text-xl">📐</div>
          <p>No hay datos de flujo de código disponibles para este repositorio.</p>
        </div>
      </div>
    );
  }

  const visibleNodes = data.nodes;
  const visibleEdges = data.edges;

  const styledEdges = useMemo(() => {
    const baseEdges = buildEdges(visibleEdges, new Set(visibleNodes.map((n) => n.id)));
    if (!hoveredNode) return baseEdges;
    return baseEdges.map((edge) => {
      const isConnected = edge.source === hoveredNode || edge.target === hoveredNode;
      return {
        ...edge,
        style: {
          ...edge.style,
          strokeWidth: isConnected ? 2.5 : 1,
          opacity: isConnected ? 1 : 0.12,
        },
      };
    });
  }, [visibleEdges, visibleNodes, hoveredNode]);

  const flowNodes = useMemo(() => layoutNodes(visibleNodes, visibleEdges), [visibleNodes, visibleEdges]);

  const styledNodes = useMemo(() => {
    if (!hoveredNode) return flowNodes;
    const connectedIds = new Set<string>([hoveredNode]);
    visibleEdges.forEach((e) => {
      if (e.source === hoveredNode) connectedIds.add(e.target);
      if (e.target === hoveredNode) connectedIds.add(e.source);
    });
    return flowNodes.map((node) => ({
      ...node,
      style: connectedIds.has(node.id) ? {} : { opacity: 0.2 },
    }));
  }, [flowNodes, hoveredNode, visibleEdges]);

  return (
    <div className="flex flex-col h-full">
      {/* Graph canvas */}
      <div className="flex-1 overflow-hidden bg-[#0D1526]">
        <ReactFlow
          nodes={styledNodes}
          edges={styledEdges}
          nodeTypes={nodeTypes}
          onNodeMouseEnter={onNodeMouseEnter}
          onNodeMouseLeave={onNodeMouseLeave}
          fitView
          fitViewOptions={{ padding: 0.15, minZoom: 0.6 }}
          minZoom={0.3}
          maxZoom={3}
          defaultViewport={{ x: 0, y: 0, zoom: 0.75 }}
          proOptions={{ hideAttribution: true }}
        >
          <ViewportPanner nodeCount={styledNodes.length} />
          <Controls position="bottom-left" showInteractive={false} />
          <Background variant={BackgroundVariant.Cross} gap={80} size={1.5} color="rgba(100, 140, 200, 0.12)" />
        </ReactFlow>
      </div>
    </div>
  );
}
