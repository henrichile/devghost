# Implementation Plan: Precision Analysis Enhancements

## Overview

Implementación incremental de mejoras de precisión en DevGhost-Parser: nuevo NodeType "Config", extracción de métodos vía tree-sitter con filtrado de visibilidad, descripciones basadas en métodos reales, exposición de métodos en la API, visualización en frontend, e inferencia de dominio de negocio en el resumen global.

## Tasks

- [x] 1. Extensión del modelo de datos y constantes de clasificación
  - [x] 1.1 Añadir "Config" al NodeType Literal y campo `method_names` al dataclass Node en `models.py`
    - Agregar "Config" a la definición `NodeType = Literal[...]`
    - Añadir campo `method_names: list[str] = field(default_factory=list)` al dataclass `Node`
    - _Requirements: 7.1, 2.1_

  - [x] 1.2 Añadir constantes de clasificación Config e Init en `code_flow_analyzer.py`
    - Crear `_CONFIG_PATTERNS: list[str]` con los patrones: "config", "configuration", "connection", "database", "appconfig", "dbconfig", "settings"
    - Crear `_INIT_PATTERNS: list[str]` con los patrones: "init", "bootstrap", "setup", "startup"
    - _Requirements: 1.1, 1.2_

  - [x] 1.3 Implementar lógica de clasificación con prioridad Config en `code_flow_analyzer.py`
    - Modificar la función de clasificación para evaluar Config patterns ANTES de Route
    - Priorizar "Config" sobre cualquier tipo excepto "Controller"
    - Si coincide Config + Init simultáneamente, asignar "Config"
    - Si coincide Config + Controller simultáneamente, asignar "Controller"
    - Si coincide solo Init patterns (sin Config), asignar "Utility"
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

  - [x] 1.4 Write property tests for Config classification (Properties 1 & 2)
    - **Property 1: Config Classification Correctness**
    - **Property 2: Classification Priority — Config Over Others Except Controller**
    - **Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5**

- [x] 2. Extracción de métodos desde el AST con tree-sitter
  - [x] 2.1 Implementar función `_extract_method_names` en `code_flow_analyzer.py`
    - Recorrer el AST depth-first para encontrar nodos de tipo function/method definition
    - Extraer nombres en orden de aparición en el código fuente
    - Almacenar resultado en `method_names` del FileContext
    - _Requirements: 2.1_

  - [x] 2.2 Implementar función `_filter_methods_by_visibility` en `code_flow_analyzer.py`
    - Para Python: excluir nombres que comiencen con `__` (dunder methods)
    - Para Java/TypeScript/C#: excluir métodos private/protected
    - Para Go/Rust/Ruby: no aplicar filtrado, retornar todos
    - _Requirements: 2.2, 2.5_

  - [x] 2.3 Aplicar cap de 15 métodos y manejo de errores en `code_flow_analyzer.py`
    - Aplicar `[:15]` sobre la lista filtrada de métodos
    - Si la extensión no está soportada o el parser lanza excepción: retornar lista vacía sin error fatal
    - Registrar warning no-fatal cuando ocurra un error de parsing
    - _Requirements: 2.3, 2.4_

  - [x] 2.4 Write property tests for method extraction (Properties 3, 4 & 5)
    - **Property 3: Method Extraction Produces Ordered List Capped at 15**
    - **Property 4: Private/Dunder Method Exclusion**
    - **Property 5: Graceful Fallback for Unsupported Files**
    - **Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5**

- [x] 3. Checkpoint - Validar clasificación y extracción de métodos
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Generación de descripciones basadas en métodos reales
  - [x] 4.1 Añadir soporte para NodeType "Config" en `description_generator.py`
    - Agregar entrada `"Config": "Configuración del sistema"` a `_GENERIC_FALLBACKS`
    - Agregar entrada `"Config": "Configuración que define"` a `_TYPE_PREFIXES`
    - Implementar `_config_description(node)` con inferencia de dominio desde label (database → "base de datos", redis → "Redis", auth → "autenticación", etc.)
    - _Requirements: 3.3, 3.6_

  - [x] 4.2 Implementar descripción desde métodos con PURPOSE_MAP en `description_generator.py`
    - Cuando method_names tiene matches en METHOD_PURPOSE_MAP: concatenar prefijo del NodeType con hasta 3 propósitos inferidos
    - Cuando NO hay matches: implementar `_from_methods_no_match` que lista hasta 3 nombres de métodos directamente con formato "[Prefijo] método1, método2 y método3"
    - Mantener truncamiento a 120 caracteres (117 + "...")
    - Garantizar que la descripción nunca sea cadena vacía
    - _Requirements: 3.1, 3.2, 3.4, 3.5, 3.6_

  - [x] 4.3 Write property tests for description generation (Properties 6, 7 & 8)
    - **Property 6: Description From Methods Uses Purpose Map or Direct Listing**
    - **Property 7: Description Invariant (Including Config)**
    - **Property 8: Config Description Template**
    - **Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6**

