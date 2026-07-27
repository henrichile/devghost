"""
Unit tests for Description_Generator.

Tests the heuristic strategy:
1. Method-based description
2. Import-based description
3. Generic type fallback
4. Truncation at ≤120 characters
5. Non-empty result guarantee
"""

import pytest

from dev_ghost_parser.description_generator import Description_Generator
from dev_ghost_parser.models import FileContext, Node


@pytest.fixture
def generator():
    return Description_Generator()


# ---------------------------------------------------------------------------
# Generic fallbacks per NodeType
# ---------------------------------------------------------------------------


class TestGenericFallbacks:
    """Test that generic fallbacks are returned for each NodeType."""

    def test_controller_fallback(self, generator):
        node = Node(id="abc123", label="AppController", type="Controller")
        result = generator.generate(node, None)
        assert result == "Controlador principal del sistema"

    def test_service_fallback(self, generator):
        node = Node(id="abc123", label="AppService", type="Service")
        result = generator.generate(node, None)
        assert result == "Servicio auxiliar del sistema"

    def test_route_fallback(self, generator):
        node = Node(id="abc123", label="AppRoute", type="Route")
        result = generator.generate(node, None)
        assert result == "Definición de rutas del sistema"

    def test_middleware_fallback(self, generator):
        node = Node(id="abc123", label="AppMiddleware", type="Middleware")
        result = generator.generate(node, None)
        assert result == "Middleware de procesamiento intermedio"

    def test_repository_fallback(self, generator):
        node = Node(id="abc123", label="AppRepository", type="Repository")
        result = generator.generate(node, None)
        assert result == "Repositorio de acceso a datos"

    def test_utility_fallback(self, generator):
        node = Node(id="abc123", label="Utils", type="Utility")
        result = generator.generate(node, None)
        assert result == "Utilidad auxiliar del proyecto"


# ---------------------------------------------------------------------------
# Method-based descriptions
# ---------------------------------------------------------------------------


class TestMethodBasedDescription:
    """Test description generation from method names."""

    def test_controller_with_crud_methods(self, generator):
        node = Node(id="abc123", label="UserController", type="Controller")
        ctx = FileContext(
            imports=[], class_name="UserController",
            method_names=["getUsers", "createUser", "deleteUser"]
        )
        result = generator.generate(node, ctx)
        assert "Controlador que gestiona" in result
        assert "consulta" in result
        assert "creación" in result
        assert "eliminación" in result

    def test_service_with_auth_methods(self, generator):
        node = Node(id="abc123", label="AuthService", type="Service")
        ctx = FileContext(
            imports=[], class_name="AuthService",
            method_names=["login", "logout", "validateToken"]
        )
        result = generator.generate(node, ctx)
        assert "Servicio que provee" in result
        assert "autenticación" in result

    def test_methods_take_priority_over_imports(self, generator):
        node = Node(id="abc123", label="OrderService", type="Service")
        ctx = FileContext(
            imports=["database", "redis"],
            class_name="OrderService",
            method_names=["createOrder", "updateOrder"]
        )
        result = generator.generate(node, ctx)
        # Methods should be used since they exist
        assert "Servicio que provee" in result
        assert "creación" in result

    def test_empty_method_names_falls_through(self, generator):
        node = Node(id="abc123", label="MyService", type="Service")
        ctx = FileContext(
            imports=["database"],
            class_name="MyService",
            method_names=[]
        )
        result = generator.generate(node, ctx)
        # Should fall through to import-based
        assert "base de datos" in result

    def test_unrecognized_methods_listed_directly(self, generator):
        node = Node(id="abc123", label="MyService", type="Service")
        ctx = FileContext(
            imports=["redis"],
            class_name="MyService",
            method_names=["foo", "bar", "baz"]
        )
        result = generator.generate(node, ctx)
        # No recognized methods → _from_methods_no_match lists methods directly
        assert "Servicio que provee" in result
        assert "foo" in result
        assert "bar" in result
        assert "baz" in result


# ---------------------------------------------------------------------------
# Import-based descriptions
# ---------------------------------------------------------------------------


class TestImportBasedDescription:
    """Test description generation from imports."""

    def test_database_imports(self, generator):
        node = Node(id="abc123", label="DataRepo", type="Repository")
        ctx = FileContext(
            imports=["sqlalchemy", "database.connection"],
            class_name="DataRepo",
            method_names=[]
        )
        result = generator.generate(node, ctx)
        assert "Repositorio que administra" in result

    def test_http_imports(self, generator):
        node = Node(id="abc123", label="ApiController", type="Controller")
        ctx = FileContext(
            imports=["express", "http"],
            class_name="ApiController",
            method_names=[]
        )
        result = generator.generate(node, ctx)
        assert "Controlador que gestiona" in result

    def test_no_matching_imports_falls_to_generic(self, generator):
        node = Node(id="abc123", label="MyUtil", type="Utility")
        ctx = FileContext(
            imports=["some_random_thing", "another_unknown"],
            class_name="MyUtil",
            method_names=[]
        )
        result = generator.generate(node, ctx)
        assert result == "Utilidad auxiliar del proyecto"


# ---------------------------------------------------------------------------
# Truncation and invariants
# ---------------------------------------------------------------------------


class TestTruncation:
    """Test the ≤120 character constraint."""

    def test_short_description_not_truncated(self, generator):
        node = Node(id="abc123", label="UserController", type="Controller")
        result = generator.generate(node, None)
        assert len(result) <= 120

    def test_long_description_truncated(self, generator):
        # Create a scenario with many recognized methods to generate a long description
        node = Node(id="abc123", label="MegaController", type="Controller")
        ctx = FileContext(
            imports=[],
            class_name="MegaController",
            method_names=[
                "getAllUsers", "createNewUser", "updateExistingUser",
                "deleteOldUser", "searchUsers", "filterResults",
                "sortResults", "paginateResults", "exportData",
                "importData", "validateInput", "transformOutput"
            ]
        )
        result = generator.generate(node, ctx)
        assert len(result) <= 120

    def test_result_always_non_empty(self, generator):
        node = Node(id="abc123", label="", type="Utility")
        ctx = FileContext(imports=[], class_name=None, method_names=[])
        result = generator.generate(node, ctx)
        assert len(result) > 0

    def test_result_is_string(self, generator):
        node = Node(id="abc123", label="Test", type="Controller")
        result = generator.generate(node, None)
        assert isinstance(result, str)
