import { describe, it, expect } from 'vitest';
import * as fc from 'fast-check';
import { getNodeStyle } from './CodeFlowGraph';
import type { NodeType } from '../types';

/**
 * Property 2: Distinct node types produce distinct visual indicators
 *
 * For any two CodeFlowNode values with different type fields, the
 * node-type-to-visual-style mapping function SHALL return different
 * background colors (or icons), ensuring visual distinguishability.
 *
 * **Validates: Requirements 3.5**
 */
describe('Property 2: Distinct node types produce distinct visual indicators', () => {
  const allNodeTypes: NodeType[] = [
    'Controller',
    'Service',
    'Route',
    'Middleware',
    'Repository',
    'Utility',
  ];

  const nodeTypeArb = fc.constantFrom<NodeType>(...allNodeTypes);

  it('distinct node types produce distinct background colors', () => {
    fc.assert(
      fc.property(
        nodeTypeArb,
        nodeTypeArb,
        (type1, type2) => {
          fc.pre(type1 !== type2);
          const style1 = getNodeStyle(type1);
          const style2 = getNodeStyle(type2);
          expect(style1.backgroundColor).not.toBe(style2.backgroundColor);
        }
      ),
      { numRuns: 100 }
    );
  });

  it('every node type returns a non-empty background color', () => {
    fc.assert(
      fc.property(nodeTypeArb, (type) => {
        const style = getNodeStyle(type);
        expect(style.backgroundColor).toBeDefined();
        expect(style.backgroundColor.length).toBeGreaterThan(0);
      }),
      { numRuns: 100 }
    );
  });
});
