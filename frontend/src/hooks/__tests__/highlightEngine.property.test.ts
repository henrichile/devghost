// Feature: interactive-ux-enhancements, Property 9: Highlight node selection covers all type groups
// **Validates: Requirements 4.1**

import { describe, it, expect } from 'vitest';
import * as fc from 'fast-check';
import { selectRepresentativeNodes } from '../useHighlightEngine';
import type { CodeFlowNode, NodeType } from '../../types';

const ALL_NODE_TYPES: NodeType[] = [
  'Controller',
  'Service',
  'Route',
  'Middleware',
  'Repository',
  'Utility',
];

/**
 * Arbitrary that generates a non-empty subset of NodeType values
 * and then generates a list of CodeFlowNodes covering exactly those types.
 */
const nodesWithDistinctTypes = fc
  .subarray(ALL_NODE_TYPES, { minLength: 1, maxLength: ALL_NODE_TYPES.length })
  .chain((selectedTypes) =>
    fc
      .tuple(
        ...selectedTypes.map((type) =>
          fc
            .integer({ min: 1, max: 5 })
            .chain((count) =>
              fc.array(
                fc.record({
                  id: fc.uuid(),
                  label: fc.string({ minLength: 1, maxLength: 30 }),
                  type: fc.constant(type),
                  description: fc.string({ minLength: 0, maxLength: 120 }),
                }),
                { minLength: count, maxLength: count }
              )
            )
        )
      )
      .map((arrays) => ({
        nodes: arrays.flat() as CodeFlowNode[],
        expectedTypeCount: selectedTypes.length,
        expectedTypes: new Set(selectedTypes),
      }))
  );

describe('HighlightEngine - Property 9: Highlight node selection covers all type groups', () => {
  it('should return exactly N nodes for N distinct NodeType values, one per type', () => {
    fc.assert(
      fc.property(nodesWithDistinctTypes, ({ nodes, expectedTypeCount, expectedTypes }) => {
        const result = selectRepresentativeNodes(nodes);

        // 1. Returns exactly N nodes (one per distinct type)
        expect(result).toHaveLength(expectedTypeCount);

        // 2. Each returned node has a unique type (no duplicates)
        const resultTypes = result.map((n) => n.type);
        const uniqueResultTypes = new Set(resultTypes);
        expect(uniqueResultTypes.size).toBe(resultTypes.length);

        // 3. Every distinct type in the input is represented
        for (const type of expectedTypes) {
          expect(uniqueResultTypes.has(type)).toBe(true);
        }
      }),
      { numRuns: 100 }
    );
  });
});
