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
diagnostics, artifacts, and Postman request results when available.

HTML, Markdown, and JUnit reports escape untrusted content and are rendered from
the same redacted canonical data used for JSON export. Sensitive terms in
diagnostic fields and sensitive URL query values are redacted before
serialization.

Artifacts always include `name`, `type`, and `path`. They may also include a
bounded structured `data` payload for execution diagnostics such as BiDi console
events. Structured artifact payloads are redacted before serialization and must
not contain credentials, session identifiers, authorization headers, or raw BiDi
endpoint URLs.
