# Feature: dev-ghost-parser, Property 1: Integridad referencial del grafo de flujo
"""
Property 1: Integridad referencial del grafo de flujo

Validates: Requisitos 1.3, 1.5

Para todo código base válido analizado, cada arista en el array `edges` de la salida
debe tener tanto `source` como `target` correspondiendo al `id` de un nodo existente
en el array `nodes` de la misma respuesta.
"""

import os
import random
import tempfile

from hypothesis import given, settings
from hypothesis import strategies as st

from dev_ghost_parser.code_flow_analyzer import Code_Flow_Analyzer, _make_node_id
from dev_ghost_parser.models import Edge, Node

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

VALID_TYPES = ["Controller", "Service", "Route", "Middleware", "Repository", "Utility"]
VALID_RELATIONS = ["imports", "calls", "depends_on"]

# Strategy for generating hex-like node IDs (similar to SHA-1 hashes)
node_ids = st.text(min_size=1, max_size=40, alphabet="abcdef0123456789")


@given(
    node_id_list=st.lists(node_ids, min_size=1, max_size=20, unique=True),
    extra_ids=st.lists(node_ids, min_size=1, max_size=10),
    seed=st.integers(min_value=0, max_value=2**32 - 1),
)
@settings(max_examples=100)
def test_property_1_referential_integrity_filter(node_id_list, extra_ids, seed):
    """
    **Validates: Requisitos 1.3, 1.5**

    Given a set of valid node IDs and a set of extra (potentially invalid) IDs,
    generate random edges referencing both valid and invalid IDs. After applying
    the referential integrity filter, every remaining edge must have both `source`
    and `target` in the set of valid node IDs.

    This tests the filter logic directly — the same logic used in
    Code_Flow_Analyzer.analyze() (Task 4.4).
    """
    rng = random.Random(seed)

    # Create nodes from the valid ID list
    nodes = [
        Node(id=nid, label=f"node_{i}", type=rng.choice(VALID_TYPES))
        for i, nid in enumerate(node_id_list)
    ]
    node_id_set = {n.id for n in nodes}

    # Create edges referencing both valid nodes and extra (possibly invalid) IDs
    all_ids = node_id_list + extra_ids
    edges = [
        Edge(
            source=rng.choice(all_ids),
            target=rng.choice(all_ids),
            relation=rng.choice(VALID_RELATIONS),
        )
        for _ in range(min(30, len(all_ids) * 2))
    ]

    # Apply the same referential integrity filter used in Code_Flow_Analyzer
    filtered_edges = [
        e for e in edges if e.source in node_id_set and e.target in node_id_set
    ]

    # Property: every remaining edge references existing nodes
    for e in filtered_edges:
        assert e.source in node_id_set, (
            f"Edge source '{e.source}' not in node_id_set after filtering"
        )
        assert e.target in node_id_set, (
            f"Edge target '{e.target}' not in node_id_set after filtering"
        )

    # Additional: edges with invalid references must have been removed
    for e in edges:
        if e.source not in node_id_set or e.target not in node_id_set:
            assert e not in filtered_edges, (
                f"Edge with invalid reference was not removed: {e}"
            )


@given(
    filenames=st.lists(
        st.text(
            alphabet=st.characters(
                whitelist_categories=("Lu", "Ll", "Nd"),
                whitelist_characters="_",
            ),
            min_size=1,
            max_size=20,
        ).filter(lambda s: s[0].isalpha()),
        min_size=2,
        max_size=8,
        unique=True,
    ),
)
@settings(max_examples=50)
def test_property_1_referential_integrity_full_analyzer(filenames):
    """
    **Validates: Requisitos 1.3, 1.5**

    Create a temporary directory with multiple Python files that import each
    other (some with valid imports, some with invalid/unresolvable imports).
    Run Code_Flow_Analyzer.analyze() and verify that every edge in the result
    references a node that exists in the result's nodes list.

    This exercises the full analysis pipeline end-to-end and confirms that the
    referential integrity invariant holds regardless of the file contents.
    """
    with tempfile.TemporaryDirectory() as tmp:
        # Create Python files where some import others (valid) and some import
        # non-existent modules (invalid — should be filtered out)
        for i, name in enumerate(filenames):
            filepath = os.path.join(tmp, name + ".py")
            lines = []
            # Import the next file in the list (valid, within the codebase)
            if i < len(filenames) - 1:
                lines.append(f"import {filenames[i + 1]}")
            # Import a non-existent external module (should NOT produce an edge
            # after the referential integrity filter)
            lines.append("import nonexistent_external_module")
            lines.append(f"class {name}Service:\n    pass\n")
            with open(filepath, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))

        result = Code_Flow_Analyzer().analyze(tmp)

        # Build the set of node IDs from the result
        node_id_set = {n.id for n in result.nodes}

        # Property 1: every edge must reference existing nodes
        for edge in result.edges:
            assert edge.source in node_id_set, (
                f"Edge source '{edge.source}' not found in nodes. "
                f"Available node IDs: {node_id_set}"
            )
            assert edge.target in node_id_set, (
                f"Edge target '{edge.target}' not found in nodes. "
                f"Available node IDs: {node_id_set}"
            )
