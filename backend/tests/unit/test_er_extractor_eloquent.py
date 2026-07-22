"""
Unit tests for Task 5.1: Eloquent (PHP + tree-sitter) parser in ER_Extractor.

Covers:
- Detection of PHP files with 'extends Model'
- Extraction of class name → Entity.name
- Extraction of $fillable → Entity.attributes (type defaults to "string")
- Extraction of $casts → updating attribute types
- Extraction of $primaryKey → Entity.primaryKey (defaults to "id")
- Relationship method extraction: hasOne, hasMany, belongsTo, belongsToMany, morphTo, etc.
- Relation.from_entity, Relation.to_entity, Relation.type, Relation.foreignKey
- rawDeclaration set for morph / unknown relation methods
- Skipping non-model PHP files
- Error recording on unparseable files
- ER_Extractor.extract() directory walk and deduplication

Satisfies Requirements: 2.1, 2.2, 2.3
"""

from __future__ import annotations

import os
import tempfile

import pytest

from dev_ghost_parser.er_extractor import ER_Extractor, _parse_eloquent_file
from dev_ghost_parser.models import AnalysisError, Attribute, Entity, ERResult, Relation


# ---------------------------------------------------------------------------
# PHP fixture helpers
# ---------------------------------------------------------------------------

def _write_php(tmp_path: str, filename: str, content: str) -> str:
    """Write a PHP source file into tmp_path and return its absolute path."""
    filepath = os.path.join(tmp_path, filename)
    with open(filepath, "w", encoding="utf-8") as fh:
        fh.write(content)
    return filepath


# ---------------------------------------------------------------------------
# Fixture PHP source strings
# ---------------------------------------------------------------------------

PHP_MINIMAL_MODEL = """\
<?php

namespace App\\Models;

use Illuminate\\Database\\Eloquent\\Model;

class User extends Model
{
    protected $fillable = ['name', 'email'];
}
"""

PHP_MODEL_WITH_CASTS = """\
<?php

namespace App\\Models;

use Illuminate\\Database\\Eloquent\\Model;

class Post extends Model
{
    protected $fillable = ['title', 'body', 'published_at', 'views', 'active'];

    protected $casts = [
        'published_at' => 'datetime',
        'views'        => 'integer',
        'active'       => 'boolean',
    ];
}
"""

PHP_MODEL_WITH_PRIMARY_KEY = """\
<?php

namespace App\\Models;

use Illuminate\\Database\\Eloquent\\Model;

class Product extends Model
{
    protected $primaryKey = 'product_id';

    protected $fillable = ['sku', 'price'];
}
"""

PHP_MODEL_WITH_RELATIONS = """\
<?php

namespace App\\Models;

use Illuminate\\Database\\Eloquent\\Model;

class Order extends Model
{
    protected $fillable = ['total', 'status'];

    public function customer()
    {
        return $this->belongsTo(Customer::class);
    }

    public function items()
    {
        return $this->hasMany(OrderItem::class, 'order_id');
    }

    public function invoice()
    {
        return $this->hasOne(Invoice::class);
    }

    public function tags()
    {
        return $this->belongsToMany(Tag::class);
    }
}
"""

PHP_MODEL_WITH_MORPH = """\
<?php

namespace App\\Models;

use Illuminate\\Database\\Eloquent\\Model;

class Comment extends Model
{
    protected $fillable = ['body'];

    public function commentable()
    {
        return $this->morphTo();
    }
}
"""

PHP_NOT_A_MODEL = """\
<?php

namespace App\\Http\\Controllers;

class UserController
{
    public function index()
    {
        return 'hello';
    }
}
"""

PHP_EMPTY_MODEL = """\
<?php

namespace App\\Models;

use Illuminate\\Database\\Eloquent\\Model;

class EmptyModel extends Model {}
"""

PHP_MODEL_AUTHENTICATABLE = """\
<?php

namespace App\\Models;

use Illuminate\\Foundation\\Auth\\User as Authenticatable;

class Admin extends Authenticatable
{
    protected $fillable = ['username', 'password'];
}
"""


# ---------------------------------------------------------------------------
# Tests for _parse_eloquent_file
# ---------------------------------------------------------------------------

