<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://github.com/idelium/idelium-docker/raw/main/logo/idelium_white.png">
  <img alt="Idelium" src="https://github.com/idelium/idelium-docker/raw/main/logo/idelium.png">
</picture>

# Idelium CLI

Idelium CLI is the Python execution agent for the Idelium test automation
platform. It downloads test definitions from Idelium API, executes browser,
mobile, API, or plugin-based steps, and reports structured results back to the
configured reporting service.

It is designed for developer workstations, CI systems such as Jenkins, GitLab
CI, and Bamboo, and remotely managed test-execution hosts.

## Main capabilities

- Execute Idelium projects and test cycles from a command line.
- Run Selenium tests with local drivers or Selenium Grid.
- Run native, hybrid, and mobile-web tests through Appium.
- Execute Postman Collection v2.1 requests, folders, variables, and examples.
- Load project plugins and configuration steps supplied by Idelium API.
- Report execution progress and results to Idelium or Jira/Zephyr.
- Operate as an HTTPS listener for remotely launched enterprise executions.
- Verify TLS certificates by default with configurable finite timeouts.

## Requirements

- CPython 3.10, 3.11, 3.12, or 3.13.
- `pip` and a virtual environment are strongly recommended.
- Network access to Idelium API and any tested endpoint.
- A supported browser and driver for local Selenium execution, or a reachable
  Selenium Grid.
- Appium server, platform SDK, and device/emulator for mobile execution.
- `libmagic` system support where required by the Python `libmagic` package.

The package metadata, classifiers, test matrix, and CI workflow use the same
Python support range.

## Installation

Create an isolated environment and install the released package:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install idelium
```

Upgrade an existing installation with:

```bash
python -m pip install --upgrade idelium
```

Confirm the command is available:

```bash
idelium --help
```

## Authentication

Idelium API requires a customer API key. The CLI accepts
`--ideliumKey=<value>`, but command-line arguments may be visible to other local
processes and CI logs. The safer built-in mechanism is the user key file:

```bash
install -m 600 /dev/null ~/.idelium
```

Copy the key into `~/.idelium` using a secure editor or secret-management tool.
Do not print it, commit it, pass it in a URL, or paste it into support output.
Protect the file so only its owner can read it. CI systems should materialize the
file from their protected secret store for the duration of the job and remove it
afterward.

## Run a test cycle

The required values for normal Idelium reporting are:

- `--idProject=<id>` — project identifier.
- `--idCycle=<id>` — cycle identifier.
- `--environment=<name>` — environment name configured in the project.
- an API key from `~/.idelium` or `--ideliumKey`.

With the protected key file in place, run:

```bash
idelium --idProject=8 --idCycle=2 --environment=production
```

The hosted API is used by default. To use a local Idelium stack:

```bash
idelium \
  --idProject=8 \
  --idCycle=2 \
  --environment=local \
  --ideliumwsBaseurl=https://localhost \
  --caBundle=/path/to/trusted-local-ca.pem
