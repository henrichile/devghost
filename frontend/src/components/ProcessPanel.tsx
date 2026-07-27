import { useEffect, useRef, useCallback, useMemo } from 'react';
import type { AgentEvent, AgentPanelEntry } from '../types/streaming';
import { formatElapsedTime, formatDuration, truncateMessage } from '../utils/formatters';
import { GhostLoader } from './GhostLoader';

export interface ProcessPanelProps {
  events: AgentEvent[];
  startTime: number;
}

const AGENT_DISPLAY_NAMES: Record<string, string> = {
  ast_analyzer: 'Analizando AST y Code Flow',
  er_extractor: 'Extrayendo modelo ER',
  code_auditor: 'Auditando código',
  doc_generator: 'Generando documentación',
  system_reporter: 'Detectando stack tecnológico',
};

function buildEntries(events: AgentEvent[], startTime: number): AgentPanelEntry[] {
  const entryMap = new Map<string, AgentPanelEntry>();
  const order: string[] = [];

  for (const event of events) {
    const agentId = event.agent;
    if (!agentId) continue;

    if (!entryMap.has(agentId)) {
      const eventTime = new Date(event.timestamp).getTime();
      const startedAt = isNaN(eventTime) ? 0 : eventTime - startTime;
      entryMap.set(agentId, {
        agent: agentId,
        status: 'running',
        messages: [],
        startedAt: Math.max(0, startedAt),
      });
      order.push(agentId);
    }

    const entry = entryMap.get(agentId)!;

    switch (event.type) {
      case 'agent_start':
        entry.messages.push(event.message);
        break;
      case 'agent_progress':
        entry.messages.push(event.message);
        break;
      case 'agent_complete':
        entry.status = 'complete';
        entry.durationMs = event.duration_ms;
        break;
      case 'agent_error':
        entry.status = 'error';
        entry.error = event.error || event.message;
        break;
    }
  }

  return order.map((id) => entryMap.get(id)!);
}

export function ProcessPanel({ events, startTime }: ProcessPanelProps) {
  const logRef = useRef<HTMLDivElement>(null);
  const isAutoScrolling = useRef(true);

  const entries = useMemo(() => buildEntries(events, startTime), [events, startTime]);

  const completedCount = entries.filter(e => e.status === 'complete').length;
  const totalAgents = 5;
  const progress = Math.min(95, (completedCount / totalAgents) * 100);

  useEffect(() => {
    if (isAutoScrolling.current && logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [events]);

  const handleScroll = useCallback(() => {
    const el = logRef.current;
    if (!el) return;
    const isAtBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 30;
    isAutoScrolling.current = isAtBottom;
  }, []);

  return (
    <div className="fixed inset-0 bg-[#060911] z-50 flex flex-col items-center justify-center px-4">
      {/* Background glows */}
      <div className="absolute top-1/3 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[500px] h-[500px] bg-purple-600/8 rounded-full blur-[120px] pointer-events-none" />
      <div className="absolute bottom-1/3 left-1/2 -translate-x-1/2 w-[300px] h-[300px] bg-cyan-500/6 rounded-full blur-[100px] pointer-events-none" />

      <div className="relative z-10 max-w-md w-full space-y-6 text-center">
        {/* Ghost animation */}
        <div className="flex justify-center">
          <GhostLoader />
        </div>

        {/* Title */}
        <h2 className="text-xl font-bold text-slate-100">Analizando repositorio</h2>
        <p className="text-[13px] text-slate-500 leading-relaxed">
          Agentes autónomos procesando en paralelo. Progreso en tiempo real.
        </p>

        {/* Progress bar */}
        <div className="w-full">
          <div className="h-2 bg-slate-800 rounded-full overflow-hidden border border-slate-700/30">
            <div
              className="h-full bg-gradient-to-r from-purple-500 via-cyan-400 to-blue-500 rounded-full transition-all duration-700 ease-out"
              style={{ width: `${progress}%` }}
            />
          </div>
          <div className="flex justify-between mt-2 text-xs text-slate-500">
            <span>{completedCount}/{totalAgents} agentes</span>
            <span>{formatElapsedTime(Date.now() - startTime).replace('+', '')} transcurridos</span>
          </div>
        </div>

        {/* Real-time agent entries */}
        <div
          ref={logRef}
          onScroll={handleScroll}
          className="space-y-2.5 text-left max-h-[280px] overflow-y-auto pr-1"
        >
          {entries.length === 0 ? (
            <div className="flex items-center gap-3 px-4 py-2.5 rounded-lg border bg-slate-800/60 border-cyan-500/30 text-cyan-300">
              <div className="shrink-0 w-5 h-5 flex items-center justify-center">
                <div className="w-2.5 h-2.5 rounded-full bg-cyan-400 animate-ping" />
              </div>
              <span className="text-sm font-medium">Inicializando agentes...</span>
            </div>
          ) : (
            entries.map((entry) => {
              const isActive = entry.status === 'running';
              const isDone = entry.status === 'complete';
              const isError = entry.status === 'error';
              const displayName = AGENT_DISPLAY_NAMES[entry.agent] || entry.agent;
              const latestMessage = entry.messages[entry.messages.length - 1] || '';

              return (
                <div
                  key={entry.agent}
                  className={`flex items-center gap-3 px-4 py-2.5 rounded-lg border transition-all duration-500 ${
                    isActive
                      ? 'bg-slate-800/60 border-cyan-500/30 text-cyan-300'
                      : isDone
                      ? 'bg-slate-900/30 border-slate-800/20 text-slate-400'
                      : isError
                      ? 'bg-red-900/10 border-red-500/20 text-red-300'
                      : 'bg-slate-900/20 border-slate-800/10 text-slate-600'
                  }`}
                >
                  <div className="shrink-0">
                    {isDone ? (
                      <svg className="w-5 h-5 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                      </svg>
                    ) : isError ? (
                      <svg className="w-5 h-5 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                      </svg>
                    ) : isActive ? (
                      <div className="w-5 h-5 flex items-center justify-center">
                        <div className="w-2.5 h-2.5 rounded-full bg-cyan-400 animate-ping" />
                      </div>
                    ) : (
                      <div className="w-5 h-5 flex items-center justify-center">
                        <div className="w-2 h-2 rounded-full bg-slate-700" />
                      </div>
                    )}
                  </div>
                  <div className="flex-1 min-w-0">
                    <span className="text-sm font-medium block">{displayName}</span>
                    {isActive && latestMessage && (
                      <span className="text-xs text-slate-500 block truncate">{truncateMessage(latestMessage)}</span>
                    )}
                    {isError && entry.error && (
                      <span className="text-xs text-red-400/80 block truncate">{truncateMessage(entry.error)}</span>
                    )}
                  </div>
                  <div className="shrink-0 text-xs text-slate-600 font-mono">
                    {isDone && entry.durationMs != null && (
                      <span className="text-emerald-400">{formatDuration(entry.durationMs)}</span>
                    )}
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}
