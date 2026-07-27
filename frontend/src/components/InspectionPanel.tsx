import { useState } from 'react';
import { useGraphStore } from '../store/useGraphStore';
import { getNodeStyle } from './CodeFlowGraph';
import { MarkdownRenderer } from './MarkdownRenderer';
import type { CodeFlowNode } from '../types';
import { analyzeMethod } from '../services/api';

function extractScore(audit: string): number {
  const match = audit.match(/(\d+)\s*\/\s*10/);
  return match ? parseInt(match[1]) : 0;
}

function MethodAnalysisModal({ content, methodName, loading, onClose }: { content: string | null; methodName: string; loading: boolean; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-6 bg-black/70 backdrop-blur-sm" onClick={onClose}>
      <div
        className="bg-white rounded-2xl shadow-2xl w-full max-w-5xl max-h-[85vh] overflow-hidden flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 bg-gray-50">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-cyan-100 flex items-center justify-center text-sm font-mono text-cyan-600">ƒ</div>
            <div>
              <h3 className="text-sm font-bold text-gray-900">Análisis de Función</h3>
              <span className="text-[11px] text-gray-500 font-mono">{methodName}</span>
            </div>
          </div>
          <button onClick={onClose} className="w-8 h-8 flex items-center justify-center rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors">✕</button>
        </div>
        <div className="flex-1 overflow-y-auto p-6">
          {loading ? (
            <div className="flex flex-col items-center justify-center py-16 space-y-4">
              <div className="w-8 h-8 border-2 border-cyan-500 border-t-transparent rounded-full animate-spin" />
              <p className="text-sm text-gray-500">Analizando <span className="font-mono font-medium text-gray-700">{methodName}</span>...</p>
              <p className="text-xs text-gray-400">Evaluando calidad, errores, flujo y consumidores</p>
            </div>
          ) : content ? (
            <MarkdownRenderer content={content} />
          ) : (
            <p className="text-sm text-gray-500 text-center py-8">No se pudo generar el análisis.</p>
          )}
        </div>
      </div>
    </div>
  );
}

function AuditModal({ content, onClose }: { content: string; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-6 bg-black/70 backdrop-blur-sm" onClick={onClose}>
      <div
        className="bg-white rounded-2xl shadow-2xl w-full max-w-5xl max-h-[85vh] overflow-hidden flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 bg-gray-50">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-blue-100 flex items-center justify-center text-sm">🔍</div>
            <h3 className="text-sm font-bold text-gray-900">Reporte de Auditoría Completo</h3>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => {
                const blob = new Blob([content], { type: 'text/markdown' });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url; a.download = 'audit-report.md'; a.click();
                URL.revokeObjectURL(url);
              }}
              className="px-3 py-1.5 text-[11px] font-medium rounded-lg bg-blue-50 border border-blue-200 text-blue-600 hover:bg-blue-100 transition-all"
            >⬇️ Descargar .md</button>
            <button onClick={onClose} className="w-8 h-8 flex items-center justify-center rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors">✕</button>
          </div>
        </div>
        <div className="flex-1 overflow-y-auto p-6">
          <MarkdownRenderer content={content} />
        </div>
      </div>
    </div>
  );
}

type InspectionTab = 'methods' | 'dependencies' | 'audit';

