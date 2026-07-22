# Requirements Document

## Introduction

DevGhost-Parser is a software architecture analysis system that statically analyzes a codebase and produces a structured JSON output describing: a code-flow graph (nodes and edges compatible with web diagram libraries like React Flow), an Entity-Relationship (ER) data model extracted from ORM definitions or SQL scripts, and a narrated executive summary suitable for voice-guided tours. The system never returns friendly text, markdown formatting, or any content outside a single valid JSON object.

## Glossary

- **DevGhost_Parser**: The top-level system responsible for orchestrating code analysis and producing structured JSON output.
- **Code_Flow_Analyzer**: The subsystem that scans source files, identifies architectural entities, and maps their call/dependency relationships.
- **ER_Extractor**: The subsystem that locates ORM models, migration files, or raw SQL scripts and extracts table schemas and relationships.
- **Summary_Generator**: The subsystem that produces a concise, voice-ready executive summary of the analyzed codebase.
- **Output_Serializer**: The subsystem responsible for composing and validating the final JSON output.
- **Node**: A graph element representing a single source file or architectural unit (e.g., Controller, Service, Route).
- **Edge**: A graph element representing a directed relationship between two Nodes (e.g., a call, import, or dependency).
- **Entity**: A table or domain object discovered in ORM models, migrations, or SQL scripts.
- **Relation**: A typed association between two Entities (one-to-one, one-to-many, many-to-many).
- **Target_Codebase**: The source code directory or repository provided as input to DevGhost_Parser.
- **ORM**: Object-Relational Mapper (e.g., Eloquent for Laravel, Prisma for Node.js, SQLAlchemy for Python).

---

## Requirements

### Requirement 1: Code Flow Graph Generation

**User Story:** As a software architect, I want the system to identify architectural entities and their interactions, so that I can visualize the code flow as a diagram in my web application.

#### Acceptance Criteria

1. WHEN a Target_Codebase path is provided, THE Code_Flow_Analyzer SHALL scan all source files and identify architectural entity types including Controllers, Services, Routes, Middlewares, Repositories, and Utilities.
2. WHEN source files are scanned, THE Code_Flow_Analyzer SHALL produce one Node per identified file, where each Node contains a unique `id`, a `label` derived from the class name when a class declaration is present or the file name otherwise, and a `type` field indicating the entity category.
3. WHEN source files are scanned, THE Code_Flow_Analyzer SHALL produce one Edge per detected inter-file dependency or function call, where each Edge contains a `source` node id, a `target` node id, and a `relation` field describing the relationship type (e.g., "calls", "imports", "depends_on"); edges whose `source` or `target` do not correspond to an existing Node `id` SHALL be excluded from the output.
4. IF no source files matching known architectural patterns are found in the Target_Codebase, THEN THE Code_Flow_Analyzer SHALL return an empty `nodes` array and an empty `edges` array.
5. THE Code_Flow_Analyzer SHALL enforce referential integrity so that every Edge in the output references `source` and `target` values that each correspond to the `id` of a Node present in the same `nodes` array; any Edge violating this constraint SHALL be removed before output.
6. IF the Target_Codebase path is invalid or inaccessible, THEN THE Code_Flow_Analyzer SHALL propagate an error to the Output_Serializer rather than returning a partial graph.

---

### Requirement 2: Entity-Relationship (ER) Model Extraction

**User Story:** As a data modeler, I want the system to extract table definitions and relationships from ORM models or SQL scripts, so that I can generate an ER diagram automatically.

#### Acceptance Criteria

1. WHEN ORM model files (e.g., Eloquent models, Prisma schema, SQLAlchemy models) are detected in the Target_Codebase, THE ER_Extractor SHALL parse each model and produce an Entity containing a `name`, a list of `attributes` (field name and data type), and a `primaryKey` field.
2. WHEN both ORM model files and migration files or SQL scripts are present in the Target_Codebase, THE ER_Extractor SHALL use ORM model files as the authoritative source for Entity definitions and treat migration files or SQL scripts as supplementary; WHEN migration files or SQL scripts are detected and no ORM model files are present, THE ER_Extractor SHALL parse the migration or SQL source to produce Entities with the same structure as in criterion 1.
3. WHEN relationships between Entities are declared (foreign keys, `hasMany`, `belongsTo`, `manyToMany`, or equivalent ORM relationship methods), THE ER_Extractor SHALL produce a Relation entry containing `from` (entity name), `to` (entity name), `type` (one-to-one | one-to-many | many-to-many), and `foreignKey` field; for many-to-many relations where no single foreign key column exists, THE ER_Extractor SHALL set `foreignKey` to the name of the pivot or join table; IF a relationship declaration uses an unknown or unsupported method, THEN THE ER_Extractor SHALL set `type` to "unknown" and include the raw declaration string in a `rawDeclaration` field.
4. WHEN no ORM models, migrations, or SQL scripts are found in the Target_Codebase, THE ER_Extractor SHALL return an empty `entities` array and an empty `relations` array.
5. THE ER_Extractor SHALL deduplicate Entities so that each table or model name appears at most once in the output; WHEN the same table name is defined in multiple sources, THE ER_Extractor SHALL prefer the ORM model definition over migration definitions, and migration definitions over raw SQL definitions.
6. WHEN a model file, migration file, or SQL script cannot be parsed due to syntax errors or encoding issues, THE ER_Extractor SHALL skip that file, continue processing remaining files, and record the skipped file path and error reason in the top-level `errors` array.

