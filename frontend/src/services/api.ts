import type { AnalysisResponse } from '../types';

const API_BASE_URL = '/analyze';
const TIMEOUT_MS = 600_000; // 10 minutes — accounts for LLM processing of all nodes

/**
 * Sends a repository URL to the backend for analysis.
 * Uses AbortController with a 130-second timeout.
 *
 * @param url - The repository URL to analyze
 * @returns The analysis response from the backend
 * @throws Error with descriptive message for HTTP errors, timeouts, or network failures
 */
export async function analyzeRepo(url: string): Promise<AnalysisResponse> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), TIMEOUT_MS);

  try {
    const response = await fetch(API_BASE_URL, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ repo_url: url }),
      signal: controller.signal,
    });

    if (!response.ok) {
      let detail = `La solicitud falló con estado ${response.status}`;
      try {
        const errorBody = await response.json();
        if (errorBody.detail) {
          detail = errorBody.detail;
        }
      } catch {
        // If we can't parse the error body, use the default message
      }
      throw new Error(detail);
    }

    const data: AnalysisResponse = await response.json();
    return data;
  } catch (error: unknown) {
    // Check for AbortError (timeout) - DOMException may not extend Error in all environments
    if (
      error instanceof DOMException ||
      (error instanceof Error && error.name === 'AbortError')
    ) {
      if ((error as { name: string }).name === 'AbortError') {
        throw new Error(
          'La solicitud de análisis expiró después de 10 minutos. El repositorio puede ser muy grande o el servidor está ocupado. Intenta de nuevo más tarde.'
        );
      }
    }
    if (error instanceof Error) {
      // Network errors (TypeError thrown by fetch on connection failure)
      if (error.name === 'TypeError') {
        throw new Error(
          'No se pudo conectar al servidor de análisis. Verifica tu conexión a internet e intenta de nuevo.'
        );
      }
      // Re-throw our own HTTP errors (or any other Error)
      throw error;
    }
    // Fallback for non-Error throws
    throw new Error(
      'No se pudo conectar al servidor de análisis. Verifica tu conexión a internet e intenta de nuevo.'
    );
  } finally {
    clearTimeout(timeoutId);
  }
}


import type { ArtifactsResponse } from '../types';

const ARTIFACTS_URL = '/api/artifacts';

/**
 * Requests documentation artifacts generation from the backend.
 */
export async function generateArtifacts(repoUrl: string): Promise<ArtifactsResponse> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 180_000); // 3 min for LLM generation

  try {
    const response = await fetch(ARTIFACTS_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ repo_url: repoUrl }),
      signal: controller.signal,
    });

    if (!response.ok) {
      let detail = `Error ${response.status}`;
      try {
        const errorBody = await response.json();
        if (errorBody.detail) detail = errorBody.detail;
      } catch { /* ignore */ }
      throw new Error(detail);
    }

    return await response.json();
  } catch (error: unknown) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new Error('La generación de artefactos expiró. Intenta de nuevo.');
    }
    if (error instanceof Error) throw error;
    throw new Error('Error de conexión al generar artefactos.');
  } finally {
    clearTimeout(timeoutId);
  }
}


/**
 * Requests deep analysis of a specific method/function from the backend LLM.
 */
export async function analyzeMethod(params: {
  methodName: string;
  componentName: string;
  componentType: string;
  allMethods: string[];
  description: string;
  dependencies: string[];
  dependents: string[];
  sourceCode: string;
}): Promise<{ analysis: string | null }> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 60_000);

  try {
    const response = await fetch('/api/analyze-method', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        method_name: params.methodName,
        component_name: params.componentName,
        component_type: params.componentType,
        all_methods: params.allMethods,
        description: params.description,
        dependencies: params.dependencies,
        dependents: params.dependents,
        source_code: params.sourceCode,
      }),
      signal: controller.signal,
    });

    if (!response.ok) throw new Error(`Error ${response.status}`);
    return await response.json();
  } catch (error: unknown) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new Error('El análisis de la función expiró.');
    }
    if (error instanceof Error) throw error;
    throw new Error('Error de conexión.');
  } finally {
    clearTimeout(timeoutId);
  }
}
