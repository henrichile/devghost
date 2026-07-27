# Documento de Requisitos

## Introducción

Este documento define los requisitos para la generación automática de Historias de Usuario (User Stories) y Casos de Uso (Use Cases) en DevGhost Parser. El sistema derivará estos artefactos a partir de la estructura de código detectada durante el análisis estático (controladores, rutas, servicios y lógica de negocio), produciendo documentación en español que sigue formatos estándar de ingeniería de software.

## Glosario

- **Generador_Casos_Uso**: Módulo dentro de `Artifacts_Generator` responsable de producir el artefacto combinado de Historias de Usuario y Casos de Uso.
- **Code_Flow**: Resultado del análisis AST que contiene nodos (Controller, Service, Route, Middleware, Repository, Utility) con sus métodos detectados.
- **Historia_de_Usuario**: Descripción breve en formato "Como [rol], quiero [acción], para [beneficio]" que representa una necesidad funcional derivada de un método de controlador o ruta.
- **Caso_de_Uso**: Descripción formal estilo UML que agrupa historias de usuario relacionadas e incluye actores, precondiciones, postcondiciones, flujo principal y flujos alternativos.
- **Artefacto_UseCases**: Campo `useCases` dentro de la respuesta `artifacts` del análisis, que contiene el documento Markdown generado.
- **LLM_Client**: Cliente de API compatible con OpenAI utilizado para generar contenido textual mediante prompts.
- **DocumentationPanel**: Componente React del frontend que renderiza artefactos de documentación en pestañas dentro del tab Architecture.

## Requisitos

### Requisito 1: Generación de Historias de Usuario

**User Story:** Como desarrollador, quiero obtener historias de usuario derivadas automáticamente de los controladores y rutas detectados, para entender las funcionalidades del sistema sin documentación manual.

#### Criterios de Aceptación

1. WHEN el análisis detecta nodos de tipo Controller o Route con métodos, THE Generador_Casos_Uso SHALL generar una Historia_de_Usuario por cada método público detectado en formato "Como [rol], quiero [acción], para [beneficio]".
2. THE Generador_Casos_Uso SHALL derivar el rol del actor a partir del contexto del controlador (autenticación, administración, usuario público).
3. THE Generador_Casos_Uso SHALL derivar la acción a partir del nombre del método y su contexto dentro del controlador.
4. THE Generador_Casos_Uso SHALL derivar el beneficio a partir de la lógica de negocio asociada al método.
5. WHEN un controlador no tiene métodos detectados, THE Generador_Casos_Uso SHALL omitir ese controlador de la generación de historias.
6. THE Generador_Casos_Uso SHALL generar todas las historias de usuario en idioma español.

### Requisito 2: Generación de Casos de Uso Formales

**User Story:** Como arquitecto de software, quiero obtener casos de uso formales estilo UML agrupando funcionalidades relacionadas, para documentar los flujos del sistema de manera estructurada.

#### Criterios de Aceptación

1. THE Generador_Casos_Uso SHALL generar casos de uso formales que agrupen historias de usuario relacionadas por controlador o dominio funcional.
2. THE Generador_Casos_Uso SHALL incluir para cada caso de uso: nombre, actores, precondiciones, postcondiciones, flujo principal (pasos numerados) y flujos alternativos.
3. WHEN existen nodos de tipo Middleware asociados a un controlador, THE Generador_Casos_Uso SHALL incluir las validaciones del middleware como precondiciones del caso de uso correspondiente.
4. WHEN existen nodos de tipo Service invocados por un controlador, THE Generador_Casos_Uso SHALL reflejar las llamadas a servicios como pasos del flujo principal.
5. THE Generador_Casos_Uso SHALL identificar flujos alternativos a partir de validaciones, manejo de errores y condiciones detectadas en la lógica de negocio.
6. THE Generador_Casos_Uso SHALL generar todos los casos de uso en idioma español.

