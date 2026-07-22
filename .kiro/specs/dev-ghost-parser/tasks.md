# Implementation Plan: DevGhost-Parser

## Overview

Implementación de un analizador estático de arquitectura de software en Python que examina un directorio de código fuente y produce un único objeto JSON estructurado con tres dimensiones: grafo de flujo de código, modelo entidad-relación y resumen ejecutivo narrado. El sistema utiliza tree-sitter para análisis AST multi-lenguaje, Hypothesis para pruebas de propiedades y pytest para pruebas unitarias.

## Tasks

- [x] 1. Configurar la estructura del proyecto y las interfaces base
  - Crear la estructura de directorios: `src/dev_ghost_parser/`, `tests/unit/`, `tests/property/`
  - Crear `pyproject.toml` o `setup.py` con dependencias: `tree-sitter`, `hypothesis`, `pytest`, `pytest-cov`
  - Instalar las gramáticas tree-sitter para PHP, JavaScript, TypeScript, Python, Ruby, Go, Rust, Java, C#
  - Definir los tipos de datos compartidos: `Node`, `Edge`, `Entity`, `Relation`, `CodeFlowResult`, `ERResult`, `AnalysisError`, `SubsystemError`
  - Crear el archivo `src/dev_ghost_parser/__init__.py` y exponer la clase `DevGhost_Parser`
  - _Requisitos: 1.2, 1.3, 2.1, 2.3, 4.3, 4.4_

- [x] 2. Implementar `DevGhost_Parser` — validación de entrada y orquestación
  - [x] 2.1 Implementar la secuencia de validación de entrada en `DevGhost_Parser.analyze()`
    - Implementar los 4 checks en orden estricto: path ausente/vacío → no encontrado → sin permisos → no es directorio
    - Retornar `{"errors": [{"message": "..."}]}` en bytes UTF-8 sin BOM ante el primer check fallido
    - Serializar la respuesta de error usando `json.dumps(..., ensure_ascii=False).encode("utf-8")`
    - _Requisitos: 5.1, 5.2, 5.3, 5.4, 5.5_

  - [x] 2.2 Escribir prueba de propiedad para la validación de entrada (Propiedad 10)
    - **Propiedad 10: Orden de validación de entrada**
    - **Valida: Requisito 5.5**
    - Usar `@given` con estrategias que generen combinaciones de condiciones de error (path None, path inexistente, path sin permisos, path a archivo)
    - Verificar que solo se retorna el error del check de mayor prioridad según el orden mandatorio
    - Etiquetar: `# Feature: dev-ghost-parser, Property 10: Orden de validación de entrada`

  - [x] 2.3 Implementar la lógica de orquestación en `DevGhost_Parser.analyze()`
    - Instanciar y llamar a `Code_Flow_Analyzer`, `ER_Extractor` y `Summary_Generator` cuando la validación pasa
    - Capturar errores fatales de subsistemas y propagarlos a `Output_Serializer`
    - Garantizar que nunca se lancen excepciones hacia el llamador
    - _Requisitos: 5.6, 4.7_

  - [x] 2.4 Escribir pruebas unitarias para `DevGhost_Parser`
    - Verificar los 4 checks de validación con ejemplos concretos de cada condición
    - Verificar que cuando la validación pasa, se invocan los tres subsistemas
    - Verificar que la respuesta de error contiene solo la clave `errors`
    - _Requisitos: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

- [x] 3. Checkpoint — Verificar estructura base y validación de entrada
  - Asegurar que todos los tests pasan hasta este punto, consultar al usuario si surgen dudas.

