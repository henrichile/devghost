# Requirements Document

## Introduction

This feature introduces a multi-agent architecture with real-time SSE streaming to the DevGhost Parser application. Instead of a single monolithic analysis endpoint, specialized AI agents (AST Analyzer, ER Extractor, Code Auditor, Doc Generator, System Reporter) run in parallel via asyncio. Progress from each agent streams to the frontend via Server-Sent Events, replacing the simulated loading screen with a live agent activity log. A new "System Report" tab provides technology stack detection, implementation instructions, and a general project description.

## Glossary

- **Agent_Orchestrator**: The backend component that coordinates the execution of multiple specialized agents in parallel using asyncio
- **SSE_Endpoint**: The `/analyze-stream` FastAPI endpoint that emits Server-Sent Events to the frontend during analysis
- **Agent_Event**: A structured JSON message sent over SSE representing one agent's status update (started, progress, completed, error)
- **Process_Panel**: The right-side UI panel on the loading/process screen that displays a real-time log of agent activity
- **System_Report_Tab**: A new dashboard tab that displays technology stack, implementation instructions, and project description
- **Specialized_Agent**: A Python async class responsible for one analysis domain (AST, ER, Audit, Docs, System Report)
- **Analysis_Session**: The lifecycle from the user submitting a repo URL until all agents complete and the dashboard renders
- **Frontend_SSE_Client**: The browser-side fetch-based reader that consumes SSE events from the backend via ReadableStream

## Requirements

### Requirement 1: Agent Orchestrator Parallel Execution

**User Story:** As a developer using DevGhost Parser, I want the backend to run multiple analysis agents in parallel, so that the total analysis time is reduced compared to sequential processing.

#### Acceptance Criteria

1. WHEN a repository analysis is requested, THE Agent_Orchestrator SHALL spawn all Specialized_Agents concurrently using asyncio.gather or asyncio.TaskGroup
2. THE Agent_Orchestrator SHALL support at minimum five Specialized_Agents: AST Analyzer, ER Extractor, Code Auditor, Doc Generator, and System Reporter
3. IF one Specialized_Agent raises an exception, THEN THE Agent_Orchestrator SHALL continue executing the remaining agents, record the failure as a SubsystemError entry (containing the agent name and error message) in the final response, and include the successful agents' results alongside the error entries
4. WHEN all Specialized_Agents complete, THE Agent_Orchestrator SHALL merge their individual results into a single combined analysis response within 5 seconds of the last agent completing
5. THE Agent_Orchestrator SHALL limit concurrent LLM calls to a configurable maximum (default 5) using an asyncio.Semaphore
6. IF the total parallel execution time exceeds 120 seconds, THEN THE Agent_Orchestrator SHALL cancel any still-running agents and return the results collected so far along with a timeout indication for each cancelled agent
7. WHEN all Specialized_Agents complete successfully in parallel, THE Agent_Orchestrator SHALL produce a total wall-clock time that is less than the sum of all individual agent execution times

### Requirement 2: SSE Streaming Endpoint

**User Story:** As a frontend developer, I want a streaming endpoint that sends real-time progress events, so that the UI can show users exactly what is happening during analysis.

#### Acceptance Criteria

1. THE SSE_Endpoint SHALL be accessible at `POST /analyze-stream` and accept the same request body as the existing `/analyze` endpoint (a JSON object containing `repo_url`)
2. WHEN a Specialized_Agent starts processing, THE SSE_Endpoint SHALL emit an Agent_Event with type "agent_start" containing the agent name and a non-empty description string of what it does
3. WHILE a Specialized_Agent is processing, THE SSE_Endpoint SHALL emit at least one Agent_Event with type "agent_progress" containing a non-empty progress message describing the current sub-task
4. WHEN a Specialized_Agent completes successfully, THE SSE_Endpoint SHALL emit an Agent_Event with type "agent_complete" containing the agent name and duration in milliseconds as an integer
5. IF a Specialized_Agent fails, THEN THE SSE_Endpoint SHALL emit an Agent_Event with type "agent_error" containing the agent name and a non-empty error description, and continue processing remaining agents
6. WHEN all agents complete, THE SSE_Endpoint SHALL emit a final event with type "analysis_complete" containing the full merged analysis result as JSON (matching the schema returned by the `/analyze` endpoint), and then close the connection
7. THE SSE_Endpoint SHALL set the response content-type to `text/event-stream` and include CORS headers consistent with the existing middleware configuration (allow all origins)
8. THE SSE_Endpoint SHALL format each event as valid SSE: lines prefixed with `data:` followed by a JSON-serialized object, terminated by two newline characters (`\n\n`)
9. IF the request body fails validation, THEN THE SSE_Endpoint SHALL respond with an HTTP error status (not a stream) before initiating the event stream, using the same validation rules as the `/analyze` endpoint
10. THE SSE_Endpoint SHALL emit events in chronological order per agent, with all "agent_start" events for a given agent preceding its "agent_progress" events, and all "agent_progress" events preceding its "agent_complete" or "agent_error" event
11. IF the overall analysis exceeds 300 seconds without completing, THEN THE SSE_Endpoint SHALL emit an event with type "analysis_error" containing a timeout indication and close the connection

