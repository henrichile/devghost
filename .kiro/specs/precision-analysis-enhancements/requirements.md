# Requirements Document

## Introduction

Este documento especifica los requisitos para mejorar la precisión, calidad y riqueza de la información extraída por DevGhost-Parser. Las mejoras abarcan tres áreas: clasificación correcta de nodos arquitectónicos, extracción de métodos reales desde el AST para generar descripciones contextuales, y generación de resúmenes globales con inferencia de dominio de negocio. El objetivo es eliminar descripciones genéricas e imprecisas y producir información fiel a la naturaleza real de cada archivo analizado.

## Glossary

- **Code_Flow_Analyzer**: Componente backend responsable de recorrer el directorio del proyecto, clasificar archivos fuente en tipos arquitectónicos (NodeType) y generar nodos y aristas del grafo de flujo.
- **Description_Generator**: Componente backend que genera descripciones en español (≤120 caracteres) para cada nodo, basándose en contexto extraído del archivo (métodos, imports, tipo).
- **Summary_Generator**: Componente backend que produce un resumen ejecutivo de 3-4 oraciones en texto plano describiendo la arquitectura y propósito del proyecto analizado.
- **FileContext**: Modelo de datos que contiene información extraída de un archivo fuente (imports, class_name, method_names) utilizada para la generación de descripciones.
- **InspectionPanel**: Componente frontend (React) que muestra los detalles de un nodo seleccionado en el grafo, incluyendo tipo, descripción, dependencias y tablas relacionadas.
- **NodeType**: Tipo literal que categoriza un nodo arquitectónico. Valores válidos: "Controller", "Service", "Route", "Middleware", "Repository", "Utility", "Config".
- **AST**: Árbol de Sintaxis Abstracta generado por tree-sitter para analizar el código fuente de forma estructural.
- **Tree_Sitter**: Librería de parsing incremental utilizada para extraer nombres de clases, métodos e imports de archivos fuente.
- **Config**: Nuevo valor de NodeType para archivos de configuración, conexión a base de datos o inicialización del sistema.

## Requirements

### Requirement 1: Clasificación Precisa de Archivos de Configuración

**User Story:** Como desarrollador que visualiza la arquitectura, quiero que los archivos de configuración y conexión a BD se clasifiquen como "Config" o "Utility", para que el grafo represente fielmente la naturaleza de cada componente.

#### Acceptance Criteria

1. WHEN el Code_Flow_Analyzer clasifica un archivo cuyo nombre (filename stem o class_name, comparación case-insensitive de subcadena) contiene los patrones "Config", "Configuration", "Connection", "Database", "AppConfig", "DBConfig" o "Settings", THE Code_Flow_Analyzer SHALL asignar el NodeType "Config" a dicho nodo.
2. WHEN el Code_Flow_Analyzer clasifica un archivo cuyo nombre (filename stem o class_name, comparación case-insensitive de subcadena) contiene los patrones "Init", "Bootstrap", "Setup" o "Startup", THE Code_Flow_Analyzer SHALL asignar el NodeType "Utility" a dicho nodo.
3. THE Code_Flow_Analyzer SHALL evaluar las reglas de clasificación de configuración e inicialización antes de evaluar las reglas de clasificación de "Route", para evitar que archivos de configuración se clasifiquen como rutas.
4. WHEN el Code_Flow_Analyzer clasifica un archivo y el nombre coincide con un patrón de configuración, THE Code_Flow_Analyzer SHALL priorizar la clasificación "Config" sobre cualquier otra clasificación excepto "Controller".
5. WHEN un nombre coincide tanto con un patrón de configuración como con un patrón de inicialización ("Setup", "Init"), THE Code_Flow_Analyzer SHALL asignar "Config" si la subcadena de configuración aparece en el nombre, priorizando "Config" sobre "Utility".

### Requirement 2: Extracción de Métodos Exportados desde el AST

**User Story:** Como desarrollador, quiero que el sistema extraiga los nombres reales de las funciones y métodos principales de cada archivo, para que las descripciones reflejen las capacidades reales del código.

#### Acceptance Criteria