---

### Requirement 3: Narrated Executive Summary

**User Story:** As a voice AI integration engineer, I want a short plain-language summary of the analyzed codebase, so that I can guide users through a quick audio tour of the architecture.

#### Acceptance Criteria

1. WHEN analysis of a Target_Codebase is complete, THE Summary_Generator SHALL produce a `summary` string of at most 3 sentences describing the primary purpose, dominant architectural pattern, and main data entities found.
2. THE Summary_Generator SHALL produce a `summary` string free of the following character classes: markdown formatting characters (*, #, `, _, ~, >), backtick-delimited code identifiers, camelCase or snake_case identifiers, angle brackets, and Unicode control characters in the range U+0000–U+001F.
3. WHEN the Target_Codebase contains no files with extensions in the set (.php, .js, .ts, .py, .rb, .java, .cs, .go, .rs, .sql, .prisma) or equivalent source file extensions, THE Summary_Generator SHALL produce a `summary` string with the value "No analyzable source files were found in the provided codebase."
4. THE Summary_Generator SHALL limit the `summary` field to a maximum of 500 Unicode code points.
5. WHEN the Target_Codebase contains some recognizable source files but one or more subsystems fail to complete analysis, THE Summary_Generator SHALL produce a `summary` string based on the partial results available, and SHALL append a sentence noting that the summary may be incomplete due to analysis errors.

---

### Requirement 4: Structured JSON Output

**User Story:** As a frontend developer, I want the system to respond exclusively with a valid JSON object, so that I can parse and use the analysis results programmatically without any preprocessing.

#### Acceptance Criteria

1. THE Output_Serializer SHALL produce a response whose entire content is a single valid JSON object as defined by RFC 8259 — with no leading or trailing whitespace, no byte-order mark (BOM), no markdown code fences, no introductory text, and no trailing commentary outside the JSON object boundaries.
2. THE Output_Serializer SHALL include exactly the following top-level keys in every successful response: `codeFlow`, `erModel`, and `summary`.
3. THE `codeFlow` value SHALL be an object containing a `nodes` array and an `edges` array conforming to the structures defined in Requirement 1.
4. THE `erModel` value SHALL be an object containing an `entities` array and a `relations` array conforming to the structures defined in Requirement 2.
5. THE `summary` value SHALL be a string conforming to the constraints defined in Requirement 3.
6. WHEN the JSON output is parsed by an RFC 8259-compliant JSON parser, THE Output_Serializer SHALL produce no parse errors.
7. IF any subsystem (Code_Flow_Analyzer, ER_Extractor, or Summary_Generator) fails to complete its analysis, THEN THE Output_Serializer SHALL include a top-level `errors` array containing objects with `subsystem` (string) and `message` (string) fields describing each failure, and SHALL set the corresponding top-level key (`codeFlow`, `erModel`, or `summary`) to `null` for each failed subsystem; WHEN all subsystems succeed, THE Output_Serializer SHALL omit the `errors` key from the output entirely.

---

### Requirement 5: Input Validation

**User Story:** As a developer integrating DevGhost-Parser, I want the system to validate the provided input before analysis begins, so that I receive clear error information when the input is invalid.

#### Acceptance Criteria

1. WHEN no Target_Codebase path is provided or an empty string is supplied, THE DevGhost_Parser SHALL return a JSON object containing only an `errors` array with exactly one entry whose `message` field indicates that a Target_Codebase path is required.
2. WHEN a Target_Codebase path is provided but the path does not exist on the filesystem, THE DevGhost_Parser SHALL return a JSON object containing only an `errors` array with exactly one entry whose `message` field includes the provided path and indicates it was not found.
3. WHEN a Target_Codebase path exists but the process does not have read permission to access it, THE DevGhost_Parser SHALL return a JSON object containing only an `errors` array with exactly one entry whose `message` field includes the provided path and indicates a permission error.
4. WHEN a Target_Codebase path points to a single file rather than a directory, THE DevGhost_Parser SHALL return a JSON object containing only an `errors` array with exactly one entry whose `message` field includes the provided path and indicates that a directory path is required.
5. THE DevGhost_Parser SHALL evaluate all input validation checks in the order: (1) missing/empty path, (2) path not found, (3) permission denied, (4) not a directory — and SHALL return on the first failing check without invoking any analysis subsystem.
6. WHEN input validation passes all checks, THE DevGhost_Parser SHALL invoke the Code_Flow_Analyzer, ER_Extractor, and Summary_Generator subsystems before producing any output.

---

### Requirement 6: Round-Trip JSON Serialization Consistency

**User Story:** As a quality engineer, I want the JSON output to be self-consistent and re-parseable, so that downstream tools can reliably consume the data across multiple processing steps.

#### Acceptance Criteria

1. FOR ALL valid Target_Codebase inputs, serializing the analysis result to a JSON string and then parsing that JSON string SHALL produce an object that: (a) contains exactly the same set of top-level keys, (b) has values of the same JSON type (object, array, string, number, boolean, or null) for each key, (c) has identical scalar values (strings, numbers, booleans, null) at every field path, and (d) has arrays with the same element count and the same element values in the same order at every array field path.
2. THE Output_Serializer SHALL produce UTF-8 encoded output with no byte-order mark (BOM).
3. THE Output_Serializer SHALL represent all string values using standard JSON string escaping as defined in RFC 8259 so that no Unicode control characters in the range U+0000–U+001F appear unescaped in the output.
