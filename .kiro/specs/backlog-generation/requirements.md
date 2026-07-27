# Requirements Document

## Introduction

Este documento define los requisitos para la generación automática de un Product Backlog en DevGhost Parser. El sistema derivará épicas y historias de usuario priorizadas a partir de la estructura de código detectada durante el análisis estático (controladores, rutas, servicios, repositorios y lógica de negocio), produciendo documentación en español que incluye estimación de story points, niveles de prioridad y criterios de aceptación. El artefacto sigue el mismo patrón de integración que los artefactos existentes (C4, ADR, RBAC, Testing, Casos de Uso).

## Glossary

- **Generador_Backlog**: Módulo dentro de `Artifacts_Generator` responsable de producir el artefacto de Product Backlog.
- **Code_Flow**: Resultado del análisis AST que contiene nodos (Controller, Service, Route, Middleware, Repository, Utility) con sus métodos detectados y edges que representan relaciones entre ellos.
- **Épica**: Agrupación de alto nivel de funcionalidades relacionadas derivada de un controlador, dominio funcional o módulo del sistema analizado.
- **Historia_de_Usuario_Backlog**: Elemento del backlog en formato "Como [rol], quiero [acción], para [beneficio]" que incluye story points, prioridad y criterios de aceptación.
- **Story_Points**: Estimación relativa de esfuerzo asignada a cada historia de usuario, expresada en la escala Fibonacci (1, 2, 3, 5, 8, 13).
- **Prioridad**: Nivel de importancia asignado a cada historia de usuario (Alta, Media, Baja) derivado de la centralidad del componente en el grafo de dependencias.
- **Artefacto_Backlog**: Campo `backlog` dentro de la respuesta `artifacts` del análisis, que contiene el documento Markdown generado.
- **LLM_Client**: Cliente de API compatible con OpenAI utilizado para generar contenido textual mediante prompts.
- **DocumentationPanel**: Componente React del frontend que renderiza artefactos de documentación en pestañas dentro del tab Architecture.

## Requirements

### Requisito 1: Generación de Historias de Usuario para el Backlog

**User Story:** Como product owner, quiero obtener historias de usuario priorizadas derivadas automáticamente del código analizado, para disponer de un backlog inicial sin esfuerzo manual de descubrimiento.

#### Criterios de Aceptación

1. WHEN el análisis detecta nodos de tipo Controller o Route con métodos, THE Generador_Backlog SHALL generar una Historia_de_Usuario_Backlog por cada funcionalidad significativa detectada en formato "Como [rol], quiero [acción], para [beneficio]".
2. THE Generador_Backlog SHALL derivar el rol del actor a partir del contexto del controlador y el middleware de autenticación asociado.
3. THE Generador_Backlog SHALL derivar la acción a partir del nombre del método, su verbo HTTP implícito y su contexto funcional.
4. THE Generador_Backlog SHALL incluir criterios de aceptación específicos para cada historia de usuario, derivados de las validaciones y lógica de negocio detectadas.
5. WHEN un controlador no tiene métodos detectados, THE Generador_Backlog SHALL omitir ese controlador de la generación de historias.
6. THE Generador_Backlog SHALL generar todas las historias de usuario en idioma español.

### Requisito 2: Agrupación en Épicas

**User Story:** Como product owner, quiero que las historias de usuario estén agrupadas en épicas coherentes, para entender la estructura funcional del sistema a alto nivel.

#### Criterios de Aceptación

1. THE Generador_Backlog SHALL agrupar las historias de usuario en épicas derivadas de los controladores o dominios funcionales detectados.
2. THE Generador_Backlog SHALL asignar un nombre descriptivo a cada épica que refleje el dominio funcional que cubre.
3. THE Generador_Backlog SHALL incluir una descripción breve del alcance de cada épica.
4. WHEN existen nodos de tipo Service invocados por múltiples controladores, THE Generador_Backlog SHALL considerar esos servicios como indicadores de dominio transversal al agrupar épicas.
5. THE Generador_Backlog SHALL generar un mínimo de una épica y un máximo proporcional al número de controladores detectados.

### Requisito 3: Estimación de Story Points y Prioridad

**User Story:** Como scrum master, quiero que cada historia de usuario tenga una estimación de story points y nivel de prioridad, para facilitar la planificación de sprints.

#### Criterios de Aceptación

