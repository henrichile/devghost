# Feature: dev-ghost-parser, Property 3: Unicidad de entidades ER
"""
Property 3: Unicidad de entidades ER

Validates: Requisito 2.5

Para todo código base que contiene definiciones de modelos, el array `entities`
en la salida no debe contener dos entidades con el mismo `name`.
"""

import os
import tempfile

from hypothesis import given, settings
from hypothesis import strategies as st

from dev_ghost_parser.er_extractor import ER_Extractor
from dev_ghost_parser.models import Entity


# ---------------------------------------------------------------------------
# Test 1: Deduplication logic directly
# ---------------------------------------------------------------------------

@given(
    entity_names=st.lists(
        st.text(
            min_size=1,
            max_size=50,
            alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
        ),
        min_size=1,
        max_size=30,
    )
)
@settings(max_examples=100)
def test_property_3_no_duplicate_entity_names(entity_names):
    """
    **Validates: Requirements 2.5**

    Simulate the deduplication logic from ER_Extractor: given a list of entity
    names (possibly with duplicates), the deduplicated result must have all
    unique names.
    """
    # Simulate the same deduplication logic used in ER_Extractor.extract()
    seen = set()
    deduplicated = []
    for name in entity_names:
        if name not in seen:
            seen.add(name)
            deduplicated.append(Entity(name=name))

    # Verify uniqueness
    result_names = [e.name for e in deduplicated]
    assert len(result_names) == len(set(result_names)), (
        f"Duplicate entity names found after deduplication: {result_names}"
    )


# ---------------------------------------------------------------------------
# Test 2: ER_Extractor.extract() with duplicate model files
# ---------------------------------------------------------------------------

@given(
    model_names=st.lists(
        st.text(
            min_size=1,
            max_size=30,
            alphabet=st.characters(whitelist_categories=("Lu", "Ll")),
        ).filter(lambda s: s[0].isupper()),
        min_size=2,
        max_size=10,
    )
)
@settings(max_examples=100)
def test_property_3_extractor_deduplicates_prisma_models(model_names):
    """
    **Validates: Requirements 2.5**

    Create multiple Prisma schema files with potentially duplicate model names
    across different subdirectories. ER_Extractor.extract() must produce entities
    with unique names regardless of how many files define the same model.
    """
    with tempfile.TemporaryDirectory() as tmp:
        # Create multiple subdirectories each with a schema.prisma containing
        # the same model names, ensuring duplicates exist across sources
        for i, name in enumerate(model_names):
            subdir = os.path.join(tmp, f"sub{i}")
            os.makedirs(subdir, exist_ok=True)

            # Generate a minimal Prisma schema with this model name
            schema_content = (
                f"model {name} {{\n"
                f"  id Int @id\n"
                f"  name String\n"
                f"}}\n"
            )
            schema_path = os.path.join(subdir, "schema.prisma")
            with open(schema_path, "w", encoding="utf-8") as f:
                f.write(schema_content)

        # Run the extractor
        result = ER_Extractor().extract(tmp)

        # Verify: no duplicate entity names in the result
        entity_names_result = [e.name for e in result.entities]
        assert len(entity_names_result) == len(set(entity_names_result)), (
            f"ER_Extractor produced duplicate entity names: {entity_names_result}"
        )
