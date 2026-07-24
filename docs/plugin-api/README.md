# Idelium CLI Plugin API

Status: **Draft**  
Current API version: **idelium-plugin/1.0**

Idelium CLI plugins extend execution only through constrained, versioned
contracts. A plugin must declare its API version, capabilities, entrypoint, and
source code before the runtime can dispatch a step to it.

## Manifest

The API payload returned by Idelium API should be a JSON object:

```json
{
  "apiVersion": "idelium-plugin/1.0",
  "capabilities": ["browser.step"],
  "entrypoint": "init",
  "source": "from idelium._internal.commons.resultenum import Result\n\ndef init(driver, json_config, params):\n    return Result.OK\n"
}
```

The current `browser.step` capability is the only supported extension point. It
allows a named Idelium step to call the declared Python entrypoint with the
active driver, environment configuration, and step parameters.

## Compatibility

Legacy plugin payloads stored as a JSON list whose first item is Python source
remain supported and are normalized internally as `idelium-plugin-legacy/1`
with the `browser.step` capability and `init` entrypoint. New plugins should use
the explicit `idelium-plugin/1.0` manifest.

Unknown API versions, invalid plugin names, unsupported capabilities, invalid
entrypoint names, malformed JSON, and empty source code are rejected before the
plugin is written or imported.

## Security

The runtime only dispatches to plugins downloaded into the current test
configuration and only when the plugin declares the requested capability. A
step name that is not registered as a plugin is treated as a failed step rather
than a generic Python import request.

Plugin errors are isolated at the extension boundary. Diagnostic messages are
redacted for common credential terms such as passwords, tokens, cookies,
authorization headers, session identifiers, and API keys.

Plugins must not print credentials, spawn arbitrary subprocesses, or bypass
tenant authorization checks. Future API versions may add narrower capabilities
for specific browser, artifact, or reporting use cases.
