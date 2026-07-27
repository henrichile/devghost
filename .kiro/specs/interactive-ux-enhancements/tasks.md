# Implementation Plan: Interactive UX Enhancements

## Overview

This plan implements five interconnected enhancements to the DevGhost-Parser web visualization: node purpose descriptions (backend), inspection side panel (frontend), enhanced audio tour summary (backend), live node highlighting during audio tour (frontend), and node subtitle aesthetics (frontend). Tasks are ordered by dependency: backend model changes → backend logic → frontend types → frontend state → UI components → integration → tests.

## Tasks

- [x] 1. Backend model and data layer changes
  - [x] 1.1 Add `description` field to the Node dataclass and create FileContext dataclass
    - Add `description: str = ""` field to the `Node` dataclass in `backend/src/dev_ghost_parser/models.py`
    - Create `FileContext` dataclass with fields: `imports: list[str]`, `class_name: str | None`, `method_names: list[str]`
    - Ensure backward compatibility: the default value `""` means existing code continues to work
    - _Requirements: 1.5_

  - [x] 1.2 Update Output_Serializer to include description in node serialization
    - Modify `_code_flow_to_dict` in `backend/src/dev_ghost_parser/output_serializer.py` to include `"description": node.description` in each node dict
    - _Requirements: 1.6_

- [x] 2. Backend Description_Generator implementation
  - [x] 2.1 Create Description_Generator module
    - Create `backend/src/dev_ghost_parser/description_generator.py`
    - Implement `Description_Generator` class with a `generate(node: Node, file_context: FileContext | None) -> str` method
    - Implement heuristic strategy: method-based description → import-based description → generic type fallback
    - Enforce ≤120 character limit via truncation
    - Always return non-empty string in Spanish
    - Generic fallbacks per type: Controller → "Controlador principal del sistema", Service → "Servicio auxiliar del sistema", Route → "Definición de rutas del sistema", Middleware → "Middleware de procesamiento intermedio", Repository → "Repositorio de acceso a datos", Utility → "Utilidad auxiliar del proyecto"
    - _Requirements: 1.1, 1.2, 1.3, 1.4_

  - [x] 2.2 Write property test for Description_Generator (Property 1)
    - **Property 1: Description generation invariant**
    - Create `backend/tests/property/test_property_description_invariant.py`
    - Generate random Nodes (all NodeType values) and optional FileContext instances using Hypothesis
    - Assert: result is non-empty string and `len(result) <= 120`
    - Use `@settings(max_examples=100)`
    - Tag: `# Feature: interactive-ux-enhancements, Property 1: Description generation invariant`
    - **Validates: Requirements 1.1, 1.2**

  - [x] 2.3 Integrate Description_Generator into Code_Flow_Analyzer
    - Modify `Code_Flow_Analyzer.analyze()` in `backend/src/dev_ghost_parser/code_flow_analyzer.py`
    - After creating each Node, extract FileContext (imports, class_name, method_names) from the already-parsed tree-sitter AST
    - Call `Description_Generator.generate(node, file_context)` and assign result to `node.description`
    - Handle errors gracefully: if description generation fails for a file, use the generic fallback
    - _Requirements: 1.1, 1.3_

- [x] 3. Backend Summary_Generator enhancement
  - [x] 3.1 Extend Summary_Generator to produce 3-4 sentences with Spanish type names
    - Modify `backend/src/dev_ghost_parser/summary_generator.py`
    - Change `_MAX_SENTENCES` concept from 3 to 4
    - Add Sentence 3: Component type breakdown using Spanish names ("Los componentes incluyen {n} controladores, {n} servicios, y {n} rutas.")
    - Add Sentence 4 (optional): General purpose inference ("El sistema parece orientado a [inferred purpose].")
    - If the 4th sentence pushes summary over 500 code points, omit it (graceful degradation)
    - Ensure all architectural type names use Spanish terms (controladores, servicios, rutas, middleware, repositorios, utilidades)
    - Maintain existing `_MAX_CODE_POINTS = 500` constraint
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

  - [x] 3.2 Write property test for Summary sentence count (Property 5)
    - **Property 5: Enhanced summary sentence count**
    - Create `backend/tests/property/test_property_summary_sentences_enhanced.py`
    - Generate random CodeFlowResult (≥1 node) + ERResult (≥1 entity)
    - Assert: output contains 3 or 4 sentences (period-delimited)
    - Use `@settings(max_examples=100)`
    - Tag: `# Feature: interactive-ux-enhancements, Property 5: Enhanced summary sentence count`
    - **Validates: Requirements 3.1**

  - [x] 3.3 Write property test for Summary Spanish type names (Property 6)
    - **Property 6: Summary uses Spanish architectural type names**
    - Create `backend/tests/property/test_property_summary_spanish_names.py`
    - Generate CodeFlowResult with Controller-type nodes
    - Assert: output contains "controlador" or "controladores" and does NOT contain standalone "Controller"
    - Use `@settings(max_examples=100)`
    - Tag: `# Feature: interactive-ux-enhancements, Property 6: Summary uses Spanish architectural type names`
    - **Validates: Requirements 3.3**

  - [x] 3.4 Write property test for Summary entity mention (Property 7)
    - **Property 7: Summary mentions entities when present**
    - Create `backend/tests/property/test_property_summary_entities_mention.py`
    - Generate ERResult with ≥1 entity
    - Assert: output contains "entidad" or "entidades" and at least one entity name
    - Use `@settings(max_examples=100)`
    - Tag: `# Feature: interactive-ux-enhancements, Property 7: Summary mentions entities when present`
    - **Validates: Requirements 3.4**

  - [x] 3.5 Write property test for Summary length invariant (Property 8)
    - **Property 8: Summary length invariant**
    - Create `backend/tests/property/test_property_summary_length_enhanced.py`
    - Generate random CodeFlowResult + ERResult combinations
    - Assert: `len(output) <= 500` code points
    - Use `@settings(max_examples=100)`
    - Tag: `# Feature: interactive-ux-enhancements, Property 8: Summary length invariant`
    - **Validates: Requirements 3.5**

