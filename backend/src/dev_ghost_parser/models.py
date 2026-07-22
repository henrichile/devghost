"""
Shared data models for DevGhost-Parser.

All types are defined as dataclasses to provide:
- Type safety with Python type hints
- Clean __repr__ for debugging
- Easy conversion to dict for JSON serialization
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional


# ---------------------------------------------------------------------------
# Node — represents a single architectural unit (file) in the code-flow graph
# ---------------------------------------------------------------------------

NodeType = Literal[
    "Controller", "Service", "Route", "Middleware", "Repository", "Utility"
]

EdgeRelation = Literal["imports", "calls", "depends_on"]

RelationType = Literal["one-to-one", "one-to-many", "many-to-many", "unknown"]


@dataclass
class Node:
    """A graph node representing a source file or architectural unit.

    Satisfies Requirements 1.2, 4.3.
    """

    id: str          # Unique stable identifier — SHA-1 of the relative path
    label: str       # Class name (if found) or filename without extension
    type: NodeType   # Architectural category


@dataclass
class Edge:
    """A directed dependency between two Nodes.

    Satisfies Requirements 1.3, 4.3.
    """

    source: str        # id of the originating Node
    target: str        # id of the destination Node
    relation: EdgeRelation  # Nature of the relationship


# ---------------------------------------------------------------------------
# Entity — a table or domain object from the ER model
# ---------------------------------------------------------------------------


@dataclass
class Attribute:
    """A single field/column of an Entity."""

    name: str
    type: str  # e.g. "string", "integer", "boolean", "DateTime"


@dataclass
class Entity:
    """A table or ORM model extracted from the codebase.

    Satisfies Requirements 2.1, 4.4.
    """

    name: str                          # Table/class name
    attributes: list[Attribute] = field(default_factory=list)
    primaryKey: str = "id"             # Primary key column name


# ---------------------------------------------------------------------------
# Relation — a typed association between two Entities
# ---------------------------------------------------------------------------


@dataclass
class Relation:
    """A directed ER relationship between two Entities.

    Satisfies Requirements 2.3, 4.4.
    """

    from_entity: str      # Name of the source Entity  (JSON key: "from")
    to_entity: str        # Name of the target Entity  (JSON key: "to")
    type: RelationType    # Cardinality
    foreignKey: str       # FK column name or pivot table name
    rawDeclaration: Optional[str] = None  # Populated when type == "unknown"


# ---------------------------------------------------------------------------
# Error types
# ---------------------------------------------------------------------------


@dataclass
class AnalysisError:
    """A non-fatal per-file error recorded during subsystem analysis."""

    path: str    # Relative or absolute path of the file that failed
    reason: str  # Human-readable explanation


class AnalysisFatalError(Exception):
    """Fatal error raised when a subsystem cannot proceed (e.g., root_path inaccessible).

    Propagated to the orchestrator; Output_Serializer encodes it as a subsystem error
    in the top-level JSON ``errors`` array.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


@dataclass
class SubsystemError:
    """A fatal error raised by a subsystem and surfaced in the top-level JSON."""

    subsystem: str  # e.g. "Code_Flow_Analyzer", "ER_Extractor", "Summary_Generator"
    message: str


# ---------------------------------------------------------------------------
# Aggregate result types
# ---------------------------------------------------------------------------


@dataclass
class CodeFlowResult:
    """Complete output of Code_Flow_Analyzer.

    Satisfies Requirements 1.2, 1.3, 4.3.
    """

    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    errors: list[AnalysisError] = field(default_factory=list)


@dataclass
class ERResult:
    """Complete output of ER_Extractor.

    Satisfies Requirements 2.1, 2.3, 4.4.
    """

    entities: list[Entity] = field(default_factory=list)
    relations: list[Relation] = field(default_factory=list)
    errors: list[AnalysisError] = field(default_factory=list)
