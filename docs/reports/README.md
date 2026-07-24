# Idelium CLI Reports

Idelium CLI can export local execution reports without changing the remote
Idelium API result flow or the process exit-code semantics.

Use `--jsonReport=<path>` to write a canonical machine-readable report and
`--htmlReport=<path>` to write a self-contained human-readable report. When both
options are provided, both files are generated from the same canonical report.

The JSON format is versioned by `schemaVersion` and validated by
[execution-report.schema.json](execution-report.schema.json). The report
contains run metadata, summary counts, test entries, step timeline entries,
diagnostics, artifacts, and Postman request results when available.

HTML reports escape untrusted content and are rendered from the same redacted
canonical data used for JSON export. Sensitive terms in diagnostic fields and
sensitive URL query values are redacted before serialization.
