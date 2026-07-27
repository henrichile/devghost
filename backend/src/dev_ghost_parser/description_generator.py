"""
Description_Generator — Spanish-language description generation for nodes.

Generates concise descriptions in Spanish for architectural nodes.
Primary strategy: use LLM (≤90 characters) when available.
Fallback strategy: heuristic logic (≤120 characters) based on context.

Heuristic Strategy (fallback):
1. If file_context has method names → compose description from inferred purpose.
2. If file_context has imports → infer purpose from imported modules.
3. Fallback → generic description based on NodeType.

Satisfies Requirements 1.1, 1.2, 1.3, 1.4, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .models import FileContext, Node, NodeType

if TYPE_CHECKING:
    from .llm_client import LLM_Client


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MAX_DESCRIPTION_LENGTH = 500

# Generic fallbacks per NodeType (used when no meaningful context is available)
_GENERIC_FALLBACKS: dict[NodeType, str] = {
    "Controller": "Controlador principal del sistema",
    "Service": "Servicio auxiliar del sistema",
    "Route": "Definición de rutas del sistema",
    "Middleware": "Middleware de procesamiento intermedio",
    "Repository": "Repositorio de acceso a datos",
    "Utility": "Utilidad auxiliar del proyecto",
    "Config": "Configuración del sistema",
}

# Spanish prefixes per NodeType for method-based descriptions
_TYPE_PREFIXES: dict[NodeType, str] = {
    "Controller": "Controlador que gestiona",
    "Service": "Servicio que provee",
    "Route": "Rutas que definen",
    "Middleware": "Middleware que procesa",
    "Repository": "Repositorio que administra",
    "Utility": "Utilidad que ofrece",
    "Config": "Configuración que define",
}

# Import keyword → domain inference (Spanish)
_IMPORT_DOMAIN_MAP: dict[str, str] = {
    "auth": "autenticación",
    "login": "autenticación",
    "jwt": "autenticación con tokens",
    "oauth": "autenticación OAuth",
    "session": "manejo de sesiones",
    "database": "acceso a base de datos",
    "db": "acceso a base de datos",
    "sql": "consultas SQL",
    "mongo": "base de datos MongoDB",
    "redis": "caché con Redis",
    "cache": "gestión de caché",
    "http": "comunicación HTTP",
    "request": "manejo de peticiones",
    "response": "generación de respuestas",
    "express": "servidor web Express",
    "fastapi": "servidor web FastAPI",
    "flask": "servidor web Flask",
    "django": "framework Django",
    "email": "envío de correos",
    "mail": "envío de correos",
    "log": "registro de eventos",
    "logger": "registro de eventos",
    "logging": "registro de eventos",
    "file": "manejo de archivos",
    "fs": "sistema de archivos",
    "path": "manejo de rutas de archivos",
    "crypto": "operaciones criptográficas",
    "encrypt": "cifrado de datos",
    "hash": "funciones de hash",
    "validation": "validación de datos",
    "validator": "validación de datos",
    "test": "pruebas automatizadas",
    "queue": "procesamiento de colas",
    "event": "manejo de eventos",
    "socket": "comunicación por sockets",
    "websocket": "comunicación WebSocket",
    "payment": "procesamiento de pagos",
    "stripe": "pagos con Stripe",
    "upload": "carga de archivos",
    "image": "procesamiento de imágenes",
    "pdf": "generación de PDF",
    "csv": "procesamiento de CSV",
    "json": "serialización JSON",
    "xml": "procesamiento XML",
    "config": "configuración del sistema",
    "env": "variables de entorno",
    "middleware": "procesamiento intermedio",
    "router": "enrutamiento de peticiones",
    "route": "definición de rutas",
    "model": "modelado de datos",
    "schema": "esquemas de datos",
    "migration": "migraciones de base de datos",
    "seed": "datos semilla",
    "user": "gestión de usuarios",
    "admin": "administración del sistema",
    "notification": "envío de notificaciones",
    "schedule": "tareas programadas",
    "cron": "tareas programadas",
}

# Method keyword → purpose inference (Spanish)
_METHOD_PURPOSE_MAP: dict[str, str] = {
    "get": "consulta",
    "find": "búsqueda",
    "search": "búsqueda",
    "list": "listado",
    "fetch": "obtención",
    "create": "creación",
    "add": "creación",
    "insert": "inserción",
    "save": "almacenamiento",
    "store": "almacenamiento",
    "update": "actualización",
    "edit": "edición",
    "modify": "modificación",
    "delete": "eliminación",
    "remove": "eliminación",
    "destroy": "eliminación",
    "login": "autenticación",
    "logout": "cierre de sesión",
    "authenticate": "autenticación",
    "authorize": "autorización",
    "validate": "validación",
    "verify": "verificación",
    "check": "verificación",
    "send": "envío",
    "notify": "notificación",
    "upload": "carga de archivos",
    "download": "descarga de archivos",
    "export": "exportación",
    "import": "importación",
    "parse": "análisis sintáctico",
    "transform": "transformación",
    "convert": "conversión",
    "format": "formateo",
    "render": "renderizado",
    "process": "procesamiento",
    "handle": "manejo",
    "execute": "ejecución",
    "run": "ejecución",
    "init": "inicialización",
    "setup": "configuración",
    "configure": "configuración",
    "connect": "conexión",
    "disconnect": "desconexión",
    "subscribe": "suscripción",
    "publish": "publicación",
    "log": "registro",
    "track": "seguimiento",
    "count": "conteo",
    "calculate": "cálculo",
    "filter": "filtrado",
    "sort": "ordenamiento",
    "paginate": "paginación",
    "index": "indexación",
}


# ---------------------------------------------------------------------------
# Description_Generator
# ---------------------------------------------------------------------------


class Description_Generator:
    """Generates Spanish descriptions for architectural nodes.

    Primary strategy: LLM-based (≤90 chars) when LLM_Client is available.
    Fallback strategy: heuristic (≤120 chars) based on file context:
    1. Method names → infer purpose from method keywords.
    2. Imports → infer domain from imported module names.
    3. Config-specific → infer domain from node label.
    4. Fallback → generic description based on NodeType.
    """

    def __init__(self, llm_client: LLM_Client | None = None) -> None:
        """Initialize Description_Generator with optional LLM client.

        Parameters
        ----------
        llm_client : LLM_Client | None
            Optional LLM client for AI-powered descriptions.
            When None, only heuristic logic is used (backward compatible).
        """
        self._llm_client = llm_client

    def generate(self, node: Node, file_context: FileContext | None) -> str:
        """Return a Spanish description for the given node.

        Attempts LLM generation first (if available), then falls back
        to heuristic logic.

        Parameters
        ----------
        node : Node
            The node to describe (has id, label, type).
        file_context : FileContext | None
            Optional context including imports, class_name, method_names.
            When None, a generic type-based fallback is used.

        Returns
        -------
        str
            A Spanish description, never empty.
        """
        # Try LLM first
        if self._llm_client and self._llm_client.available:
            llm_description = self._from_llm(node, file_context)
            if llm_description:
                return llm_description

        # Fallback to heuristics (existing logic unchanged)
        return self._heuristic_generate(node, file_context)

    def _from_llm(self, node: Node, file_context: FileContext | None) -> str | None:
        """Attempt to generate a description using the LLM.

        Builds a prompt with the node's label, type, and method names (up to 10).
        Returns the LLM response if valid (≥5 chars), otherwise None.
        """
        # Get method names from file_context or node
        method_names: list[str] = []
        if file_context and file_context.method_names:
            method_names = file_context.method_names
        elif node.method_names:
            method_names = node.method_names

        methods_str = ", ".join(method_names[:10]) if method_names else "ninguno"

        # Include imports for richer context
        imports_str = ""
        if file_context and file_context.imports:
            imports_str = f"\nImports: {', '.join(file_context.imports[:8])}"

        user_prompt = (
            f"Componente: {node.label}\n"
            f"Tipo arquitectónico: {node.type}\n"
            f"Métodos públicos: {methods_str}"
            f"{imports_str}"
        )
        system_prompt = (
            "Eres un arquitecto de software senior. "
            "Genera una descripción técnica precisa y completa en español "
            "que explique el PROPÓSITO ESPECÍFICO de este componente dentro del sistema. "
            "Incluye: qué dominio de negocio maneja, qué operaciones principales realiza, "
            "y cómo se relaciona con el patrón arquitectónico (MVC, Clean Architecture, etc). "
            "NO uses frases genéricas como 'gestiona operaciones CRUD'. "
            "Sé específico basándote en los nombres de métodos e imports. "
            "Solo responde con la descripción, sin comillas."
        )
        result = self._llm_client.complete(system_prompt, user_prompt)
        if result and len(result.strip()) >= 5:
            return self._truncate_llm(result.strip())
        return None

    def _truncate_llm(self, description: str) -> str:
        """Return LLM description without truncation."""
        return description

    def _heuristic_generate(self, node: Node, file_context: FileContext | None) -> str:
        """Generate description using heuristic logic (original behavior).

        Parameters
        ----------
        node : Node
            The node to describe (has id, label, type).
        file_context : FileContext | None
            Optional context including imports, class_name, method_names.
            When None, a generic type-based fallback is used.

        Returns
        -------
        str
            A Spanish description of ≤120 characters, never empty.
        """
        description = ""

        if file_context is not None:
            # Strategy 1: Method-based description (PURPOSE_MAP match)
            if file_context.method_names:
                description = self._from_methods(node, file_context.method_names)

            # Strategy 1b: Method-based description (no PURPOSE_MAP match, list methods directly)
            if not description and file_context.method_names:
                description = self._from_methods_no_match(node, file_context.method_names)

            # Strategy 2: Import-based description
            if not description and file_context.imports:
                description = self._from_imports(node, file_context.imports)

        # Strategy 3: Config-specific description with domain inference from label
        if not description and node.type == "Config":
            description = self._config_description(node)

        # Strategy 4: Generic type fallback
        if not description:
            description = self._generic_fallback(node.type)

        # Enforce ≤120 character limit
        return self._truncate(description)

    def _from_methods(self, node: Node, method_names: list[str]) -> str:
        """Compose a description from method names by inferring purpose."""
        purposes: list[str] = []
        seen: set[str] = set()

        for method in method_names:
            # Normalize: strip underscores, convert camelCase
            normalized = self._normalize_method_name(method)
            for keyword, purpose in _METHOD_PURPOSE_MAP.items():
                if keyword in normalized and purpose not in seen:
                    purposes.append(purpose)
                    seen.add(purpose)
                    break

        if not purposes:
            return ""

        prefix = _TYPE_PREFIXES.get(node.type, "Componente que gestiona")

        # Limit to 3 purposes to keep description concise
        limited_purposes = purposes[:3]
        purpose_text = ", ".join(limited_purposes)

        return f"{prefix} {purpose_text}"

    def _from_methods_no_match(self, node: Node, method_names: list[str]) -> str:
        """Lista hasta 3 métodos directamente cuando no hay match en PURPOSE_MAP."""
        prefix = _TYPE_PREFIXES.get(node.type, "Componente que gestiona")
        limited = method_names[:3]
        if len(limited) == 1:
            return f"{prefix} {limited[0]}"
        elif len(limited) == 2:
            return f"{prefix} {limited[0]} y {limited[1]}"
        else:
            return f"{prefix} {limited[0]}, {limited[1]} y {limited[2]}"

    def _from_imports(self, node: Node, imports: list[str]) -> str:
        """Infer description from imported modules."""
        domains: list[str] = []
        seen: set[str] = set()

        for imp in imports:
            # Get the last segment of the import path
            segments = imp.replace("\\", "/").replace("::", "/").replace(".", "/").split("/")
            for segment in segments:
                segment_lower = segment.lower()
                for keyword, domain in _IMPORT_DOMAIN_MAP.items():
                    if keyword in segment_lower and domain not in seen:
                        domains.append(domain)
                        seen.add(domain)
                        break

        if not domains:
            return ""

        prefix = _TYPE_PREFIXES.get(node.type, "Componente relacionado con")

        # Limit to 2 domains to keep description concise
        limited_domains = domains[:2]
        domain_text = " y ".join(limited_domains)

        return f"{prefix} {domain_text}"

    def _generic_fallback(self, node_type: NodeType) -> str:
        """Return a generic fallback description based on node type."""
        return _GENERIC_FALLBACKS.get(node_type, "Utilidad auxiliar del proyecto")

    def _config_description(self, node: Node) -> str:
        """Generate a description for Config nodes by inferring domain from label.

        When the node label contains a recognizable domain substring,
        returns a domain-specific configuration description.
        Otherwise returns the generic Config fallback.
        """
        label_lower = node.label.lower()

        # Domain map: keyword in label → Spanish domain name
        domain_map: dict[str, str] = {
            "database": "base de datos",
            "redis": "Redis",
            "auth": "autenticación",
            "mail": "correo electrónico",
            "email": "correo electrónico",
            "cache": "caché",
            "cors": "CORS",
            "swagger": "Swagger",
            "logging": "registro de eventos",
            "queue": "colas de mensajes",
            "session": "sesiones",
            "security": "seguridad",
            "aws": "AWS",
            "firebase": "Firebase",
            "payment": "pagos",
            "storage": "almacenamiento",
        }

        for key, domain in domain_map.items():
            if key in label_lower:
                return f"Configuración de {domain}"

        return "Configuración del sistema"

    def _truncate(self, description: str) -> str:
        """Return description without truncation."""
        return description

    @staticmethod
    def _normalize_method_name(name: str) -> str:
        """Normalize a method name: strip prefixes and convert to lowercase.

        Handles: snake_case, camelCase, and common prefixes like _ or __.
        """
        # Strip leading underscores
        stripped = name.lstrip("_")
        if not stripped:
            return name.lower()

        # Insert spaces before uppercase letters (camelCase → camel case)
        result: list[str] = []
        for i, ch in enumerate(stripped):
            if ch.isupper() and i > 0:
                result.append(" ")
            result.append(ch.lower())

        return "".join(result)
