# Feature: dev-ghost-parser, Property 4: Estructura completa de entidades ER
"""
Property 4: Estructura completa de entidades ER

Validates: Requisito 2.1

Para toda entidad extraída, el objeto debe contener un campo `name` no vacío,
un array `attributes` (posiblemente vacío), y un campo `primaryKey`.
"""

import os
import tempfile

from hypothesis import given, settings
from hypothesis import strategies as st

from dev_ghost_parser.er_extractor import ER_Extractor
from dev_ghost_parser.models import Attribute, Entity

# --- Strategies ---

attribute_strategy = st.builds(
    Attribute,
    name=st.text(min_size=1, max_size=20, alphabet=st.characters(categories=("L", "N", "P"))),
    type=st.text(min_size=1, max_size=20, alphabet=st.characters(categories=("L", "N", "P"))),
)


@given(
    name=st.text(min_size=1, max_size=50, alphabet=st.characters(categories=("L", "N"))),
    attrs=st.lists(attribute_strategy, max_size=10),
    pk=st.text(min_size=1, max_size=20, alphabet=st.characters(categories=("L", "N"))),
)
@settings(max_examples=100)
def test_property_4_entity_has_required_fields(name, attrs, pk):
    """
    **Validates: Requirements 2.1**

    Every Entity object must contain a non-empty `name`, an `attributes` array,
    and a `primaryKey` field. This test constructs entities directly and verifies
    the structural invariant holds.
    """
    entity = Entity(name=name, attributes=attrs, primaryKey=pk)

    # name must be non-empty
    assert entity.name != "", "Entity name must not be empty"
    assert len(entity.name) > 0

    # attributes must be a list
    assert isinstance(entity.attributes, list), "Entity attributes must be a list"

    # primaryKey must exist and be non-empty
    assert hasattr(entity, "primaryKey"), "Entity must have a primaryKey field"
    assert entity.primaryKey != "", "Entity primaryKey must not be empty"


@given(
    name=st.text(min_size=1, max_size=50, alphabet=st.characters(categories=("L", "N"))),
    attrs=st.lists(attribute_strategy, min_size=0, max_size=15),
)
@settings(max_examples=100)
def test_property_4_entity_default_primary_key(name, attrs):
    """
    **Validates: Requirements 2.1**

    When no primaryKey is provided to an Entity, the default value "id" should
    still satisfy the completeness requirement (non-empty primaryKey).
    """
    entity = Entity(name=name, attributes=attrs)

    assert entity.name != "", "Entity name must not be empty"
    assert isinstance(entity.attributes, list), "Entity attributes must be a list"
    assert entity.primaryKey != "", "Entity primaryKey must not be empty (default is 'id')"
    assert entity.primaryKey == "id", "Default primaryKey should be 'id'"


@given(
    model_names=st.lists(
        st.text(min_size=3, max_size=30, alphabet=st.characters(categories=("Lu",))),
        min_size=1,
        max_size=5,
    ),
    columns_per_model=st.lists(
        st.lists(
            st.text(min_size=2, max_size=15, alphabet=st.characters(categories=("Ll",))),
            min_size=1,
            max_size=6,
        ),
        min_size=1,
        max_size=5,
    ),
)
@settings(max_examples=50)
def test_property_4_entity_structure_from_prisma_parsing(model_names, columns_per_model):
    """
    **Validates: Requirements 2.1**

    Generate random Prisma schema files with model definitions, run ER_Extractor,
    and verify that all extracted entities have complete structure (non-empty name,
    attributes array, and primaryKey field).
    """
    # Build a Prisma schema string with the generated models
    schema_lines = []
    for i, model_name in enumerate(model_names):
        cols = columns_per_model[i % len(columns_per_model)]
        schema_lines.append(f"model {model_name} {{")
        schema_lines.append(f"  id Int @id @default(autoincrement())")
        for col in cols:
            schema_lines.append(f"  {col} String")
        schema_lines.append("}")
        schema_lines.append("")

    schema_content = "\n".join(schema_lines)

    with tempfile.TemporaryDirectory() as tmpdir:
        schema_path = os.path.join(tmpdir, "schema.prisma")
        with open(schema_path, "w", encoding="utf-8") as f:
            f.write(schema_content)

        extractor = ER_Extractor()
        result = extractor.extract(tmpdir)

        # Every entity produced must satisfy the structural invariant
        for entity in result.entities:
            assert entity.name != "", (
                f"Entity name must not be empty. Got entity: {entity}"
            )
            assert isinstance(entity.attributes, list), (
                f"Entity attributes must be a list. Got: {type(entity.attributes)} for entity '{entity.name}'"
            )
            assert hasattr(entity, "primaryKey"), (
                f"Entity must have a primaryKey field. Entity: '{entity.name}'"
            )
            assert entity.primaryKey is not None, (
                f"Entity primaryKey must not be None. Entity: '{entity.name}'"
            )


