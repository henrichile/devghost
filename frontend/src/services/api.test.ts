import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { analyzeRepo } from './api';
import type { AnalysisResponse } from '../types';

describe('analyzeRepo', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('sends POST to /analyze with correct body and headers', async () => {
    const mockResponse: AnalysisResponse = {
      codeFlow: null,
      erModel: null,
      summary: 'Test summary',
    };

    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(mockResponse), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    );

    const result = await analyzeRepo('https://github.com/user/repo');

    expect(fetchSpy).toHaveBeenCalledWith('/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ repo_url: 'https://github.com/user/repo' }),
      signal: expect.any(AbortSignal),
    });
    expect(result).toEqual(mockResponse);
  });

  it('returns parsed AnalysisResponse on success', async () => {
    const mockResponse: AnalysisResponse = {
      codeFlow: {
        nodes: [{ id: '1', label: 'UserService', type: 'Service', description: '' }],
        edges: [{ source: '1', target: '2', relation: 'imports' }],
      },
      erModel: {
        entities: [{ name: 'User', attributes: [{ name: 'id', type: 'int' }], primaryKey: 'id' }],
        relations: [{ from: 'User', to: 'Post', type: 'one-to-many', foreignKey: 'user_id' }],
      },
      summary: 'A REST API with services',
    };

    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(mockResponse), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    );

    const result = await analyzeRepo('https://github.com/user/repo');
    expect(result).toEqual(mockResponse);
  });

  it('throws error with detail message on HTTP 4xx', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ detail: 'git clone failed: repository not found' }), {
        status: 400,
        headers: { 'Content-Type': 'application/json' },
      })
    );

    await expect(analyzeRepo('https://github.com/user/bad-repo')).rejects.toThrow(
      'git clone failed: repository not found'
    );
  });

  it('throws error with detail message on HTTP 5xx', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ detail: 'Internal server error' }), {
        status: 500,
        headers: { 'Content-Type': 'application/json' },
      })
    );

    await expect(analyzeRepo('https://github.com/user/repo')).rejects.toThrow(
      'Internal server error'
    );
  });

  it('throws generic status error when error body has no detail field', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response('not json', { status: 502 })
    );

    await expect(analyzeRepo('https://github.com/user/repo')).rejects.toThrow(
      'La solicitud falló con estado 502'
    );
  });

  it('throws timeout error when AbortController fires after 130 seconds', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(
      (_url, options) =>
        new Promise((_resolve, reject) => {
          (options as RequestInit).signal?.addEventListener('abort', () => {
            const abortError = new DOMException('The operation was aborted.', 'AbortError');
            reject(abortError);
          });
        })
    );

    const promise = analyzeRepo('https://github.com/user/repo');

    // Advance time past the 130-second timeout
    vi.advanceTimersByTime(130_000);

    await expect(promise).rejects.toThrow(
      'La solicitud de análisis expiró después de 130 segundos'
    );
  });

  it('throws network error when fetch fails with TypeError', async () => {
    const networkError = new TypeError('Failed to fetch');
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(networkError);

    await expect(analyzeRepo('https://github.com/user/repo')).rejects.toThrow(
      'No se pudo conectar al servidor de análisis'
    );
  });
});
