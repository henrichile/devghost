import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { ERDatabaseGraph } from '../ERDatabaseGraph';

// Mock ReactFlow since it requires DOM measurements
vi.mock('@xyflow/react', () => ({
  ReactFlow: ({ children }: { children: React.ReactNode }) => <div data-testid="reactflow">{children}</div>,
  Controls: () => <div />,
  Background: () => <div />,
  Handle: () => <div />,
  Position: { Top: 'top', Bottom: 'bottom' },
  BackgroundVariant: { Dots: 'dots', Lines: 'lines', Cross: 'cross' },
  MarkerType: { ArrowClosed: 'arrowclosed' },
}));

describe('ERDatabaseGraph', () => {
  it('when entities and relations are empty, shows "No ER model data available" message', () => {
    render(<ERDatabaseGraph entities={[]} relations={[]} />);

    expect(
      screen.getByText(/no hay datos del modelo er/i)
    ).toBeInTheDocument();
  });
});
