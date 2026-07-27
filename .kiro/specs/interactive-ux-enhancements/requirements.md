# Requirements Document

## Introduction

This feature set enhances the DevGhost-Parser web visualization with richer contextual information and interactive narrative capabilities. The enhancements span both the backend (enriching node data with purpose descriptions) and the frontend (inspection panel, improved audio tour with live graph highlighting, and aesthetic node improvements). All user-facing text is rendered in Spanish.

## Glossary

- **Code_Flow_Analyzer**: The backend subsystem that traverses a codebase and produces architectural graph nodes and edges.
- **Node**: A graph element representing a source file or architectural unit, containing id, label, type, and (new) description fields.
- **Description_Generator**: The new backend component responsible for generating concise Spanish-language purpose descriptions for each Node.
- **Inspection_Panel**: A slide-out sidebar on the right side of the frontend that displays detailed information about a selected node.
- **Audio_Tour**: The frontend component that narrates a project summary using Web Speech API synthesis in Spanish.
- **Highlight_Engine**: The frontend mechanism that applies visual emphasis (glow, border, zoom) to graph nodes during audio narration.
- **CodeFlowGraph**: The React component that renders the architectural graph using React Flow.
- **Summary_Generator**: The backend subsystem that produces a plain-text executive summary of a codebase in Spanish.

## Requirements

### Requirement 1: Node Purpose Description Generation

**User Story:** As a developer viewing the code architecture graph, I want each node to include a concise description of its purpose in the system, so that I can quickly understand what each component does without reading its source code.

#### Acceptance Criteria

1. WHEN the Code_Flow_Analyzer produces a Node, THE Description_Generator SHALL generate a concise purpose description in Spanish for that Node.
2. THE Description_Generator SHALL produce descriptions of at most 120 characters.
3. THE Description_Generator SHALL derive the description from the Node label, Node type, and the file content context (imports, class name, method names).
4. WHEN the Description_Generator cannot determine a meaningful purpose, THE Description_Generator SHALL return a generic description based on the Node type (e.g., "Servicio auxiliar del sistema" for a Service node with no further context).
5. THE Node data model SHALL include a `description` field of type string alongside the existing id, label, and type fields.
6. THE output JSON response SHALL include the description field for every Node in the codeFlow result.

### Requirement 2: Node Inspection Side Panel

**User Story:** As a developer exploring the architecture graph, I want to click on a node and see its full details in a side panel, so that I can inspect its dependencies and database interactions without navigating away from the graph.

#### Acceptance Criteria

1. WHEN a user clicks a node in the CodeFlowGraph, THE Inspection_Panel SHALL open on the right side of the viewport.
2. THE Inspection_Panel SHALL display the selected node's name (label) and category (type) with a colored badge matching the node's type color.
3. THE Inspection_Panel SHALL display the node's purpose description in Spanish.
4. THE Inspection_Panel SHALL display a list of direct dependencies derived from edges where the selected node is the source.
5. WHEN the selected node has edges with relation "calls" or "depends_on" targeting Repository-type nodes, THE Inspection_Panel SHALL display a "Tablas relacionadas" section listing those repository nodes.
6. WHEN a user clicks a different node while the Inspection_Panel is open, THE Inspection_Panel SHALL update its content to reflect the newly selected node.
7. WHEN a user clicks a close button on the Inspection_Panel, THE Inspection_Panel SHALL close and restore the full graph viewport width.
8. IF no dependency data exists for a selected node, THEN THE Inspection_Panel SHALL display a message "Sin dependencias directas detectadas" in the dependencies section.

### Requirement 3: Enhanced Audio Tour Summary

**User Story:** As a developer reviewing an analyzed project, I want the audio tour to narrate a rich architectural overview in Spanish, so that I can understand the overall system design through spoken narrative.

#### Acceptance Criteria

1. THE Summary_Generator SHALL produce a narrative summary of 3 to 4 sentences describing the project architecture, dominant patterns, component count, and general purpose.
2. THE Summary_Generator SHALL write the narrative in natural Spanish prose suitable for text-to-speech synthesis.
3. THE Summary_Generator SHALL reference the main architectural components by their human-readable type names (controladores, servicios, rutas, repositorios) rather than code identifiers.
4. WHEN the codebase contains database entities, THE Summary_Generator SHALL mention the data model scope (number and sample names of entities) in the narrative.
5. THE Summary_Generator SHALL keep the narrative within 500 Unicode code points.

### Requirement 4: Live Node Highlighting During Audio Tour

**User Story:** As a developer listening to the audio tour, I want the graph to automatically focus on and highlight relevant nodes as they are mentioned in the narration, so that I can visually follow the architectural walkthrough.

#### Acceptance Criteria

1. WHEN the Audio_Tour begins playback, THE Highlight_Engine SHALL identify the main nodes to highlight based on Node type groups present in the graph (one representative per type).
2. WHILE the Audio_Tour is playing, THE Highlight_Engine SHALL sequentially apply a visual glow effect (colored border or box-shadow) to highlighted nodes at timed intervals distributed across the narration duration.
3. WHILE a node is highlighted by the Highlight_Engine, THE CodeFlowGraph SHALL use the React Flow fitView or setCenter function to pan and zoom the viewport toward the highlighted node.
4. WHEN the Audio_Tour playback ends or is stopped, THE Highlight_Engine SHALL remove all glow effects and restore normal node appearance.
5. WHEN the Audio_Tour is stopped mid-playback, THE Highlight_Engine SHALL immediately remove all active highlights and stop the panning sequence.

### Requirement 5: Node Aesthetic Enhancement with Subtitles

**User Story:** As a developer viewing the code architecture graph, I want each node to display a short subtitle with its category or description, so that the graph is more informative at a glance.

#### Acceptance Criteria

1. THE CodeFlowGraph custom node component SHALL render a subtitle line below the node label.
2. WHEN a Node has a description shorter than 60 characters, THE CodeFlowGraph SHALL display the full description as the subtitle.
3. WHEN a Node has a description of 60 characters or longer, THE CodeFlowGraph SHALL truncate the description to 57 characters followed by an ellipsis ("...") for the subtitle display.
4. THE subtitle text SHALL be styled with reduced opacity and smaller font size relative to the node label to maintain visual hierarchy.
5. THE node visual container SHALL accommodate the subtitle without clipping or overlapping adjacent nodes.
