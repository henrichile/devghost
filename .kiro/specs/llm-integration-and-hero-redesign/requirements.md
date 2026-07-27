# Requirements Document

## Introduction

Este documento especifica los requisitos para integrar un cliente LLM basado en la API compatible con OpenAI de Alibaba Cloud MaaS en el sistema DevGhost-Parser, y rediseñar el componente Hero del frontend. El cliente LLM enriquecerá las descripciones de nodos y los resúmenes de audio tour con generación de texto en español mediante el modelo qwen3.7-plus. Se incluye un mecanismo de fallback a las heurísticas locales existentes cuando la API no esté disponible, falle o exceda el timeout.

## Glossary

- **LLM_Client**: Módulo Python (`llm_client.py`) que encapsula la comunicación con la API de Alibaba Cloud MaaS usando el SDK de OpenAI.
- **Description_Generator**: Subsistema existente que genera descripciones en español (≤120 caracteres) para nodos arquitectónicos usando heurísticas locales.
- **Summary_Generator**: Subsistema existente que genera resúmenes narrativos de 3 a 4 oraciones en español (≤500 caracteres) sobre la base de código analizada.
- **LLM_API_KEY**: Variable de entorno que contiene la clave de autenticación para la API de Alibaba Cloud MaaS.
- **LLM_BASE_URL**: Variable de entorno opcional que permite sobreescribir la URL base de la API. Valor por defecto: `https://llm-pbjcab85dgzvpajw.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1`.
- **LLM_MODEL**: Variable de entorno opcional que permite sobreescribir el modelo LLM. Valor por defecto: `qwen3.7-plus`.
- **Fallback_Heuristic**: Lógica heurística local existente en Description_Generator y Summary_Generator que se usa como respaldo cuando el LLM no está disponible.
- **Hero_Component**: Componente React (`InitialHeroState.tsx`) que se muestra como pantalla principal antes de que el usuario envíe una URL para análisis.
- **Logo_Animation**: Animación CSS del logotipo dev.ghost() que incluye un efecto de levitación (float).

## Requirements

### Requirement 1: Configuración del cliente LLM

**User Story:** Como desarrollador del sistema, quiero un módulo centralizado de cliente LLM, para que la comunicación con la API de Alibaba Cloud MaaS esté encapsulada y sea reutilizable.

#### Acceptance Criteria

1. THE LLM_Client SHALL initialize an OpenAI-compatible client using the `openai.OpenAI` constructor with `api_key` read from the `LLM_API_KEY` environment variable.
2. THE LLM_Client SHALL use `https://llm-pbjcab85dgzvpajw.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1` as the default `base_url` value.
3. WHERE the `LLM_BASE_URL` environment variable is set, THE LLM_Client SHALL use its value as the `base_url` instead of the default.
4. THE LLM_Client SHALL use `qwen3.7-plus` as the default model identifier.
5. WHERE the `LLM_MODEL` environment variable is set, THE LLM_Client SHALL use its value as the model identifier instead of the default.
6. THE LLM_Client SHALL enforce a timeout of 4 seconds on each API request.
7. IF the `LLM_API_KEY` environment variable is not set or is empty, THEN THE LLM_Client SHALL expose an `available` property that returns `False` and SHALL NOT attempt any network connection during initialization.
8. IF an API request exceeds the 4-second timeout, THEN THE LLM_Client SHALL raise a timeout-specific exception without retrying the request.
9. IF the `LLM_BASE_URL` environment variable is set but contains a value that does not start with `http://` or `https://`, THEN THE LLM_Client SHALL treat the configuration as invalid and set the `available` property to `False`.

### Requirement 2: Generación de descripciones de nodo con LLM

**User Story:** Como usuario del sistema, quiero que las descripciones de nodos sean generadas por un LLM cuando esté disponible, para que las descripciones sean más precisas y contextuales que las heurísticas locales.

#### Acceptance Criteria

1. WHEN the LLM_Client is available, THE Description_Generator SHALL send the node component name (label), node type (NodeType), and list of extracted method names to the LLM_Client as a structured prompt for description generation.
2. WHEN the LLM_Client is available, THE Description_Generator SHALL include in the prompt the instruction to produce a technical, direct summary in Spanish with a maximum of 90 characters.
3. WHEN the LLM_Client returns a non-empty response containing at least 5 characters, THE Description_Generator SHALL use the LLM-generated text as the node description.
4. THE Description_Generator SHALL truncate any LLM-generated description that exceeds 90 characters to exactly 87 characters followed by "...".
5. IF the LLM_Client request exceeds 4 seconds without receiving a complete response, THEN THE Description_Generator SHALL cancel the pending request and fall back to the existing local heuristic logic.
6. IF the LLM_Client returns an HTTP error status, a network error, or a response body that is empty or contains only whitespace, THEN THE Description_Generator SHALL fall back to the existing local heuristic logic.
7. IF the LLM_Client signals unavailability (available property is False), THEN THE Description_Generator SHALL use the existing local heuristic logic without attempting an API call.

### Requirement 3: Generación de audio tour con LLM

