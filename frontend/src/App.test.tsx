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
    // Verify that all component modules can be resolved
    const header = await import('./components/Header');
    const tabView = await import('./components/TabView');
    const audioTour = await import('./components/AudioTourPanel');
    const errorBanner = await import('./components/ErrorBanner');
    const loadingIndicator = await import('./components/LoadingIndicator');

    expect(header.Header).toBeDefined();
    expect(tabView.TabView).toBeDefined();
    expect(audioTour.AudioTourPanel).toBeDefined();
    expect(errorBanner.ErrorBanner).toBeDefined();
    expect(loadingIndicator.LoadingIndicator).toBeDefined();
  });

  it('imports analyzeRepo from the API service', async () => {
    const api = await import('./services/api');
    expect(api.analyzeRepo).toBeDefined();
    expect(typeof api.analyzeRepo).toBe('function');
  });
});
