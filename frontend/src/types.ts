// src/types.ts

export type NodeType = "Controller" | "Service" | "Route" | "Middleware" | "Repository" | "Utility";
export type EdgeRelation = "imports" | "calls" | "depends_on";
export type RelationType = "one-to-one" | "one-to-many" | "many-to-many" | "unknown";

export interface CodeFlowNode {
  id: string;
  label: string;
  type: NodeType;
}

export interface CodeFlowEdge {
  source: string;
  target: string;
  relation: EdgeRelation;
}

export interface EntityAttribute {
  name: string;
  type: string;
}

export interface EREntity {
  name: string;
  attributes: EntityAttribute[];
  primaryKey: string;
}

export interface ERRelation {
  from: string;
  to: string;
  type: RelationType;
  foreignKey: string;
  rawDeclaration?: string;
}

export interface AnalysisResponse {
  codeFlow: { nodes: CodeFlowNode[]; edges: CodeFlowEdge[] } | null;
  erModel: { entities: EREntity[]; relations: ERRelation[] } | null;
  summary: string | null;
  errors?: { subsystem: string; message: string }[];
}

export interface AnalysisError {
  detail: string;
}