@given(
    class_names=st.lists(
        st.text(min_size=3, max_size=20, alphabet=st.characters(categories=("Lu",))),
        min_size=1,
        max_size=4,
    ),
    column_names=st.lists(
        st.lists(
            st.text(min_size=2, max_size=12, alphabet=st.characters(categories=("Ll",))),
            min_size=1,
            max_size=5,
        ),
        min_size=1,
        max_size=4,
    ),
)
@settings(max_examples=50)
def test_property_4_entity_structure_from_sqlalchemy_parsing(class_names, column_names):
    """
    **Validates: Requirements 2.1**

    Generate random SQLAlchemy model files, run ER_Extractor, and verify that all
    extracted entities have complete structure.
    """
    # Build a SQLAlchemy model Python file
    lines = [
        "from sqlalchemy import Column, Integer, String",
        "from sqlalchemy.ext.declarative import declarative_base",
        "",
        "Base = declarative_base()",
        "",
    ]

    for i, class_name in enumerate(class_names):
        cols = column_names[i % len(column_names)]
        lines.append(f"class {class_name}(Base):")
        lines.append(f"    __tablename__ = '{class_name.lower()}'")
        lines.append(f"    id = Column(Integer, primary_key=True)")
        for col in cols:
            lines.append(f"    {col} = Column(String)")
        lines.append("")

    file_content = "\n".join(lines)

    with tempfile.TemporaryDirectory() as tmpdir:
        model_path = os.path.join(tmpdir, "models.py")
        with open(model_path, "w", encoding="utf-8") as f:
            f.write(file_content)

        extractor = ER_Extractor()
        result = extractor.extract(tmpdir)

        # Every entity produced must satisfy the structural invariant
        for entity in result.entities:
            assert entity.name != "", (
                f"Entity name must not be empty. Got entity: {entity}"
            )
            assert isinstance(entity.attributes, list), (
                f"Entity attributes must be a list. Got: {type(entity.attributes)} for entity '{entity.name}'"
            )
            assert hasattr(entity, "primaryKey"), (
                f"Entity must have a primaryKey field. Entity: '{entity.name}'"
            )
            assert entity.primaryKey is not None, (
                f"Entity primaryKey must not be None. Entity: '{entity.name}'"
            )


@given(
    table_names=st.lists(
        st.from_regex(r"[a-z]{3,15}", fullmatch=True),
        min_size=1,
        max_size=4,
    ),
    col_defs=st.lists(
        st.lists(
            st.tuples(
                st.from_regex(r"[a-z]{2,10}", fullmatch=True),
                st.sampled_from(["INT", "VARCHAR(255)", "TEXT", "BOOLEAN", "DATETIME"]),
            ),
            min_size=1,
            max_size=5,
        ),
        min_size=1,
        max_size=4,
    ),
)
@settings(max_examples=50)
def test_property_4_entity_structure_from_sql_parsing(table_names, col_defs):
    """
    **Validates: Requirements 2.1**

    Generate random SQL CREATE TABLE statements, run ER_Extractor, and verify
    that all extracted entities have complete structure.
    """
    sql_lines = []
    for i, table_name in enumerate(table_names):
        columns = col_defs[i % len(col_defs)]
        col_stmts = [f"  id INT PRIMARY KEY"]
        for col_name, col_type in columns:
            col_stmts.append(f"  {col_name} {col_type}")
        sql_lines.append(f"CREATE TABLE {table_name} (")
        sql_lines.append(",\n".join(col_stmts))
        sql_lines.append(");")
        sql_lines.append("")

    sql_content = "\n".join(sql_lines)

    with tempfile.TemporaryDirectory() as tmpdir:
        sql_path = os.path.join(tmpdir, "schema.sql")
        with open(sql_path, "w", encoding="utf-8") as f:
            f.write(sql_content)

        extractor = ER_Extractor()
        result = extractor.extract(tmpdir)

        # Every entity produced must satisfy the structural invariant
        for entity in result.entities:
            assert entity.name != "", (
                f"Entity name must not be empty. Got entity: {entity}"
            )
            assert isinstance(entity.attributes, list), (
                f"Entity attributes must be a list. Got: {type(entity.attributes)} for entity '{entity.name}'"
            )
            assert hasattr(entity, "primaryKey"), (
                f"Entity must have a primaryKey field. Entity: '{entity.name}'"
            )
            assert entity.primaryKey is not None, (
                f"Entity primaryKey must not be None. Entity: '{entity.name}'"
            )