- [x] 4. Implementar `Code_Flow_Analyzer`
  - [x] 4.1 Implementar el recorrido de directorios y clasificación arquitectónica
    - Implementar `Code_Flow_Analyzer.analyze(root_path)` con `os.walk` para recorrer el directorio recursivamente
    - Implementar la lógica de clasificación usando los patrones de nombre de archivo/clase: `*Controller*` → `Controller`, `*Service*` → `Service`, `*Route*`/`router*`/`routes*` → `Route`, `*Middleware*` → `Middleware`, `*Repository*`/`*Repo*` → `Repository`, resto → `Utility`
    - Generar `Node.id` como hash SHA-1 estable del path relativo al `root_path`
    - Generar `Node.label` desde el nombre de la clase principal cuando existe, o el nombre del archivo sin extensión
    - _Requisitos: 1.1, 1.2_

  - [x] 4.2 Escribir prueba de propiedad para los campos de nodo requeridos (Propiedad 2)
    - **Propiedad 2: Los nodos generados contienen los campos requeridos**
    - **Valida: Requisito 1.2**
    - Usar `@given` con estrategias que generen paths de archivo aleatorios con extensiones reconocidas
    - Verificar que cada nodo producido tiene `id` no vacío, `label` no vacío, y `type` dentro del conjunto `{Controller, Service, Route, Middleware, Repository, Utility}`
    - Etiquetar: `# Feature: dev-ghost-parser, Property 2: Los nodos generados contienen los campos requeridos`

  - [x] 4.3 Implementar la extracción de imports/dependencias con tree-sitter
    - Para cada archivo con extensión reconocida (`.php`, `.js`, `.ts`, `.py`, `.rb`, `.go`, `.rs`, `.java`, `.cs`), obtener el parser tree-sitter correspondiente
    - Usar consultas S-expression para identificar `import`, `require`, `use`, llamadas entre módulos
    - Generar `Edge` con `source` = id del archivo actual, `target` = id del archivo importado, `relation` = `"imports"` | `"calls"` | `"depends_on"`
    - Registrar archivos no parseables en `CodeFlowResult.errors` (no fatales) y continuar
    - _Requisitos: 1.3, 1.6_

  - [x] 4.4 Implementar el filtro de integridad referencial de aristas
    - Construir el conjunto de todos los `id` de nodos generados
    - Eliminar toda arista cuyo `source` o `target` no esté en ese conjunto
    - Retornar `CodeFlowResult` con `nodes`, `edges` filtradas y `errors`
    - Si `root_path` es inaccesible, lanzar `AnalysisFatalError`
    - _Requisitos: 1.3, 1.4, 1.5, 1.6_

  - [x] 4.5 Escribir prueba de propiedad para integridad referencial (Propiedad 1)
    - **Propiedad 1: Integridad referencial del grafo de flujo**
    - **Valida: Requisitos 1.3, 1.5**
    - Usar `@given` con estrategias que generen listas arbitrarias de nodos y aristas (algunas con targets inválidos)
    - Invocar el filtro de integridad y verificar que todas las aristas resultantes referencian nodos existentes
    - Etiquetar: `# Feature: dev-ghost-parser, Property 1: Integridad referencial del grafo de flujo`

  - [x] 4.6 Escribir pruebas unitarias para `Code_Flow_Analyzer`
    - Verificar que `UserController.php` produce `type = "Controller"`
    - Verificar que `orderService.ts` produce `type = "Service"`
    - Verificar que el mismo path siempre produce el mismo `id` (estabilidad del hash)
    - Verificar que un directorio sin archivos reconocibles retorna arrays vacíos
    - _Requisitos: 1.1, 1.2, 1.4_

