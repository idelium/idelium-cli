# Retry and Wait Policy Contract

Idelium retry and wait metadata is versioned as `idelium-retry-policy.v1`.

Retries are allowed only for operations that are both:

- explicitly idempotent: `DELETE`, `GET`, `HEAD`, `OPTIONS`, or `PUT`;
- classified as transient by HTTP status: `429`, `500`, `502`, `503`, or `504`.

Deterministic failures such as validation errors, unsupported commands,
assertion mismatches, missing locators, `400`, `401`, `403`, `404`, and `409`
must not be hidden by retries.

## Budgets and backoff

The default HTTP retry budget is `2`, matching the previous client behavior.
Backoff is deterministic exponential backoff using the configured
`backoffFactor`. Negative retry budgets and negative backoff values are rejected
before any request is configured.

## Wait policy

Polling waits use bounded positive timeouts and a positive polling interval. The
DSL runtime keeps the existing defaults:

- default timeout: `5000ms`;
- maximum timeout: `120000ms`;
- poll interval: `0.1s`.

Explicit wait timeouts outside the configured bounds are classified as validation
failures before command dispatch. A wait that exhausts its valid budget remains a
timeout failure and does not become a retryable success.
