import { useMemo, useState } from 'react';
import {
  ReactFlow,
  Controls,
  Background,
  MarkerType,
  type Node,
  type Edge,
  type NodeProps,
  Handle,
  Position,
  BackgroundVariant,
} from '@xyflow/react';
import Dagre from '@dagrejs/dagre';
import '@xyflow/react/dist/style.css';
import type { EREntity, ERRelation, EntityAttribute } from '../types';

interface ERDatabaseGraphProps {
  entities: EREntity[];
  relations: ERRelation[];
}

type EntityNodeData = {
  label: string;
  attributes: EntityAttribute[];
  primaryKey: string;
  relationCount: number;
};

function getRelationLabel(type: string): string {
  switch (type) {
    case 'one-to-one': return '1 : 1';
    case 'one-to-many': return '1 : N';
    case 'many-to-many': return 'N : M';
    default: return type;
  }
}

function getRelationColor(type: string): string {
  switch (type) {
    case 'one-to-one': return '#6366f1';
    case 'one-to-many': return '#3b82f6';
    case 'many-to-many': return '#a855f7';
    default: return '#6366f1';
  }
}

function EntityNode({ data }: NodeProps<Node<EntityNodeData>>) {
  return (
    <div className="rounded-xl min-w-[200px] max-w-[260px] transition-shadow hover:shadow-xl bg-[#0f1320] border border-indigo-500/20 shadow-lg shadow-indigo-500/5">
      <Handle type="target" position={Position.Top} className="!bg-indigo-400 !w-2 !h-2 !border-0" />
      <div className="bg-gradient-to-r from-indigo-600 to-indigo-500 text-white px-3 py-2 rounded-t-xl flex items-center justify-between">
        <span className="font-bold text-xs">{data.label}</span>
        {data.relationCount > 0 && (
          <span className="text-[9px] bg-white/20 px-1.5 py-0.5 rounded-full">
            {data.relationCount} rel
          </span>
        )}
      </div>
      <div className="px-3 py-2">
        {data.attributes.slice(0, 5).map((attr: EntityAttribute) => (
          <div
            key={attr.name}
            className={`flex items-center justify-between py-0.5 text-[10px] ${
              attr.name === data.primaryKey ? 'text-amber-300 font-semibold' : 'text-slate-400'
            }`}
          >
            <span className="truncate flex items-center gap-1">
              {attr.name === data.primaryKey && <span className="text-amber-400">🔑</span>}
              {attr.name}
            </span>
            <span className="text-slate-600 font-mono ml-2">{attr.type}</span>
          </div>
        ))}
        {data.attributes.length > 5 && (
          <div className="text-[9px] text-slate-600 mt-1 italic">
            +{data.attributes.length - 5} campos más
          </div>
        )}
        {data.attributes.length === 0 && (
          <div className="text-[10px] text-slate-600 italic py-1">Sin atributos</div>
        )}
      </div>
      <Handle type="source" position={Position.Bottom} className="!bg-indigo-400 !w-2 !h-2 !border-0" />
    </div>
  );
}

const nodeTypes = { entity: EntityNode };

const NODE_WIDTH = 220;
const NODE_HEIGHT = 140;

function layoutEntities(entities: EREntity[], relations: ERRelation[]) {
  const useDagre = entities.length <= 25 && relations.length > 0;
  const relCounts = new Map<string, number>();
  relations.forEach((r) => {
    relCounts.set(r.from, (relCounts.get(r.from) || 0) + 1);
    relCounts.set(r.to, (relCounts.get(r.to) || 0) + 1);
  });

  if (useDagre) {
    const g = new Dagre.graphlib.Graph().setDefaultEdgeLabel(() => ({}));
    g.setGraph({ rankdir: 'TB', nodesep: 120, ranksep: 160, edgesep: 50 });

    entities.forEach((entity) => { g.setNode(entity.name, { width: NODE_WIDTH, height: NODE_HEIGHT }); });
    relations.forEach((rel) => {
      if (entities.some((e) => e.name === rel.from) && entities.some((e) => e.name === rel.to)) {
        g.setEdge(rel.from, rel.to);
      }
    });

    Dagre.layout(g);

    return entities.map((entity) => {
      const pos = g.node(entity.name);
      return {
        id: entity.name,
        type: 'entity' as const,
        position: { x: pos.x - NODE_WIDTH / 2, y: pos.y - NODE_HEIGHT / 2 },
        data: { label: entity.name, attributes: entity.attributes, primaryKey: entity.primaryKey, relationCount: relCounts.get(entity.name) || 0 },
      };
    });
  }

  const sorted = [...entities].sort((a, b) => (relCounts.get(b.name) || 0) - (relCounts.get(a.name) || 0));
  const cols = Math.min(5, Math.ceil(Math.sqrt(sorted.length * 1.2)));

  return sorted.map((entity, index) => {
    const col = index % cols;
    const row = Math.floor(index / cols);
    return {
      id: entity.name,
      type: 'entity' as const,
      position: { x: col * (NODE_WIDTH + 80), y: row * (NODE_HEIGHT + 80) },
      data: { label: entity.name, attributes: entity.attributes, primaryKey: entity.primaryKey, relationCount: relCounts.get(entity.name) || 0 },
    };
  });
}