1. THE Generador_Backlog SHALL asignar Story_Points a cada historia de usuario utilizando la escala Fibonacci (1, 2, 3, 5, 8, 13).
2. THE Generador_Backlog SHALL derivar la estimación de story points a partir de la complejidad inferida del método (número de dependencias, servicios invocados y flujos alternativos detectados).
3. THE Generador_Backlog SHALL asignar un nivel de Prioridad (Alta, Media, Baja) a cada historia de usuario.
4. THE Generador_Backlog SHALL derivar la prioridad a partir de la centralidad del componente en el grafo de dependencias del Code_Flow (componentes con más dependencias entrantes reciben prioridad más alta).
5. THE Generador_Backlog SHALL incluir la estimación de story points y la prioridad de forma visible en el formato de salida de cada historia.

### Requisito 4: Formato de Salida Markdown

**User Story:** Como desarrollador, quiero que el backlog generado esté en formato Markdown estructurado, para poder integrarlo directamente en herramientas de gestión de proyectos.

#### Criterios de Aceptación

1. THE Generador_Backlog SHALL producir un documento Markdown único que contenga un resumen del backlog, seguido de las épicas con sus historias de usuario.
2. THE Generador_Backlog SHALL estructurar el documento con encabezados Markdown jerárquicos (## para secciones principales, ### para épicas, #### para historias de usuario).
3. THE Generador_Backlog SHALL incluir para cada historia de usuario: identificador (HU-XXX), título, descripción en formato historia de usuario, story points, prioridad y criterios de aceptación.
4. THE Generador_Backlog SHALL incluir una tabla resumen al inicio del documento con el total de épicas, historias, y distribución de story points por prioridad.
5. WHEN el análisis Code_Flow no contiene nodos de tipo Controller ni Route, THE Generador_Backlog SHALL retornar un valor nulo en lugar de generar un documento vacío.

### Requisito 5: Integración en el Backend

**User Story:** Como desarrollador del sistema, quiero que el artefacto de backlog se integre en el pipeline de generación existente, para mantener consistencia con los demás artefactos.

#### Criterios de Aceptación

1. THE Generador_Backlog SHALL implementarse como un nuevo método `generate_backlog` dentro de la clase `Artifacts_Generator`.
2. THE Generador_Backlog SHALL recibir el resultado del Code_Flow como parámetro de entrada.
3. WHEN el LLM_Client no está disponible o su propiedad `available` es falsa, THE Generador_Backlog SHALL retornar un valor nulo.
4. THE Artefacto_Backlog SHALL incluirse en la respuesta del análisis bajo la clave `artifacts.backlog`.
5. THE Artefacto_Backlog SHALL generarse durante el pipeline de análisis del endpoint `/analyze-stream` emitiendo eventos SSE de progreso.
6. THE Generador_Backlog SHALL utilizar el LLM_Client para generar el contenido del artefacto a partir de los datos estructurales del Code_Flow.

### Requisito 6: Integración en el Frontend

**User Story:** Como usuario del dashboard, quiero visualizar el backlog generado en una nueva pestaña dentro de Architecture, para consultarlo junto con los demás artefactos de documentación.

#### Criterios de Aceptación

1. THE DocumentationPanel SHALL incluir una nueva sub-pestaña denominada "Backlog" con el ícono 📋.
2. WHEN el campo `artifacts.backlog` contiene contenido, THE DocumentationPanel SHALL renderizar el Markdown del artefacto utilizando el componente `MarkdownRenderer` existente.
3. WHEN el campo `artifacts.backlog` es nulo o está ausente, THE DocumentationPanel SHALL mostrar un mensaje indicando que el artefacto no pudo ser generado.
4. THE DocumentationPanel SHALL permitir copiar y descargar el contenido del artefacto de backlog con los botones existentes de "Copiar" y "Descargar".
5. THE interfaz de tipos `ArtifactsResponse` SHALL extenderse con un campo `backlog` de tipo `string | null`.

### Requisito 7: Calidad y Relevancia del Contenido Generado

**User Story:** Como usuario, quiero que el backlog generado sea coherente, específico al proyecto analizado y útil como punto de partida real, para evitar contenido genérico sin valor.

#### Criterios de Aceptación

1. THE Generador_Backlog SHALL producir historias de usuario que sean específicas al contexto del código analizado y no genéricas.
2. THE Generador_Backlog SHALL producir criterios de aceptación verificables y concretos para cada historia de usuario.
3. THE Generador_Backlog SHALL vincular cada historia de usuario con la épica correspondiente mediante el identificador de la épica.
4. IF el LLM_Client retorna una respuesta vacía o nula, THEN THE Generador_Backlog SHALL retornar un valor nulo en lugar de un documento malformado.
5. THE Generador_Backlog SHALL incluir en el prompt del LLM información sobre los métodos del controlador, los servicios invocados, los repositorios asociados y el middleware detectado para maximizar la relevancia del contenido generado.
6. THE Generador_Backlog SHALL ordenar las historias dentro de cada épica por prioridad descendente (Alta primero, Baja al final).