### Requisito 3: Producción del Artefacto Combinado

**User Story:** Como desarrollador, quiero que las historias de usuario y casos de uso se generen como un único artefacto de documentación, para tener toda la información funcional consolidada.

#### Criterios de Aceptación

1. THE Generador_Casos_Uso SHALL producir un documento Markdown único que contenga una sección de Historias de Usuario seguida de una sección de Casos de Uso.
2. THE Generador_Casos_Uso SHALL estructurar el documento con encabezados Markdown jerárquicos (## para secciones principales, ### para cada historia o caso de uso).
3. WHEN el análisis Code_Flow no contiene nodos de tipo Controller ni Route, THE Generador_Casos_Uso SHALL retornar un valor nulo en lugar de generar un documento vacío.
4. THE Generador_Casos_Uso SHALL utilizar el LLM_Client para generar el contenido del artefacto a partir de los datos estructurales del Code_Flow.

### Requisito 4: Integración en el Backend

**User Story:** Como desarrollador del sistema, quiero que el artefacto de casos de uso se integre en el pipeline de generación existente, para mantener consistencia con los demás artefactos.

#### Criterios de Aceptación

1. THE Generador_Casos_Uso SHALL implementarse como un nuevo método `generate_use_cases` dentro de la clase `Artifacts_Generator`.
2. THE Generador_Casos_Uso SHALL recibir el resultado del Code_Flow como parámetro de entrada.
3. WHEN el LLM_Client no está disponible o su propiedad `available` es falsa, THE Generador_Casos_Uso SHALL retornar un valor nulo.
4. THE Artefacto_UseCases SHALL incluirse en la respuesta del análisis bajo la clave `artifacts.useCases`.
5. THE Artefacto_UseCases SHALL generarse durante el pipeline de análisis del endpoint `/analyze-stream` emitiendo eventos SSE de progreso.

### Requisito 5: Integración en el Frontend

**User Story:** Como usuario del dashboard, quiero visualizar las historias de usuario y casos de uso generados en la pestaña de Architecture, para consultarlos junto con los demás artefactos de documentación.

#### Criterios de Aceptación

1. THE DocumentationPanel SHALL incluir una nueva sub-pestaña denominada "Casos de Uso" con un ícono representativo.
2. WHEN el campo `artifacts.useCases` contiene contenido, THE DocumentationPanel SHALL renderizar el Markdown del artefacto utilizando el componente `MarkdownRenderer` existente.
3. WHEN el campo `artifacts.useCases` es nulo o está ausente, THE DocumentationPanel SHALL mostrar un mensaje indicando que el artefacto no pudo ser generado.
4. THE DocumentationPanel SHALL permitir copiar y descargar el contenido del artefacto de casos de uso con los botones existentes de "Copiar" y "Descargar".
5. THE interfaz de tipos `ArtifactsResponse` SHALL extenderse con un campo opcional `useCases` de tipo `string | null`.

### Requisito 6: Calidad y Estructura del Contenido Generado

**User Story:** Como usuario, quiero que el contenido generado sea coherente, bien estructurado y útil, para poder utilizarlo como base de documentación real del proyecto.

#### Criterios de Aceptación

1. THE Generador_Casos_Uso SHALL producir historias de usuario que sean específicas al contexto del código analizado y no genéricas.
2. THE Generador_Casos_Uso SHALL producir casos de uso con flujos principales de entre 3 y 10 pasos numerados.
3. THE Generador_Casos_Uso SHALL vincular cada caso de uso con las historias de usuario que agrupa, referenciándolas por identificador.
4. IF el LLM_Client retorna una respuesta vacía o nula, THEN THE Generador_Casos_Uso SHALL retornar un valor nulo en lugar de un documento malformado.
5. THE Generador_Casos_Uso SHALL incluir en el prompt del LLM información sobre los métodos del controlador, los servicios invocados y el middleware asociado para maximizar la relevancia del contenido generado.