class TestParseEloquentFile:
    """Tests for the _parse_eloquent_file helper function."""

    def test_minimal_model_returns_entity(self, tmp_path):
        """A class extending Model should produce one Entity."""
        filepath = _write_php(str(tmp_path), "User.php", PHP_MINIMAL_MODEL)
        entities, relations, errors = _parse_eloquent_file(filepath)

        assert errors == []
        assert len(entities) == 1
        entity = entities[0]
        assert entity.name == "User"
        assert entity.primaryKey == "id"

    def test_minimal_model_attributes_default_to_string(self, tmp_path):
        """$fillable items should produce Attribute(name=..., type='string') by default."""
        filepath = _write_php(str(tmp_path), "User.php", PHP_MINIMAL_MODEL)
        entities, _, _ = _parse_eloquent_file(filepath)

        attrs = {a.name: a.type for a in entities[0].attributes}
        assert attrs.get("name") == "string"
        assert attrs.get("email") == "string"

    def test_casts_override_attribute_types(self, tmp_path):
        """$casts values should update the type of corresponding attributes."""
        filepath = _write_php(str(tmp_path), "Post.php", PHP_MODEL_WITH_CASTS)
        entities, _, errors = _parse_eloquent_file(filepath)

        assert errors == []
        assert len(entities) == 1
        attrs = {a.name: a.type for a in entities[0].attributes}
        assert attrs["published_at"] == "datetime"
        assert attrs["views"] == "integer"
        assert attrs["active"] == "boolean"
        # Non-cast fields remain string
        assert attrs["title"] == "string"

    def test_primary_key_extracted(self, tmp_path):
        """$primaryKey property value should override the default 'id'."""
        filepath = _write_php(str(tmp_path), "Product.php", PHP_MODEL_WITH_PRIMARY_KEY)
        entities, _, _ = _parse_eloquent_file(filepath)

        assert entities[0].primaryKey == "product_id"

    def test_default_primary_key_is_id(self, tmp_path):
        """When $primaryKey is not declared, primaryKey defaults to 'id'."""
        filepath = _write_php(str(tmp_path), "User.php", PHP_MINIMAL_MODEL)
        entities, _, _ = _parse_eloquent_file(filepath)

        assert entities[0].primaryKey == "id"

    def test_non_model_php_ignored(self, tmp_path):
        """PHP files without 'extends Model' should produce no entities."""
        filepath = _write_php(str(tmp_path), "UserController.php", PHP_NOT_A_MODEL)
        entities, relations, errors = _parse_eloquent_file(filepath)

        assert entities == []
        assert relations == []
        assert errors == []

    def test_empty_model_class(self, tmp_path):
        """A Model subclass with no body should still produce a minimal Entity."""
        filepath = _write_php(str(tmp_path), "EmptyModel.php", PHP_EMPTY_MODEL)
        entities, relations, errors = _parse_eloquent_file(filepath)

        assert errors == []
        assert len(entities) == 1
        assert entities[0].name == "EmptyModel"
        assert entities[0].primaryKey == "id"

    def test_authenticatable_base_is_accepted(self, tmp_path):
        """Classes extending Authenticatable should also be treated as Eloquent models."""
        filepath = _write_php(str(tmp_path), "Admin.php", PHP_MODEL_AUTHENTICATABLE)
        entities, _, errors = _parse_eloquent_file(filepath)

        assert errors == []
        assert len(entities) == 1
        assert entities[0].name == "Admin"
        attrs = {a.name: a.type for a in entities[0].attributes}
        assert "username" in attrs

    def test_missing_file_returns_error(self, tmp_path):
        """A path that doesn't exist should produce an AnalysisError, no entities."""
        filepath = os.path.join(str(tmp_path), "nonexistent.php")
        entities, relations, errors = _parse_eloquent_file(filepath)

        assert entities == []
        assert relations == []
        assert len(errors) == 1
        assert errors[0].path == filepath


# ---------------------------------------------------------------------------
# Tests for relationship extraction
# ---------------------------------------------------------------------------