**User Story:** Como usuario del sistema, quiero que el resumen de audio tour sea generado por un LLM cuando esté disponible, para que la narrativa sea más fluida y natural que las plantillas heurísticas.

#### Acceptance Criteria

1. WHEN the LLM_Client is available, THE Summary_Generator SHALL send the list of controller names and database entity names to the LLM_Client for narrative generation.
2. WHEN the LLM_Client is available, THE Summary_Generator SHALL request a fluid narrative of 3 to 4 sentences in Spanish with a maximum of 450 characters.
3. WHEN the LLM_Client returns a non-empty response that contains between 1 and 450 characters and at least one complete sentence ending in a period, THE Summary_Generator SHALL use the LLM-generated text as the audio tour summary.
4. THE Summary_Generator SHALL truncate any LLM-generated summary that exceeds 450 characters to exactly 447 characters followed by "...".
5. IF the LLM_Client request exceeds 4 seconds without receiving a complete response, THEN THE Summary_Generator SHALL cancel the pending request and fall back to the existing local heuristic logic.
6. IF the LLM_Client returns an HTTP error status, a network error, or a response body that is empty or contains only whitespace, THEN THE Summary_Generator SHALL fall back to the existing local heuristic logic.
7. IF the LLM_Client signals unavailability before the request is attempted, THEN THE Summary_Generator SHALL use the existing local heuristic logic without attempting an API call.
8. THE Summary_Generator SHALL apply the existing sanitization rules (removal of control characters, prohibited markdown characters, and code identifiers, followed by whitespace normalization) to LLM-generated text after truncation and before returning the summary.
9. IF the LLM-generated text after sanitization results in an empty string or a string shorter than 10 characters, THEN THE Summary_Generator SHALL discard the LLM result and fall back to the existing local heuristic logic.

### Requirement 4: Resiliencia y manejo de errores del LLM

**User Story:** Como operador del sistema, quiero que el sistema sea resiliente a fallos del LLM, para que el análisis de arquitectura funcione correctamente incluso sin conectividad a la API.

#### Acceptance Criteria

1. THE LLM_Client SHALL catch all exceptions from the OpenAI SDK (including `openai.APIError`, `openai.APITimeoutError`, `openai.APIConnectionError`) and return `None` as the error indicator instead of propagating exceptions.
2. IF the LLM API responds with an HTTP status code outside the 2xx range, THEN THE LLM_Client SHALL treat the response as an error and return `None`.
3. WHEN a request fails due to timeout, network error, or API error, THE LLM_Client SHALL log a warning message via the `logging` module including the error type and message.
4. THE Description_Generator and Summary_Generator SHALL complete analysis within 5 seconds regardless of LLM availability, accounting for the 4-second timeout plus processing overhead.
5. WHEN the LLM_Client is unavailable (available property is False), THE system SHALL produce identical output to the current heuristic-only behavior, with no observable difference in the JSON response.
6. THE LLM_Client SHALL NOT implement any retry logic; each failed request SHALL result in immediate fallback to heuristics.

### Requirement 5: Rediseño del Hero Component

**User Story:** Como usuario de la interfaz, quiero ver una pantalla inicial atractiva con el logo animado de dev.ghost() prominente, para que la primera impresión del producto sea profesional y memorable.

#### Acceptance Criteria

1. WHILE no analysis has been submitted, THE Hero_Component SHALL render as a full-width section occupying the available viewport height below the browser chrome, displaying the logo, tagline, input field, and analyze button as the primary content.
2. THE Hero_Component SHALL display the animated dev.ghost() logo horizontally centered within the header area at a minimum rendered size of 32×32 pixels.
3. THE Hero_Component SHALL include a tagline of no more than 120 characters describing the purpose of DevGhost-Parser, positioned below the logo.
4. THE Hero_Component SHALL include the repository URL input field (maximum 2048 characters) and the analyze button grouped together below the tagline.
5. WHEN the user submits a valid URL for analysis, THE Hero_Component SHALL be replaced by the analysis results view, removing the tagline and centering layout from the viewport.
6. IF the user attempts to submit an empty or invalid URL, THEN THE Hero_Component SHALL keep the analyze button disabled and remain in its current state without navigating away.
7. THE Logo_Animation SHALL use the existing ghost-float CSS keyframe animation with a 3-second cycle duration for the levitation effect.
8. THE Hero_Component SHALL be responsive, stacking elements vertically on viewports narrower than 640px and using horizontal grouping on viewports 640px and wider, supporting viewport widths from 320px to 1920px.
9. THE Hero_Component SHALL maintain accessible contrast ratios conforming to WCAG 2.1 AA (minimum 4.5:1 for normal text, 3:1 for large text) for all text elements against their background.

### Requirement 6: Dependencia del paquete OpenAI

**User Story:** Como desarrollador del sistema, quiero que la dependencia del SDK de OpenAI esté correctamente declarada, para que el entorno de producción pueda instalar el paquete sin conflictos.

#### Acceptance Criteria

1. THE project configuration SHALL declare `openai` as a production dependency in `pyproject.toml`.
2. THE project configuration SHALL pin the `openai` dependency to a compatible version range using the `>=X.Y.Z,<X+1` format to allow patch updates while preventing breaking changes.