- [x] 4. Checkpoint - Backend complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Frontend type and state layer
  - [x] 5.1 Update CodeFlowNode type to include description field
    - Add `description: string` to the `CodeFlowNode` interface in `frontend/src/types.ts`
    - _Requirements: 1.5, 1.6_

  - [x] 5.2 Install zustand and create the graph store
    - Install `zustand` dependency in `frontend/package.json`
    - Create `frontend/src/store/useGraphStore.ts`
    - Implement state: `selectedNode`, `inspectionOpen`, `highlightedNodeId`, `isTouring`, `tourNodeIds`, `edges`, `nodes`
    - Implement actions: `selectNode`, `closeInspection`, `startTour`, `stopTour`, `setHighlightedNode`, `setGraphData`
    - _Requirements: 2.1, 2.6, 4.1, 4.4_

- [x] 6. Frontend InspectionPanel component
  - [x] 6.1 Create InspectionPanel component
    - Create `frontend/src/components/InspectionPanel.tsx`
    - Read `selectedNode`, `inspectionOpen`, `edges`, `nodes` from zustand store
    - Display: node label, type badge (colored using `getNodeStyle`), description
    - Display dependency list: derived from `edges.filter(e => e.source === selectedNode.id)`
    - Display "Tablas relacionadas" section: edges with relation "calls" or "depends_on" targeting Repository-type nodes
    - Show "Sin dependencias directas detectadas" when no outgoing edges exist
    - Include close button that calls `closeInspection()`
    - Style: fixed 320px width, slides in from right, uses flex layout
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8_

  - [x] 6.2 Write property test for InspectionPanel data rendering (Property 3)
    - **Property 3: InspectionPanel renders all node data fields**
    - Create `frontend/src/components/__tests__/InspectionPanel.property.test.tsx`
    - Generate random CodeFlowNode with non-empty label, type, and description using fast-check
    - Render InspectionPanel with store populated, assert label, type, and description appear in rendered output
    - Use `fc.assert(property, { numRuns: 100 })`
    - Tag: `// Feature: interactive-ux-enhancements, Property 3: InspectionPanel renders all node data fields`
    - **Validates: Requirements 2.2, 2.3**

  - [x] 6.3 Write property test for InspectionPanel dependency derivation (Property 4)
    - **Property 4: InspectionPanel dependency derivation correctness**
    - Create `frontend/src/components/__tests__/InspectionPanel.deps.property.test.tsx`
    - Generate random graphs (nodes + edges), select a node, verify displayed dependencies match edges where selected node is source
    - Verify "Tablas relacionadas" appears iff edges with relation "calls"/"depends_on" target Repository-type nodes
    - Use `fc.assert(property, { numRuns: 100 })`
    - Tag: `// Feature: interactive-ux-enhancements, Property 4: InspectionPanel dependency derivation correctness`
    - **Validates: Requirements 2.4, 2.5**

- [x] 7. Frontend HighlightEngine hook
  - [x] 7.1 Create useHighlightEngine hook
    - Create `frontend/src/hooks/useHighlightEngine.ts`
    - Accept parameters: `nodes: CodeFlowNode[]`, `duration: number`, `isPlaying: boolean`
    - On `isPlaying=true`: select one representative node per distinct NodeType group
    - Calculate interval: `duration / selectedNodes.length`
    - Use `setInterval` to cycle through nodes, calling `setHighlightedNode(id)` on the store
    - On `isPlaying=false` or unmount: clear interval, call `setHighlightedNode(null)`
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

  - [x] 7.2 Write property test for Highlight node selection (Property 9)
    - **Property 9: Highlight node selection covers all type groups**
    - Create `frontend/src/hooks/__tests__/highlightEngine.property.test.ts`
    - Generate random sets of CodeFlowNodes with N distinct NodeType values
    - Assert: selection returns exactly N nodes, one per distinct type
    - Use `fc.assert(property, { numRuns: 100 })`
    - Tag: `// Feature: interactive-ux-enhancements, Property 9: Highlight node selection covers all type groups`
    - **Validates: Requirements 4.1**

  - [x] 7.3 Write property test for Highlight timing distribution (Property 10)
    - **Property 10: Highlight timing distribution**
    - Create `frontend/src/hooks/__tests__/highlightEngine.timing.property.test.ts`
    - Generate random positive durations D and node counts N
    - Assert: each interval ≈ D/N and sum of intervals = D
    - Use `fc.assert(property, { numRuns: 100 })`
    - Tag: `// Feature: interactive-ux-enhancements, Property 10: Highlight timing distribution`
    - **Validates: Requirements 4.2**

