import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import { TabView } from '../TabView';
import type { AnalysisResponse } from '../../types';

// Mock ReactFlow since it requires DOM measurements
vi.mock('@xyflow/react', () => ({
  ReactFlow: ({ children }: { children: React.ReactNode }) => <div data-testid="reactflow">{children}</div>,
  Controls: () => <div />,
  Background: () => <div />,
  Handle: () => <div />,
  Position: { Top: 'top', Bottom: 'bottom' },
}));

describe('TabView', () => {
  const mockResponse: AnalysisResponse = {
    codeFlow: { nodes: [], edges: [] },
    erModel: { entities: [], relations: [] },
    summary: 'Test summary',
  };

  it('renders "Code Flow Graph" and "ER Database Graph" tabs', () => {
    render(
      <TabView activeTab="codeflow" onTabChange={vi.fn()} response={mockResponse} />
    );

    expect(screen.getByRole('tab', { name: 'Code Flow Graph' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'ER Database Graph' })).toBeInTheDocument();
  });

  it('"Code Flow Graph" tab is initially active (aria-selected=true)', () => {
    render(
      <TabView activeTab="codeflow" onTabChange={vi.fn()} response={mockResponse} />
    );

    expect(screen.getByRole('tab', { name: 'Code Flow Graph' })).toHaveAttribute(
      'aria-selected',
      'true'
    );
    expect(screen.getByRole('tab', { name: 'ER Database Graph' })).toHaveAttribute(
      'aria-selected',
      'false'
    );
  });

  it('clicking "ER Database Graph" calls onTabChange', async () => {
    const onTabChange = vi.fn();
    const user = userEvent.setup();

    render(
      <TabView activeTab="codeflow" onTabChange={onTabChange} response={mockResponse} />
    );

    await user.click(screen.getByRole('tab', { name: 'ER Database Graph' }));

    expect(onTabChange).toHaveBeenCalledWith('er');
  });
});
