# W3C WebDriver adapter contract

Idelium browser execution uses a small adapter boundary between runtime steps
and Selenium WebDriver objects. The boundary keeps classic WebDriver behavior
compatible while making new runtime features easier to validate, test, and
diagnose.

## Contract scope

The adapter covers:

- locator validation for current `findBy`/`target` fields and legacy `xpath`;
- element lookup with explicit W3C locator strategies;
- allow-listed handlers for frames, windows, alerts, uploads, and browser
  download behavior where the driver supports it;
- session health checks and deterministic session cleanup results;
- command execution result envelopes;
- bounded failure screenshot artifact metadata;
- classified, redacted WebDriver diagnostics.

## Locator strategies

Supported locator strategies are:

- `css` / `css selector`
- `xpath`
- `id`
- `name`
- `class` / `class name`
- `tag` / `tag name`
- `link text`
- `partial link text`

New steps should use explicit `findBy` and `target` fields. Legacy steps that
only provide `xpath` remain supported for backward compatibility. Drag-and-drop
steps can use `dragFindBy`/`dragTarget` and `dropFindBy`/`dropTarget`; legacy
`xpathDrag`/`xpathDrop` payloads remain supported.

## Session lifecycle

Runtime cleanup closes optional BiDi resources first, then routes WebDriver
teardown through the adapter. Cleanup failures are reported with
`IDELIUM_WEBDRIVER_SESSION_CLEANUP_FAILED` and do not expose session data.

## Failure screenshots

Eligible browser-step failures capture at most one screenshot artifact for the
local execution report. The artifact metadata uses a generic name,
`failure-screenshot.png`, media type `image/png`, a local relative path, bounded
size metadata, safe source test/step identifiers, and a `captureOutcome` value.
If screenshot capture fails, Idelium records a warning and keeps the original
test failure unchanged.

## Download behavior

The generic `selenium_command` dispatcher exposes `set_download_behavior` for
drivers that provide Chrome DevTools download control. Unsupported drivers fail
with `IDELIUM_WEBDRIVER_CONTRACT_ERROR` instead of attempting browser-specific
fallbacks silently.

## Error contract

Adapter errors are JSON-serializable and intentionally redacted:

```json
{
  "code": "IDELIUM_WEBDRIVER_TIMEOUT",
  "message": "The WebDriver operation timed out.",
  "transient": true
}
```

The current stable codes are:

| Code | Meaning | Transient |
| --- | --- | --- |
| `IDELIUM_WEBDRIVER_CONTRACT_ERROR` | The Idelium step payload violates the adapter contract. | No |
| `IDELIUM_WEBDRIVER_LOCATOR_NOT_FOUND` | The locator did not match an element. | No |
| `IDELIUM_WEBDRIVER_INVALID_SELECTOR` | The selector is invalid for the selected strategy. | No |
| `IDELIUM_WEBDRIVER_TIMEOUT` | The WebDriver operation timed out. | Yes |
| `IDELIUM_WEBDRIVER_ERROR` | Selenium reported an execution failure. | Depends on classification |
| `IDELIUM_WEBDRIVER_SESSION_UNHEALTHY` | The driver session is no longer responsive. | Depends on classification |
| `IDELIUM_WEBDRIVER_SESSION_CLEANUP_FAILED` | `driver.quit()` did not complete cleanly. | No |

Diagnostics must not include credentials, cookies, full authorization headers,
session identifiers, or raw remote URLs with embedded credentials.

## Compatibility

Existing Selenium wrapper methods still return the legacy Idelium step result
shape, for example:

```json
{
  "returnCode": 1,
  "error": {
    "code": "IDELIUM_WEBDRIVER_CONTRACT_ERROR",
    "message": "Step locator must include both findBy and target fields.",
    "transient": false
  }
}
```

This lets CI and API integrations consume richer diagnostics without requiring a
breaking change to the basic `returnCode` contract.
