import { useState } from 'react';
import type { ArtifactsResponse } from '../types';
import { MermaidDiagram } from './MermaidDiagram';
import { MarkdownRenderer } from './MarkdownRenderer';

interface DocumentationPanelProps {
  repoUrl: string;
  artifacts: ArtifactsResponse | null;
  artifactsLoading: boolean;
}

type ArtifactTab = 'c4' | 'dictionary' | 'adr' | 'rbac' | 'testing' | 'usecases' | 'uml';

const FALLBACK_C4 = `flowchart TD
    A[Cliente] --> B[Controlador]
    B --> C[Servicio]
    C --> D[(Base de Datos)]`;

const FALLBACK_DICTIONARY = `No se pudo generar el diccionario. Intenta analizar nuevamente.`;
const FALLBACK_ADR = `No se pudo generar el ADR. Intenta analizar nuevamente.`;
const FALLBACK_RBAC = `No se pudo generar la matriz RBAC. Intenta analizar nuevamente.`;
const FALLBACK_TESTING = `No se pudo generar el plan de testing. Intenta analizar nuevamente.`;
const FALLBACK_USECASES = `No se pudo generar los casos de uso. Intenta analizar nuevamente.`;
const FALLBACK_UML = `No se pudo generar el análisis UML. Intenta analizar nuevamente.`;

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      onClick={() => {
        navigator.clipboard.writeText(text).then(() => {
          setCopied(true);
          setTimeout(() => setCopied(false), 2000);
        });
      }}
      className="px-2.5 py-1 text-[10px] font-medium rounded-md bg-slate-700/50 hover:bg-slate-600/50 text-slate-400 transition-colors"
    >
      {copied ? '✓ Copiado' : '📋 Copiar'}
    </button>
  );
}

function DownloadButton({ text, filename }: { text: string; filename: string }) {
  return (
    <button
      onClick={() => {
        const blob = new Blob([text], { type: 'text/markdown' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        a.click();
        URL.revokeObjectURL(url);
      }}
      className="px-2.5 py-1 text-[10px] font-medium rounded-md bg-cyan-500/10 hover:bg-cyan-500/20 text-cyan-400 transition-colors"
    >
      ⬇️ Descargar
    </button>
  );
}

export function DocumentationPanel({ artifacts, artifactsLoading }: DocumentationPanelProps) {
  const [activeArtifact, setActiveArtifact] = useState<ArtifactTab>('c4');

  const tabs: { id: ArtifactTab; label: string; icon: string }[] = [
    { id: 'c4', label: 'C4 Mermaid', icon: '🏗️' },
    { id: 'dictionary', label: 'Diccionario ER', icon: '📖' },
    { id: 'adr', label: 'ADR-001', icon: '📝' },
    { id: 'rbac', label: 'RBAC', icon: '🔐' },
    { id: 'testing', label: 'Testing', icon: '🧪' },
    { id: 'usecases', label: 'Casos de Uso', icon: '📋' },
    { id: 'uml', label: 'Análisis UML', icon: '📐' },
  ];

  const getContent = (tab: ArtifactTab): string => {
    if (artifacts) {
      if (tab === 'c4') return artifacts.c4Mermaid || FALLBACK_C4;
      if (tab === 'dictionary') return artifacts.dbDictionary || FALLBACK_DICTIONARY;
      if (tab === 'adr') return artifacts.adrDocument || FALLBACK_ADR;
      if (tab === 'rbac') return artifacts.rbacMatrix || FALLBACK_RBAC;
      if (tab === 'usecases') return artifacts.useCasesDoc || FALLBACK_USECASES;
      if (tab === 'uml') return artifacts.useCases || FALLBACK_UML;
      return artifacts.testPlan || FALLBACK_TESTING;
    }
    if (tab === 'c4') return FALLBACK_C4;
    if (tab === 'dictionary') return FALLBACK_DICTIONARY;
    if (tab === 'adr') return FALLBACK_ADR;
    if (tab === 'rbac') return FALLBACK_RBAC;
    if (tab === 'usecases') return FALLBACK_USECASES;
    if (tab === 'uml') return FALLBACK_UML;
    return FALLBACK_TESTING;
  };

  const currentContent = getContent(activeArtifact);

  const currentFilename = activeArtifact === 'c4'
    ? 'c4-diagram.mmd'
    : activeArtifact === 'dictionary'
    ? 'db-dictionary.md'
    : activeArtifact === 'adr'
    ? 'adr-001.md'
    : activeArtifact === 'rbac'
    ? 'rbac-matrix.md'
    : activeArtifact === 'usecases'
    ? 'use-cases.md'
    : 'test-plan.md';

  return (
    <div className="flex flex-col h-full">
      {/* Sub-tabs */}
      <div className="shrink-0 flex items-center gap-1 px-4 py-2 border-b border-slate-800/40 bg-[#0a0e18]/80">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveArtifact(tab.id)}
            className={`px-3 py-1.5 text-[11px] font-medium rounded-lg transition-all ${
              activeArtifact === tab.id
                ? 'bg-purple-500/20 text-purple-300 border border-purple-500/30 shadow-sm shadow-purple-500/10'
                : 'text-slate-500 hover:text-slate-300 hover:bg-slate-800/40'
            }`}
          >
            {tab.icon} {tab.label}
          </button>
        ))}
        <div className="ml-auto flex gap-1.5">
          <CopyButton text={currentContent} />
          <DownloadButton text={currentContent} filename={currentFilename} />
          {artifactsLoading && (
            <span className="px-2.5 py-1 text-[10px] text-cyan-400 animate-pulse">⏳ Generando...</span>
          )}
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-auto p-4 bg-white/[0.02]">
        {activeArtifact === 'c4' && currentContent ? (
          <MermaidDiagram code={currentContent} />
        ) : currentContent ? (
          <MarkdownRenderer content={currentContent} />
        ) : (
          <div className="flex items-center justify-center h-full text-slate-500 text-sm">
            Este artefacto no pudo ser generado.
          </div>
        )}
      </div>
    </div>
  );
}