1. WHEN el Code_Flow_Analyzer procesa un archivo fuente cuya extensión pertenece al conjunto de gramáticas soportadas por tree-sitter y el parser se inicializa correctamente, THE Code_Flow_Analyzer SHALL extraer los nombres de todas las funciones y métodos definidos en el archivo mediante recorrido depth-first del AST y almacenarlos en el campo method_names del FileContext asociado, en el orden en que aparecen en el código fuente.
2. WHEN el archivo fuente contiene una clase con métodos, THE Code_Flow_Analyzer SHALL excluir del campo method_names los métodos que cumplan alguna de las siguientes condiciones: en Python, nombres que comiencen con doble guion bajo (incluyendo dunder methods como __init__); en Java, TypeScript y C#, métodos con modificador de acceso private o protected.
3. WHEN el archivo fuente tiene una extensión no incluida en el mapa de gramáticas soportadas o WHEN el parser de tree-sitter lanza una excepción durante el análisis del archivo, THE Code_Flow_Analyzer SHALL asignar una lista vacía al campo method_names del FileContext asociado sin registrar un error fatal.
4. THE Code_Flow_Analyzer SHALL limitar la extracción a un máximo de 15 métodos por archivo, seleccionando los primeros 15 según su orden de aparición en el código fuente y descartando el resto.
5. WHEN el archivo fuente está escrito en Go, Rust o Ruby (lenguajes sin modificador explícito de visibilidad basado en keywords), THE Code_Flow_Analyzer SHALL extraer todas las funciones y métodos definidos en el archivo sin aplicar filtrado por visibilidad.

### Requirement 3: Generación de Descripciones Basadas en Métodos Reales

**User Story:** Como desarrollador, quiero que las descripciones de cada nodo reflejen las operaciones reales que implementa el archivo, para obtener una comprensión inmediata de su funcionalidad sin abrir el código.

#### Acceptance Criteria

1. WHEN el FileContext contiene method_names con al menos un método cuyo nombre normalizado coincide con una palabra clave del _METHOD_PURPOSE_MAP, THE Description_Generator SHALL construir la descripción concatenando el prefijo correspondiente al NodeType con hasta 3 propósitos inferidos separados por comas (por ejemplo: "Controlador que gestiona autenticación, búsqueda, creación").
2. WHEN el FileContext contiene method_names pero ningún nombre normalizado coincide con alguna palabra clave del _METHOD_PURPOSE_MAP, THE Description_Generator SHALL construir la descripción listando los nombres de hasta 3 métodos directamente con el formato "[Prefijo según NodeType] [método1], [método2] y [método3]".
3. WHEN el NodeType del nodo es "Config", THE Description_Generator SHALL utilizar la plantilla de fallback "Configuración del sistema" y cuando el label del nodo contiene subcadenas reconocibles (como "database", "redis", "auth"), SHALL generar "Configuración de [dominio inferido del label]".
4. THE Description_Generator SHALL producir descripciones de un máximo de 120 caracteres Unicode, truncando a 117 caracteres seguidos de "..." si la descripción generada excede el límite.
5. WHEN el FileContext contiene method_names con al menos un método reconocido en el _METHOD_PURPOSE_MAP, THE Description_Generator SHALL incluir en la descripción generada al menos uno de los valores de propósito mapeados desde los métodos detectados, en lugar de utilizar exclusivamente el texto de fallback genérico del NodeType.
6. IF el FileContext es None o contiene method_names vacío e imports vacío, THEN THE Description_Generator SHALL retornar la descripción genérica de fallback correspondiente al NodeType del nodo, garantizando que la descripción resultante nunca sea una cadena vacía.

### Requirement 4: Exposición de Métodos Clave en la API

**User Story:** Como consumidor de la API, quiero que el endpoint de análisis retorne la lista de métodos principales de cada nodo, para poder mostrarlos en la interfaz.

#### Acceptance Criteria

1. WHEN el servidor retorna el resultado de análisis, THE Output_Serializer SHALL incluir un campo "methods" de tipo array de strings en cada objeto nodo del arreglo codeFlow.nodes, conteniendo la lista de nombres de métodos extraídos en el mismo orden en que fueron detectados en el código fuente.
2. WHEN el FileContext de un nodo tiene method_names vacío, THE Output_Serializer SHALL serializar el campo "methods" como un arreglo JSON vacío ([]).
3. THE Output_Serializer SHALL limitar el campo "methods" a un máximo de 10 elementos por nodo en la respuesta JSON, seleccionando los primeros 10 según el orden de declaración en el código fuente y descartando el resto.

### Requirement 5: Visualización de Métodos en el Panel de Inspección

**User Story:** Como usuario de la interfaz, quiero ver una sección "Métodos / Funciones clave" en el panel de inspección, para conocer rápidamente las capacidades de un componente seleccionado.

#### Acceptance Criteria

