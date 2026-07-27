# Requirements Document

## Introduction

Este documento especifica los requisitos para mejorar la arquitectura de análisis paralelo basada en sub-agentes del sistema DevGhost-Parser. El objetivo es reestructurar el pipeline de análisis para que los sub-agentes especializados ejecuten tareas independientes de forma concurrente, mejorando la velocidad de ejecución y la precisión de los resultados. Actualmente el orquestador ejecuta todos los agentes en paralelo pero sin gestión de dependencias entre ellos, sin reintentos, y sin priorización inteligente. Esta mejora introduce ejecución basada en un grafo de dependencias, reintentos con backoff, particionamiento de trabajo por sub-agentes especializados y agregación precisa de resultados.

## Glossary

- **Orchestrator**: Componente central que coordina la ejecución paralela de todos los sub-agentes, gestiona dependencias y agrega resultados.
- **Sub_Agent**: Componente especializado que ejecuta una tarea de análisis específica (AST, ER, auditoría, documentación, reporte de sistema).
- **Dependency_Graph**: Estructura de datos dirigida acíclica (DAG) que define el orden de ejecución y las dependencias entre sub-agentes.
- **Task_Partition**: Subdivisión de un trabajo grande en unidades más pequeñas que pueden procesarse en paralelo por múltiples workers.
- **Agent_Result**: Estructura de datos que encapsula el resultado de la ejecución de un sub-agente, incluyendo estado, datos y métricas.
- **SSE_Stream**: Flujo de eventos Server-Sent Events utilizado para reportar progreso en tiempo real al frontend.
- **Retry_Policy**: Configuración que define el número máximo de reintentos y la estrategia de backoff exponencial para agentes fallidos.
- **Concurrency_Limiter**: Semáforo que restringe el número máximo de sub-agentes ejecutándose simultáneamente.
- **Pipeline**: Secuencia completa de análisis desde la clonación del repositorio hasta la entrega del resultado final.

## Requirements

### Requirement 1: Fase Fundacional de Análisis AST

**User Story:** Como desarrollador del backend, quiero que el análisis AST se ejecute primero como fase fundacional obligatoria, para que todos los sub-agentes posteriores operen sobre datos coherentes y consistentes del proyecto.

#### Acceptance Criteria

1. WHEN execution starts, THE Orchestrator SHALL execute the AST_Analyzer Sub_Agent first as the foundational phase before launching any other Sub_Agent.
2. WHEN the AST_Analyzer completes successfully, THE Orchestrator SHALL make the AST analysis result (code flow graph, node list, component map) available as shared context for all subsequent Sub_Agents.
3. WHEN the AST_Analyzer fails after all retry attempts, THE Orchestrator SHALL abort the entire Pipeline and return an error indicating the foundational analysis could not be completed.
4. THE Orchestrator SHALL pass the full AST analysis result to each downstream Sub_Agent's execution context, ensuring data coherence across all analysis outputs.
5. WHEN the AST_Analyzer completes, THE Orchestrator SHALL emit an agent_complete event via the SSE_Stream before launching subsequent Sub_Agents.

### Requirement 2: Ejecución Paralela Basada en Grafo de Dependencias

**User Story:** Como desarrollador del backend, quiero que los sub-agentes se ejecuten en paralelo respetando sus dependencias, para que el análisis sea lo más rápido posible sin comprometer la precisión.

#### Acceptance Criteria

1. WHEN the AST foundational phase completes, THE Orchestrator SHALL build a Dependency_Graph based on each remaining Sub_Agent's declared dependencies.
2. WHEN the Dependency_Graph is built, THE Orchestrator SHALL validate that the graph contains no cycles and reject execution if a cycle is detected.
3. WHEN post-AST execution starts, THE Orchestrator SHALL launch all Sub_Agents that have zero unresolved dependencies (beyond the already-resolved AST dependency) simultaneously.
4. WHEN a Sub_Agent completes successfully, THE Orchestrator SHALL unlock dependent Sub_Agents whose remaining dependencies are all resolved and launch them immediately.
5. THE Orchestrator SHALL enforce a configurable maximum concurrency limit via the Concurrency_Limiter (default: 5 concurrent Sub_Agents).
6. WHEN all Sub_Agents complete or fail, THE Orchestrator SHALL return an aggregated AnalysisResult within 50ms of the last Sub_Agent completing.

### Requirement 3: Declaración de Dependencias entre Sub-Agentes

**User Story:** Como desarrollador del backend, quiero declarar dependencias entre sub-agentes de forma explícita, para que el orquestador pueda determinar automáticamente el orden de ejecución óptimo.

#### Acceptance Criteria

1. THE Sub_Agent interface SHALL expose a `dependencies` property that returns a list of Sub_Agent names required to execute before the current Sub_Agent.
2. WHEN a Sub_Agent declares dependencies on other Sub_Agents (beyond the implicit AST dependency), THE Orchestrator SHALL wait for those dependencies to complete before launching the dependent Sub_Agent.
3. WHEN a Sub_Agent declares dependencies, THE Orchestrator SHALL pass the resolved Agent_Results of those dependencies to the dependent Sub_Agent's execute method via the context.
4. WHEN a dependency Sub_Agent fails, THE Orchestrator SHALL skip all downstream Sub_Agents that depend on the failed agent and mark them as failed with a descriptive error indicating the upstream failure.
5. THE Sub_Agent interface SHALL allow each agent to declare dependencies as an empty list by default (meaning only the implicit AST dependency), preserving backward compatibility with existing agents.

### Requirement 4: Reintentos con Backoff Exponencial

**User Story:** Como desarrollador del backend, quiero que los sub-agentes fallidos se reintenten automáticamente con backoff exponencial, para mejorar la resiliencia del pipeline ante errores transitorios.