- [x] 5. Implementar `ER_Extractor`
  - [x] 5.1 Implementar el parseo de modelos Eloquent (PHP + tree-sitter)
    - Detectar archivos `*.php` que contengan `extends Model`
    - Usar tree-sitter PHP para extraer nombre de clase, propiedades `$fillable`, `$casts`
    - Extraer métodos de relación: `hasMany`, `belongsTo`, `hasOne`, `belongsToMany`, `morphTo`, etc.
    - Producir `Entity` con `name`, `attributes` y `primaryKey`; producir `Relation` por cada método de relación
    - _Requisitos: 2.1, 2.2, 2.3_

  - [x] 5.2 Implementar el parseo del esquema Prisma
    - Detectar archivos `schema.prisma`
    - Usar regex/tree-sitter para parsear bloques `model { }`, extraer campos y tipos
    - Detectar relaciones mediante anotaciones `@relation` y campos de tipo referenciado
    - Producir `Entity` y `Relation` con la misma estructura que en 5.1
    - _Requisitos: 2.1, 2.2, 2.3_

  - [x] 5.3 Implementar el parseo de modelos SQLAlchemy (Python + tree-sitter)
    - Detectar archivos `*.py` que contengan `declarative_base` o `Base`
    - Usar tree-sitter Python para extraer clases que hereden de `Base`, columnas `Column(...)`
    - Inferir relaciones desde `relationship(...)` y `ForeignKey(...)`
    - Producir `Entity` y `Relation` con la misma estructura
    - _Requisitos: 2.1, 2.2, 2.3_

  - [x] 5.4 Implementar el parseo de migraciones SQL y deduplicación
    - Detectar archivos `*.sql` y `*.migration.*`
    - Usar regex + árbol sintáctico para `CREATE TABLE`, `ALTER TABLE ADD FOREIGN KEY`
    - Implementar la deduplicación: ORM > migración > SQL crudo; cuando hay conflicto, la fuente de mayor prioridad prevalece
    - Retornar arrays vacíos si no se encuentran archivos ORM, migraciones ni SQL
    - Registrar archivos no parseables en `ERResult.errors` y continuar
    - _Requisitos: 2.2, 2.4, 2.5, 2.6_

  - [x] 5.5 Escribir prueba de propiedad para unicidad de entidades ER (Propiedad 3)
    - **Propiedad 3: Unicidad de entidades ER**
    - **Valida: Requisito 2.5**
    - Usar `@given` con estrategias que generen conjuntos de nombres de entidad con posibles duplicados de distintas fuentes
    - Verificar que el resultado de la deduplicación no contiene dos entidades con el mismo `name`
    - Etiquetar: `# Feature: dev-ghost-parser, Property 3: Unicidad de entidades ER`

  - [x] 5.6 Escribir prueba de propiedad para estructura completa de entidades (Propiedad 4)
    - **Propiedad 4: Estructura completa de entidades ER**
    - **Valida: Requisito 2.1**
    - Usar `@given` con estrategias que generen definiciones de modelo aleatorias (nombres de tabla, listas de columnas)
    - Verificar que cada `Entity` producida contiene `name` no vacío, `attributes` (array), y `primaryKey`
    - Etiquetar: `# Feature: dev-ghost-parser, Property 4: Estructura completa de entidades ER`

  - [x] 5.7 Escribir pruebas unitarias para `ER_Extractor`
    - Verificar que un `schema.prisma` de ejemplo produce las entidades y relaciones correctas
    - Verificar que un modelo SQLAlchemy de ejemplo produce la entidad correcta
    - Verificar que relaciones con métodos desconocidos producen `type = "unknown"` con `rawDeclaration`
    - Verificar que un directorio sin archivos ORM/SQL retorna arrays vacíos
    - _Requisitos: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

- [x] 6. Checkpoint — Verificar subsistemas de análisis
  - Asegurar que todos los tests pasan hasta este punto, consultar al usuario si surgen dudas.

