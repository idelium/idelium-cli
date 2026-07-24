# Idelium DSL v1 Canonical AST

Schema version: **1.0**  
Language version: **1.0**  
Machine-readable schema: [ast.schema.json](ast.schema.json)

## Purpose

The canonical AST is the contract between source parsing, static validation,
persistence, and execution. It contains no backend-specific Selenium method
names and never permits arbitrary driver, plugin, Python, or subprocess calls.

Every node uses a `kind` discriminator and an exact field set. Unknown fields
are rejected. Source spans use one-based lines and columns, and their `end`
position is exclusive.

Durations are normalized to positive integer milliseconds. Locators preserve
their CSS or XPath strategy without rewriting the selector. Literal values remain
strings and carry an explicit `sensitive` flag where they may contain protected
data.

## Compatibility rules

1. `schemaVersion` and `languageVersion` are independent and mandatory.
2. A consumer must reject unsupported major schema versions before persistence
   or execution.
3. A minor schema release may add optional fields or new node kinds only when
   older consumers can reject them safely.
4. Existing fields cannot change type, meaning, or required status within schema
   major version 1.
5. Persisted AST documents retain their original schema version.
6. Migration creates a new document and records the source schema version; it
   never mutates the only stored copy silently.
7. Unknown node kinds and properties are validation failures, never plugin
   dispatch requests.
8. Migrations require fixture-based forward and backward-compatibility tests and
   an English release note.

## Security

The AST is untrusted input even when produced by an Idelium parser. Consumers
must validate it against the schema and apply configured limits before use.
The `sensitive` marker guides diagnostics and serialization but does not replace
tenant authorization, encryption, secret management, or server-side redaction.

## Example

See [complete.ast.json](examples/complete.ast.json), which represents every DSL
v1 statement kind.

