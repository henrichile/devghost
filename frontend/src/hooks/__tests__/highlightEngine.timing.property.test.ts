// Feature: interactive-ux-enhancements, Property 10: Highlight timing distribution
// **Validates: Requirements 4.2**

import { describe, it, expect } from 'vitest';
import * as fc from 'fast-check';
import { calculateInterval } from '../../hooks/useHighlightEngine';

describe('Property 10: Highlight timing distribution', () => {
  it('each interval ≈ D/N and sum of intervals = D for positive duration and node count', () => {
    fc.assert(
      fc.property(
        fc.float({ min: 1, max: 100000, noNaN: true }),
        fc.integer({ min: 1, max: 1000 }),
        (duration: number, nodeCount: number) => {
          const interval = calculateInterval(duration, nodeCount);

          // Each interval should equal D/N
          const expected = duration / nodeCount;
          expect(interval).toBeCloseTo(expected, 10);

          // Sum of all intervals (interval * N) should equal D within floating-point tolerance
          const totalTime = interval * nodeCount;
          expect(totalTime).toBeCloseTo(duration, 5);
        }
      ),
      { numRuns: 100 }
    );
  });

  it('returns 0 for nodeCount <= 0', () => {
    fc.assert(
      fc.property(
        fc.float({ min: 1, max: 100000, noNaN: true }),
        fc.integer({ min: -1000, max: 0 }),
        (duration: number, nodeCount: number) => {
          const interval = calculateInterval(duration, nodeCount);
          expect(interval).toBe(0);
        }
      ),
      { numRuns: 100 }
    );
  });
});
