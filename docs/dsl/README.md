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

## Version policy

- A source file declares the language version in its first statement.
- Minor releases may add backward-compatible commands, options, conditions, or
  diagnostics.
- A major release may change grammar or semantics and requires migration
  guidance.
- Deprecated syntax remains accepted for the documented deprecation window.
- An implementation must reject unsupported versions before executing any step.
