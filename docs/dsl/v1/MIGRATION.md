# Idelium DSL v1 migration notes

DSL v1 intentionally keeps the supported legacy browser intent small,
deterministic, and network-free to validate. Existing scripts that map to
navigation, CSS/XPath locators, text input, waits, assertions, browser history,
and screenshots remain representable.

## Supported legacy mappings

| Legacy intent | DSL v1 form |
| --- | --- |
| Open browser/page URL | `open "https://example.invalid"` |
| CSS or XPath element lookup | `click css "#save"` / `click xpath "//button"` |
| Send text to an element | `write css "#email" value "user@example.invalid"` |
| Wait for element readiness | `wait css "#email" visible timeout 10s` |
| Assert element visibility | `assert visible css "#dashboard"` |
| Assert visible text | `assert text css "h1" equals "Dashboard"` |
| Back/forward navigation | `back` / `forward` |
| Screenshot checkpoint | `screenshot "checkpoint-name"` |

## Intentional incompatibilities

- Embedded credentials in `open` URLs are rejected. Use DSL secure parameters
  instead.
- Arbitrary command execution and plugin dispatch are not DSL statements. Keep
  those behind explicit runtime integrations.
- Screenshot names cannot contain path separators or `..`; the runtime owns
  artifact paths.
- Unknown uppercase or mixed-case keywords are rejected instead of normalized.

These incompatibilities return stable syntax or lint diagnostics before browser
or network work starts.
