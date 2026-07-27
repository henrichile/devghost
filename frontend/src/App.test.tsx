import { describe, it, expect, vi } from 'vitest';

// Mock the API service
vi.mock('./services/api', () => ({
  analyzeRepo: vi.fn(),
}));

describe('App module', () => {
  it('exports a default function component', async () => {
    const module = await import('./App');
    expect(module.default).toBeDefined();
    expect(typeof module.default).toBe('function');
  });

  it('imports all required child components', async () => {
    const dashboardLayout = await import('./components/DashboardLayout');
    const audioTour = await import('./components/AudioTourPanel');
    const loadingIndicator = await import('./components/LoadingIndicator');

    expect(dashboardLayout.DashboardLayout).toBeDefined();
    expect(audioTour.AudioTourPanel).toBeDefined();
    expect(loadingIndicator.LoadingIndicator).toBeDefined();
  });

  it('imports analyzeRepo from the API service', async () => {
    const api = await import('./services/api');
    expect(api.analyzeRepo).toBeDefined();
    expect(typeof api.analyzeRepo).toBe('function');
  });
});
