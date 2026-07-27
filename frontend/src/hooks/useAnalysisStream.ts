import { useState, useRef, useCallback, useEffect } from 'react';
import type { AgentEvent } from '../types/streaming';
import type { AnalysisResponse } from '../types';

export type StreamStatus = 'idle' | 'connecting' | 'streaming' | 'complete' | 'error';

export interface UseAnalysisStreamReturn {
  startAnalysis: (repoUrl: string) => void;
  events: AgentEvent[];
  status: StreamStatus;
  result: AnalysisResponse | null;
  error: string | null;
  retry: () => void;
}

const INACTIVITY_TIMEOUT_MS = 300_000;

/**
 * React hook for consuming SSE events from the /analyze-stream endpoint.
 */
export function useAnalysisStream(): UseAnalysisStreamReturn {
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [status, setStatus] = useState<StreamStatus>('idle');
  const [result, setResult] = useState<AnalysisResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const abortControllerRef = useRef<AbortController | null>(null);
  const lastRepoUrlRef = useRef<string>('');
  const inactivityTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearInactivityTimer = useCallback(() => {
    if (inactivityTimerRef.current !== null) {
      clearTimeout(inactivityTimerRef.current);
      inactivityTimerRef.current = null;
    }
  }, []);

  const resetInactivityTimer = useCallback(
    (onTimeout: () => void) => {
      clearInactivityTimer();
      inactivityTimerRef.current = setTimeout(onTimeout, INACTIVITY_TIMEOUT_MS);
    },
    [clearInactivityTimer]
  );

  const startAnalysis = useCallback(
    (repoUrl: string) => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }

      setEvents([]);
      setResult(null);
      setError(null);
      setStatus('connecting');
      lastRepoUrlRef.current = repoUrl;

      const controller = new AbortController();
      abortControllerRef.current = controller;

      const handleTimeout = () => {
        controller.abort();
        setError('Conexión perdida: no se recibieron datos en 5 minutos');
        setStatus('error');
      };

      (async () => {
        try {
          const response = await fetch('/analyze-stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ repo_url: repoUrl }),
            signal: controller.signal,
          });

          if (!response.ok) {
            let errorMessage: string;
            try {
              const errorBody = await response.json();
              errorMessage = errorBody.detail || `HTTP ${response.status}: ${response.statusText}`;
            } catch {
              errorMessage = `HTTP ${response.status}: ${response.statusText}`;
            }
            setError(errorMessage);
            setStatus('error');
            return;
          }

          setStatus('streaming');

          const reader = response.body?.getReader();
          if (!reader) {
            setError('El cuerpo de la respuesta no es legible');
            setStatus('error');
            return;
          }

          const decoder = new TextDecoder();
          let buffer = '';

          resetInactivityTimer(handleTimeout);

          while (true) {
            const { done, value } = await reader.read();

            if (done) break;

            resetInactivityTimer(handleTimeout);

            buffer += decoder.decode(value, { stream: true });

            const parts = buffer.split('\n\n');
            buffer = parts.pop() || '';

            for (const part of parts) {
              const trimmed = part.trim();
              if (!trimmed) continue;

              let jsonStr: string | null = null;
              for (const line of trimmed.split('\n')) {
                if (line.startsWith('data: ')) {
                  jsonStr = line.slice(6);
                } else if (line.startsWith('data:')) {
                  jsonStr = line.slice(5);
                }
              }

              if (!jsonStr) continue;

              let event: AgentEvent;
              try {
                event = JSON.parse(jsonStr) as AgentEvent;
              } catch {
                continue;
              }

              setEvents((prev) => [...prev, event]);

              if (event.type === 'analysis_complete') {
                setResult(event.result as unknown as AnalysisResponse ?? null);
                setStatus('complete');
                clearInactivityTimer();
                reader.cancel();
                return;
              }

              if (event.type === 'analysis_error') {
                setError(event.error || event.message || 'El análisis falló');
                setStatus('error');
                clearInactivityTimer();
                reader.cancel();
                return;
              }
            }
          }

          clearInactivityTimer();
          setStatus((currentStatus) => {
            if (currentStatus === 'streaming') {
              setError('Conexión cerrada antes de completar el análisis');
              return 'error';
            }
            return currentStatus;
          });
        } catch (err: unknown) {
          clearInactivityTimer();
          if (err instanceof DOMException && err.name === 'AbortError') {
            return;
          }
          const message = err instanceof Error ? err.message : 'Ocurrió un error inesperado';
          setError(message);
          setStatus('error');
        }
      })();
    },
    [clearInactivityTimer, resetInactivityTimer]
  );

  const retry = useCallback(() => {
    if (lastRepoUrlRef.current) {
      startAnalysis(lastRepoUrlRef.current);
    }
  }, [startAnalysis]);

  useEffect(() => {
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
      clearInactivityTimer();
    };
  }, [clearInactivityTimer]);

  return { startAnalysis, events, status, result, error, retry };
}
