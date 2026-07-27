"""
Integration tests for the complete DevGhost-Parser analysis flow.

Tests the end-to-end pipeline: directory traversal → AST parsing → ER extraction →
summary generation → JSON serialization, verifying the final output structure and
content correctness across multiple languages and edge cases.

Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7
"""

from __future__ import annotations

import json
import os
import tempfile

import pytest

from dev_ghost_parser import DevGhost_Parser


# ---------------------------------------------------------------------------
# Fixtures — realistic source file content
# ---------------------------------------------------------------------------

PHP_USER_MODEL = b"""\
<?php

namespace App\\Models;

use Illuminate\\Database\\Eloquent\\Model;

class User extends Model
{
    protected $fillable = [
        'name',
        'email',
        'password',
    ];

    protected $casts = [
        'email_verified_at' => 'datetime',
        'password' => 'string',
    ];

    public function posts()
    {
        return $this->hasMany(Post::class);
    }

    public function profile()
    {
        return $this->hasOne(Profile::class);
    }
}
"""

PHP_POST_MODEL = b"""\
<?php

namespace App\\Models;

use Illuminate\\Database\\Eloquent\\Model;

class Post extends Model
{
    protected $fillable = [
        'title',
        'body',
        'user_id',
    ];

    public function user()
    {
        return $this->belongsTo(User::class);
    }

    public function comments()
    {
        return $this->hasMany(Comment::class);
    }
}
"""

PHP_USER_CONTROLLER = b"""\
<?php

namespace App\\Http\\Controllers;

use App\\Models\\User;

class UserController extends Controller
{
    public function index()
    {
        return User::all();
    }

    public function show($id)
    {
        return User::findOrFail($id);
    }
}
"""

PYTHON_SERVICE = b"""\
class OrderService:
    def __init__(self, repository):
        self.repository = repository

    def create_order(self, user_id: int, items: list) -> dict:
        order = self.repository.save(user_id=user_id, items=items)
        return {"order_id": order.id, "status": "created"}

    def cancel_order(self, order_id: int) -> bool:
        return self.repository.cancel(order_id)
"""

PRISMA_SCHEMA = b"""\
datasource db {
  provider = "postgresql"
  url      = env("DATABASE_URL")
}

generator client {
  provider = "prisma-client-js"
}

model Product {
  id          Int       @id @default(autoincrement())
  name        String
  price       Float
  categoryId  Int
  category    Category  @relation(fields: [categoryId], references: [id])
  orders      OrderItem[]
  createdAt   DateTime  @default(now())
}

model Category {
  id       Int       @id @default(autoincrement())
  name     String
  products Product[]
}

model OrderItem {
  id        Int     @id @default(autoincrement())
  productId Int
  quantity  Int
  product   Product @relation(fields: [productId], references: [id])
}
"""

PYTHON_SQLALCHEMY_MODEL = b"""\
from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()

class Customer(Base):
    __tablename__ = 'customers'

    id = Column(Integer, primary_key=True)
    name = Column(String)
    email = Column(String)
    orders = relationship("Order", back_populates="customer")

class Order(Base):
    __tablename__ = 'orders'

    id = Column(Integer, primary_key=True)
    total = Column(Integer)
    customer_id = Column(Integer, ForeignKey("customers.id"))
    customer = relationship("Customer", back_populates="orders")
"""


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _write_file(base_dir: str, relative_path: str, content: bytes) -> str:
    """Write content to a file within base_dir, creating subdirectories as needed."""
    full_path = os.path.join(base_dir, relative_path.replace("/", os.sep))
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, "wb") as f:
        f.write(content)
    return full_path


def _parse_result(raw: bytes) -> dict:
    """Parse bytes result to dict, asserting it's valid UTF-8 JSON."""
    assert isinstance(raw, bytes)
    return json.loads(raw.decode("utf-8"))


# ---------------------------------------------------------------------------
# Test 1: Full flow with multi-language codebase (PHP + Python + Prisma)
# ---------------------------------------------------------------------------