- [x] 7. Implementar `Summary_Generator`
  - [x] 7.1 Implementar la generación del texto del resumen
    - Contar tipos de nodos del grafo para inferir el patrón arquitectónico dominante
    - Listar las entidades principales del modelo ER
    - Construir el resumen (máximo 3 oraciones) usando plantillas de texto plano en inglés
    - Retornar la cadena fija `"No analyzable source files were found in the provided codebase."` si no hay archivos reconocibles
    - Agregar oración de advertencia si algún subsistema falló
    - _Requisitos: 3.1, 3.3, 3.5_

  - [x] 7.2 Implementar la sanitización y truncado del resumen
    - Eliminar los caracteres prohibidos: `* # \` _ ~ > < >` y caracteres de control U+0000–U+001F
    - Eliminar identificadores camelCase/snake_case del texto generado
    - Truncar a 500 puntos de código Unicode si el texto excede ese límite
    - _Requisitos: 3.2, 3.4_

  - [x] 7.3 Escribir prueba de propiedad para el límite de 500 puntos de código (Propiedad 5)
    - **Propiedad 5: El resumen respeta el límite de 500 puntos de código**
    - **Valida: Requisito 3.4**
    - Usar `@given` con estrategias que generen resultados de análisis arbitrarios (nodos, entidades, errores)
    - Verificar que `len(summary) <= 500` para toda entrada generada
    - Etiquetar: `# Feature: dev-ghost-parser, Property 5: El resumen respeta el límite de 500 puntos de código`

  - [x] 7.4 Escribir prueba de propiedad para caracteres prohibidos en el resumen (Propiedad 6)
    - **Propiedad 6: El resumen está libre de caracteres prohibidos**
    - **Valida: Requisitos 3.2**
    - Usar `@given` con estrategias que generen texto fuente con caracteres especiales y de control
    - Verificar que tras la sanitización el `summary` no contiene ningún carácter del conjunto prohibido ni caracteres U+0000–U+001F
    - Etiquetar: `# Feature: dev-ghost-parser, Property 6: El resumen está libre de caracteres prohibidos`

  - [x] 7.5 Escribir pruebas unitarias para `Summary_Generator`
    - Verificar que un codebase vacío retorna exactamente la cadena fija mandatoria
    - Verificar que el resumen con entradas normales no excede 3 oraciones
    - Verificar que la sanitización elimina los caracteres prohibidos
    - _Requisitos: 3.1, 3.2, 3.3, 3.4, 3.5_

- [x] 8. Implementar `Output_Serializer`
  - [x] 8.1 Implementar la composición del objeto JSON de salida exitosa
    - Cuando todos los subsistemas tienen éxito, emitir `{"codeFlow": {...}, "erModel": {...}, "summary": "..."}` sin clave `errors`
    - Serializar con `json.dumps(obj, ensure_ascii=False).encode("utf-8")` para producir bytes UTF-8 sin BOM
    - _Requisitos: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_

  - [x] 8.2 Implementar la composición del objeto JSON con errores de subsistemas
    - Cuando algún subsistema falla, establecer la clave correspondiente en `null` y agregar `"errors": [{"subsystem": "...", "message": "..."}]`
    - Incluir también errores no fatales de archivo individual en el array `errors`
    - Garantizar que la clave `errors` se omite completamente cuando todos los subsistemas tienen éxito
    - _Requisitos: 4.7_

  - [x] 8.3 Escribir prueba de propiedad para la serialización round-trip (Propiedad 7)
    - **Propiedad 7: Serialización de ida y vuelta (round-trip)**
    - **Valida: Requisito 6.1**
    - Usar `@given` con estrategias que generen objetos de resultado arbitrarios válidos
    - Verificar que `json.loads(output.decode("utf-8"))` produce un objeto con las mismas claves, tipos, valores escalares y arrays en el mismo orden
    - Etiquetar: `# Feature: dev-ghost-parser, Property 7: Serialización de ida y vuelta`

  - [x] 8.4 Escribir prueba de propiedad para UTF-8 sin BOM (Propiedad 8)
    - **Propiedad 8: La salida es UTF-8 sin BOM**
    - **Valida: Requisitos 4.1, 6.2**
    - Usar `@given` con estrategias que generen objetos de resultado arbitrarios
    - Verificar que los bytes de salida no comienzan con `\xef\xbb\xbf` y son decodificables como UTF-8 válido
    - Etiquetar: `# Feature: dev-ghost-parser, Property 8: La salida es UTF-8 sin BOM`

  - [x] 8.5 Escribir prueba de propiedad para caracteres de control sin escapar (Propiedad 9)
    - **Propiedad 9: Los caracteres de control no aparecen sin escapar**
    - **Valida: Requisito 6.3**
    - Usar `@given` con estrategias que generen strings con caracteres de control U+0000–U+001F en los valores
    - Verificar que en la cadena JSON de salida todos los caracteres de control están representados como `\uXXXX`
    - Etiquetar: `# Feature: dev-ghost-parser, Property 9: Los caracteres de control no aparecen sin escapar`

  - [x] 8.6 Escribir pruebas unitarias para `Output_Serializer`
    - Verificar que la salida con todos los subsistemas exitosos omite la clave `errors`
    - Verificar que cuando un subsistema falla, la clave correspondiente es `null` y `errors` contiene la entrada correcta
    - Verificar que la salida es bytes y no comienza con BOM
    - _Requisitos: 4.1, 4.2, 4.6, 4.7_

