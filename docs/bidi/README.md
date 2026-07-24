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

The negotiation layer does not capture console or network data by itself. Later
BiDi adapters must use explicit allow-lists, size limits, redaction, and tenant
isolation before storing any artifact.
