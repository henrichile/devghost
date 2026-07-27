// Feature: interactive-ux-enhancements, Property 4: InspectionPanel dependency derivation correctness
import { render, cleanup } from '@testing-library/react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { act } from 'react';
import * as fc from 'fast-check';
import { useGraphStore } from '../../store/useGraphStore';
import type { CodeFlowNode, CodeFlowEdge, NodeType, EdgeRelation } from '../../types';

// Mock ReactFlow-dependent module (CodeFlowGraph exports getNodeStyle)
vi.mock('../CodeFlowGraph', () => ({
  getNodeStyle: () => ({ bg: '#1e3a5f', border: 'rgba(59,130,246,0.3)', glow: 'rgba(59,130,246,0.15)', badge: '#3B82F6' }),
}));

// Mock MarkdownRenderer
vi.mock('../MarkdownRenderer', () => ({
  MarkdownRenderer: ({ content }: { content: string }) => <div data-testid="markdown">{content}</div>,
}));

// Lazy import InspectionPanel after mock is set up
const { InspectionPanel } = await import('../InspectionPanel');

const nodeTypes: NodeType[] = ['Controller', 'Service', 'Route', 'Middleware', 'Repository', 'Utility'];
const edgeRelations: EdgeRelation[] = ['imports', 'calls', 'depends_on'];

// Generator for a non-empty trimmed string
const arbTrimmedString = (max: number) =>
  fc.string({ minLength: 1, maxLength: max, unit: 'grapheme' })
    .map((s) => s.trim())
    .filter((s) => s.length > 0);

// Generator for a set of nodes (2-6 nodes)
const arbNodes: fc.Arbitrary<CodeFlowNode[]> = fc
  .integer({ min: 2, max: 6 })
  .chain((count) =>
    fc.array(
      fc.record({
        id: fc.uuid(),
        label: arbTrimmedString(20),
        type: fc.constantFrom(...nodeTypes),
        description: arbTrimmedString(80),
      }),
      { minLength: count, maxLength: count }
    )
  );

// Generator for edges between a given set of nodes
function arbEdgesForNodes(nodes: CodeFlowNode[]): fc.Arbitrary<CodeFlowEdge[]> {
  if (nodes.length < 2) return fc.constant([]);
  const nodeIds = nodes.map((n) => n.id);
  return fc.array(
    fc.record({
      source: fc.constantFrom(...nodeIds),
      target: fc.constantFrom(...nodeIds),
      relation: fc.constantFrom(...edgeRelations),
    }),
    { minLength: 1, maxLength: nodes.length * 2 }
  ).map((edges) => edges.filter((e) => e.source !== e.target));
}

// Combined generator: nodes + edges + selected node index
const arbGraph = arbNodes.chain((nodes) =>
  fc.tuple(
    fc.constant(nodes),
    arbEdgesForNodes(nodes),
    fc.integer({ min: 0, max: nodes.length - 1 })
  )
);

describe('InspectionPanel - Property 4: dependency derivation correctness', () => {
  afterEach(() => {
    cleanup();
    act(() => {
      useGraphStore.setState({
        selectedNode: null,
        inspectionOpen: false,
        edges: [],
        nodes: [],
      });
    });
  });

  /**
   * **Validates: Requirements 2.4, 2.5**
   *
   * For any graph (set of nodes and edges) and any selected node,
   * the dependencies displayed by InspectionPanel SHALL correctly reflect
   * the outgoing and incoming edges of the selected node.
   */
  it('displays correct dependency counts for any graph configuration', () => {
    fc.assert(
      fc.property(arbGraph, ([nodes, edges, selectedIdx]) => {
        cleanup();

        const selectedNode = nodes[selectedIdx];

        act(() => {
          useGraphStore.setState({
            selectedNode,
            inspectionOpen: true,
            edges,
            nodes,
          });
        });

        const { container } = render(<InspectionPanel />);

        // Click the "Deps" tab to see dependencies
        const buttons = container.querySelectorAll('button');
        const depsTab = Array.from(buttons).find((b) => b.textContent?.includes('Deps'));
        if (depsTab) {
          act(() => { depsTab.click(); });
        }

        // Compute expected dependencies
        const outgoingEdges = edges.filter((e) => e.source === selectedNode.id);
        const incomingEdges = edges.filter((e) => e.target === selectedNode.id);

        const expectedOutIds = [...new Set(outgoingEdges.map((e) => e.target))];
        const expectedDeps = expectedOutIds
          .map((id) => nodes.find((n) => n.id === id))
          .filter((n): n is CodeFlowNode => n != null);

        const expectedInIds = [...new Set(incomingEdges.map((e) => e.source))];
        const expectedDependents = expectedInIds
          .map((id) => nodes.find((n) => n.id === id))
          .filter((n): n is CodeFlowNode => n != null);

        const text = container.textContent || '';

        // Verify correct labels are rendered for dependencies
        for (const dep of expectedDeps) {
          expect(text).toContain(dep.label);
        }

        // Verify "Depends on" section shows correct count
        if (expectedDeps.length > 0) {
          expect(text).toContain(`Depends on (${expectedDeps.length})`);
        }

        // Verify "Used by" section shows correct count
        if (expectedDependents.length > 0) {
          expect(text).toContain(`Used by (${expectedDependents.length})`);
        }

        // If no deps at all, should show "Sin dependencias detectadas"
        if (expectedDeps.length === 0 && expectedDependents.length === 0) {
          expect(text).toContain('Sin dependencias detectadas');
        }

        cleanup();
      }),
      { numRuns: 50 }
    );
  });
});
