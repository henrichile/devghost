import type { AnalysisResponse } from '../types';

const API_BASE_URL = '/analyze';
const TIMEOUT_MS = 130_000; // 130 seconds

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
          'La solicitud de análisis expiró después de 130 segundos. El repositorio puede ser muy grande o el servidor está ocupado. Intenta de nuevo más tarde.'
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