- [x] 9. Integración y conexión de componentes
  - [x] 9.1 Conectar todos los subsistemas en `DevGhost_Parser.analyze()`
    - Integrar `Code_Flow_Analyzer`, `ER_Extractor`, `Summary_Generator` y `Output_Serializer` en el flujo completo del orquestador
    - Pasar `CodeFlowResult` y `ERResult` como entrada a `Summary_Generator`
    - Pasar todos los resultados (o errores) a `Output_Serializer.serialize()`
    - Garantizar que `analyze()` nunca lanza excepciones: todo error queda codificado en el JSON de salida
    - _Requisitos: 4.2, 4.7, 5.6_

  - [x] 9.2 Escribir pruebas de integración del flujo completo
    - Crear fixtures de directorios de código fuente de ejemplo con archivos PHP, Python y Prisma
    - Verificar que el JSON de salida contiene las tres claves `codeFlow`, `erModel` y `summary`
    - Verificar el flujo completo con un codebase vacío
    - Verificar el flujo completo con un codebase que contiene errores de parseo en algunos archivos
    - _Requisitos: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7_

- [x] 10. Checkpoint final — Asegurar cobertura y corrección
  - Asegurar que todos los tests pasan (unitarios y de propiedades), cobertura ≥ 85% en subsistemas y 100% en `DevGhost_Parser.analyze()` y `Output_Serializer.serialize()`. Consultar al usuario si surgen dudas.

## Notes

- Las tareas marcadas con `*` son opcionales y pueden omitirse para una versión MVP más rápida
- Cada tarea referencia requisitos específicos para trazabilidad
- Los checkpoints garantizan validación incremental
- Las pruebas de propiedades (Hypothesis) validan las 10 propiedades universales de corrección definidas en el diseño
- Las pruebas unitarias (pytest) validan ejemplos concretos, casos límite y condiciones de error
- Las gramáticas tree-sitter deben instalarse antes de ejecutar cualquier test: `pip install tree-sitter tree-sitter-php tree-sitter-javascript tree-sitter-typescript tree-sitter-python tree-sitter-ruby tree-sitter-go tree-sitter-rust tree-sitter-java tree-sitter-c-sharp`
- La cobertura mínima esperada es: 100% en `DevGhost_Parser.analyze()` y `Output_Serializer.serialize()`, ≥ 85% en cada subsistema

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1"] },
    { "id": 1, "tasks": ["2.1", "4.1", "5.1", "7.1"] },
    { "id": 2, "tasks": ["2.2", "2.3", "4.2", "4.3", "5.2", "5.3", "7.2"] },
    { "id": 3, "tasks": ["2.4", "4.4", "5.4", "7.3", "7.4", "8.1"] },
    { "id": 4, "tasks": ["4.5", "4.6", "5.5", "5.6", "5.7", "7.5", "8.2"] },
    { "id": 5, "tasks": ["8.3", "8.4", "8.5", "8.6", "9.1"] },
    { "id": 6, "tasks": ["9.2"] }
  ]
}
```
