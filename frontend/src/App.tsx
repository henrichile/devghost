import { useState, useEffect, useRef, useCallback } from 'react';
import type { AnalysisResponse, ArtifactsResponse } from './types';
import { useAnalysisStream } from './hooks/useAnalysisStream';
import { ProcessPanel } from './components/ProcessPanel';
import { useGraphStore } from './store/useGraphStore';
import InitialHeroState from './components/InitialHeroState';
import { DashboardLayout } from './components/DashboardLayout';

function App() {
  const [repoUrl, setRepoUrl] = useState('');
  const [artifacts, setArtifacts] = useState<ArtifactsResponse | null>(null);

  const { startAnalysis, events, status, result, error, retry } = useAnalysisStream();
  const startTimeRef = useRef<number>(0);

  // Map SSE result to the format expected by DashboardLayout
  const response: AnalysisResponse | null = result;

  useEffect(() => {
    if (response?.codeFlow) {
      useGraphStore.getState().setGraphData(response.codeFlow.nodes, response.codeFlow.edges);
    }
    if (response?.artifacts) {
      setArtifacts(response.artifacts);
    }
    if (response?.nodeInspections) {
      useGraphStore.getState().setNodeInspections(response.nodeInspections);
    }
  }, [response]);

  const handleAnalyze = useCallback((url?: string) => {
    const targetUrl = url || repoUrl;
    if (!targetUrl) return;
    setRepoUrl(targetUrl);
    setArtifacts(null);
    startTimeRef.current = Date.now();
    startAnalysis(targetUrl);
  }, [repoUrl, startAnalysis]);

  // Idle state: show hero
  if (status === 'idle') {
    return <InitialHeroState onAnalyze={(url) => handleAnalyze(url)} />;
  }

  // Streaming/connecting state: show real-time process panel
  if (status === 'connecting' || status === 'streaming') {
    return <ProcessPanel events={events} startTime={startTimeRef.current} />;
  }

  // Error state
  if (status === 'error') {
    return (
      <div className="h-screen flex flex-col items-center justify-center bg-[#060911] text-white px-8">
        <div className="max-w-md w-full text-center space-y-6">
          <div className="w-16 h-16 mx-auto rounded-2xl bg-red-500/10 border border-red-500/20 flex items-center justify-center text-3xl">⚠️</div>
          <h2 className="text-lg font-bold text-red-300">Error en el análisis</h2>
          <p className="text-sm text-slate-400 leading-relaxed">{error}</p>
          <div className="flex gap-3 justify-center">
            <button
              onClick={retry}
              className="px-6 py-2.5 rounded-xl bg-cyan-600 text-sm font-semibold text-white hover:bg-cyan-500 transition-all"
            >
              Reintentar
            </button>
            <button
              onClick={() => window.location.reload()}
              className="px-6 py-2.5 rounded-xl bg-slate-700 text-sm font-semibold text-white hover:bg-slate-600 transition-all"
            >
              Volver al inicio
            </button>
          </div>
        </div>
      </div>
    );
  }

  // Complete state: show dashboard
  if (status === 'complete' && response) {
    return (
      <DashboardLayout
        response={response}
        repoUrl={repoUrl}
        artifacts={artifacts}
        onNewAnalysis={() => window.location.reload()}
      />
    );
  }

  return null;
}

export default App;