function buildEdges(relations: ERRelation[], entityNames: Set<string>): Edge[] {
  return relations
    .filter((rel) => entityNames.has(rel.from) && entityNames.has(rel.to))
    .map((rel, index) => {
      const color = getRelationColor(rel.type);
      return {
        id: `edge-${index}-${rel.from}-${rel.to}`,
        source: rel.from,
        target: rel.to,
        label: `${getRelationLabel(rel.type)} (${rel.foreignKey})`,
        style: { stroke: color, strokeWidth: 2, opacity: 0.8 },
        labelStyle: { fontSize: 10, fill: color, fontWeight: 700 },
        labelBgStyle: { fill: '#0f1320', fillOpacity: 0.95, rx: 4 },
        labelBgPadding: [4, 6] as [number, number],
        markerEnd: { type: MarkerType.ArrowClosed, color, width: 14, height: 14 },
        type: 'smoothstep',
      };
    });
}

function inferRelationsFromAttributes(entities: EREntity[], existingRelations: ERRelation[]): ERRelation[] {
  const entityNamesLower = new Map(entities.map((e) => [e.name.toLowerCase(), e.name]));
  const existingPairs = new Set(existingRelations.map((r) => `${r.from}→${r.to}`));
  const inferred: ERRelation[] = [];

  for (const entity of entities) {
    for (const attr of entity.attributes) {
      if (!attr.name.endsWith('_id') || attr.name === entity.primaryKey) continue;
      const baseName = attr.name.slice(0, -3);
      const candidates = [baseName + 's', baseName + 'es', baseName, baseName.replace(/_/g, '')];

      for (const candidate of candidates) {
        const targetName = entityNamesLower.get(candidate);
        if (targetName && targetName !== entity.name) {
          const pairKey = `${entity.name}→${targetName}`;
          if (!existingPairs.has(pairKey)) {
            inferred.push({ from: entity.name, to: targetName, type: 'one-to-many', foreignKey: attr.name });
            existingPairs.add(pairKey);
          }
          break;
        }
      }
    }
  }
  return inferred;
}

const PAGE_SIZE = 20;

export function ERDatabaseGraph({ entities, relations }: ERDatabaseGraphProps) {
  const [page, setPage] = useState(0);

  const allRelations = useMemo(() => {
    const inferred = inferRelationsFromAttributes(entities, relations);
    return [...relations, ...inferred];
  }, [entities, relations]);

  const totalPages = Math.ceil(entities.length / PAGE_SIZE);
  const isLarge = entities.length > PAGE_SIZE;

  const visibleEntities = useMemo(() => {
    if (!isLarge) return entities;
    return entities.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);
  }, [entities, page, isLarge]);

  const visibleRelations = useMemo(() => {
    const names = new Set(visibleEntities.map((e) => e.name));
    return allRelations.filter((r) => names.has(r.from) && names.has(r.to));
  }, [allRelations, visibleEntities]);

  const nodes: Node<EntityNodeData>[] = useMemo(
    () => layoutEntities(visibleEntities, visibleRelations),
    [visibleEntities, visibleRelations]
  );

  const edges = useMemo(
    () => buildEdges(visibleRelations, new Set(visibleEntities.map((e) => e.name))),
    [visibleRelations, visibleEntities]
  );

  if (entities.length === 0 && allRelations.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-slate-500 text-sm">
        No hay datos del modelo ER disponibles para este repositorio.
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Info bar */}
      <div className="shrink-0 flex items-center justify-between px-4 py-2 border-b border-slate-800/40 bg-[#0a0e18]/80 text-[11px]">
        <div className="flex items-center gap-3 text-slate-500">
          <span className="font-medium text-slate-300">{entities.length} entidades</span>
          <span>·</span>
          <span>{allRelations.length} relaciones{allRelations.length > relations.length && ` (${allRelations.length - relations.length} inferidas)`}</span>
          {allRelations.length > 0 && (
            <>
              <span>·</span>
              <span className="flex items-center gap-1"><span className="w-3 h-0.5 inline-block rounded" style={{ backgroundColor: '#6366f1' }} /> 1:1</span>
              <span className="flex items-center gap-1"><span className="w-3 h-0.5 inline-block rounded" style={{ backgroundColor: '#3b82f6' }} /> 1:N</span>
              <span className="flex items-center gap-1"><span className="w-3 h-0.5 inline-block rounded" style={{ backgroundColor: '#a855f7' }} /> N:M</span>
            </>
          )}
        </div>
        {isLarge && (
          <div className="flex items-center gap-1">
            <button
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={page === 0}
              className="w-6 h-6 flex items-center justify-center rounded-md bg-slate-800 text-slate-400 disabled:opacity-30 hover:bg-slate-700"
            >‹</button>
            <span className="text-[10px] text-slate-500 px-1">{page + 1}/{totalPages}</span>
            <button
              onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
              disabled={page >= totalPages - 1}
              className="w-6 h-6 flex items-center justify-center rounded-md bg-slate-800 text-slate-400 disabled:opacity-30 hover:bg-slate-700"
            >›</button>
          </div>
        )}
      </div>

      {/* Graph */}
      <div className="flex-1 overflow-hidden bg-[#080c15]">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          fitView
          fitViewOptions={{ padding: 0.2 }}
          minZoom={0.2}
          maxZoom={2.5}
          proOptions={{ hideAttribution: true }}
        >
          <Controls position="bottom-left" showInteractive={false} className="!bg-slate-800/90 !border-slate-700/50 !rounded-lg [&>button]:!bg-slate-800 [&>button]:!border-slate-700 [&>button]:!text-slate-300" />
          <Background variant={BackgroundVariant.Dots} gap={20} size={1} color="#1e293b" />
        </ReactFlow>
      </div>
    </div>
  );
}