- [x] 5. Serialización de métodos en la API
  - [x] 5.1 Incluir campo "methods" en la serialización de nodos en `output_serializer.py`
    - Añadir `"methods": node.method_names[:10]` al diccionario serializado de cada nodo
    - Si method_names está vacío, serializar como array JSON vacío `[]`
    - Respetar el orden de declaración en el código fuente
    - _Requirements: 4.1, 4.2, 4.3, 7.4_

  - [x] 5.2 Write property test for serialization (Property 9)
    - **Property 9: Serialization Includes Methods Field Capped at 10**
    - **Validates: Requirements 4.1, 4.2, 4.3**

- [x] 6. Inferencia de dominio de negocio en el resumen global
  - [x] 6.1 Implementar mapa de palabras clave de dominio en `summary_generator.py`
    - Crear `_DOMAIN_KEYWORD_MAP` con al menos 15 entradas (asistencia, producto, factura, usuario, orden, paciente, alumno, empleado, vehiculo, reserva, pago, cuenta, inventario, ticket, proyecto, cliente, venta, compra, envio, curso)
    - _Requirements: 6.5_

  - [x] 6.2 Implementar función `_infer_domain` en `summary_generator.py`
    - Comparar entidades ER + labels de nodos contra keyword map (case-insensitive, substring match bidireccional)
    - Seleccionar dominio con mayor cantidad de coincidencias
    - Tie-break: primera coincidencia más temprana en el orden de entidades
    - Si no hay match: retornar None (mantener oración genérica)
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

  - [x] 6.3 Integrar oración de dominio en el resumen generado en `summary_generator.py`
    - Reemplazar oración genérica de propósito con "El sistema esta diseñado para [propósito del dominio]"
    - Verificar que el resumen no exceda 500 code points ni 4 oraciones
    - Si la oración de dominio haría exceder el límite: omitirla
    - _Requirements: 6.2, 6.6_

  - [x] 6.4 Write property tests for domain inference and summary (Properties 10 & 11)
    - **Property 10: Domain Inference Correctness**
    - **Property 11: Summary Invariant With Domain Inference**
    - **Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.5, 6.6**

- [x] 7. Checkpoint - Validar backend completo
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Actualización del frontend — tipos y grafo
  - [x] 8.1 Actualizar tipos TypeScript en `types.ts`
    - Añadir "Config" al union type `NodeType`
    - Añadir campo opcional `methods?: string[]` a la interfaz `CodeFlowNode`
    - _Requirements: 7.1_

  - [x] 8.2 Implementar renderizado de nodos Config en `CodeFlowGraph.tsx`
    - Añadir case "Config" en `getNodeStyle` con color de fondo exclusivo (`#9333ea` — Purple-600)
    - Añadir case "Config" en `getNodeIcon` con icono distinto (ej: '⚙️' o '📋')
    - Añadir case "Config" en `getNodeTypeLabel` retornando "CONFIG"
    - Añadir case "Config" en `getNodeRank` con valor 6
    - Añadir botón de filtro para "Config" en la barra de filtros por tipo
    - _Requirements: 7.2, 7.5_

- [x] 9. Visualización de métodos en el panel de inspección
  - [x] 9.1 Implementar sección "Métodos / Funciones clave" en `InspectionPanel.tsx`
    - Mostrar sección entre descripción y dependencias cuando `methods` tiene al menos 1 elemento
    - Ocultar sección completamente cuando `methods` está vacío o undefined
    - Renderizar cada método con prefijo "ƒ " y nombre truncado a 37 chars + "..." si excede 40 chars
    - Mostrar máximo 20 métodos con indicador de métodos adicionales si hay más
    - Mostrar badge de tipo "Config" con color correspondiente en InspectionPanel
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 7.3_

  - [x] 9.2 Write property test for method display truncation (Property 12)
    - **Property 12: Method Display Name Truncation**
    - **Validates: Requirements 5.3**

- [x] 10. Final checkpoint - Verificar integración completa
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties using Hypothesis (already installed)
- Unit tests validate specific examples and edge cases
- Backend uses Python; frontend uses TypeScript/React
- El cap de métodos es 15 en extracción, 10 en serialización, 20 en display frontend

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["1.3", "6.1"] },
    { "id": 2, "tasks": ["1.4", "2.1"] },
    { "id": 3, "tasks": ["2.2", "2.3"] },
    { "id": 4, "tasks": ["2.4", "4.1"] },
    { "id": 5, "tasks": ["4.2", "5.1", "6.2"] },
    { "id": 6, "tasks": ["4.3", "5.2", "6.3"] },
    { "id": 7, "tasks": ["6.4", "8.1"] },
    { "id": 8, "tasks": ["8.2", "9.1"] },
    { "id": 9, "tasks": ["9.2"] }
  ]
}
```
