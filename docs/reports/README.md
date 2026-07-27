# Idelium CLI Reports

Idelium CLI can export local execution reports without changing the remote
Idelium API result flow or the process exit-code semantics.

Use `--jsonReport=<path>` to write a canonical machine-readable report,
`--htmlReport=<path>` to write a self-contained human-readable report,
`--markdownReport=<path>` to write a Markdown review artifact, and
`--junitReport=<path>` to write CI-compatible JUnit XML. When multiple options
are provided, every file is generated from the same canonical report.

The JSON format is versioned by `schemaVersion` and validated by
[execution-report.schema.json](execution-report.schema.json). The report
contains run metadata, summary counts, test entries, step timeline entries,
diagnostics, artifacts, optional performed-step traces, and Postman request
results when available.

Performed-step traces use `schemaVersion: "performed-step-trace.v1"`. Each trace
records stable step identity, terminal status, duration, redacted page context,
optional safe locator context, and classified diagnostics. The trace is optional
for compatibility with older Idelium API results, but when present it is
validated by the same JSON schema as the rest of the local execution report.

HTML, Markdown, and JUnit reports escape untrusted content and are rendered from
the same redacted canonical data used for JSON export. Sensitive terms in
diagnostic fields and sensitive URL query values are redacted before
serialization, including inside performed-step traces.

Artifacts always include `name`, `type`, and `path`. They may also include a
bounded structured `data` payload for execution diagnostics such as BiDi console
events. Structured artifact payloads are redacted before serialization and must
not contain credentials, session identifiers, authorization headers, or raw BiDi
endpoint URLs.

Failure screenshot artifacts use the deterministic name `failure-screenshot.png`
and media type `image/png`. Their metadata includes `captureOutcome`,
`mediaType`, `sizeBytes`, `sourceTestId`, and `sourceStepId` so storage and API
consumers can associate the attachment without exposing tenant-specific labels.