```

Use project and cycle identifiers from your own Idelium instance. The selected
environment is retrieved from the API; it is a configured environment name, not
a local credentials file.

## Command-line options

Options use `--name=value` unless shown as a flag.

### Execution selection

| Option | Purpose | Default |
| --- | --- | --- |
| `--idProject=<id>` | Idelium project to execute | required |
| `--idCycle=<id>` | One or more associated cycle identifiers | required |
| `--environment=<name>` | Project environment to load | required |
| `--url=<url>` | Override the environment target URL | environment value |
| `--idChannel=<id>` | Optional execution channel | none |
| `--reportingService=<service>` | Result destination: `idelium` or `zephyr` | `idelium` |
| `--ideliumwsBaseurl=<url>` | Idelium service origin | configured default |
| `--ideliumKey=<key>` | API key; prefer the protected key file | `~/.idelium` |
| `--verbose` | Emit additional redacted diagnostics | off |
| `--help` | Display built-in command help | — |

### Browser and execution overrides

| Option | Purpose | Default |
| --- | --- | --- |
| `--useragent=<value>` | Override the browser user agent | environment value |
| `--width=<pixels>` | Browser viewport width | `1920` |
| `--height=<pixels>` | Browser viewport height | `1080` |
| `--device=<name>` | Device emulation profile; supersedes viewport/user-agent choices | none |
| `--seleniumGridUrl=<url>` | Remote Selenium Grid endpoint | environment value or local driver |
| `--seleniumGridCapabilities=<json>` | JSON object merged into W3C capabilities | environment value |
| `--forcedownload` | Force a driver or execution artifact download | off |

### HTTP security and reliability

| Option | Purpose | Default |
| --- | --- | --- |
| `--caBundle=<path>` | CA bundle used to verify private/internal certificates | system trust store |
| `--insecure` | Disable TLS verification and print a warning | off |
| `--httpConnectTimeout=<seconds>` | Connection timeout, greater than zero | `5` |
| `--httpReadTimeout=<seconds>` | Response read timeout, greater than zero | `30` |

### Server mode

| Option | Purpose | Default |
| --- | --- | --- |
| `--ideliumServer` | Start the remote-execution HTTPS listener | off |
| `--ideliumServerPort=<port>` | Listener port | `8691` |

### Jira and Zephyr

| Option | Purpose |
| --- | --- |
| `--jiraApiUrl=<url>` | Override the Jira REST API base URL |
| `--idJira=<key>` | Jira issue or project key used by the selected workflow |
| `--idVersion=<id>` | Zephyr version identifier |
| `--username=<value>` | Jira user name; inject securely |
| `--password=<value>` | Jira credential; avoid command history and logs |

Run `idelium --help` for the options supported by the installed version. Keep
automation pinned to a known Idelium CLI version and review release changes
before adopting new behavior.

## HTTP and TLS behavior

Every Idelium, Postman, Jira, and Zephyr request verifies certificates and uses
finite connection and read timeouts by default. Use `--caBundle` for a private
certificate authority or local development certificate.

`--insecure` disables certificate verification only when explicitly supplied
and emits a visible warning. It is intended for an isolated development system,
never CI or production. Automatic retries are bounded and apply only to safe or
idempotent methods; POST requests are not retried, preventing accidental
duplicate execution records.

Verbose diagnostics include the method, redacted URL, and response status. They
must not include credentials, authorization headers, API keys, payloads, full
response bodies, sensitive query parameters, or session identifiers.

## Selenium execution

For local browser execution, install a compatible browser. The CLI uses Selenium
and WebDriver Manager to select or acquire supported drivers. Browser availability
and vendor restrictions still apply on the execution host.

### Selenium Grid

Set `seleniumGridUrl` in an Idelium environment to create remote sessions instead
of starting a local driver. Optional W3C capabilities belong in the
`seleniumGridCapabilities` object:

```json
{
  "browser": "chrome",
  "seleniumGridUrl": "https://selenium-grid.example.invalid:4444",
  "seleniumGridCapabilities": {
    "platformName": "linux",
    "se:name": "Idelium test"
  }
}
```

The command line can override both values:

```bash
idelium \
  --idProject=8 \
  --idCycle=2 \
  --environment=ci \
  --seleniumGridUrl=https://selenium-grid.example.invalid:4444 \
  --seleniumGridCapabilities='{"platformName":"linux"}'
