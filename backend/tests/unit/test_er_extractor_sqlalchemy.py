"""
Unit tests for Task 5.3: SQLAlchemy (Python + tree-sitter) parser in ER_Extractor.

Covers:
- Detection of Python files with declarative_base / Base / db.Model
- Extraction of class name → Entity.name
- Extraction of __tablename__ → overrides Entity.name
- Extraction of Column(...) → Entity.attributes with type mapping
- Extraction of primary_key=True → Entity.primaryKey
- Extraction of relationship(...) → Relation
- Extraction of ForeignKey(...) → Relation
- Relation type inference: uselist=False → one-to-one, secondary → many-to-many
- Skipping non-SQLAlchemy Python files
- Empty directory returns empty result

Satisfies Requirements: 2.1, 2.2, 2.3
"""

from __future__ import annotations

import os

import pytest

from dev_ghost_parser.er_extractor import ER_Extractor, _parse_sqlalchemy_file
from dev_ghost_parser.models import AnalysisError, Attribute, Entity, ERResult, Relation


# ---------------------------------------------------------------------------
# Python fixture helpers
# ---------------------------------------------------------------------------

def _write_py(tmp_path: str, filename: str, content: str) -> str:
    """Write a Python source file into tmp_path and return its absolute path."""
    filepath = os.path.join(tmp_path, filename)
    with open(filepath, "w", encoding="utf-8") as fh:
        fh.write(content)
    return filepath


# ---------------------------------------------------------------------------
# Fixture Python source strings
# ---------------------------------------------------------------------------

PY_MINIMAL_MODEL = """\
from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True)
    name = Column(String)
    email = Column(String)
"""

PY_MODEL_NO_TABLENAME = """\
from sqlalchemy import Column, Integer, String, Boolean
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class Product(Base):
    id = Column(Integer, primary_key=True)
    sku = Column(String)
    active = Column(Boolean)
    price = Column(Float)
"""

PY_MODEL_WITH_RELATIONSHIPS = """\
from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class Order(Base):
    __tablename__ = 'orders'

    id = Column(Integer, primary_key=True)
    total = Column(Float)
    customer_id = Column(Integer, ForeignKey('customers.id'))

    customer = relationship("Customer")
    items = relationship("OrderItem")
    invoice = relationship("Invoice", uselist=False)
"""

PY_MODEL_MANY_TO_MANY = """\
from sqlalchemy import Column, Integer, String, Table, ForeignKey
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class Student(Base):
    __tablename__ = 'students'

    id = Column(Integer, primary_key=True)
    name = Column(String)

    courses = relationship("Course", secondary="student_courses")
"""

PY_MODEL_WITH_VARIOUS_TYPES = """\
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Float
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class Event(Base):
    __tablename__ = 'events'

    id = Column(Integer, primary_key=True)
    title = Column(String)
    description = Column(Text)
    is_active = Column(Boolean)
    start_time = Column(DateTime)
    rating = Column(Float)
"""

PY_NOT_SQLALCHEMY = """\
class MyService:
    def __init__(self):
        self.data = []

    def process(self, item):
        self.data.append(item)
        return len(self.data)
"""

PY_DJANGO_MODEL = """\
from django.db import models

class Article(models.Model):
    title = models.CharField(max_length=200)
    body = models.TextField()
"""

PY_CUSTOM_PRIMARY_KEY = """\
from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class Category(Base):
    __tablename__ = 'categories'

    category_id = Column(Integer, primary_key=True)
    name = Column(String)
"""

PY_DB_MODEL = """\
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class Post(db.Model):
    __tablename__ = 'posts'

    id = Column(Integer, primary_key=True)
    title = Column(String)
    body = Column(String)
"""

PY_MULTIPLE_MODELS = """\
from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class Author(Base):
    __tablename__ = 'authors'

    id = Column(Integer, primary_key=True)
    name = Column(String)

    books = relationship("Book")

class Book(Base):
    __tablename__ = 'books'

    id = Column(Integer, primary_key=True)
    title = Column(String)
    author_id = Column(Integer, ForeignKey('authors.id'))
"""


# ---------------------------------------------------------------------------
# Tests for _parse_sqlalchemy_file
# ---------------------------------------------------------------------------

