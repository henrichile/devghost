import { useEffect, useRef, useCallback, useMemo, useState } from 'react';
import type { AgentEvent, AgentPanelEntry } from '../types/streaming';
import { formatElapsedTime, formatDuration, truncateMessage } from '../utils/formatters';
import { GhostLoader } from './GhostLoader';

export interface ProcessPanelProps {
  events: AgentEvent[];
  startTime: number;
}

const AGENT_DISPLAY_NAMES: Record<string, string> = {
  ast_analyzer: 'Análisis de Arquitectura',
  er_extractor: 'Modelo de Datos',
  code_auditor: 'Auditoría de Código',
  doc_generator: 'Documentación Técnica',
  system_reporter: 'Stack Tecnológico',
};

const AGENT_DESCRIPTIONS: Record<string, string> = {
  ast_analyzer: 'Escaneando archivos, clasificando componentes y mapeando dependencias entre módulos',
  er_extractor: 'Detectando entidades, atributos, claves primarias y relaciones del modelo de datos',
  code_auditor: 'Extrayendo código fuente, generando descripciones y evaluando calidad con IA',
  doc_generator: 'Generando C4, ADR, RBAC, plan de testing y casos de uso UML',
  system_reporter: 'Identificando lenguajes, frameworks, bases de datos e infraestructura',
};

