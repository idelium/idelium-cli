# Environment Resolution

Idelium environment resolution is versioned as
`idelium-environment-resolution.v1`.

The selected `--environment` must exist in the environments returned for the
selected project. If an environment declares `projectId`, it must match
`--idProject`; otherwise resolution fails before browser, Appium, Postman,
plugin, artifact, or reporting execution begins.

## Inheritance

An environment may declare `extends: "<parent>"`. Parent environments are
resolved first, then child values override parent values. Inheritance cycles and
unknown parents are validation failures.

## Override precedence

The effective configuration is resolved in this order:

1. inherited parent environment values;
2. selected environment values;
3. explicit CLI overrides, such as `--url`, `--seleniumGridUrl`,
   `--seleniumGridCapabilities`, and non-default `--bidiMode`.

Sequential execution remains backward compatible when environments do not use
`extends` and no CLI override is provided.

## Secrets

Environment configuration should contain references to externally managed
secrets, not raw secret values. Sensitive-looking keys such as passwords, API
tokens, cookies, authorization headers, and session identifiers are diagnosed and
redacted from resolution metadata.
