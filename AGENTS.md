# Idelium CLI Directives

These rules extend the workspace-level Idelium engineering directives.

## Directives

1. **Use English for documentation and source-code comments.** This includes Python
   docstrings, inline comments, CLI help, error messages, examples, and release
   notes.
2. **Keep TLS verification enabled by default.** Never introduce `verify=False` as
   a default. A development-only insecure mode must be explicit, visibly warned,
   and covered by tests. Prefer a configurable CA bundle.
3. **Centralize HTTP behavior.** All API calls must use the shared client with
   finite timeouts, status validation, predictable JSON handling, and bounded
   retries only for safe or idempotent operations.
4. **Redact credentials.** API keys, passwords, OAuth secrets, cookies, and complete
   authorization headers must never appear in normal or verbose output.
5. **Keep the CLI contract stable.** Do not rename flags, change defaults, or alter
   exit-code semantics without compatibility handling and release documentation.
6. **Return meaningful exit codes.** Validation failures, connection failures,
   test failures, and internal errors must be distinguishable by automation tools.
7. **Test integrations at their boundaries.** Mock external HTTP services in unit
   tests and maintain contract tests for Idelium API payloads. Do not require a
   browser, device, Jira, or network connection for the default unit-test suite.
8. **Maintain supported Python metadata.** Keep `python_requires`, classifiers,
   documentation, and the CI version matrix aligned. Bound dependencies where an
   incompatible major upgrade could break execution.
9. **Constrain generic runtime commands.** Generic Selenium, Appium, Postman, or
   plugin command dispatch must use explicit allow-lists, runtime validation, and
   safe failure responses. Do not pass arbitrary user payloads directly to a
   driver or subprocess without redaction and compatibility checks.
10. **Preserve Appium and Selenium compatibility boundaries.** Driver-specific
    capabilities, Appium `mobile:*` extensions, Selenium Grid capabilities, and
    BiDi-ready settings must remain backward compatible with existing Idelium
    steps and include network-free boundary tests.

## Required verification

- Compile or import the package on every supported Python version.
- Run unit tests without network access.
- Verify CLI help and at least one representative command invocation.
- Run linting and type checks configured by the project.