const AGENT_ICONS: Record<string, string> = {
  ast_analyzer: '🏗️',
  er_extractor: '🗄️',
  code_auditor: '🔍',
  doc_generator: '📄',
  system_reporter: '⚙️',
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
  const [now, setNow] = useState(Date.now());

  // Update timer every second
  useEffect(() => {
    const interval = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(interval);
  }, []);

  const entries = useMemo(() => buildEntries(events, startTime), [events, startTime]);

  // Always show all 5 agents — merge real entries with pending placeholders
  const ALL_AGENT_IDS = ['ast_analyzer', 'er_extractor', 'code_auditor', 'doc_generator', 'system_reporter'];
  const allEntries = useMemo(() => {
    const entryMap = new Map(entries.map(e => [e.agent, e]));
    return ALL_AGENT_IDS.map(id => entryMap.get(id) || {
      agent: id,
      status: 'pending' as const,
      messages: [],
      startedAt: 0,
    });
  }, [entries]);

  const completedCount = allEntries.filter(e => e.status === 'complete').length;
  const totalAgents = 5;
  const progress = Math.min(95, (completedCount / totalAgents) * 100);

  // Estimate remaining time based on completed agents
  const elapsed = now - startTime;
  const getEstimate = () => {
    if (completedCount === 0) {
      if (elapsed < 30000) return 'Estimado: 2-4 minutos';
      if (elapsed < 90000) return 'Procesando repo grande...';
      return 'Repos grandes pueden tardar varios minutos';
    }
    // Calculate average time per agent and extrapolate
    const avgPerAgent = elapsed / completedCount;
    const remaining = (totalAgents - completedCount) * avgPerAgent;
    if (remaining < 30000) return 'Casi listo...';
    if (remaining < 60000) return `~${Math.ceil(remaining / 1000)}s restantes`;
    return `~${Math.ceil(remaining / 60000)} min restantes`;
  };

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
      {/* Background animated glows */}
      <div className="absolute top-1/4 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-purple-600/10 rounded-full blur-[150px] pointer-events-none animate-pulse" />
      <div className="absolute bottom-1/4 left-1/3 w-[400px] h-[400px] bg-cyan-500/8 rounded-full blur-[120px] pointer-events-none animate-[pulse_3s_ease-in-out_infinite]" />
      <div className="absolute top-1/2 right-1/4 w-[300px] h-[300px] bg-blue-500/6 rounded-full blur-[100px] pointer-events-none animate-[pulse_4s_ease-in-out_infinite_0.5s]" />

      {/* Subtle grid pattern */}
      <div className="absolute inset-0 opacity-[0.03]" style={{ backgroundImage: 'radial-gradient(circle, #38bdf8 1px, transparent 1px)', backgroundSize: '40px 40px' }} />

      <div className="relative z-10 max-w-lg w-full space-y-8 text-center">
        {/* Ghost animation */}
        <div className="flex justify-center mb-2">
          <GhostLoader />
        </div>

        {/* Title with gradient */}
        <div>
          <h2 className="text-2xl font-bold bg-gradient-to-r from-white via-slate-100 to-slate-300 bg-clip-text text-transparent">
            Analizando repositorio
          </h2>
          <p className="text-[13px] text-slate-500 leading-relaxed mt-2">
            {completedCount === 0 && 'Fase fundacional: analizando estructura del código...'}
            {completedCount === 1 && 'Análisis AST completado. Lanzando agentes en paralelo...'}
            {completedCount >= 2 && completedCount < 5 && `${completedCount} agentes completados. Procesando con IA...`}
            {completedCount === 5 && 'Todos los agentes finalizaron. Preparando resultados...'}
          </p>
        </div>

        {/* Progress bar with glow */}
        <div className="w-full px-2">
          <div className="h-2.5 bg-slate-800/80 rounded-full overflow-hidden border border-slate-700/40 shadow-inner">
            <div
              className="h-full bg-gradient-to-r from-purple-500 via-cyan-400 to-blue-500 rounded-full transition-all duration-700 ease-out relative"
              style={{ width: `${progress}%` }}
            >
              <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/20 to-transparent animate-[shimmer_2s_infinite] rounded-full" />
            </div>
          </div>
          <div className="flex justify-between mt-3 text-[12px] text-slate-400 font-medium">
            <span className="flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-pulse" />
              {completedCount}/{totalAgents} agentes
            </span>
            <span className="font-mono text-slate-500">{formatElapsedTime(now - startTime).replace('+', '')} transcurridos</span>
          </div>
          <div className="text-center mt-2">
            <span className="text-[11px] text-slate-600 italic">{getEstimate()}</span>
          </div>
        </div>

        {/* Real-time agent entries */}
        <div
          ref={logRef}
          onScroll={handleScroll}
          className="space-y-3 text-left max-h-[450px] overflow-y-auto pr-1 px-1"
        >
          {allEntries.map((entry, idx) => {
              const isActive = entry.status === 'running';
              const isDone = entry.status === 'complete';
              const isError = entry.status === 'error';
              const isPending = entry.status === 'pending';
              const displayName = AGENT_DISPLAY_NAMES[entry.agent] || entry.agent;
              const description = AGENT_DESCRIPTIONS[entry.agent] || '';
              const icon = AGENT_ICONS[entry.agent] || '⚡';
              const latestMessage = entry.messages[entry.messages.length - 1] || '';
              const statusText = isActive
                ? (latestMessage || description)
                : isPending
                ? 'En espera'
                : '';

              return (
                <div
                  key={entry.agent}
                  className={`flex items-center gap-3 px-5 py-3.5 rounded-xl border transition-all duration-500 ${
                    isActive
                      ? 'bg-gradient-to-r from-cyan-950/40 to-slate-800/60 border-cyan-500/30 text-cyan-200 shadow-lg shadow-cyan-500/5'
                      : isDone
                      ? 'bg-slate-900/30 border-emerald-500/10 text-slate-300'
                      : isError
                      ? 'bg-red-950/20 border-red-500/20 text-red-300'
                      : 'bg-slate-900/20 border-slate-700/20 text-slate-500'
                  }`}
                  style={{ animationDelay: `${idx * 100}ms` }}
                >
                  <div className="shrink-0">
                    {isDone ? (
                      <div className="w-8 h-8 rounded-lg bg-emerald-500/20 flex items-center justify-center text-sm">
                        ✅
                      </div>
                    ) : isError ? (
                      <div className="w-8 h-8 rounded-lg bg-red-500/20 flex items-center justify-center text-sm">
                        ❌
                      </div>
                    ) : isActive ? (
                      <div className="w-8 h-8 rounded-lg bg-cyan-500/10 border border-cyan-500/30 flex items-center justify-center text-sm relative">
                        <span>{icon}</span>
                        <div className="absolute -top-0.5 -right-0.5 w-2 h-2 rounded-full bg-cyan-400 animate-ping" />
                      </div>
                    ) : (
                      <div className="w-8 h-8 rounded-lg bg-slate-800/50 border border-slate-700/30 flex items-center justify-center text-sm opacity-50">
                        {icon}
                      </div>
                    )}
                  </div>
                  <div className="flex-1 min-w-0">
                    <span className={`text-[13px] font-bold block ${isDone ? 'text-slate-300' : isPending ? 'text-slate-500' : ''}`}>{displayName}</span>
                    {isActive && statusText && (
                      <span className="text-[11px] text-slate-400 block truncate mt-0.5">{truncateMessage(statusText)}</span>
                    )}
                    {isDone && (
                      <span className="text-[10px] text-emerald-500/70 block mt-0.5">Análisis finalizado</span>
                    )}
                    {isPending && (
                      <span className="text-[10px] text-slate-600 block mt-0.5">Esperando turno...</span>
                    )}
                    {isError && entry.error && (
                      <span className="text-[11px] text-red-400/80 block truncate mt-0.5">{truncateMessage(entry.error)}</span>
                    )}
                  </div>
                  <div className="shrink-0 text-[12px] font-mono">
                    {isDone && entry.durationMs != null && (
                      <span className="text-emerald-400 font-bold">{formatDuration(entry.durationMs)}</span>
                    )}
                    {isActive && (
                      <span className="text-cyan-500/60 text-[10px] animate-pulse">en curso</span>
                    )}
                    {isPending && (
                      <span className="text-slate-700 text-[10px]">—</span>
                    )}
                  </div>
                </div>
              );
            })}
        </div>
      </div>
    </div>
  );
}
