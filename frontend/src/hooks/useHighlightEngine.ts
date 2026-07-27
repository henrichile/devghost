import { useEffect, useRef } from 'react';
import type { CodeFlowNode } from '../types';
import { useGraphStore } from '../store/useGraphStore';

/**
 * Selects one representative node per distinct NodeType group.
 * For each unique NodeType in the input, picks the first node of that type
 * (deterministic, stable ordering based on input array order).
 */
export function selectRepresentativeNodes(nodes: CodeFlowNode[]): CodeFlowNode[] {
  const seen = new Set<string>();
  const result: CodeFlowNode[] = [];

  for (const node of nodes) {
    if (!seen.has(node.type)) {
      seen.add(node.type);
      result.push(node);
    }
  }

  return result;
}

/**
 * Calculates the interval time for each node highlight.
 * Distributes the total duration evenly across all nodes.
 */
export function calculateInterval(duration: number, nodeCount: number): number {
  if (nodeCount <= 0) return 0;
  return duration / nodeCount;
}

/**
 * Hook that manages highlight sequencing during audio tour playback.
 *
 * On isPlaying=true: selects one representative node per type group,
 * calculates interval timing, and cycles through nodes calling
 * setHighlightedNode on the store.
 *
 * On isPlaying=false or unmount: clears interval and resets highlight.
 */
export function useHighlightEngine(
  nodes: CodeFlowNode[],
  duration: number,
  isPlaying: boolean
): void {
  const setHighlightedNode = useGraphStore((state) => state.setHighlightedNode);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const indexRef = useRef(0);

  useEffect(() => {
    // Clean up any existing interval
    if (intervalRef.current !== null) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }

    if (!isPlaying) {
      setHighlightedNode(null);
      return;
    }

    const selectedNodes = selectRepresentativeNodes(nodes);

    if (selectedNodes.length === 0) {
      setHighlightedNode(null);
      return;
    }

    const interval = calculateInterval(duration, selectedNodes.length);
    indexRef.current = 0;

    // Highlight the first node immediately
    setHighlightedNode(selectedNodes[0].id);

    intervalRef.current = setInterval(() => {
      indexRef.current = indexRef.current + 1;

      if (indexRef.current >= selectedNodes.length) {
        // Tour complete - clear interval and reset
        if (intervalRef.current !== null) {
          clearInterval(intervalRef.current);
          intervalRef.current = null;
        }
        setHighlightedNode(null);
        return;
      }

      setHighlightedNode(selectedNodes[indexRef.current].id);
    }, interval);

    // Cleanup on unmount or dependency change
    return () => {
      if (intervalRef.current !== null) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
      setHighlightedNode(null);
    };
  }, [nodes, duration, isPlaying, setHighlightedNode]);
}
