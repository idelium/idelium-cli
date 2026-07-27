# Idelium DSL v1 Specification

Status: **Draft**  
Language version: **1.0**  
Specification identifier: **idelium-dsl/1.0**

## 1. Purpose

Idelium DSL v1 is a small, deterministic language for describing browser test
flows. It separates test intent from the WebDriver implementation and from the
JSON payloads currently persisted by Idelium API.

This document is normative unless a section is explicitly marked informative.
The accompanying [EBNF grammar](grammar.ebnf) is also normative. If prose and
grammar disagree, the prose defines the intended semantics and the discrepancy
must be treated as a specification defect.

## 2. Scope

DSL v1.0 supports:

- an explicit language-version declaration;
- one or more named tests;
- typed string variables and deterministic string interpolation;
- reusable step definitions and invocation with parameters;
- page navigation;
- CSS and XPath element locators;
- clicking and entering text;
- explicit element waits;
- visibility, text, value, collection-count, URL, and title assertions;
- validated `if` blocks and bounded `repeat` loops;
- browser back and forward navigation;
- named screenshots;
- comments and optional statement terminators.

External functions and arbitrary runtime commands are reserved for later
backward-compatible DSL v1 revisions. A v1.0 implementation must not interpret
unknown syntax as a plugin or arbitrary runtime command.

## 3. Source format

Source files:

- use UTF-8 without requiring a byte-order mark;
- conventionally use the `.idelium` extension;
- are case-sensitive;
- use double-quoted strings;
- may use spaces, tabs, LF, or CRLF as whitespace;
- may contain line comments beginning with `#`;
- may terminate statements with a semicolon.

Keywords are lowercase. A parser must reject an uppercase or mixed-case keyword
instead of silently normalizing it.

### 3.1 Strings

Strings use JSON-compatible escaping:

```text
"plain text"
"a quote: \""
"line one\nline two"
"unicode: \u20ac"
```

Supported escape sequences are `"`, `\`, `/`, `b`, `f`, `n`, `r`, `t`, and
four-hex-digit Unicode escapes introduced by `\u`. Unescaped control characters
are invalid.

### 3.2 Durations

A duration is a positive integer followed immediately by:

- `ms` for milliseconds;
- `s` for seconds;
- `m` for minutes.

Examples are `250ms`, `10s`, and `2m`. Zero, negative, fractional, or unitless
durations are invalid. Implementations must apply their documented upper bound
before execution.

### 3.3 Variables and interpolation

Variables are string values declared inside a test:

```text
let baseUrl = "https://example.invalid"
secret password = "correct-horse-battery-staple"
```

`let` declares a normal string variable. `secret` declares a string variable
whose value may be used during execution but must be redacted from normal
diagnostics and command results. Variable names must start with an ASCII letter
or `_` and may then contain ASCII letters, digits, or `_`.

Interpolation uses `${name}` inside supported command strings:

```text
open "${baseUrl}/login"
write css "#password" value "${password}"
```

Scope is per test. Variables declared in one test are not visible to another
test. Runtime-provided variables may seed a test, but declarations inside the
test take precedence from the declaration point onward. Referencing a missing
variable is a runtime validation failure and must not echo the variable name as
a sensitive value.

Runtime-provided variables may be loaded from a structured parameter file and
overridden by CLI-provided parameters. Precedence is:

1. parameter file `variables` and `secrets`;
2. CLI non-secret parameters;
3. CLI secret parameters.

Parameter names follow the same identifier rules as DSL variables. Parameter
values must be strings. Malformed files, invalid names, invalid values, and
malformed `name=value` assignments fail during CLI validation before DSL
execution starts. Secret parameters are expanded for execution but must be
redacted from normal output, reports, diagnostics, and tracebacks.

### 3.4 Reusable steps

Reusable steps are declared at document level before or between tests:

```text
step login(email, password) {
    write css "#email" value "${email}"
    write css "#password" value "${password}"
    click css "button[type='submit']"
}
```

Tests invoke them with `use`:

```text
use login("user@example.invalid", "${password}")
```

Definition names and parameter names use the same identifier rules as
variables. Invocation arguments are strings and may use interpolation. Parameter
bindings are scoped to the reusable-step invocation and do not leak into the
caller after the call completes. If an invocation argument references a `secret`
variable, the corresponding parameter is treated as secret for the duration of
the invocation.

## 4. Grammar

The complete grammar is published in [grammar.ebnf](grammar.ebnf). The root form
is:

```text
idelium 1.0

