/**
 * Frontend event models for Agent Streaming & Reporting.
 */

export type AgentEventType =
  | 'agent_start'
  | 'agent_progress'
  | 'agent_complete'
  | 'analysis_complete'
  | 'agent_error'
  | 'analysis_error';

export type AgentIdentifier =
  | 'ast_analyzer'
  | 'er_extractor'
  | 'code_auditor'
  | 'doc_generator'
  | 'system_reporter';

export interface AgentEvent {
  type: AgentEventType | string;
  agent: AgentIdentifier | string;
  message: string;
  timestamp: string;
  duration_ms?: number;
  result?: Record<string, unknown>;
  error?: string;
}

export interface AgentPanelEntry {
  agent: string;
  status: 'running' | 'complete' | 'error';
  messages: string[];
  durationMs?: number;
  error?: string;
  startedAt: number;
}