class TestParseSQLAlchemyFile:
    """Tests for the _parse_sqlalchemy_file helper function."""

    def test_minimal_model_returns_entity(self, tmp_path):
        """A class inheriting from Base with Column definitions produces an Entity."""
        filepath = _write_py(str(tmp_path), "models.py", PY_MINIMAL_MODEL)
        entities, relations, errors = _parse_sqlalchemy_file(filepath)

        assert errors == []
        assert len(entities) == 1
        entity = entities[0]
        assert entity.name == "users"  # __tablename__ override
        assert entity.primaryKey == "id"

    def test_tablename_override(self, tmp_path):
        """__tablename__ should be used as Entity.name instead of the class name."""
        filepath = _write_py(str(tmp_path), "models.py", PY_MINIMAL_MODEL)
        entities, _, _ = _parse_sqlalchemy_file(filepath)

        assert entities[0].name == "users"

    def test_no_tablename_uses_class_name(self, tmp_path):
        """Without __tablename__, the class name is used as Entity.name."""
        filepath = _write_py(str(tmp_path), "models.py", PY_MODEL_NO_TABLENAME)
        entities, _, _ = _parse_sqlalchemy_file(filepath)

        assert entities[0].name == "Product"

    def test_column_type_extraction(self, tmp_path):
        """Column type arguments should be mapped to simplified type names."""
        filepath = _write_py(str(tmp_path), "models.py", PY_MINIMAL_MODEL)
        entities, _, _ = _parse_sqlalchemy_file(filepath)

        attrs = {a.name: a.type for a in entities[0].attributes}
        assert attrs["id"] == "integer"
        assert attrs["name"] == "string"
        assert attrs["email"] == "string"

    def test_various_column_types(self, tmp_path):
        """Multiple column types should be correctly mapped."""
        filepath = _write_py(str(tmp_path), "models.py", PY_MODEL_WITH_VARIOUS_TYPES)
        entities, _, _ = _parse_sqlalchemy_file(filepath)

        attrs = {a.name: a.type for a in entities[0].attributes}
        assert attrs["id"] == "integer"
        assert attrs["title"] == "string"
        assert attrs["is_active"] == "boolean"
        assert attrs["start_time"] == "datetime"
        assert attrs["rating"] == "float"

    def test_primary_key_extraction(self, tmp_path):
        """Column with primary_key=True should set Entity.primaryKey."""
        filepath = _write_py(str(tmp_path), "models.py", PY_CUSTOM_PRIMARY_KEY)
        entities, _, _ = _parse_sqlalchemy_file(filepath)

        assert entities[0].primaryKey == "category_id"

    def test_non_sqlalchemy_file_ignored(self, tmp_path):
        """Python files without SQLAlchemy markers should produce no entities."""
        filepath = _write_py(str(tmp_path), "service.py", PY_NOT_SQLALCHEMY)
        entities, relations, errors = _parse_sqlalchemy_file(filepath)

        assert entities == []
        assert relations == []
        assert errors == []

    def test_django_model_ignored(self, tmp_path):
        """Django models should not be detected as SQLAlchemy models."""
        filepath = _write_py(str(tmp_path), "models.py", PY_DJANGO_MODEL)
        entities, relations, errors = _parse_sqlalchemy_file(filepath)

        assert entities == []

    def test_missing_file_returns_error(self, tmp_path):
        """A path that doesn't exist should produce an AnalysisError."""
        filepath = os.path.join(str(tmp_path), "nonexistent.py")
        entities, relations, errors = _parse_sqlalchemy_file(filepath)

        assert entities == []
        assert relations == []
        assert len(errors) == 1
        assert errors[0].path == filepath


# ---------------------------------------------------------------------------
# Tests for relationship extraction
# ---------------------------------------------------------------------------