class TestFullFlowMultiLanguage:
    """Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5, 4.6"""

    def test_output_contains_three_required_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _write_file(tmp, "app/Models/User.php", PHP_USER_MODEL)
            _write_file(tmp, "app/Models/Post.php", PHP_POST_MODEL)
            _write_file(tmp, "app/Http/Controllers/UserController.php", PHP_USER_CONTROLLER)
            _write_file(tmp, "services/order_service.py", PYTHON_SERVICE)
            _write_file(tmp, "prisma/schema.prisma", PRISMA_SCHEMA)

            result = _parse_result(DevGhost_Parser().analyze(tmp))

            assert "codeFlow" in result
            assert "erModel" in result
            assert "summary" in result

    def test_no_errors_key_when_all_succeed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _write_file(tmp, "app/Models/User.php", PHP_USER_MODEL)
            _write_file(tmp, "app/Models/Post.php", PHP_POST_MODEL)
            _write_file(tmp, "services/order_service.py", PYTHON_SERVICE)
            _write_file(tmp, "prisma/schema.prisma", PRISMA_SCHEMA)

            result = _parse_result(DevGhost_Parser().analyze(tmp))

            assert "errors" not in result

    def test_codeflow_has_nodes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _write_file(tmp, "app/Models/User.php", PHP_USER_MODEL)
            _write_file(tmp, "app/Models/Post.php", PHP_POST_MODEL)
            _write_file(tmp, "app/Http/Controllers/UserController.php", PHP_USER_CONTROLLER)
            _write_file(tmp, "services/order_service.py", PYTHON_SERVICE)
            _write_file(tmp, "prisma/schema.prisma", PRISMA_SCHEMA)

            result = _parse_result(DevGhost_Parser().analyze(tmp))

            assert len(result["codeFlow"]["nodes"]) > 0

    def test_er_model_has_entities(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _write_file(tmp, "app/Models/User.php", PHP_USER_MODEL)
            _write_file(tmp, "app/Models/Post.php", PHP_POST_MODEL)
            _write_file(tmp, "prisma/schema.prisma", PRISMA_SCHEMA)

            result = _parse_result(DevGhost_Parser().analyze(tmp))

            assert len(result["erModel"]["entities"]) > 0

    def test_summary_is_nonempty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _write_file(tmp, "app/Models/User.php", PHP_USER_MODEL)
            _write_file(tmp, "services/order_service.py", PYTHON_SERVICE)
            _write_file(tmp, "prisma/schema.prisma", PRISMA_SCHEMA)

            result = _parse_result(DevGhost_Parser().analyze(tmp))

            assert result["summary"] != ""


# ---------------------------------------------------------------------------
# Test 2: Empty codebase
# ---------------------------------------------------------------------------


class TestFullFlowEmptyCodebase:
    """Validates: Requirements 4.1, 4.2, 4.5"""

    def test_empty_codebase_nodes_are_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = _parse_result(DevGhost_Parser().analyze(tmp))

            assert result["codeFlow"]["nodes"] == []

    def test_empty_codebase_entities_are_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = _parse_result(DevGhost_Parser().analyze(tmp))

            assert result["erModel"]["entities"] == []

    def test_empty_codebase_summary_fixed_message(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = _parse_result(DevGhost_Parser().analyze(tmp))

            assert (
                result["summary"]
                == "No se encontraron archivos de codigo fuente analizables en la base de codigo proporcionada."
            )

    def test_empty_codebase_no_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = _parse_result(DevGhost_Parser().analyze(tmp))

            assert "errors" not in result


# ---------------------------------------------------------------------------
# Test 3: Codebase with parse errors in some files
# ---------------------------------------------------------------------------


class TestFullFlowWithParseErrors:
    """Validates: Requirements 4.7"""

    def test_valid_file_still_produces_nodes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            # Valid Python file
            _write_file(
                tmp,
                "valid_service.py",
                b"class ValidService:\n    def run(self):\n        pass\n",
            )
            # Binary garbage with a recognized extension
            _write_file(tmp, "broken.php", b"\x00\xff\xfe INVALID PHP CONTENT")

            result = _parse_result(DevGhost_Parser().analyze(tmp))

            assert "codeFlow" in result
            assert result["codeFlow"] is not None
            # The valid Python file should produce at least one node
            assert len(result["codeFlow"]["nodes"]) >= 1

    def test_output_still_has_required_structure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _write_file(
                tmp,
                "app_controller.py",
                b"class AppController:\n    pass\n",
            )
            _write_file(tmp, "garbage.js", b"\x00\x01\x02\x03 not real javascript")

            result = _parse_result(DevGhost_Parser().analyze(tmp))

            # Even with broken files, output still contains the three keys
            assert "codeFlow" in result
            assert "erModel" in result
            assert "summary" in result


# ---------------------------------------------------------------------------
# Test 4: Output format (valid JSON, UTF-8, no BOM)
# ---------------------------------------------------------------------------


class TestOutputFormat:
    """Validates: Requirements 4.1, 4.5, 4.6"""

    def test_output_is_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _write_file(
                tmp, "service.py", b"class OrderService:\n    pass\n"
            )
            raw = DevGhost_Parser().analyze(tmp)
            assert isinstance(raw, bytes)

    def test_no_bom_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _write_file(
                tmp, "service.py", b"class OrderService:\n    pass\n"
            )
            raw = DevGhost_Parser().analyze(tmp)
            assert not raw.startswith(b"\xef\xbb\xbf")

    def test_valid_utf8_decoding(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _write_file(
                tmp, "service.py", b"class OrderService:\n    pass\n"
            )
            raw = DevGhost_Parser().analyze(tmp)
            # Must decode as valid UTF-8 without raising
            decoded = raw.decode("utf-8")
            assert len(decoded) > 0

    def test_valid_json_parsing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _write_file(
                tmp, "service.py", b"class OrderService:\n    pass\n"
            )
            raw = DevGhost_Parser().analyze(tmp)
            # Must parse as valid JSON without raising
            result = json.loads(raw.decode("utf-8"))
            assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# Test 5: Node classification in full flow
# ---------------------------------------------------------------------------


class TestNodeClassification:
    """Validates: Requirements 1.1, 1.2"""

    def test_php_controller_classified_correctly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _write_file(
                tmp,
                "app/Http/Controllers/UserController.php",
                PHP_USER_CONTROLLER,
            )

            result = _parse_result(DevGhost_Parser().analyze(tmp))
            nodes = result["codeFlow"]["nodes"]

            assert len(nodes) >= 1
            controller_nodes = [n for n in nodes if n["type"] == "Controller"]
            assert len(controller_nodes) >= 1

    def test_python_service_classified_correctly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _write_file(tmp, "services/order_service.py", PYTHON_SERVICE)

            result = _parse_result(DevGhost_Parser().analyze(tmp))
            nodes = result["codeFlow"]["nodes"]

            assert len(nodes) >= 1
            service_nodes = [n for n in nodes if n["type"] == "Service"]
            assert len(service_nodes) >= 1

    def test_node_fields_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _write_file(
                tmp,
                "app/Http/Controllers/UserController.php",
                PHP_USER_CONTROLLER,
            )
            _write_file(tmp, "services/order_service.py", PYTHON_SERVICE)

            result = _parse_result(DevGhost_Parser().analyze(tmp))
            nodes = result["codeFlow"]["nodes"]

            for node in nodes:
                assert "id" in node and node["id"] != ""
                assert "label" in node and node["label"] != ""
                assert "type" in node and node["type"] in {
                    "Controller",
                    "Service",
                    "Route",
                    "Middleware",
                    "Repository",
                    "Utility",
                }


# ---------------------------------------------------------------------------
# Test 6: ER entities from Prisma in full flow
# ---------------------------------------------------------------------------


class TestEREntitiesFromPrisma:
    """Validates: Requirements 2.1, 2.2, 2.3"""

    def test_prisma_entities_extracted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _write_file(tmp, "prisma/schema.prisma", PRISMA_SCHEMA)

            result = _parse_result(DevGhost_Parser().analyze(tmp))
            entities = result["erModel"]["entities"]

            entity_names = [e["name"] for e in entities]
            assert "Product" in entity_names
            assert "Category" in entity_names
            assert "OrderItem" in entity_names

    def test_prisma_entity_has_attributes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _write_file(tmp, "prisma/schema.prisma", PRISMA_SCHEMA)

            result = _parse_result(DevGhost_Parser().analyze(tmp))
            entities = result["erModel"]["entities"]

            # Find the Product entity
            product = next(
                (e for e in entities if e["name"] == "Product"), None
            )
            assert product is not None
            assert len(product["attributes"]) > 0

            # Product should have a 'name' attribute
            attr_names = [a["name"] for a in product["attributes"]]
            assert "name" in attr_names

    def test_prisma_relations_extracted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _write_file(tmp, "prisma/schema.prisma", PRISMA_SCHEMA)

            result = _parse_result(DevGhost_Parser().analyze(tmp))
            relations = result["erModel"]["relations"]

            # There should be relations between Product ↔ Category and OrderItem ↔ Product
            assert len(relations) > 0

    def test_prisma_entity_has_primary_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _write_file(tmp, "prisma/schema.prisma", PRISMA_SCHEMA)

            result = _parse_result(DevGhost_Parser().analyze(tmp))
            entities = result["erModel"]["entities"]

            for entity in entities:
                assert "primaryKey" in entity


# ---------------------------------------------------------------------------
# Test 7: ER entities from Eloquent PHP in full flow
# ---------------------------------------------------------------------------


class TestEREntitiesFromEloquent:
    """Validates: Requirements 2.1, 2.2, 2.3"""

    def test_eloquent_entities_extracted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _write_file(tmp, "app/Models/User.php", PHP_USER_MODEL)
            _write_file(tmp, "app/Models/Post.php", PHP_POST_MODEL)

            result = _parse_result(DevGhost_Parser().analyze(tmp))
            entities = result["erModel"]["entities"]

            entity_names = [e["name"] for e in entities]
            assert "User" in entity_names
            assert "Post" in entity_names

    def test_eloquent_relations_extracted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _write_file(tmp, "app/Models/User.php", PHP_USER_MODEL)
            _write_file(tmp, "app/Models/Post.php", PHP_POST_MODEL)

            result = _parse_result(DevGhost_Parser().analyze(tmp))
            relations = result["erModel"]["relations"]

            # User hasMany Post, Post belongsTo User
            assert len(relations) > 0

    def test_eloquent_fillable_becomes_attributes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _write_file(tmp, "app/Models/User.php", PHP_USER_MODEL)

            result = _parse_result(DevGhost_Parser().analyze(tmp))
            entities = result["erModel"]["entities"]

            user = next((e for e in entities if e["name"] == "User"), None)
            assert user is not None
            attr_names = [a["name"] for a in user["attributes"]]
            assert "name" in attr_names
            assert "email" in attr_names


# ---------------------------------------------------------------------------
# Test 8: Combined multi-source ER deduplication
# ---------------------------------------------------------------------------


class TestMultiSourceERDeduplication:
    """Validates: Requirements 2.5"""

    def test_no_duplicate_entities_from_multiple_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _write_file(tmp, "app/Models/User.php", PHP_USER_MODEL)
            _write_file(tmp, "app/Models/Post.php", PHP_POST_MODEL)
            _write_file(tmp, "prisma/schema.prisma", PRISMA_SCHEMA)
            _write_file(tmp, "models/db.py", PYTHON_SQLALCHEMY_MODEL)

            result = _parse_result(DevGhost_Parser().analyze(tmp))
            entities = result["erModel"]["entities"]

            # Each entity name should appear only once
            entity_names = [e["name"] for e in entities]
            assert len(entity_names) == len(set(entity_names))
