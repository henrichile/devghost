# Feature: dev-ghost-parser, Property 2: Los nodos generados contienen los campos requeridos
"""
Property 2: Los nodos generados contienen los campos requeridos

Validates: Requisito 1.2

Para todo archivo fuente identificado como entidad arquitectónica, el nodo generado
debe contener un `id` no vacío, un `label` no vacío, y un `type` cuyo valor pertenece
al conjunto {Controller, Service, Route, Middleware, Repository, Utility}.
"""

import os
import tempfile

from hypothesis import given, settings
from hypothesis import strategies as st

from dev_ghost_parser.code_flow_analyzer import Code_Flow_Analyzer

RECOGNIZED_EXTENSIONS = [".php", ".js", ".ts", ".py", ".rb", ".go", ".rs", ".java", ".cs"]
VALID_TYPES = {"Controller", "Service", "Route", "Middleware", "Repository", "Utility"}


@given(
    filename=st.text(
        alphabet=st.characters(
            whitelist_categories=("Lu", "Ll", "Nd"),
            whitelist_characters="_",
        ),
        min_size=1,
        max_size=30,
    ).filter(lambda s: s[0].isalpha()),
    extension=st.sampled_from(RECOGNIZED_EXTENSIONS),
    content=st.binary(max_size=200),
)
@settings(max_examples=100)
def test_property_2_node_required_fields(filename, extension, content):
    """
    **Validates: Requisito 1.2**

    For every file with a recognized extension placed in a temporary directory,
    Code_Flow_Analyzer.analyze() must produce a Node with:
      - id: non-empty string
      - label: non-empty string
      - type: one of {Controller, Service, Route, Middleware, Repository, Utility}

    Tree-sitter may fail to parse arbitrary binary content, but the analyzer
    must still produce a valid node using the filename-based fallback label.
    """
    with tempfile.TemporaryDirectory() as tmp:
        filepath = os.path.join(tmp, filename + extension)
        with open(filepath, "wb") as f:
            f.write(content)

        result = Code_Flow_Analyzer().analyze(tmp)

        # The file has a recognized extension, so exactly one node must be produced.
        assert len(result.nodes) == 1, (
            f"Expected 1 node for file '{filename + extension}', "
            f"got {len(result.nodes)}"
        )

        for node in result.nodes:
            # id must be a non-empty string
            assert isinstance(node.id, str), f"node.id is not a str: {node.id!r}"
            assert node.id != "", f"node.id is empty for file '{filename + extension}'"

            # label must be a non-empty string
            assert isinstance(node.label, str), f"node.label is not a str: {node.label!r}"
            assert node.label != "", (
                f"node.label is empty for file '{filename + extension}'"
            )

            # type must be one of the valid architectural categories
            assert node.type in VALID_TYPES, (
                f"node.type '{node.type}' is not in {VALID_TYPES} "
                f"for file '{filename + extension}'"
            )
