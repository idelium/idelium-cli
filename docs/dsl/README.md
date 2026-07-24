# Idelium DSL

Idelium DSL is the versioned, human-readable language used to describe test
automation independently from Selenium, Appium, Postman, or another execution
backend.

## Published versions

| Version | Status | Specification |
| --- | --- | --- |
| 1.0 | Draft | [DSL v1 specification](v1/SPECIFICATION.md) and [canonical AST](v1/AST.md) |

The v1 specification is normative for the language surface. The current Idelium
CLI still executes persisted JSON steps; parser, canonical AST, and execution
runtime work is tracked separately in the product roadmap.

## Offline AST export

Use the CLI in offline mode to parse a DSL source file and write the canonical
AST JSON document without contacting the Idelium API:

```bash
idelium --dslSource=docs/dsl/v1/examples/minimal.idelium \
  --astReport=reports/minimal.ast.json
```

The AST export is separate from execution-result exports. It uses the
`schemaVersion` and `languageVersion` declared in the v1 AST contract and fails
before writing output when the source declares an unsupported future DSL version.

## Version policy

- A source file declares the language version in its first statement.
- Minor releases may add backward-compatible commands, options, conditions, or
  diagnostics.
- A major release may change grammar or semantics and requires migration
  guidance.
- Deprecated syntax remains accepted for the documented deprecation window.
- An implementation must reject unsupported versions before executing any step.