test "Test name" {
    statement
}
```

At least one test is required. Test names must be non-empty after trimming
Unicode whitespace. Duplicate test names in the same source file are invalid.

Newlines and semicolons both separate statements. A semicolon is optional before
a closing brace.

## 5. Locators

A locator selects one element and consists of a strategy plus a non-empty
selector string:

```text
css "#submit"
xpath "//button[@type='submit']"
```

The supported v1.0 strategies are:

| Strategy | Meaning |
| --- | --- |
| `css` | W3C WebDriver CSS selector |
| `xpath` | W3C WebDriver XPath selector |

The runtime must pass the selector to the selected WebDriver strategy without
rewriting it. An invalid selector is a locator failure, not a syntax failure,
unless the string itself is malformed.

Commands that consume a locator operate on the first element returned by the
WebDriver strategy. Absence, ambiguity policies, and stale-element conditions
must be represented by classified runtime diagnostics.

## 6. Commands

Commands execute in source order. Unless stated otherwise, a failed command
stops the current test and later commands in that test are marked as skipped.
The next named test may run according to the enclosing suite policy.

Variable declarations are executable statements. They update the test-local
scope and succeed without browser interaction.

Control blocks are executable statements with nested statement results. A
failure inside a block fails the enclosing control statement and stops the
current test. A false `if` condition skips its nested statements without failing
the test. `repeat` loops must be bounded by the runtime before executing any
nested statement.

Reusable-step invocations are executable statements with nested statement
results. The runtime must validate arity before dispatching nested statements.
Recursive or mutually recursive invocations must fail when the configured
expansion limit is reached.

### 6.1 Open a page

```text
open "https://example.invalid/login"
```

`open` navigates the active browser context to an absolute `http` or `https`
URL. User information in a URL is invalid. Implementations should redact
sensitive query values in diagnostics.

### 6.2 Click an element

```text
click css "button[type='submit']"
```

`click` locates the element and performs the WebDriver element click operation.
It does not add an implicit retry. A caller that needs readiness must use
`wait ... clickable` first.

### 6.3 Enter text

```text
write css "#email" value "user@example.invalid"
```

`write` locates the element and sends the supplied text. It does not clear an
existing value. Text values are potentially sensitive and must not be copied
into normal diagnostics.

### 6.4 Wait for an element condition

```text
wait css "#dashboard" visible timeout 10s
wait xpath "//button[@type='submit']" clickable
```

The optional timeout uses the execution environment default when omitted. The
supported conditions are:

| Condition | Success condition |
| --- | --- |
| `present` | The element exists in the current DOM |
| `visible` | The element exists and is displayed |
| `hidden` | The element is absent or not displayed |
| `clickable` | The element is visible and enabled |

A timeout is a classified timeout failure. Implementations must use an explicit,
bounded wait and must not convert this command into an unbounded polling loop.

### 6.5 Assert visibility

```text
assert visible css "#dashboard"
assert hidden css ".loading"
```

`assert visible` succeeds when the selected element is displayed.
`assert hidden` succeeds when the element is absent or not displayed. A false
condition is an assertion failure and remains distinct from an invalid selector,
session failure, or network failure.

### 6.6 Assert text

```text
assert text css "h1" equals "Dashboard"
assert text css ".notice" contains "completed"
```

Text assertions read the selected element's visible text. Supported comparisons
are:

| Comparison | Meaning |
| --- | --- |
| `equals` | Actual text equals the expected string exactly |
| `contains` | Actual text contains the expected string |

Comparisons are case-sensitive and do not trim or normalize whitespace. Expected
and actual values may be sensitive and must be redacted according to execution
policy.

### 6.7 Assert element value

```text
assert value css "#email" equals "user@example.invalid"
assert value css "#token" contains "prefix"
```

Value assertions read the selected element's `value` attribute. Supported
comparisons are `equals` and `contains`. Sensitive expected or actual values
must be redacted in runtime results and diagnostics.

### 6.8 Assert collection count

```text
assert count css ".row" equals 3
assert count css ".result" at_least 1
```

Count assertions evaluate the number of elements matching the locator. Supported
comparisons are `equals`, `greater_than`, `less_than`, `at_least`, and
`at_most`. Expected counts are non-negative integers.

### 6.9 Assert runtime state

```text
assert url contains "/dashboard"
assert title equals "Dashboard"
```

Runtime assertions read browser state without a locator. The supported targets
are `url` and `title`; supported comparisons are `equals` and `contains`.

### 6.10 Assertion result contract

Assertion command output and assertion-failure diagnostics use the
`dsl-assertion.v1` payload:

```json
{
  "contractVersion": "dsl-assertion.v1",
  "kind": "text",
  "target": "text",
  "operator": "contains",
  "expected": "Dashboard",
  "actual": "Dashboard - Production"
}
```

Assertion failures use `IDELIUM_DSL_RUNTIME_ASSERTION_FAILED`, keeping
assertion mismatches distinct from execution errors such as locator, timeout,
session, or network failures.

### 6.11 Navigate back or forward

```text
back
forward
```

`back` and `forward` invoke the corresponding WebDriver history operation in the
active browser context. They do not imply a page-readiness wait.

### 6.12 Conditional blocks

```text
if visible css "#dashboard" {
    click css "#refresh"
}

