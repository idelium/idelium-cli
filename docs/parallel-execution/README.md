# Parallel Execution Contract

Idelium scheduling metadata is versioned as `idelium-scheduling.v1`. The contract
defines how suites, tests, steps, workers, cancellation, ordering, and result
aggregation must behave when a parallel executor is enabled.

The current CLI execution path remains sequential by default. A one-worker
schedule is therefore the backward-compatible baseline: work is dispatched in
input order and results are emitted in the same order as the configured tests and
steps.

## Worker limits

Worker counts must be positive integers. `0`, negative values, and non-integer
values are rejected before any browser session, API call, plugin, temporary file,
or artifact path is created.

When the requested worker count is greater than the amount of available work,
`maxWorkers` is bounded to the work-item count. This prevents empty workers from
owning credentials, sessions, or temporary directories.

## Ordering guarantees

Parallel dispatch uses input-order scheduling with a stable tie-break. Result
aggregation always uses `resultOrdering: "input-order"` so downstream Idelium API,
JSON, HTML, Markdown, and JUnit consumers receive deterministic output even when
workers finish at different times.

## Cancellation

The cancellation policy is `fail-fast-with-in-test-interruption`. A failed
required step interrupts later steps in the same test and records those steps as
skipped. Other already-finished results keep their original status, timing, and
diagnostics.

## Isolation requirements

Every concurrent path must isolate:

- tenant identifiers;
- credentials and runtime secrets;
- browser or mobile sessions;
- environment and step configuration;
- temporary files;
- screenshot and diagnostic artifacts.

No worker may share mutable credentials, sessions, temporary directories, or
artifact write paths with another worker.

## Runtime isolation context

The runtime isolation contract is versioned as `idelium-runtime-isolation.v1`.
Each worker owns:

- a copied execution configuration;
- a private temporary directory;
- a private artifact directory;
- independent driver, Postman, diagnostic, and artifact result state;
- deterministic cleanup after success, failure, or cancellation.

Temporary paths use generic worker prefixes and must not contain tenant names,
credential names, credential values, cookies, or API tokens. Reportable metadata
contains only the isolation contract version, tenant identifier, worker
identifier, private paths, and cleanup errors.

## Setup and teardown hooks

Lifecycle hooks are versioned as `idelium-lifecycle-hooks.v1`. Hooks are
allow-listed command payloads, not arbitrary shell commands. The supported
contract commands are:

- `log`;
- `set_variable`;
- `clear_artifacts`.

The deterministic order is:

1. suite setup;
2. test setup;
3. test execution;
4. test teardown;
5. suite teardown.

If suite setup or test setup fails, test execution is skipped and teardown still
runs where safe. If test execution fails or is cancelled, teardown still runs.
Teardown failures fail the lifecycle only when no earlier setup or test failure
already determined the result. Hook diagnostics are redacted before they are
stored or reported.
