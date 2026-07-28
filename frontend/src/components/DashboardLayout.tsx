import { useState } from 'react';
import type { AnalysisResponse, ArtifactsResponse } from '../types';
import { AudioTourPanel } from './AudioTourPanel';
import { CodeFlowGraph } from './CodeFlowGraph';
import { ERDatabaseGraph } from './ERDatabaseGraph';
import { DocumentationPanel } from './DocumentationPanel';
import { InspectionPanel } from './InspectionPanel';
import { SystemReportTab } from './SystemReportTab';
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

  const nodeCount = response.codeFlow?.nodes?.length || 0;
  const entityCount = response.erModel?.entities?.length || 0;
  const edgeCount = response.codeFlow?.edges?.length || 0;
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

      {/* ══════════════════════════════════════════════════════════════════
          TOP NAVIGATION BAR
      ══════════════════════════════════════════════════════════════════ */}
      <header className="shrink-0 h-14 bg-[#0A0E17] border-b border-white/[0.06] px-5 flex items-center gap-3 z-50">

        {/* Logo + Repo */}
        <button
          onClick={onNewAnalysis}
          className="shrink-0 flex items-center gap-2.5 group cursor-pointer"
        >
          <svg width="30" height="30" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg" className="shrink-0">
            <path d="M16 4C10.477 4 6 8.477 6 14v10c0 0.5 0.5 1 1 0.5l2-2 2 2 2-2 2 2 2-2 2 2 2-2 2 2c0.5 0.5 1 0 1-0.5V14c0-5.523-4.477-10-10-10z" fill="url(#hg)" opacity="0.95"/>
            <circle cx="12.5" cy="14" r="2" fill="#1e293b"/>
            <circle cx="19.5" cy="14" r="2" fill="#1e293b"/>
            <path d="M11 19l-2 1.5 2 1.5M21 19l2 1.5-2 1.5M14.5 23l3-5" stroke="#1e293b" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" opacity="0.7"/>
            <defs><linearGradient id="hg" x1="6" y1="4" x2="26" y2="28" gradientUnits="userSpaceOnUse"><stop stopColor="#818cf8"/><stop offset="1" stopColor="#6366f1"/></linearGradient></defs>
          </svg>
          <span className="text-[14px] font-bold text-white font-mono tracking-tight">
            <span className="text-indigo-400">dev</span><span className="text-slate-500">.</span><span className="text-white">ghost</span><span className="text-slate-500">()</span>
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

        {/* RIGHT SIDEBAR: Inspection Panel (only on codeflow tab) */}
        {activeTab === 'codeflow' && <InspectionPanel />}
      </div>
    </div>
  );
}
