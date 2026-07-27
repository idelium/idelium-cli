# Getting started with Idelium DSL v1

Idelium DSL v1 is a deterministic browser-test language for describing test
intent without embedding Python, shell commands, or arbitrary WebDriver calls.
It is designed to be parsed, linted, reviewed, and migrated without contacting
the Idelium API or opening a browser.

## 1. Start with a versioned file

Every DSL source starts with the language declaration:

```text
idelium 1.0
```

The `1.0` declaration is part of the compatibility contract. Future v1 releases
may add syntax, but valid v1.0 source keeps its meaning.

## 2. Write a minimal test

```text
idelium 1.0

test "Smoke" {
    open "https://example.invalid"
    wait css "main" visible timeout 10s
    assert title contains "Example"
}
```

Use CSS or XPath locators, explicit waits, and assertions. A failed statement
stops the current test and marks later statements as skipped.

## 3. Add parameters safely

Declare local values with `let` and secrets with `secret`:

```text
let baseUrl = "https://example.invalid"
secret password = "replace-with-runtime-secret"
open "${baseUrl}/login"
write css "#password" value "${password}"
```

For CI, prefer runtime parameters:

```json
{
  "variables": {
    "baseUrl": "https://staging.example.invalid"
  },
  "secrets": {
    "password": "from-secret-manager"
  }
}
```

CLI precedence is parameter file first, then `--dslParam`, then `--dslSecret`.
Secret values are expanded for execution and redacted from normal output.

## 4. Reuse common flows

Reusable steps live at document level and are invoked with `use`:

```text
step login(email, password) {
    write css "#email" value "${email}"
    write css "#password" value "${password}"
    click css "button[type='submit']"
}

test "Dashboard" {
    use login("user@example.invalid", "${password}")
}
```

Reusable-step parameters are scoped to the invocation and do not leak back to
the caller. Recursive expansion is bounded and fails safely.

## 5. Use controlled flow

Use `if` for conditional work and `repeat` for fixed bounded loops:

```text
if visible css ".toast" {
    screenshot "toast-visible"
}

repeat 2 times {
    click css ".refresh"
}
```

`if` supports `visible` and `hidden`. `repeat` accepts a positive integer and is
checked against the runtime loop bound before nested statements execute.

## 6. Validate before execution

Export an AST:

```bash
idelium --dslSource=docs/dsl/v1/examples/medium-flow.idelium \
  --astReport=reports/medium-flow.ast.json
```

Lint in CI:

```bash
idelium --dslLint=docs/dsl/v1/examples/medium-flow.idelium \
  --dslLintReport=reports/medium-flow.lint.json
```

Exit semantics:

- AST export success: `0`
- lint warnings only: `0`
- syntax or lint errors: `2`

## 7. Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| `IDELIUM_DSL_RUNTIME_MISSING_VARIABLE` | A `${name}` reference has no local or runtime value. | Declare `let`/`secret` earlier or pass a runtime parameter. |
| `IDL-LINT-UNKNOWN-STEP` | `use name(...)` has no matching `step name(...)`. | Add the reusable-step definition or fix the call name. |
| `IDELIUM_DSL_RUNTIME_LOOP_BOUND_EXCEEDED` | `repeat` exceeds the configured runtime bound. | Lower the repeat count or raise the explicit runtime limit. |
| URL credential syntax error | The source embeds credentials in an `open` URL. | Move credentials to secure parameters. |

## 8. Medium example

See [examples/medium-flow.idelium](examples/medium-flow.idelium) for parameters,
reuse, conditional blocks, bounded loops, assertions, and screenshots in one
reviewable test.