class TestSQLAlchemyRelationships:
    """Tests for SQLAlchemy relationship extraction."""

    def test_relationship_produces_relation(self, tmp_path):
        """relationship("Model") should produce a Relation."""
        filepath = _write_py(str(tmp_path), "models.py", PY_MODEL_WITH_RELATIONSHIPS)
        _, relations, _ = _parse_sqlalchemy_file(filepath)

        rel = next((r for r in relations if r.to_entity == "Customer"), None)
        assert rel is not None
        assert rel.from_entity == "orders"
        assert rel.type == "one-to-many"

    def test_relationship_uselist_false_is_one_to_one(self, tmp_path):
        """relationship("X", uselist=False) should produce a one-to-one Relation."""
        filepath = _write_py(str(tmp_path), "models.py", PY_MODEL_WITH_RELATIONSHIPS)
        _, relations, _ = _parse_sqlalchemy_file(filepath)

        rel = next((r for r in relations if r.to_entity == "Invoice"), None)
        assert rel is not None
        assert rel.type == "one-to-one"

    def test_relationship_default_is_one_to_many(self, tmp_path):
        """relationship("X") without uselist should default to one-to-many."""
        filepath = _write_py(str(tmp_path), "models.py", PY_MODEL_WITH_RELATIONSHIPS)
        _, relations, _ = _parse_sqlalchemy_file(filepath)

        rel = next((r for r in relations if r.to_entity == "OrderItem"), None)
        assert rel is not None
        assert rel.type == "one-to-many"

    def test_relationship_secondary_is_many_to_many(self, tmp_path):
        """relationship("X", secondary=...) should produce a many-to-many Relation."""
        filepath = _write_py(str(tmp_path), "models.py", PY_MODEL_MANY_TO_MANY)
        _, relations, _ = _parse_sqlalchemy_file(filepath)

        rel = next((r for r in relations if r.to_entity == "Course"), None)
        assert rel is not None
        assert rel.type == "many-to-many"

    def test_foreign_key_produces_relation(self, tmp_path):
        """ForeignKey("table.column") should produce a Relation when no explicit relationship covers it."""
        filepath = _write_py(str(tmp_path), "models.py", PY_MODEL_WITH_RELATIONSHIPS)
        _, relations, _ = _parse_sqlalchemy_file(filepath)

        # The customer_id ForeignKey should be used for the Customer relationship's foreignKey
        rel = next((r for r in relations if r.to_entity == "Customer"), None)
        assert rel is not None
        assert rel.foreignKey == "customer_id"

    def test_multiple_relations_extracted(self, tmp_path):
        """Model with multiple relationships should produce multiple Relations."""
        filepath = _write_py(str(tmp_path), "models.py", PY_MODEL_WITH_RELATIONSHIPS)
        _, relations, _ = _parse_sqlalchemy_file(filepath)

        # Should have at least 3 relationship-based relations
        rel_targets = [r.to_entity for r in relations]
        assert "Customer" in rel_targets
        assert "OrderItem" in rel_targets
        assert "Invoice" in rel_targets


# ---------------------------------------------------------------------------
# Tests for ER_Extractor.extract() with SQLAlchemy files
# ---------------------------------------------------------------------------

class TestERExtractorSQLAlchemy:
    """Tests for ER_Extractor walking a directory with SQLAlchemy Python files."""

    def test_extract_finds_sqlalchemy_entities(self, tmp_path):
        """extract() should find entities from SQLAlchemy Python files."""
        _write_py(str(tmp_path), "models.py", PY_MINIMAL_MODEL)

        result = ER_Extractor().extract(str(tmp_path))

        entity_names = {e.name for e in result.entities}
        assert "users" in entity_names

    def test_extract_multiple_models_in_one_file(self, tmp_path):
        """extract() should find all models defined in a single file."""
        _write_py(str(tmp_path), "models.py", PY_MULTIPLE_MODELS)

        result = ER_Extractor().extract(str(tmp_path))

        entity_names = {e.name for e in result.entities}
        assert "authors" in entity_names
        assert "books" in entity_names

    def test_extract_ignores_non_sqlalchemy_python(self, tmp_path):
        """extract() should not include entities from non-SQLAlchemy Python files."""
        _write_py(str(tmp_path), "service.py", PY_NOT_SQLALCHEMY)

        result = ER_Extractor().extract(str(tmp_path))
        assert result.entities == []

    def test_extract_empty_directory_returns_empty_result(self, tmp_path):
        """An empty directory should produce empty entities and relations."""
        result = ER_Extractor().extract(str(tmp_path))

        assert result.entities == []
        assert result.relations == []
        assert result.errors == []

    def test_extract_deduplicates_entities_by_name(self, tmp_path):
        """If the same entity name appears in two files, only one entry should remain."""
        subdir1 = os.path.join(str(tmp_path), "app")
        subdir2 = os.path.join(str(tmp_path), "app2")
        os.makedirs(subdir1)
        os.makedirs(subdir2)
        _write_py(subdir1, "models.py", PY_MINIMAL_MODEL)
        _write_py(subdir2, "models.py", PY_MINIMAL_MODEL)

        result = ER_Extractor().extract(str(tmp_path))

        user_entities = [e for e in result.entities if e.name == "users"]
        assert len(user_entities) == 1

    def test_extract_collects_relations(self, tmp_path):
        """extract() should collect relations from relationship() calls."""
        _write_py(str(tmp_path), "models.py", PY_MODEL_WITH_RELATIONSHIPS)

        result = ER_Extractor().extract(str(tmp_path))
        assert len(result.relations) > 0

    def test_extract_returns_er_result_type(self, tmp_path):
        """extract() must return an ERResult instance."""
        result = ER_Extractor().extract(str(tmp_path))
        assert isinstance(result, ERResult)