- [x] 8. Frontend CodeFlowGraph modifications
  - [x] 8.1 Add subtitle rendering and glow effect to CustomNode in CodeFlowGraph
    - Modify `frontend/src/components/CodeFlowGraph.tsx`
    - Add subtitle line in `CustomNode` displaying truncated description (full if <60 chars, first 57 + "..." if ≥60)
    - Style subtitle: reduced opacity (text-white/50), smaller font (text-[9px])
    - Increase `NODE_HEIGHT` to accommodate subtitle (from 65 to ~85)
    - Read `highlightedNodeId` from zustand store
    - When node id matches `highlightedNodeId`, apply CSS box-shadow glow effect (e.g., `0 0 15px 5px rgba(99,102,241,0.6)`)
    - Add node click handler: call `store.selectNode(nodeData)` on click
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 4.3_

  - [x] 8.2 Add viewport panning on highlight change in CodeFlowGraph
    - Use `useReactFlow()` hook to get the React Flow instance
    - When `highlightedNodeId` changes (via useEffect), call `reactFlowInstance.fitView({ nodes: [{ id: highlightedNodeId }], duration: 800 })` to smoothly pan
    - Handle gracefully: if instance is unavailable, skip panning (glow still applies)
    - _Requirements: 4.3_

  - [x] 8.3 Write property test for subtitle truncation logic (Property 11)
    - **Property 11: Subtitle truncation logic**
    - Create `frontend/src/components/__tests__/subtitle.property.test.ts`
    - Generate random strings of varying lengths using fast-check
    - Assert: if length < 60 → return full string; if length ≥ 60 → return first 57 chars + "..." (total 60)
    - Use `fc.assert(property, { numRuns: 100 })`
    - Tag: `// Feature: interactive-ux-enhancements, Property 11: Subtitle truncation logic`
    - **Validates: Requirements 5.2, 5.3**

- [x] 9. Frontend AudioTourPanel and App.tsx integration
  - [x] 9.1 Modify AudioTourPanel to integrate with HighlightEngine
    - Modify `frontend/src/components/AudioTourPanel.tsx`
    - Import and call `useHighlightEngine` hook with nodes from store, estimated duration (`summary.length * 80`), and playing state
    - On play: call `store.startTour(nodeIds)`
    - On stop/end: call `store.stopTour()`
    - _Requirements: 4.1, 4.2, 4.4, 4.5_

  - [x] 9.2 Modify App.tsx layout for InspectionPanel integration
    - Modify `frontend/src/App.tsx`
    - Import and render `<InspectionPanel />` alongside the graph area
    - Call `store.setGraphData(nodes, edges)` when response is loaded
    - Wrap graph + InspectionPanel in a flex container so InspectionPanel slides in from right
    - _Requirements: 2.1, 2.7_

- [x] 10. Backend serialization property test
  - [x] 10.1 Write property test for serialization includes description (Property 2)
    - **Property 2: Serialization includes description for all nodes**
    - Create `backend/tests/property/test_property_serialization_description.py`
    - Generate random CodeFlowResults with nodes that have description fields using Hypothesis
    - Serialize with Output_Serializer, parse JSON, verify every node in `codeFlow.nodes` has a `"description"` key with string value
    - Use `@settings(max_examples=100)`
    - Tag: `# Feature: interactive-ux-enhancements, Property 2: Serialization includes description for all nodes`
    - **Validates: Requirements 1.6**

- [x] 11. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- Backend uses Python with pytest + hypothesis for property-based testing
- Frontend uses TypeScript with vitest + fast-check for property-based testing
- The zustand store enables clean communication between components without prop drilling

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "5.1"] },
    { "id": 1, "tasks": ["1.2", "2.1", "5.2"] },
    { "id": 2, "tasks": ["2.2", "2.3", "3.1", "6.1", "7.1"] },
    { "id": 3, "tasks": ["3.2", "3.3", "3.4", "3.5", "6.2", "6.3", "7.2", "7.3", "10.1"] },
    { "id": 4, "tasks": ["8.1", "8.2"] },
    { "id": 5, "tasks": ["8.3", "9.1", "9.2"] }
  ]
}
```