#### Acceptance Criteria

1. WHEN a Sub_Agent execution fails with an exception, THE Orchestrator SHALL retry the Sub_Agent up to the configured maximum retry count (default: 2 retries).
2. WHEN retrying a Sub_Agent, THE Orchestrator SHALL wait an exponentially increasing delay between attempts (base delay: 1 second, multiplier: 2x per retry).
3. WHEN all retry attempts for a Sub_Agent are exhausted, THE Orchestrator SHALL mark the Sub_Agent as failed and emit an agent_error event via the SSE_Stream.
4. WHEN the AST_Analyzer (foundational phase) fails after all retries, THE Orchestrator SHALL abort the entire Pipeline without launching any subsequent Sub_Agents.
5. THE Retry_Policy SHALL be configurable per Sub_Agent, allowing individual agents to override the default retry count and base delay.

### Requirement 5: Particionamiento de Trabajo dentro de Sub-Agentes

**User Story:** Como desarrollador del backend, quiero que los sub-agentes puedan subdividir su trabajo internamente en particiones paralelas, para acelerar el procesamiento de repositorios grandes.

#### Acceptance Criteria

1. WHEN a Sub_Agent receives a repository with more than 50 source files, THE Sub_Agent SHALL partition the file set into batches of configurable size (default: 20 files per batch).
2. WHEN a Sub_Agent partitions work into batches, THE Sub_Agent SHALL process all batches concurrently using asyncio tasks bounded by the Concurrency_Limiter.
3. WHEN all batches of a Task_Partition complete, THE Sub_Agent SHALL merge batch results into a single cohesive Agent_Result.
4. WHEN a batch within a Task_Partition fails, THE Sub_Agent SHALL continue processing remaining batches and include partial results with error annotations.
5. THE Sub_Agent SHALL emit agent_progress events via the SSE_Stream reporting the number of completed batches relative to the total batch count.

### Requirement 6: Reporte de Progreso Granular vía SSE

**User Story:** Como usuario del frontend, quiero ver el progreso detallado de cada sub-agente en tiempo real, para entender qué está pasando durante el análisis.

#### Acceptance Criteria

1. WHEN a Sub_Agent starts execution, THE Orchestrator SHALL emit an agent_start event via the SSE_Stream containing the agent name, description, and timestamp.
2. WHEN a Sub_Agent emits a progress update, THE Orchestrator SHALL forward the agent_progress event via the SSE_Stream containing the agent name, message, and progress percentage.
3. WHEN a Sub_Agent completes execution, THE Orchestrator SHALL emit an agent_complete event via the SSE_Stream containing the agent name, duration in milliseconds, and summary of results.
4. WHEN a Sub_Agent fails after all retries, THE Orchestrator SHALL emit an agent_error event via the SSE_Stream containing the agent name, error message (truncated to 1024 characters), and retry count.
5. THE SSE_Stream events SHALL include a monotonically increasing sequence number to allow the frontend to detect missed events.

### Requirement 7: Timeout Individual por Sub-Agente

**User Story:** Como desarrollador del backend, quiero configurar timeouts individuales por sub-agente, para evitar que un agente lento bloquee todo el pipeline.

#### Acceptance Criteria

1. THE Sub_Agent interface SHALL expose a `timeout_seconds` property with a configurable default value of 60 seconds.
2. WHEN a Sub_Agent exceeds its individual timeout, THE Orchestrator SHALL cancel the Sub_Agent and apply the Retry_Policy.
3. WHEN the global Pipeline timeout is reached, THE Orchestrator SHALL cancel all running Sub_Agents and return partial results for completed agents.
4. THE Orchestrator SHALL log the duration of each Sub_Agent execution in the Agent_Result regardless of success or failure.

### Requirement 8: Agregación Precisa de Resultados

**User Story:** Como desarrollador del backend, quiero que los resultados de múltiples sub-agentes se agreguen de forma precisa y sin pérdida de datos, para garantizar que el análisis final sea completo.

#### Acceptance Criteria

1. WHEN all Sub_Agents complete, THE Orchestrator SHALL merge all successful Agent_Results into a single AnalysisResult preserving the full data from each agent.
2. WHEN a Sub_Agent produces partial results (due to batch failures), THE Orchestrator SHALL include partial data in the AnalysisResult and annotate the affected sections with error metadata.
3. THE Orchestrator SHALL validate that no data from a successful Sub_Agent is lost during the merge operation.
4. WHEN the same data field is produced by multiple Sub_Agents, THE Orchestrator SHALL apply a last-writer-wins strategy based on agent priority and log a warning about the conflict.
5. THE AnalysisResult SHALL include a metadata section with total execution time, per-agent durations, retry counts, and a list of agents that failed.

### Requirement 9: Compatibilidad Retroactiva con el Endpoint Existente

**User Story:** Como consumidor del API, quiero que los endpoints existentes `/analyze` y `/analyze-stream` sigan funcionando con la misma interfaz externa, para no romper integraciones existentes.

#### Acceptance Criteria

1. THE `/analyze` endpoint SHALL return the same JSON schema as el actual response (campos: codeFlow, erModel, artifacts, nodeInspections, systemReport).
2. THE `/analyze-stream` endpoint SHALL emit SSE events with the same `type` field values (agent_start, agent_progress, agent_complete, agent_error, analysis_complete, analysis_error).
3. WHEN the new Orchestrator encounters an error, THE endpoint SHALL return HTTP error codes consistent with the existing error handling (403, 404, 400, 500, 504).
4. THE new architecture SHALL support the existing request format (AnalyzeRequest with repo_url field) without requiring client-side changes.