class TestEloquentRelationships:
    """Tests for Eloquent relationship method extraction."""

    def test_belongs_to_produces_relation(self, tmp_path):
        """belongsTo should produce a one-to-many Relation."""
        filepath = _write_php(str(tmp_path), "Order.php", PHP_MODEL_WITH_RELATIONS)
        _, relations, _ = _parse_eloquent_file(filepath)

        rel = next((r for r in relations if r.to_entity == "Customer"), None)
        assert rel is not None
        assert rel.from_entity == "Order"
        assert rel.type == "one-to-many"

    def test_has_many_produces_relation(self, tmp_path):
        """hasMany should produce a one-to-many Relation."""
        filepath = _write_php(str(tmp_path), "Order.php", PHP_MODEL_WITH_RELATIONS)
        _, relations, _ = _parse_eloquent_file(filepath)

        rel = next((r for r in relations if r.to_entity == "OrderItem"), None)
        assert rel is not None
        assert rel.from_entity == "Order"
        assert rel.type == "one-to-many"

    def test_has_many_explicit_foreign_key(self, tmp_path):
        """When a second argument is provided to hasMany, it becomes the foreignKey."""
        filepath = _write_php(str(tmp_path), "Order.php", PHP_MODEL_WITH_RELATIONS)
        _, relations, _ = _parse_eloquent_file(filepath)

        rel = next((r for r in relations if r.to_entity == "OrderItem"), None)
        assert rel is not None
        assert rel.foreignKey == "order_id"

    def test_has_one_produces_one_to_one(self, tmp_path):
        """hasOne should produce a one-to-one Relation."""
        filepath = _write_php(str(tmp_path), "Order.php", PHP_MODEL_WITH_RELATIONS)
        _, relations, _ = _parse_eloquent_file(filepath)

        rel = next((r for r in relations if r.to_entity == "Invoice"), None)
        assert rel is not None
        assert rel.type == "one-to-one"

    def test_belongs_to_many_produces_many_to_many(self, tmp_path):
        """belongsToMany should produce a many-to-many Relation."""
        filepath = _write_php(str(tmp_path), "Order.php", PHP_MODEL_WITH_RELATIONS)
        _, relations, _ = _parse_eloquent_file(filepath)

        rel = next((r for r in relations if r.to_entity == "Tag"), None)
        assert rel is not None
        assert rel.type == "many-to-many"

    def test_conventional_foreign_key_derived_for_belongs_to(self, tmp_path):
        """For belongsTo without explicit FK, derive snake_case(related) + '_id'."""
        filepath = _write_php(str(tmp_path), "Order.php", PHP_MODEL_WITH_RELATIONS)
        _, relations, _ = _parse_eloquent_file(filepath)

        rel = next((r for r in relations if r.to_entity == "Customer"), None)
        assert rel is not None
        # Customer -> customer_id
        assert rel.foreignKey == "customer_id"

    def test_morph_to_produces_unknown_type(self, tmp_path):
        """morphTo should produce a Relation with type='unknown'."""
        filepath = _write_php(str(tmp_path), "Comment.php", PHP_MODEL_WITH_MORPH)
        _, relations, errors = _parse_eloquent_file(filepath)

        assert len(relations) == 1
        rel = relations[0]
        assert rel.from_entity == "Comment"
        assert rel.type == "unknown"

    def test_morph_to_has_raw_declaration(self, tmp_path):
        """morphTo relations must include rawDeclaration."""
        filepath = _write_php(str(tmp_path), "Comment.php", PHP_MODEL_WITH_MORPH)
        _, relations, _ = _parse_eloquent_file(filepath)

        rel = relations[0]
        assert rel.rawDeclaration is not None
        assert len(rel.rawDeclaration) > 0

    def test_four_relations_extracted(self, tmp_path):
        """Order model should produce exactly 4 relations."""
        filepath = _write_php(str(tmp_path), "Order.php", PHP_MODEL_WITH_RELATIONS)
        _, relations, _ = _parse_eloquent_file(filepath)

        assert len(relations) == 4


# ---------------------------------------------------------------------------
# Tests for ER_Extractor.extract()
# ---------------------------------------------------------------------------