if hidden xpath "//dialog" {
    screenshot "dialog-hidden"
}
```

`if` supports `visible` and `hidden` conditions using the same visibility
semantics as assertions. When the condition is true, nested statements run in
order. When the condition is false, nested statements are marked skipped and the
`if` statement passes.

### 6.13 Bounded loops

```text
repeat 3 times {
    click css ".retry"
}
```

`repeat` executes its nested statements a fixed positive number of times. The
runtime must enforce a documented maximum iteration count before dispatching the
first nested statement. If any nested statement fails, the current iteration
fails, remaining iterations are skipped, and the enclosing `repeat` statement
fails.

### 6.14 Capture a screenshot

```text
screenshot "dashboard-loaded"
```

The name must be non-empty and must contain only ASCII letters, digits, `.`, `_`,
or `-`. It must not contain a path separator or `..`. The runtime adds its own
extension and collision-safe execution identifier.

Screenshot storage, size, retention, and retrieval follow the configured
artifact policy. A screenshot failure is reported without replacing the
original failure that triggered it.

### 6.15 Invoke a reusable step

```text
use login("user@example.invalid", "${password}")
```

`use` expands a document-level reusable step by name. Argument count must match
the reusable-step parameter list exactly. Expansion is deterministic and bounded;
implementations must fail safely when the configured expansion limit is reached.
Parameters and variables declared inside the reusable step are isolated from the
caller.

## 7. Execution semantics

### 7.1 Validation phases

An implementation processes source in this order:

1. Decode UTF-8.
2. Parse source into a syntax representation.
3. Verify the declared language version.
4. Validate command shapes, names, durations, and literal constraints.
5. Produce the canonical AST.
6. Execute only if all source-level validation succeeds.

No browser session, network request, plugin, or external process may start
before steps 1–5 succeed for the selected source.

### 7.2 Test state

Each command has one terminal status:

- `passed`;
- `failed`;
- `skipped`.

A named test has `passed` status only when every command passed. It has `failed`
status when any command failed. Commands after the first fail-fast error are
`skipped`.

### 7.3 Error classes

The runtime preserves these top-level error classes:

| Class | Example |
| --- | --- |
| `syntax` | Unterminated string or unknown statement form |
| `validation` | Unsupported version, empty test name, invalid duration |
| `network` | Navigation or remote WebDriver connection failure |
| `locator` | Invalid selector or element not found |
| `timeout` | Wait condition did not become true in time |
| `assertion` | Expected visibility or text did not match |
| `session` | Browser session was lost or unavailable |
| `artifact` | Screenshot could not be captured or stored |
| `internal` | Unexpected implementation failure |

An assertion failure must never be reported as success because the underlying
HTTP or WebDriver command completed.

## 8. Diagnostics

Diagnostics are structured and include:

- a stable diagnostic code;
- severity;
- error class;
- English message;
- one-based start line and column;
- one-based end line and column when known;
- an optional remediation hint.

Example:

```json
{
  "code": "IDL1003",
  "severity": "error",
  "class": "syntax",
  "message": "Expected a locator after 'click'.",
  "span": {
    "start": {"line": 4, "column": 5},
    "end": {"line": 4, "column": 10}
  },
  "hint": "Use a CSS or XPath locator, for example: click css \"#save\"."
}
```

Diagnostics must not include passwords, API keys, authorization headers,
cookies, session identifiers, or complete sensitive text values. A diagnostic
may identify the field or source span without repeating its literal content.

### 8.1 Lint diagnostics

The DSL linter runs without network, browser, API, or plugin access. Lint output
uses `dsl-lint-result.v1` and stable `ruleId` values. Each diagnostic has:

- `ruleId`;
- `severity`, either `warning` or `error`;
- English `message`;
- optional source `span`;
- optional remediation.

Warnings do not fail CI by default and return exit code `0`. Syntax errors and
lint errors return exit code `2`. Current rules include syntax validation,
undefined reusable-step calls, insecure `http://` navigation, and waits that rely
on implicit runtime timeouts.

