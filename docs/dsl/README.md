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

## Minimal AST runtime

The CLI includes a network-free, allow-listed runtime for canonical AST
documents. It executes the DSL v1 browser command set against a Selenium-like
driver object and returns a stable JSON-serializable result:

- `open`
- `click`
- `write`
- `wait`
- `assert visible`
- `assert hidden`
- `assert text`
- `back`
- `forward`
- `screenshot`

The runtime rejects unsupported node kinds and unknown node fields before
dispatch. It never converts AST nodes into plugin, Python, subprocess, or raw
driver method calls. Failed statements stop the current test and later
statements are marked as skipped.

Sensitive text and URL query values are redacted in runtime output and
diagnostics. The AST remains untrusted input even when it was produced by the
Idelium parser; consumers must keep validating schema and language versions
before persistence or execution.

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

## Authoring and migration rules

Author DSL v1 files with a top-level language declaration and one or more named
test blocks:

```idelium
idelium 1.0

test "Sign in" {
    open "https://example.invalid/login"
    wait css "#email" visible timeout 10s
    write css "#email" value "user@example.invalid"
    click xpath "//button[@type='submit']"
    assert visible css "#dashboard"
}
```

Recommended authoring rules:

1. Keep keywords lowercase.
2. Prefer stable CSS selectors or explicit XPath expressions.
3. Use `wait ... clickable` before clicking dynamic controls.
4. Keep credentials out of source files; later DSL revisions will add secure
   parameter sources.
5. Use named screenshots for reviewable checkpoints.
6. Treat parser and runtime diagnostics as release-blocking feedback.

Migration rules:

1. Preserve legacy JSON steps until an equivalent DSL source and canonical AST
   are committed.
2. Do not mutate persisted AST documents in place. Create a migrated document
   and record the source schema version.
3. Reject unsupported major schema or language versions instead of attempting a
   best-effort execution.
4. Keep fixture-based regression tests for every migration path.
5. Document incompatible changes in English release notes before publishing.

## Version policy

- A source file declares the language version in its first statement.
- Minor releases may add backward-compatible commands, options, conditions, or
  diagnostics.
- A major release may change grammar or semantics and requires migration
  guidance.
- Deprecated syntax remains accepted for the documented deprecation window.
- An implementation must reject unsupported versions before executing any step.