export function InspectionPanel() {
  const selectedNode = useGraphStore((s) => s.selectedNode);
  const inspectionOpen = useGraphStore((s) => s.inspectionOpen);
  const edges = useGraphStore((s) => s.edges);
  const nodes = useGraphStore((s) => s.nodes);
  const nodeInspections = useGraphStore((s) => s.nodeInspections);
  const [showAuditModal, setShowAuditModal] = useState(false);
  const [activeTab, setActiveTab] = useState<InspectionTab>('methods');
  const [methodAnalysis, setMethodAnalysis] = useState<{ name: string; content: string | null; loading: boolean } | null>(null);
  const [descriptionExpanded, setDescriptionExpanded] = useState(false);

  const handleMethodClick = async (method: string) => {
    if (!selectedNode) return;
    setMethodAnalysis({ name: method, content: null, loading: true });

    try {
      const outDeps = edges.filter((e) => e.source === selectedNode.id).map((e) => nodes.find((n) => n.id === e.target)?.label).filter(Boolean) as string[];
      const inDeps = edges.filter((e) => e.target === selectedNode.id).map((e) => nodes.find((n) => n.id === e.source)?.label).filter(Boolean) as string[];
      const sourceCode = inspection?.methodSources?.[method] || '';

      const result = await analyzeMethod({
        methodName: method,
        componentName: selectedNode.label,
        componentType: selectedNode.type,
        allMethods: selectedNode.methods || [],
        description: selectedNode.description || '',
        dependencies: outDeps,
        dependents: inDeps,
        sourceCode: sourceCode,
      });
      setMethodAnalysis({ name: method, content: result.analysis, loading: false });
    } catch {
      setMethodAnalysis({ name: method, content: null, loading: false });
    }
  };

  if (!inspectionOpen || !selectedNode) {
    return (
      <aside className="w-[420px] shrink-0 border-l border-white/[0.04] bg-[#0A0E17] flex flex-col items-center justify-center h-full px-10 text-center">
        <div className="space-y-4">
          <div className="w-16 h-16 mx-auto rounded-2xl bg-gradient-to-br from-slate-800/50 to-slate-900/50 border border-white/[0.04] flex items-center justify-center">
            <svg className="w-7 h-7 text-slate-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M15.042 21.672L13.684 16.6m0 0l-2.51 2.225.569-9.47 5.227 7.917-3.286-.672zM12 2.25V4.5m5.834.166l-1.591 1.591M20.25 10.5H18M7.757 14.743l-1.59 1.59M6 10.5H3.75m4.007-4.243l-1.59-1.59" />
            </svg>
          </div>
          <div>
            <p className="text-[12px] text-slate-500 font-medium">Selecciona un nodo</p>
            <p className="text-[10px] text-slate-700 mt-1">Haz clic en cualquier nodo del grafo para inspeccionar sus detalles</p>
          </div>
        </div>
      </aside>
    );
  }

  const inspection = nodeInspections[selectedNode.id];
  const methodDescriptions = inspection?.descriptions || {};
  const auditResult = inspection?.audit || null;
  const score = auditResult ? extractScore(auditResult) : 0;

  const outgoingEdges = edges.filter((e) => e.source === selectedNode.id);
  const incomingEdges = edges.filter((e) => e.target === selectedNode.id);
  const dependencies = outgoingEdges.map((e) => nodes.find((n) => n.id === e.target)).filter((n): n is CodeFlowNode => n != null);
  const dependents = incomingEdges.map((e) => nodes.find((n) => n.id === e.source)).filter((n): n is CodeFlowNode => n != null);
  const nodeStyle = getNodeStyle(selectedNode.type);
  const methodCount = selectedNode.methods?.length || 0;

  // Description handling
  const fullDescription = selectedNode.description || '';
  const isLongDescription = fullDescription.length > 120;
  const previewDescription = isLongDescription ? fullDescription.slice(0, 120) + '...' : fullDescription;

  return (
    <aside className="w-[420px] shrink-0 border-l border-white/[0.04] bg-[#0A0E17] flex flex-col h-full">
      {/* Header */}
      <div className="px-5 py-4 border-b border-white/[0.04] bg-[#0F1420]/50">
        <div className="flex items-center justify-between mb-2">
          <h4 className="text-[14px] font-bold text-white font-mono truncate max-w-[200px]">{selectedNode.label}</h4>
          <span
            className="text-[9px] font-bold uppercase tracking-widest text-white/90 px-2.5 py-1 rounded-lg shrink-0 ml-2"
            style={{ backgroundColor: `${nodeStyle.badge}30`, border: `1px solid ${nodeStyle.badge}50`, color: nodeStyle.badge }}
          >
            {selectedNode.type}
          </span>
        </div>
        {fullDescription && (
          <div>
            {descriptionExpanded ? (
              <div className="max-h-[250px] overflow-y-auto pr-1 rounded-lg bg-[#0A0E17] border border-white/[0.06] p-3 mt-2">
                <div className="text-[12px] text-slate-300 leading-relaxed [&_p]:mb-2 [&_strong]:text-white [&_ul]:list-disc [&_ul]:pl-4 [&_ul]:space-y-1 [&_li]:text-slate-300 [&_h1]:text-white [&_h1]:text-sm [&_h1]:font-bold [&_h1]:mb-2 [&_h2]:text-white [&_h2]:text-xs [&_h2]:font-bold [&_h2]:mb-1 [&_code]:bg-white/10 [&_code]:px-1 [&_code]:rounded [&_code]:text-cyan-300 whitespace-pre-wrap break-words">
                  {fullDescription}
                </div>
                <button
                  onClick={() => setDescriptionExpanded(false)}
                  className="mt-2 text-[11px] font-semibold text-cyan-400 hover:text-cyan-300 transition-colors"
                >
                  ▲ Colapsar
                </button>
              </div>
            ) : (
              <div>
                <p className="text-[12px] text-slate-400 leading-relaxed">{previewDescription}</p>
                {isLongDescription && (
                  <button
                    onClick={() => setDescriptionExpanded(true)}
                    className="mt-1.5 text-[11px] font-semibold text-cyan-400 hover:text-cyan-300 transition-colors"
                  >
                    ▼ Ver más información
                  </button>
                )}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Tab bar */}
      <div className="shrink-0 flex items-center gap-1 border-b border-white/[0.04] px-4 py-1 bg-[#0A0E17]">
        {([
          { id: 'methods' as const, label: `Methods`, count: methodCount },
          { id: 'dependencies' as const, label: 'Deps', count: dependencies.length + dependents.length },
          { id: 'audit' as const, label: 'Audit', count: score > 0 ? score : null },
        ]).map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`px-3 py-2 text-[11px] font-medium rounded-lg transition-all ${
              activeTab === tab.id
                ? 'bg-cyan-500/10 text-cyan-300 border border-cyan-500/20'
                : 'text-slate-500 hover:text-slate-300 hover:bg-white/[0.03]'
            }`}
          >
            {tab.label}
            {tab.count !== null && (
              <span className={`ml-1 text-[9px] ${activeTab === tab.id ? 'text-cyan-400' : 'text-slate-600'}`}>
                [{tab.count}]
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="flex-1 overflow-y-auto px-4 py-3">
        {activeTab === 'methods' && (
          <div className="space-y-1.5">
            {selectedNode.methods && selectedNode.methods.length > 0 ? (
              selectedNode.methods.map((method, idx) => (
                <div
                  key={idx}
                  onClick={() => handleMethodClick(method)}
                  className="px-3 py-2.5 rounded-lg bg-[#0F1420] border border-white/[0.04] hover:border-cyan-500/20 transition-colors group cursor-pointer"
                >
                  <div className="flex items-center gap-2">
                    <span className="text-[9px] text-cyan-500/60 font-mono">ƒ</span>
                    <span className="text-[11px] text-slate-200 font-mono font-medium group-hover:text-cyan-300 transition-colors">{method}</span>
                    <span className="ml-auto text-[8px] text-slate-700 group-hover:text-slate-500 transition-colors">
                      {inspection?.methodSources?.[method] ? '📄 código disponible' : 'click → análisis'}
                    </span>
                  </div>
                  {methodDescriptions[method] && (
                    <div className="text-[10px] text-slate-500 mt-1 pl-4 leading-relaxed">{methodDescriptions[method]}</div>
                  )}
                </div>
              ))
            ) : (
              <p className="text-[11px] text-slate-600 text-center py-6">Sin métodos detectados</p>
            )}
          </div>
        )}

        {activeTab === 'dependencies' && (
          <div className="space-y-4">
            {/* Mini dependency diagram */}
            {(dependencies.length > 0 || dependents.length > 0) && (
              <div className="rounded-lg border border-white/[0.06] bg-[#0F1420] p-3 mb-4">
                <div className="text-[9px] text-slate-500 uppercase tracking-wider mb-2 font-medium">Dependency Graph</div>
                <div className="flex flex-col items-center gap-1 py-2">
                  {/* Dependents (who uses this node) */}
                  {dependents.length > 0 && (
                    <>
                      <div className="flex flex-wrap justify-center gap-1.5">
                        {dependents.map((dep) => {
                          const ds = getNodeStyle(dep.type);
                          return (
                            <div key={dep.id} className="flex items-center gap-1 px-2 py-1 rounded bg-[#1a2035] border border-white/[0.04] text-[9px]">
                              <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: ds.badge }} />
                              <span className="text-slate-400 truncate max-w-[70px]">{dep.label}</span>
                            </div>
                          );
                        })}
                      </div>
                      <div className="flex flex-col items-center">
                        <div className="w-px h-3 bg-slate-600" />
                        <svg className="w-3 h-3 text-slate-600" viewBox="0 0 12 12"><path d="M6 0v9M3 6l3 3 3-3" stroke="currentColor" strokeWidth="1.5" fill="none" /></svg>
                      </div>
                    </>
                  )}
                  {/* Selected node (center) */}
                  <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-cyan-500/30 bg-cyan-500/5 text-[10px]">
                    <span className="w-2 h-2 rounded-full" style={{ backgroundColor: nodeStyle.badge }} />
                    <span className="text-white font-semibold">{selectedNode.label}</span>
                    <span className="text-slate-600 text-[8px]">{selectedNode.type}</span>
                  </div>
                  {/* Dependencies (what this node depends on) */}
                  {dependencies.length > 0 && (
                    <>
                      <div className="flex flex-col items-center">
                        <svg className="w-3 h-3 text-slate-600" viewBox="0 0 12 12"><path d="M6 0v9M3 6l3 3 3-3" stroke="currentColor" strokeWidth="1.5" fill="none" /></svg>
                        <div className="w-px h-3 bg-slate-600" />
                      </div>
                      <div className="flex flex-wrap justify-center gap-1.5">
                        {dependencies.map((dep) => {
                          const ds = getNodeStyle(dep.type);
                          return (
                            <div key={dep.id} className="flex items-center gap-1 px-2 py-1 rounded bg-[#1a2035] border border-white/[0.04] text-[9px]">
                              <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: ds.badge }} />
                              <span className="text-slate-400 truncate max-w-[70px]">{dep.label}</span>
                            </div>
                          );
                        })}
                      </div>
                    </>
                  )}
                </div>
              </div>
            )}

            {dependencies.length > 0 && (
              <div>
                <h5 className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider mb-2 flex items-center gap-2">
                  <span className="w-4 h-px bg-slate-700" />
                  Depends on ({dependencies.length})
                </h5>
                <div className="space-y-1">
                  {dependencies.map((dep) => {
                    const depStyle = getNodeStyle(dep.type);
                    return (
                      <div key={dep.id} className="flex items-center gap-2.5 px-3 py-2 rounded-lg bg-[#0F1420] border border-white/[0.04] hover:border-white/[0.08] transition-colors">
                        <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ backgroundColor: depStyle.badge }} />
                        <span className="text-[11px] text-slate-300 font-mono">{dep.label}</span>
                        <span className="text-[9px] text-slate-600 ml-auto font-mono">{dep.type}</span>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
            {dependents.length > 0 && (
              <div>
                <h5 className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider mb-2 flex items-center gap-2">
                  <span className="w-4 h-px bg-slate-700" />
                  Used by ({dependents.length})
                </h5>
                <div className="space-y-1">
                  {dependents.map((dep) => {
                    const depStyle = getNodeStyle(dep.type);
                    return (
                      <div key={dep.id} className="flex items-center gap-2.5 px-3 py-2 rounded-lg bg-[#0F1420] border border-white/[0.04] hover:border-white/[0.08] transition-colors">
                        <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ backgroundColor: depStyle.badge }} />
                        <span className="text-[11px] text-slate-300 font-mono">{dep.label}</span>
                        <span className="text-[9px] text-slate-600 ml-auto font-mono">{dep.type}</span>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
            {dependencies.length === 0 && dependents.length === 0 && (
              <p className="text-[11px] text-slate-600 text-center py-6">Sin dependencias detectadas</p>
            )}
          </div>
        )}

        {activeTab === 'audit' && (
          <div>
            {auditResult ? (
              <MarkdownRenderer content={auditResult} />
            ) : (
              <div className="text-center py-8 space-y-2">
                <div className="w-10 h-10 mx-auto rounded-xl bg-slate-800/50 flex items-center justify-center text-lg">📋</div>
                <p className="text-[11px] text-slate-600">Auditoría no disponible para este componente</p>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Bottom: Quality Score */}
      {score > 0 && (
        <div className="shrink-0 px-4 py-3 border-t border-white/[0.04] bg-[#0F1420]/50 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-1.5">
              <span className={`text-[16px] font-bold font-mono ${score >= 7 ? 'text-emerald-400' : score >= 5 ? 'text-amber-400' : 'text-red-400'}`}>
                {score}
              </span>
              <span className="text-[10px] text-slate-600">/10</span>
            </div>
            <div className="w-20 h-1.5 rounded-full bg-slate-800 overflow-hidden">
              <div
                className={`h-full rounded-full transition-all ${score >= 7 ? 'bg-emerald-400' : score >= 5 ? 'bg-amber-400' : 'bg-red-400'}`}
                style={{ width: `${score * 10}%` }}
              />
            </div>
          </div>
          <button
            onClick={() => setShowAuditModal(true)}
            className="px-3 py-1.5 text-[10px] font-semibold rounded-lg bg-purple-600 text-white hover:bg-purple-500 transition-all"
          >
            Ver Reporte Completo
          </button>
        </div>
      )}

      {/* Audit Modal */}
      {showAuditModal && auditResult && (
        <AuditModal content={auditResult} onClose={() => setShowAuditModal(false)} />
      )}

      {/* Method Analysis Modal */}
      {methodAnalysis && (
        <MethodAnalysisModal
          content={methodAnalysis.content}
          methodName={methodAnalysis.name}
          loading={methodAnalysis.loading}
          onClose={() => setMethodAnalysis(null)}
        />
      )}
    </aside>
  );
}