Recommended code ranges are:

| Range | Purpose |
| --- | --- |
| `IDL1xxx` | Lexical and syntax errors |
| `IDL2xxx` | Static validation errors |
| `IDL3xxx` | Runtime and WebDriver failures |
| `IDL4xxx` | Assertions |
| `IDL5xxx` | Artifacts |
| `IDL9xxx` | Internal failures |

## 9. Versioning and compatibility

The first statement declares a `major.minor` language version:

```text
idelium 1.0
```

Compatibility rules are:

1. An implementation must support only versions it explicitly advertises.
2. A newer v1 implementation must preserve the grammar and semantics of valid
   v1.0 source.
3. A v1 minor release may add keywords only where v1.0 would reject the source.
4. A command or option cannot change meaning within major version 1.
5. Deprecations require an English warning, migration guidance, and a documented
   removal window.
6. A breaking grammar or semantic change requires a new major version.
7. Persisted source retains its declared version; it is never silently rewritten
   during execution.

Unknown versions are validation errors and must stop execution before external
side effects.

## 10. Security requirements

- Source is untrusted input and must be parsed without code evaluation.
- Unknown commands never fall through to Python, WebDriver, plugins, shell
  commands, or subprocesses.
- URLs accept only explicitly supported schemes.
- Screenshot names cannot control filesystem paths.
- Text and expected assertion values are potentially sensitive.
- Diagnostics, logs, reports, and artifacts apply redaction before persistence
  or output.
- Execution and artifact access remain scoped to the authenticated tenant and
  project outside the language runtime.
- Resource limits must bound source size, string length, statement count,
  duration, and artifact size.

## 11. Examples

The version-controlled examples are:

- [Minimal navigation](examples/minimal.idelium)
- [Login flow](examples/login.idelium)
- [Navigation and screenshot](examples/navigation-and-screenshot.idelium)

These examples are informative but must remain valid DSL v1.0 source.

## 12. Implementation conformance

An implementation conforms to DSL v1.0 when it:

- accepts every valid construct defined by this specification;
- rejects unsupported or malformed constructs before execution;
- preserves the command semantics and fail-fast status model;
- emits source-located, redacted diagnostics;
- produces the versioned canonical AST defined by the Idelium AST contract;
- passes the DSL v1 conformance suite.

The canonical AST schema, parser implementation, and execution adapter are
separate versioned contracts and may evolve independently while preserving these
language semantics.

The DSL v1 canonical representation is defined by the
[AST contract](AST.md) and its machine-readable
[JSON Schema](ast.schema.json).
