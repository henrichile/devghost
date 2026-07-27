import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { CodeFlowGraph } from '../CodeFlowGraph';

// Mock ReactFlow since it requires DOM measurements
vi.mock('@xyflow/react', () => ({
  ReactFlow: ({ children }: { children: React.ReactNode }) => <div data-testid="reactflow">{children}</div>,
  Controls: () => <div />,
  Background: () => <div />,
  BackgroundVariant: { Dots: 'dots', Lines: 'lines', Cross: 'cross' },
  MarkerType: { ArrowClosed: 'arrowclosed' },
  MiniMap: () => <div />,
  useReactFlow: () => ({ fitView: vi.fn() }),
  Handle: () => <div />,
  Position: { Top: 'top', Bottom: 'bottom' },
}));

describe('CodeFlowGraph', () => {
  it('when data is null, shows "No code flow data available" message', () => {
    render(<CodeFlowGraph data={null} />);

    expect(
      screen.getByText(/no hay datos de flujo de código/i)
    ).toBeInTheDocument();
  });
});