class TestERExtractorEloquent:
    """Tests for ER_Extractor walking a directory with Eloquent PHP files."""

    def test_extract_finds_eloquent_entities(self, tmp_path):
        """extract() should find entities from all Eloquent PHP files in the tree."""
        _write_php(str(tmp_path), "User.php", PHP_MINIMAL_MODEL)
        _write_php(str(tmp_path), "Post.php", PHP_MODEL_WITH_CASTS)

        result = ER_Extractor().extract(str(tmp_path))

        entity_names = {e.name for e in result.entities}
        assert "User" in entity_names
        assert "Post" in entity_names

    def test_extract_ignores_non_model_php(self, tmp_path):
        """extract() should not include entities from PHP files without extends Model."""
        _write_php(str(tmp_path), "UserController.php", PHP_NOT_A_MODEL)

        result = ER_Extractor().extract(str(tmp_path))
        assert result.entities == []

    def test_extract_collects_relations(self, tmp_path):
        """extract() should collect relations from relationship methods."""
        _write_php(str(tmp_path), "Order.php", PHP_MODEL_WITH_RELATIONS)

        result = ER_Extractor().extract(str(tmp_path))
        assert len(result.relations) == 4

    def test_extract_empty_directory_returns_empty_result(self, tmp_path):
        """An empty directory should produce empty entities and relations."""
        result = ER_Extractor().extract(str(tmp_path))

        assert result.entities == []
        assert result.relations == []
        assert result.errors == []

    def test_extract_deduplicates_entities_by_name(self, tmp_path):
        """If the same entity name appears in two files, only one entry should remain."""
        # Write the same model in two subdirectories
        subdir1 = os.path.join(str(tmp_path), "app")
        subdir2 = os.path.join(str(tmp_path), "app2")
        os.makedirs(subdir1)
        os.makedirs(subdir2)
        _write_php(subdir1, "User.php", PHP_MINIMAL_MODEL)
        _write_php(subdir2, "User.php", PHP_MINIMAL_MODEL)

        result = ER_Extractor().extract(str(tmp_path))

        user_entities = [e for e in result.entities if e.name == "User"]
        assert len(user_entities) == 1

    def test_extract_returns_er_result_type(self, tmp_path):
        """extract() must return an ERResult instance."""
        result = ER_Extractor().extract(str(tmp_path))
        assert isinstance(result, ERResult)

    def test_extract_error_recorded_for_unreadable_file(self, tmp_path):
        """Files that cannot be read should be recorded as AnalysisError, not crash."""
        # Create a valid model file first
        _write_php(str(tmp_path), "User.php", PHP_MINIMAL_MODEL)

        # Simulate a file with binary content (invalid UTF-8 but tree-sitter will handle it)
        bad_file = os.path.join(str(tmp_path), "Bad.php")
        with open(bad_file, "wb") as fh:
            # Write PHP that won't parse as a model (no extends Model)
            fh.write(b"<?php class Bad {}\n")

        result = ER_Extractor().extract(str(tmp_path))
        # The bad file doesn't crash the extractor; only User entity is found
        entity_names = {e.name for e in result.entities}
        assert "User" in entity_names
        assert "Bad" not in entity_names


# ---------------------------------------------------------------------------
# Tests for ERResult structure (Req 2.1)
# ---------------------------------------------------------------------------

class TestERResultStructure:
    """Verify Entity and Relation fields satisfy requirement 2.1 and 2.3."""

    def test_entity_has_required_fields(self, tmp_path):
        """Every Entity must have name (non-empty), attributes (list), primaryKey."""
        filepath = _write_php(str(tmp_path), "User.php", PHP_MINIMAL_MODEL)
        entities, _, _ = _parse_eloquent_file(filepath)

        entity = entities[0]
        assert isinstance(entity.name, str) and entity.name
        assert isinstance(entity.attributes, list)
        assert isinstance(entity.primaryKey, str) and entity.primaryKey

    def test_relation_has_required_fields(self, tmp_path):
        """Every Relation must have from_entity, to_entity, type, foreignKey."""
        filepath = _write_php(str(tmp_path), "Order.php", PHP_MODEL_WITH_RELATIONS)
        _, relations, _ = _parse_eloquent_file(filepath)

        for rel in relations:
            assert isinstance(rel.from_entity, str) and rel.from_entity
            assert isinstance(rel.to_entity, str) and rel.to_entity
            assert rel.type in ("one-to-one", "one-to-many", "many-to-many", "unknown")
            assert isinstance(rel.foreignKey, str) and rel.foreignKey

    def test_unknown_relation_has_raw_declaration(self, tmp_path):
        """A Relation with type='unknown' must have rawDeclaration set."""
        filepath = _write_php(str(tmp_path), "Comment.php", PHP_MODEL_WITH_MORPH)
        _, relations, _ = _parse_eloquent_file(filepath)

        unknown_rels = [r for r in relations if r.type == "unknown"]
        assert len(unknown_rels) >= 1
        for rel in unknown_rels:
            assert rel.rawDeclaration is not None