1. WHEN el usuario selecciona un nodo en el grafo y el nodo tiene al menos un elemento en su campo "methods" (array de strings), THE InspectionPanel SHALL mostrar una sección titulada "Métodos / Funciones clave" que liste los nombres de los métodos, mostrando un máximo de 20 elementos.
2. WHEN el nodo seleccionado tiene un campo "methods" vacío (array de longitud 0) o ausente (undefined), THE InspectionPanel SHALL ocultar la sección "Métodos / Funciones clave" completamente, sin renderizar encabezado ni contenedor vacío.
3. THE InspectionPanel SHALL renderizar cada método como un elemento de lista con el carácter indicador de función "ƒ" seguido de un espacio y el nombre del método, truncando nombres que excedan 40 caracteres a los primeros 37 caracteres seguidos de "...".
4. THE InspectionPanel SHALL mostrar la sección "Métodos / Funciones clave" entre la sección de descripción del nodo y la sección de dependencias.
5. IF el nodo tiene más de 20 métodos en su campo "methods", THEN THE InspectionPanel SHALL mostrar los primeros 20 métodos y un indicador textual al final informando la cantidad de métodos adicionales no mostrados.

### Requirement 6: Inferencia de Dominio de Negocio en el Resumen Global

**User Story:** Como usuario que escucha el audio tour, quiero que el resumen final nombre explícitamente el propósito de negocio del proyecto, para comprender inmediatamente a qué se dedica el sistema.

#### Acceptance Criteria

1. WHEN el Summary_Generator construye la oración de propósito del sistema, THE Summary_Generator SHALL comparar cada nombre de entidad del modelo ER y cada label de nodo contra el mapa de palabras clave de dominio utilizando coincidencia case-insensitive de subcadena (el nombre de la entidad contiene la palabra clave o la palabra clave contiene el nombre de la entidad).
2. WHEN al menos 1 entidad o label coincide con una entrada del mapa de palabras clave de dominio, THE Summary_Generator SHALL reemplazar la oración genérica de propósito por una oración con el formato "El sistema esta diseñado para [propósito del dominio con mayor cantidad de coincidencias]".
3. IF múltiples dominios obtienen la misma cantidad de coincidencias, THEN THE Summary_Generator SHALL seleccionar el dominio cuya primera coincidencia aparece primero en el orden de entidades del modelo ER.
4. IF ninguna entidad ni label coincide con alguna entrada del mapa de palabras clave de dominio, THEN THE Summary_Generator SHALL mantener la oración genérica de propósito existente sin modificación.
5. THE Summary_Generator SHALL utilizar un mapa de palabras clave de dominio con al menos 15 entradas que asocie nombres de entidades comunes con propósitos de negocio en español (por ejemplo: {"Asistencia": "control de asistencia", "Producto": "gestión de inventario", "Factura": "facturación", "Usuario": "gestión de usuarios", "Orden": "gestión de pedidos"}).
6. THE Summary_Generator SHALL mantener el límite de 500 code points Unicode y 4 oraciones máximas en el resumen generado, incluso con la oración de dominio inferido.

### Requirement 7: Nuevo Valor "Config" en NodeType

**User Story:** Como desarrollador del sistema, quiero que exista un NodeType "Config" formal, para representar de forma explícita archivos de configuración en el grafo y la interfaz.

#### Acceptance Criteria

1. THE NodeType SHALL incluir el valor "Config" como categoría válida adicional a los valores existentes ("Controller", "Service", "Route", "Middleware", "Repository", "Utility") tanto en la definición backend (Literal de Python) como en la definición frontend (union type de TypeScript).
2. WHEN el frontend recibe un nodo con type "Config", THE CodeFlowGraph SHALL renderizar el nodo con un color de fondo exclusivo asignado en `getNodeStyle` que no coincida con ninguno de los colores existentes de otros NodeType, un icono representativo distinto de los demás tipos, y una etiqueta de tipo "CONFIG" en mayúsculas.
3. WHEN el InspectionPanel muestra un nodo de tipo "Config", THE InspectionPanel SHALL mostrar la etiqueta de tipo como "Config" dentro de un badge cuyo color de fondo sea el mismo asignado por `getNodeStyle` para el tipo "Config".
4. THE Output_Serializer SHALL aceptar y serializar correctamente nodos con NodeType "Config" sin errores de validación, incluyendo el valor "Config" en el campo "type" del JSON de salida.
5. WHEN el CodeFlowGraph renderiza la barra de filtros por tipo, IF existen nodos de tipo "Config" en los datos, THEN THE CodeFlowGraph SHALL mostrar un botón de filtro para "Config" con su color correspondiente, permitiendo filtrar nodos de dicho tipo.
