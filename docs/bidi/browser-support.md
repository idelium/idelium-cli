# WebDriver BiDi browser support and limitations

Idelium treats WebDriver BiDi as an optional diagnostics layer on top of classic
WebDriver. Classic WebDriver remains the default, stable execution path.

## Feature status

| Area | Status | Notes |
| --- | --- | --- |
| Classic WebDriver execution | Stable | Default path for every browser and Selenium Grid session. |
| BiDi capability negotiation | Stable | Uses `bidiMode=disabled`, `auto`, or `required` and records explicit negotiation states. |
| BiDi lifecycle tracking | Stable | Starts only after a successful WebDriver session and closes registered resources before `driver.quit()`. |
| Console/log metadata artifact contract | Stable contract, experimental capture | Normalization, redaction, size limits, and report serialization are stable. Browser listener attachment is intentionally incremental. |
| Network metadata artifact contract | Stable contract, experimental capture | Stores only allow-listed metadata. Request and response bodies are excluded by default. |
| JavaScript error and SPA navigation diagnostics | Stable contract, experimental capture | Trace records are diagnostic-only and do not change test outcomes by themselves. |
| Browser-specific BiDi event subscriptions | Experimental | Browser support differs across Selenium Grid, browser driver, and browser versions. |

## Browser support

| Browser | Negotiation support | Recommended mode | Notes |
| --- | --- | --- | --- |
| Chrome | Supported | `auto` for diagnostics, `required` for strict BiDi validation | Assumes a Selenium 4 Grid or local ChromeDriver that can return a `webSocketUrl` session capability. |
| Edge | Supported | `auto` for diagnostics, `required` for strict BiDi validation | Uses Chromium-based Edge and Selenium 4 capability negotiation. |
| Firefox | Supported | `auto` for diagnostics, `required` for strict BiDi validation | Requires a GeckoDriver/browser combination that exposes a BiDi endpoint. |
| Safari | Unsupported by Idelium negotiation | `disabled` or `auto` | `auto` falls back to classic WebDriver. `required` fails before silently dropping the requested BiDi capability. |
| Internet Explorer | Unsupported | `disabled` | Keep classic WebDriver only. |
| Opera and other browsers | Unsupported unless exposed as a supported Chromium session | `disabled` or `auto` | Treat as classic WebDriver unless the environment is explicitly validated. |

The compatibility assumptions above are based on Selenium 4 behavior and browser
drivers that expose W3C capabilities. Pin the Selenium Grid, browser, and driver
versions in CI before relying on BiDi diagnostics for release gates.

## Configuration examples

Classic WebDriver only:

```bash
idelium --idCycle=2 --idProject=3 --environment=ci --bidiMode=disabled
```

Best-effort diagnostics with safe fallback:

```bash
idelium --idCycle=2 --idProject=3 --environment=ci --bidiMode=auto
```

Strict BiDi validation for a pinned browser/grid lane:

```bash
idelium --idCycle=2 --idProject=3 --environment=ci-chrome-124 --bidiMode=required
```

`required` is useful only when the browser, driver, and Selenium Grid versions
are pinned and known to return a BiDi endpoint.

## Fallback behavior

- `disabled` never adds the `webSocketUrl` capability automatically.
- `auto` adds `webSocketUrl=true` for supported browsers and falls back to
  classic WebDriver when the browser or created session cannot provide BiDi.
- `required` never silently falls back. Unsupported browsers and sessions that
  do not return a BiDi endpoint fail with a lifecycle diagnostic.
- Cleanup failures are reported as lifecycle diagnostics and remain distinct
  from test assertions.

## Privacy and storage controls

Idelium applies safe defaults before any BiDi artifact is stored:

- BiDi endpoint URLs are never persisted.
- Console messages, JavaScript errors, navigation URLs, and network URLs are
  redacted and bounded.
- Network artifacts store only method, redacted URL, status, timing, and
  allow-listed headers.
- Authorization, cookie, session, token, secret, password, key, and custom
  headers are excluded or redacted by default.
- Request and response bodies are not captured by default.
- Artifact event lists are bounded and expose `truncated`/`droppedEvents`
  counters when limits are reached.

## Troubleshooting

| Symptom | Likely cause | Action |
| --- | --- | --- |
| `unsupported` negotiation state | Browser is not in the Idelium BiDi allow-list. | Use Chrome, Edge, or Firefox, or keep `bidiMode=auto`/`disabled`. |
| `required` mode fails before navigation | Browser is unsupported or the session did not expose a BiDi endpoint. | Pin a compatible Selenium Grid/browser/driver lane or switch to `auto`. |
| Lifecycle cleanup warning | A BiDi listener or connection failed while closing. | Treat it as diagnostics infrastructure noise unless test assertions also failed. |
| No BiDi artifacts are present | BiDi was disabled, unsupported, or no selected events were observed. | Verify `bidiMode`, browser support, and the event type you expect. |
| Sensitive values appear redacted | Privacy controls are working as intended. | Use non-sensitive labels in diagnostics if you need correlation IDs. |

## Release guidance

Keep BiDi optional for general CI lanes. Use `required` only in dedicated,
version-pinned browser compatibility jobs where failure should block the
release because BiDi diagnostics themselves are part of the acceptance criteria.
