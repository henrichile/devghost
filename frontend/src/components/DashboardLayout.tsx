import { useState } from 'react';
import type { AnalysisResponse, ArtifactsResponse } from '../types';
import { AudioTourPanel } from './AudioTourPanel';
import { CodeFlowGraph } from './CodeFlowGraph';
import { ERDatabaseGraph } from './ERDatabaseGraph';
import { DocumentationPanel } from './DocumentationPanel';
import { InspectionPanel } from './InspectionPanel';
import { SystemReportTab } from './SystemReportTab';
import { OnboardingTour } from './OnboardingTour';
import { useGraphStore } from '../store/useGraphStore';

interface DashboardLayoutProps {
  response: AnalysisResponse;
  repoUrl: string;
  artifacts: ArtifactsResponse | null;
  onNewAnalysis: () => void;
}

type MainTab = 'codeflow' | 'er' | 'docs' | 'system';

function extractRepoName(url: string): string {
  try {
    const parts = url.replace(/\.git$/, '').split('/');
    return parts[parts.length - 1] || 'repo';
  } catch {
    return 'repo';
  }
}

function extractGlobalScore(nodeInspections: Record<string, { descriptions: Record<string, string>; audit: string | null }>): number {
  const scores: number[] = [];
  Object.values(nodeInspections).forEach((ins) => {
    if (ins.audit) {
      const match = ins.audit.match(/(\d+)\s*\/\s*10/);
      if (match) scores.push(parseInt(match[1]));
    }
  });
  if (scores.length === 0) return 0;
  return Math.round((scores.reduce((a, b) => a + b, 0) / scores.length) * 10) / 10;
}

export function DashboardLayout({ response, repoUrl, artifacts, onNewAnalysis }: DashboardLayoutProps) {
  const [activeTab, setActiveTab] = useState<MainTab>('codeflow');
  const nodeInspections = useGraphStore((s) => s.nodeInspections);

  const nodeCount = response.codeFlow?.nodes.length || 0;
  const entityCount = response.erModel?.entities.length || 0;
  const edgeCount = response.codeFlow?.edges.length || 0;
  const repoName = extractRepoName(repoUrl);
  const globalScore = extractGlobalScore(nodeInspections);

  const tabs: { id: MainTab; label: string; icon: string }[] = [
    { id: 'codeflow', label: 'Code Flow', icon: '⚡' },
    { id: 'er', label: 'ER Database', icon: '🗄️' },
    { id: 'docs', label: 'Architecture', icon: '📐' },
    { id: 'system', label: 'System Report', icon: '📊' },
  ];

  return (
    <div className="h-screen flex flex-col bg-[#060911] text-white overflow-hidden font-sans">
      <OnboardingTour />

      {/* ══════════════════════════════════════════════════════════════════
          TOP NAVIGATION BAR
      ══════════════════════════════════════════════════════════════════ */}
      <header className="shrink-0 h-12 bg-[#0A0E17] border-b border-white/[0.06] px-4 flex items-center gap-3 z-50">

        {/* Logo + Repo */}
        <button
          onClick={onNewAnalysis}
          className="shrink-0 flex items-center gap-2 group cursor-pointer"
        >
          <div className="w-7 h-7 rounded-lg bg-cyan-600 flex items-center justify-center">
            <svg viewBox="0 0 24 24" className="w-4 h-4" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round">
              <path d="M12 3C8 3 5 7 5 12v8l2.5-2 2.5 2 2.5-2 2.5 2 2.5-2L20 20v-8c0-5-3-9-8-9z" />
              <circle cx="9.5" cy="10" r="1.5" fill="white" stroke="none" />
              <circle cx="14.5" cy="10" r="1.5" fill="white" stroke="none" />
            </svg>
          </div>
          <span className="text-[13px] font-bold text-white">
            dev<span className="text-cyan-400">.ghost</span><span className="text-slate-400">()</span>
          </span>
        </button>

        {/* Separator */}
        <div className="w-px h-5 bg-slate-700/60" />

        {/* Repo breadcrumb */}
        <div className="flex items-center gap-1.5 text-[12px]">
          <span className="text-slate-500">hexnchile</span>
          <span className="text-slate-600">/</span>
          <span className="text-white font-medium">{repoName}</span>
        </div>

        {/* Center: Tabs */}
        <nav className="flex items-center ml-auto mr-auto gap-1 p-1 rounded-lg bg-[#141A27] border border-slate-700/40">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`px-4 py-1.5 text-[11px] font-medium rounded-md transition-all ${
                activeTab === tab.id
                  ? 'bg-[#1E293B] text-white border border-slate-600/50'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <span className="mr-1.5">{tab.icon}</span>
              {tab.label}
            </button>
          ))}
        </nav>

        {/* Right: Audio Tour + Health + Version */}
        <div className="flex items-center gap-3">
          {response.summary && <AudioTourPanel summary={response.summary} />}

          {globalScore > 0 && (
            <div className="flex items-center gap-1.5 text-[11px]">
              <span className="text-slate-500">Global Health:</span>
              <span className={`font-bold ${globalScore >= 7 ? 'text-emerald-400' : globalScore >= 5 ? 'text-amber-400' : 'text-red-400'}`}>
                {globalScore}/10
              </span>
            </div>
          )}

          <span className="text-[10px] text-slate-600 border border-slate-700/40 px-2 py-0.5 rounded">v0.3.2 α</span>
        </div>
      </header>

      {/* ══════════════════════════════════════════════════════════════════
          METRICS BAR
      ══════════════════════════════════════════════════════════════════ */}
      <div className="shrink-0 h-7 bg-[#080C14] border-b border-white/[0.04] px-4 flex items-center gap-4 text-[10px]">
        <span className="flex items-center gap-1.5 text-slate-500">
          <span className="w-1.5 h-1.5 rounded-full bg-blue-400" />
          {nodeCount} AST Nodes
        </span>
        <span className="flex items-center gap-1.5 text-slate-500">
          <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />
          {edgeCount} Relations
        </span>
        <span className="flex items-center gap-1.5 text-slate-500">
          <span className="w-1.5 h-1.5 rounded-full bg-purple-400" />
          {entityCount} DB Tables
        </span>
      </div>

      {/* ══════════════════════════════════════════════════════════════════
          MAIN CONTENT AREA - 2 Panel Layout (Canvas + Sidebar)
      ══════════════════════════════════════════════════════════════════ */}
      <div className="flex-1 flex min-h-0 overflow-hidden">

        {/* CENTER: Main Canvas */}
        <main className="flex-1 min-w-0 min-h-0 flex flex-col overflow-hidden relative">

          {activeTab === 'codeflow' && <CodeFlowGraph data={response.codeFlow} />}
          {activeTab === 'er' && (
            response.erModel ? (
              <ERDatabaseGraph entities={response.erModel.entities} relations={response.erModel.relations} />
            ) : (
              <div className="flex items-center justify-center h-full text-slate-500 text-sm">
                No se detectaron entidades ER en este repositorio.
              </div>
            )
          )}
          {activeTab === 'docs' && (
            <DocumentationPanel repoUrl={repoUrl} artifacts={artifacts} artifactsLoading={false} />
          )}
          {activeTab === 'system' && (
            <SystemReportTab data={response.systemReport} />
          )}
        </main>

        {/* RIGHT SIDEBAR: Inspection Panel */}
        <InspectionPanel />
      </div>
    </div>
  );
}
