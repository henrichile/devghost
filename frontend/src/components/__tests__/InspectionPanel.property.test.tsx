// Feature: interactive-ux-enhancements, Property 3: InspectionPanel renders all node data fields
import { render, cleanup } from '@testing-library/react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { act } from 'react';
import * as fc from 'fast-check';
import { useGraphStore } from '../../store/useGraphStore';
import type { CodeFlowNode, NodeType } from '../../types';

// Mock ReactFlow-dependent module (CodeFlowGraph exports getNodeStyle)
vi.mock('../CodeFlowGraph', () => ({
  getNodeStyle: (_type: string) => ({ bg: '#1e3a5f', border: 'rgba(59,130,246,0.3)', glow: 'rgba(59,130,246,0.15)', badge: '#3B82F6' }),
}));

// Mock MarkdownRenderer (not needed for this test)
vi.mock('../MarkdownRenderer', () => ({
  MarkdownRenderer: ({ content }: { content: string }) => <div data-testid="markdown">{content}</div>,
}));

// Lazy import InspectionPanel after mock is set up
const { InspectionPanel } = await import('../InspectionPanel');

const nodeTypes: NodeType[] = ['Controller', 'Service', 'Route', 'Middleware', 'Repository', 'Utility'];

// Generator for a random CodeFlowNode with non-empty label, type, and description
const arbCodeFlowNode: fc.Arbitrary<CodeFlowNode> = fc.record({
  id: fc.uuid(),
  label: fc.string({ minLength: 1, maxLength: 30, unit: 'grapheme' })
    .filter((s) => s.trim().length > 0 && !/\s{2,}/.test(s)),
  type: fc.constantFrom(...nodeTypes),
  description: fc.string({ minLength: 1, maxLength: 100, unit: 'grapheme' })
    .filter((s) => s.trim().length > 0 && !/\s{2,}/.test(s)),
});

describe('InspectionPanel - Property 3: renders all node data fields', () => {
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
   * **Validates: Requirements 2.2, 2.3**
   *
   * For any CodeFlowNode with a non-empty label, type, and description,
   * the InspectionPanel component SHALL render text content containing
   * the node's label, type, and description.
   */
  it('renders label, type, and description for any valid CodeFlowNode', () => {
    fc.assert(
      fc.property(arbCodeFlowNode, (node: CodeFlowNode) => {
        cleanup();

        act(() => {
          useGraphStore.setState({
            selectedNode: node,
            inspectionOpen: true,
            edges: [],
            nodes: [node],
          });
        });

        const { container } = render(<InspectionPanel />);
        const text = container.textContent || '';

        // Assert label is rendered
        expect(text).toContain(node.label);

        // Assert type is rendered
        expect(text).toContain(node.type);

        // Assert description is rendered
        expect(text).toContain(node.description);

        cleanup();
      }),
      { numRuns: 100 }
    );
  });
});