### Requirement 3: Agent Event Schema

**User Story:** As a frontend developer, I want a consistent and predictable event schema, so that I can reliably parse and display agent activity in the UI.

#### Acceptance Criteria

1. THE Agent_Event SHALL contain the fields: `type` (string, one of: "agent_start", "agent_progress", "agent_complete", "analysis_complete", "agent_error", "analysis_error"), `agent` (string), `message` (string, 1 to 2048 characters), and `timestamp` (ISO 8601 string with millisecond precision)
2. THE Agent_Event SHALL include all four required fields (`type`, `agent`, `message`, `timestamp`) as non-null, non-empty values in every emitted event
3. WHEN the event type is "agent_complete", THE Agent_Event SHALL additionally contain a `duration_ms` field (integer, minimum value 0) representing elapsed processing time in milliseconds
4. WHEN the event type is "analysis_complete", THE Agent_Event SHALL additionally contain a `result` field holding the full analysis JSON object as returned by the analysis pipeline
5. WHEN the event type is "agent_error", THE Agent_Event SHALL additionally contain an `error` field (string, 1 to 1024 characters) describing the failure condition
6. THE Agent_Event `agent` field SHALL use one of these identifiers exclusively: "ast_analyzer", "er_extractor", "code_auditor", "doc_generator", "system_reporter"
7. IF an Agent_Event is received with a `type` value not in the defined set, THEN THE frontend SHALL preserve the event data and display it using the base schema fields without raising a parsing error

### Requirement 4: Frontend SSE Client

**User Story:** As a user, I want the frontend to consume streaming events and update the UI in real-time, so that I can see analysis progress without refreshing.

#### Acceptance Criteria

1. WHEN the user submits a repository URL for analysis, THE Frontend_SSE_Client SHALL open a connection to the `/analyze-stream` endpoint using the Fetch API with ReadableStream, sending a POST request with a JSON body containing the `repo_url` field
2. WHEN an Agent_Event is received, THE Frontend_SSE_Client SHALL parse the JSON payload and update the UI state such that the Process_Panel reflects the event type, agent name, and message within 500 milliseconds of receipt
3. IF the SSE connection closes before an "analysis_complete" event is received (due to network failure, server error, or no event received within 120 seconds), THEN THE Frontend_SSE_Client SHALL display an error message to the user indicating the connection was lost and allow the user to retry the analysis
4. WHEN the "analysis_complete" event is received, THE Frontend_SSE_Client SHALL close the connection and transition the UI to the dashboard view with the received result
5. IF the `/analyze-stream` endpoint returns an HTTP error status (4xx or 5xx) before the event stream begins, THEN THE Frontend_SSE_Client SHALL display an error message to the user indicating the failure reason from the response body
6. IF a received SSE event contains malformed JSON that cannot be parsed, THEN THE Frontend_SSE_Client SHALL skip the malformed event and continue processing subsequent events without interrupting the connection

### Requirement 5: Enhanced Process Screen with Agent Activity Panel

**User Story:** As a user, I want to see a real-time log of what each agent is doing during analysis, so that I understand what is happening and feel confident the tool is working.

#### Acceptance Criteria

1. WHILE an Analysis_Session is active, THE Process_Panel SHALL display on the right side of the loading screen occupying approximately 40% of the viewport width
2. WHEN an "agent_start" event is received, THE Process_Panel SHALL append a new entry showing the agent name with an animated "running" indicator (e.g., spinner or pulsing dot)
3. WHEN an "agent_progress" event is received, THE Process_Panel SHALL update the corresponding agent entry with the latest progress message, truncating messages longer than 200 characters with an ellipsis
4. WHEN an "agent_complete" event is received, THE Process_Panel SHALL mark the agent entry as completed with a checkmark icon and show the duration formatted as seconds (e.g., "12.3s")
5. WHEN an "agent_error" event is received, THE Process_Panel SHALL mark the agent entry with a red error indicator and display the error message
6. THE Process_Panel SHALL auto-scroll to show the most recent activity entries unless the user has manually scrolled up, in which case auto-scroll SHALL be paused until the user scrolls back to the bottom
7. THE Process_Panel SHALL display a timestamp for each log entry formatted as elapsed time since analysis start (e.g., "+0:05", "+1:23")
8. BEFORE any events are received, THE Process_Panel SHALL display an initial state indicating that analysis agents are initializing

