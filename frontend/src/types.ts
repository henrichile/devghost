// src/types.ts

export type NodeType = "Controller" | "Service" | "Route" | "Middleware" | "Repository" | "Utility" | "Config";
export type EdgeRelation = "imports" | "calls" | "depends_on";
export type RelationType = "one-to-one" | "one-to-many" | "many-to-many" | "unknown";

export interface CodeFlowNode {
  id: string;
  label: string;
  type: NodeType;
  description: string;
  methods?: string[];
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

export interface NodeInspection {
  descriptions: Record<string, string>;
  audit: string | null;
  methodSources?: Record<string, string>;
}

export interface AnalysisResponse {
  codeFlow: { nodes: CodeFlowNode[]; edges: CodeFlowEdge[] } | null;
  erModel: { entities: EREntity[]; relations: ERRelation[] } | null;
  summary: string | null;
  artifacts?: ArtifactsResponse;
  nodeInspections?: Record<string, NodeInspection>;
  systemReport?: {
    tech_stack: { entries: { name: string; category: string; description?: string }[] };
    setup_instructions: string;
    project_description: string;
    could_not_determine?: boolean;
  };
  errors?: { subsystem: string; message: string }[];
}

export interface AnalysisError {
  detail: string;
}

export interface ArtifactsResponse {
  c4Mermaid: string | null;
  dbDictionary: string | null;
  adrDocument: string | null;
  rbacMatrix: string | null;
  testPlan: string | null;
  useCases: string | null;
  useCasesDoc: string | null;
}
