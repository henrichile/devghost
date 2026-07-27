import { create } from 'zustand';
import type { CodeFlowNode, CodeFlowEdge, NodeInspection } from '../types';

interface GraphState {
  // Inspection panel
  selectedNode: CodeFlowNode | null;
  inspectionOpen: boolean;
  selectNode: (node: CodeFlowNode) => void;
  closeInspection: () => void;

  // Highlight engine
  highlightedNodeId: string | null;
  isTouring: boolean;
  tourNodeIds: string[];
  startTour: (nodeIds: string[]) => void;
  stopTour: () => void;
  setHighlightedNode: (id: string | null) => void;

  // Graph data reference (for dependency lookup)
  edges: CodeFlowEdge[];
  nodes: CodeFlowNode[];
  setGraphData: (nodes: CodeFlowNode[], edges: CodeFlowEdge[]) => void;

  // Pre-computed node inspections (method descriptions + audits)
  nodeInspections: Record<string, NodeInspection>;
  setNodeInspections: (inspections: Record<string, NodeInspection>) => void;
}

export const useGraphStore = create<GraphState>((set) => ({
  // Inspection panel state
  selectedNode: null,
  inspectionOpen: false,
  selectNode: (node) => set({ selectedNode: node, inspectionOpen: true }),
  closeInspection: () => set({ inspectionOpen: false, selectedNode: null }),

  // Highlight engine state
  highlightedNodeId: null,
  isTouring: false,
  tourNodeIds: [],
  startTour: (nodeIds) => set({ isTouring: true, tourNodeIds: nodeIds }),
  stopTour: () => set({ isTouring: false, tourNodeIds: [], highlightedNodeId: null }),
  setHighlightedNode: (id) => set({ highlightedNodeId: id }),

  // Graph data
  edges: [],
  nodes: [],
  setGraphData: (nodes, edges) => set({ nodes, edges }),

  // Node inspections
  nodeInspections: {},
  setNodeInspections: (inspections) => set({ nodeInspections: inspections }),
}));