### Requirement 6: System Report Agent

**User Story:** As a user, I want the analysis to detect the technology stack, explain how to run the project, and provide a general description, so that I can quickly understand any repository.

#### Acceptance Criteria

1. WHEN triggered by the Agent_Orchestrator, THE System_Reporter agent SHALL scan the repository file structure and identify configuration files (package.json, pyproject.toml, Dockerfile, Makefile, Cargo.toml, go.mod, pom.xml, requirements.txt, composer.json, Gemfile, build.gradle) to extract technology stack metadata
2. WHEN configuration files are identified, THE System_Reporter agent SHALL produce a technology stack listing that includes at minimum: primary programming language(s), framework(s), and detected infrastructure tools (databases, containerization, CI/CD), each as named entries
3. WHEN the technology stack has been detected, THE System_Reporter agent SHALL generate setup and run instructions containing at minimum: prerequisite dependencies, installation steps, and the command(s) to start the project locally, derived from detected configuration files and scripts
4. WHEN the analysis completes, THE System_Reporter agent SHALL generate a project description of no more than 500 characters summarizing the repository purpose and its dominant architectural pattern
5. IF the LLM_Client is available, THEN THE System_Reporter agent SHALL use the LLM_Client to generate natural-language descriptions for each detected technology stack entry and to produce the project description; IF the LLM_Client is unavailable, THEN THE System_Reporter agent SHALL fall back to heuristic-based output derived solely from parsed configuration file contents
6. IF no recognizable configuration files are found in the repository root or first-level subdirectories, THEN THE System_Reporter agent SHALL return a result indicating the technology stack could not be determined and omit the setup instructions section from the output

### Requirement 7: System Report Dashboard Tab

**User Story:** As a user, I want a dedicated tab in the dashboard to view the system report, so that I can access technology stack info, setup instructions, and project description in one place.

#### Acceptance Criteria

1. THE System_Report_Tab SHALL appear as a new tab in the DashboardLayout navigation bar with label "System Report" and an icon visually distinct from the existing Code Flow, ER Database, and Architecture tab icons
2. WHEN the user selects the System_Report_Tab, THE System_Report_Tab SHALL display three sections in top-to-bottom order: Technology Stack, How to Run, and Project Description, each with a visible section heading
3. THE System_Report_Tab Technology Stack section SHALL display detected languages, frameworks, databases, and infrastructure tools grouped by category, each category rendered as a labeled group with items shown as badges or list entries; IF a category contains zero items, THEN THE System_Report_Tab SHALL omit that category from the display
4. THE System_Report_Tab How to Run section SHALL render the implementation instructions as Markdown converted to formatted HTML with support for headings, code blocks, lists, and inline code
5. THE System_Report_Tab Project Description section SHALL render the general description as Markdown converted to formatted HTML with support for headings, code blocks, lists, and inline code
6. IF the system report data is not available (agent failed or data missing), THEN THE System_Report_Tab SHALL display a non-editable placeholder message stating that the system report could not be generated, and SHALL hide the three content sections entirely
7. WHILE the system report data is loading, THE System_Report_Tab SHALL display a loading indicator in place of the content sections

### Requirement 8: Backward Compatibility

**User Story:** As an existing user of the API, I want the current `/analyze` endpoint to remain functional, so that existing integrations are not broken.

#### Acceptance Criteria

1. THE existing `/analyze` POST endpoint SHALL continue to accept the same request body schema and return all previously-existing response fields with unchanged names, types, and nesting structure
2. IF the System_Reporter agent completes successfully during an `/analyze` request, THEN THE `/analyze` endpoint response SHALL include a `systemReport` field (object type) containing the System_Reporter agent output
3. IF the System_Reporter agent fails or times out during an `/analyze` request, THEN THE `/analyze` endpoint SHALL omit the `systemReport` field from the response and return all other fields as normal without returning an error status code
4. THE `/analyze` endpoint SHALL return its response within 30 seconds of the original response time when the System_Reporter agent is invoked, so that existing integrations are not disrupted by timeout
