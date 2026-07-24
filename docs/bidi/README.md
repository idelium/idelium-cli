# WebDriver BiDi capability negotiation

Idelium supports WebDriver BiDi as an optional browser-diagnostics capability.
Classic WebDriver remains the default execution path.

## Configuration

Use `--bidiMode=<mode>` or the `bidiMode` environment field:

| Mode | Behavior |
| --- | --- |
| `disabled` | Do not request BiDi automatically. Existing explicit Selenium capabilities are preserved. |
| `auto` | Request BiDi for supported browsers and fall back to classic WebDriver for unsupported browsers. |
| `required` | Request BiDi and fail before session creation when the selected browser is unsupported. |

Supported browser names for negotiation are `chrome`, `edge`, and `firefox`.
Unsupported browsers, such as Safari or Internet Explorer, continue with classic
WebDriver only when the mode is `auto`.

## Negotiation states

Every negotiation returns a structured state for later diagnostics:

| State | Meaning |
| --- | --- |
| `disabled` | BiDi was not requested and no automatic capability was added. |
| `supported` | BiDi was requested and `webSocketUrl=true` was added to the W3C capabilities. |
| `unsupported` | BiDi was requested in `auto` mode but the browser is unsupported, so Idelium falls back to classic WebDriver. |
| `failed` | BiDi was required but could not be negotiated safely. |

## Session lifecycle

BiDi lifecycle tracking starts only after a WebDriver session is created and the
negotiation state is `supported`.

| Lifecycle state | Meaning |
| --- | --- |
| `inactive` | No BiDi resources are open. This is the default for classic WebDriver, unsupported browsers in `auto` mode, and sessions that do not expose a BiDi endpoint. |
| `open` | The WebDriver session exposed a BiDi endpoint and Idelium can attach future listeners. The endpoint value is never persisted. |
| `closed` | Registered BiDi resources were closed before the WebDriver driver was quit. |
| `failed` | BiDi setup or cleanup failed independently from test assertions. |

When `bidiMode=required`, a supported browser must return a BiDi endpoint after
session creation. If the endpoint is missing, Idelium marks the step as failed
with an explicit lifecycle diagnostic. In `auto` mode, the same condition falls
back to classic WebDriver.

The negotiation layer does not capture console or network data by itself. Later
BiDi adapters must use explicit allow-lists, size limits, redaction, and tenant
isolation before storing any artifact.

## Console event artifacts

Idelium normalizes selected browser console/log events into bounded execution
artifacts with type `application/vnd.idelium.bidi.console+json`.

Supported event types:

- `log.entryAdded`
- `runtime.consoleAPICalled`
- `cdp.Runtime.consoleAPICalled`

Supported levels are `debug`, `info`, `log`, `warning`, `error`, and `trace`.
The legacy `warn` level is normalized to `warning`; unknown levels are stored as
`log`.

Each normalized event contains:

| Field | Meaning |
| --- | --- |
| `type` | Original BiDi/CDP event type. |
| `level` | Normalized console level. |
| `text` | Redacted message text, limited to 2,000 characters. |
| `timestamp` | Optional event timestamp when provided by the browser. |
| `source` | Optional realm or browsing context identifier. |
| `url` | Optional redacted source URL. Sensitive query values are replaced. |
| `lineNumber` | Optional source line number. |
| `columnNumber` | Optional source column number. |

Console artifacts are limited to 100 events by default. If more events are
captured, the artifact sets `truncated=true` and records `totalEvents`.

Before storage, Idelium redacts common credential keys and configured sensitive
values, including authorization headers, cookies, passwords, secrets, sessions,
tokens, and API keys. BiDi endpoint URLs are never persisted.
