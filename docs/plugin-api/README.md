# Idelium CLI Plugin API

Status: **Draft**  
Current API version: **idelium-plugin/1.1**

Idelium CLI plugins extend execution only through constrained, versioned
contracts. A plugin must declare its API version, capabilities, entrypoint,
approval status, provenance, integrity hash, execution mode, and source code
before the runtime can dispatch a step to it.

## Manifest

The API payload returned by Idelium API should be a JSON object:

```json
{
  "apiVersion": "idelium-plugin/1.1",
  "capabilities": ["browser.step"],
  "entrypoint": "init",
  "approvalStatus": "approved",
  "sourceSha256": "8b4e...",
  "executionMode": "subprocess",
  "timeoutSeconds": 10,
  "provenance": {
    "reviewedBy": "security@example.test",
    "reviewedAt": "2026-07-28T00:00:00Z"
  },
  "source": "from idelium._internal.commons.resultenum import Result\n\ndef init(driver, json_config, params):\n    return Result.OK\n"
}
```

The current `browser.step` capability is the only supported extension point. It
allows a named Idelium step to call the declared Python entrypoint with
environment configuration and step parameters inside the subprocess boundary.

The `sourceSha256` value must be the SHA-256 digest of the exact UTF-8 source
string. If the source changes after approval, the digest no longer matches and
the CLI refuses to run the plugin.

## Compatibility

Legacy plugin payloads stored as a JSON list whose first item is Python source
remain parseable and are normalized internally as `idelium-plugin-legacy/1`
with the `browser.step` capability and `init` entrypoint. They are not approved
for enterprise execution. Migrate persisted plugins to the explicit
`idelium-plugin/1.1` manifest with approval metadata and source integrity.

Unknown API versions, invalid plugin names, unsupported capabilities, invalid
entrypoint names, malformed JSON, empty source code, unapproved manifests,
missing provenance, unsupported execution modes, and source-hash mismatches are
rejected before the plugin is written or executed.

## Security

The runtime only dispatches to plugins downloaded into the current test
configuration and only when the plugin declares the requested capability,
approval state, integrity hash, and subprocess execution mode. A step name that
is not registered as a plugin is treated as a failed step rather than a generic
Python import request.

Plugin execution happens in a child Python process with a finite timeout, a
temporary working directory, and a minimal environment. Diagnostic messages are
redacted for common credential terms such as passwords, tokens, cookies,
authorization headers, session identifiers, and API keys.

Plugins must not print credentials, spawn arbitrary subprocesses, access
unapproved filesystem paths, initiate unauthorized network calls, or bypass
tenant authorization checks. Future API versions may add narrower capabilities
for specific browser, artifact, or reporting use cases.