```

Grid URLs must use HTTP or HTTPS. Put credentials in infrastructure-level secret
configuration rather than the capabilities object. If Grid session creation
fails, the CLI does not fall back to a local browser; the infrastructure failure
remains visible to automation.

BiDi-capable sessions can request a WebDriver BiDi endpoint by adding the W3C
`webSocketUrl` capability. The same capability object is applied to Selenium
Grid sessions and supported local browser options:

```json
{
  "browser": "chrome",
  "seleniumGridCapabilities": {
    "webSocketUrl": true,
    "se:name": "Idelium BiDi-ready test"
  }
}
```

The CLI only requests the capability; browser, driver, and Grid versions still
decide whether a BiDi endpoint is actually returned.

Explicit waits use Selenium expected conditions. Existing steps without a
condition still wait for element presence. New steps may provide
`waitCondition` and `waitSeconds` to wait for visibility, clickability, URL,
title, frame availability, or element staleness without hard-coded sleeps.

The `selenium_command` step exposes an allow-listed WebDriver command dispatcher
for common operations such as navigation, JavaScript execution, cookies, alerts,
windows/tabs, element state checks, file upload, and shadow DOM lookup. Unknown
operations fail safely instead of falling through to arbitrary driver methods.

The `selenium_actions` step exposes Selenium W3C Actions through an allow-listed
chain for keyboard input, pointer moves/clicks, wheel scrolling, drag-and-drop,
double-click, and context-click flows. Unsupported actions fail before the chain
is performed.

## Appium execution

Mobile environments can provide `isRealDevice`, `appiumServer`, and
`appiumDesiredCaps`. The desired capabilities depend on the Appium driver and
target platform. Keep device-farm credentials outside the stored capability
payload whenever possible and consult the
[Appium documentation](https://appium.io/docs/en/latest/) for driver-specific
requirements.

The execution host is responsible for Appium, the appropriate platform driver,
SDKs, signing configuration, and access to the device or emulator.

The CLI accepts legacy unprefixed Appium capability names for compatibility and
normalizes common Appium extension capabilities such as `automationName`,
`deviceName`, `app`, `bundleId`, and `newCommandTimeout` to their W3C
`appium:` names before creating the session. Standard W3C capabilities such as
`platformName`, `browserName`, and `webSocketUrl` are preserved. UiAutomator2,
Espresso, and XCUITest options are selected from the normalized platform and
automation name.

Environments may also declare Appium infrastructure metadata:

```json
{
  "appiumRequiredDrivers": ["uiautomator2"],
  "appiumRequiredPlugins": ["images"],
  "appiumMobileCommandsAllowed": ["customPluginCommand"]
}
```

When driver metadata is present, the CLI verifies that the selected automation
driver is declared before creating the session. A generic `appium_mobile_command`
step can also declare `requiredPlugin`; the command fails before execution if
that plugin is not listed in the environment metadata.

Idelium normalizes Appium command results before reporting them to the API. A
command that returns a raw driver value is treated as successful and the value is
kept in the local command response; driver exceptions fail the Idelium step.

For Appium 2 driver- or plugin-specific extensions, use the
`appium_mobile_command` step. It executes `mobile:*` commands only when the
command is part of the built-in safe allow-list or explicitly listed in
`appiumMobileCommandsAllowed` in the environment configuration. Parameters named
like credentials, tokens, cookies, or authorization headers are rejected before
execution so they are not passed through generic command artifacts.

## Postman Collection execution

Idelium executes Postman Collection v2.1 requests, including requests inside
nested folders. Collection variables are loaded first and enabled environment
values override them.

Saved response examples define assertions:

- when an example exists, Idelium compares the expected HTTP status and body;
- JSON bodies are compared semantically without depending on object key order;
- without an example, a request passes only for an HTTP status from 200 to 399;
- a failed status or body assertion fails the containing Idelium step.

Certificate verification and finite timeouts apply to collection requests too.
An uploaded execution object may set `insecure` only for an explicit development
run and produces a warning. Stored results redact common credential fields in
JSON bodies and sensitive URL query parameters.

This runner intentionally does not execute arbitrary Postman scripts. It does
not run `pm.test`, pre-request scripts, post-response scripts, or dynamic
collection/environment mutations. Use Newman outside Idelium when full Postman
runtime compatibility is required; use the built-in runner when deterministic
request execution, saved-example assertions, redaction, and Idelium result
reporting are preferred.

## Server mode

Server mode exposes an HTTPS endpoint for remotely managed executions:

```bash
idelium --ideliumServer --ideliumServerPort=8691
```

Before starting it, create `cert/cert.pem` and `cert/key.pem` relative to the
working directory. Use a trusted certificate and protect the private key with
strict filesystem permissions. The listener binds to all interfaces, so place
it behind appropriate network controls and expose it only to authorized Idelium
components. Do not use a development certificate on an internet-facing host.

## Development setup

Clone the repository and install the project with development and test extras:

```bash
git clone https://github.com/idelium/idelium-cli.git
cd idelium-cli
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip 'setuptools>=83,<84'
python -m pip install -e '.[dev,test]'
```

The source uses a `src/` layout. Runtime dependencies are bounded in `setup.py`,
and build-system dependencies are pinned to supported ranges in
`pyproject.toml`.

## Tests and quality gates

Tests are network-free by default and cover HTTP transport behavior, sensitive
data redaction, metadata, Selenium Grid, Appium, and Postman execution. Add a
regression test for every fix and boundary tests for parsing, timeouts, retries,
TLS behavior, and error handling when those areas change.

Run the same checks used by CI:

```bash
scripts/test-package.sh
```

For the full release-quality gate, run:

```bash
python -m pip_audit
ruff check src tests
ruff format --check src/idelium/_internal/commons/connection.py src/idelium/_internal/thirdparties/ideliumpostman.py tests
mypy --allow-untyped-defs --allow-any-generics --disable-error-code var-annotated src/idelium/_internal/commons/connection.py src/idelium/_internal/thirdparties/ideliumpostman.py
COVERAGE_OUTPUT_DIR=.coverage-data coverage run --source=src/idelium -m unittest discover -s tests
coverage combine .coverage-data
coverage report --fail-under=27
check-manifest
python -m build
```

CI also imports the package and runs `idelium --help` on CPython 3.10 through
3.13. The coverage run measures branch coverage and enforces the current 27%
project gate.

## Package and release verification

Before publishing a release:

1. Keep the version in `src/idelium/_internal/main.py` aligned with package
   metadata.
2. Run all tests, audit, lint, type, manifest, import, and help checks.
3. Build both source and wheel distributions with `python -m build`.
4. Inspect the archive contents and install the wheel in a clean environment.
5. Confirm no key, certificate, execution result, cache, or local configuration
   entered the distribution.

Build the package artifacts with:

```bash
scripts/build-package.sh
```

The build script refuses dirty worktrees by default so release artifacts match a
reviewable commit. Set `ALLOW_DIRTY_BUILD=1` only for local validation.

Publish the already built artifacts to PyPI with:

```bash
scripts/publish-package.sh
```

Preview the upload without contacting PyPI with:

```bash
DRY_RUN=1 scripts/publish-package.sh
```

The publish script requires the release tag to exist, uploads only artifacts for
the package version reported by `setup.py`, verifies the tag exists on `origin`,
checks that the version is not already present on PyPI, runs `twine check`, and
never stores PyPI credentials. Set `REQUIRE_CLEAN_WORKTREE=1` to make it refuse
dirty worktrees. When prompted by Twine, use `__token__` as the username and a
project-scoped PyPI API token as the password.

To test the upload flow against TestPyPI:

```bash
PYPI_REPOSITORY_URL=https://test.pypi.org/legacy/ scripts/publish-package.sh
```

## Exit behavior and automation

Treat any non-zero process exit as a failed CLI invocation. Preserve stdout and
stderr only after checking that the output contains no credentials or customer
data. Use finite job timeouts in CI, pin the installed package version, and make
the selected project, cycle, environment, browser infrastructure, and reporting
destination explicit in the job configuration.

## Troubleshooting

### `401 Invalid key`

Verify that `~/.idelium` exists, is readable by the execution user, contains the
key for the intended customer, and has not been rotated. Do not print the file
while collecting diagnostics.

### TLS verification fails

Check the hostname, certificate validity, chain, and system clock. For an
internal authority, pass its CA bundle with `--caBundle`. Do not solve a
production trust failure with `--insecure`.

### Browser or driver cannot start

Confirm the browser is installed, its version is supported, the execution user
can create a profile and temporary files, and required system libraries exist.
For Grid, verify the endpoint and available slots; no automatic local fallback
is performed.

### Environment is not found

The value passed to `--environment` must match an environment configured for the
selected Idelium project. Also verify the project belongs to the customer
associated with the API key.

### Postman assertion differs unexpectedly

Check the saved example status and body, variable precedence, and enabled
environment values. JSON object key order is ignored, but values and array order
remain meaningful.

## Security expectations

- Verify TLS and use a CA bundle for private trust roots.
- Keep API keys, Jira credentials, device-farm credentials, and certificates in
  protected secret stores.
- Never log credentials, full sensitive URLs, request headers, protected
  payloads, or complete response bodies.
- Keep retries bounded and limited to safe or idempotent operations.
- Use stable command options and meaningful non-zero exits in automation.
- Pin runtime and package versions for reproducible CI jobs.

Report suspected vulnerabilities privately to the maintainers without including
live credentials or customer data in a public issue.

## Contributing

Read the [Idelium CLI engineering directives](https://github.com/idelium/idelium-cli/blob/main/AGENTS.md)
before making changes. Documentation, docstrings, comments, diagnostics, and new
identifiers must be in clear English. Keep transport behavior centralized,
preserve stable command options, add focused tests for behavioral changes, avoid
unrelated refactoring, and run the relevant quality gates before opening a pull
request.

## Related projects

- [`idelium-api`](https://github.com/idelium/idelium-api) — configuration and
  result API.
- [`idelium-web`](https://github.com/idelium/idelium-web) — administration UI.
- [`idelium-docker`](https://github.com/idelium/idelium-docker) — reproducible
  full-stack environment.

Idelium CLI is distributed under the
[Apache License 2.0](https://github.com/idelium/idelium-cli/blob/main/LICENSE).
Project information is available on
[GitHub](https://github.com/idelium/idelium-cli).
