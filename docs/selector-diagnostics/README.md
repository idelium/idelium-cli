# Selector Resilience Diagnostics

Idelium CLI emits selector-quality diagnostics before Selenium/Appium execution
when a selector matches a known brittle pattern. These diagnostics are warnings:
the runtime never rewrites, replaces, guesses, or repairs selectors
automatically.

Each diagnostic has a stable rule identifier that can be used in CI logs,
documentation, and future policy controls.

## Rules

| Rule identifier | Scope | Meaning |
| --- | --- | --- |
| `IDELIUM_SELECTOR_CSS_POSITIONAL` | CSS | The selector uses positional pseudo-classes such as `:nth-child`. |
| `IDELIUM_SELECTOR_CSS_DYNAMIC_ID` | CSS | The selector uses an id that looks generated or volatile. |
| `IDELIUM_SELECTOR_CSS_DYNAMIC_ATTRIBUTE` | CSS | The selector uses an id/class attribute value that looks generated. |
| `IDELIUM_SELECTOR_XPATH_ABSOLUTE` | XPath | The selector is an absolute DOM path. |
| `IDELIUM_SELECTOR_XPATH_POSITIONAL` | XPath | The selector uses numeric or `last()` positional predicates. |
| `IDELIUM_SELECTOR_XPATH_DYNAMIC_ATTRIBUTE` | XPath | The selector uses an id/class attribute value that looks generated. |
| `IDELIUM_SELECTOR_LEGACY_XPATH_FIELD` | Legacy steps | The step uses the legacy `xpath` field instead of explicit locator metadata. |

## Guidance

Prefer stable automation metadata such as `data-testid`, semantic roles, visible
labels, accessible names, business identifiers, or durable component attributes.
Avoid coupling tests to rendered DOM position, generated framework identifiers,
or full-page XPath paths.

Legacy selectors remain supported for compatibility. The diagnostics are
observability aids and do not change sequential execution behavior.
