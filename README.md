![Idelium](https://idelium.io/assets/images/idelium.png)

# Idelium-CLI

This is Idelium Command Line is the tool for test automation integrated with [Idelium AS](https://github.com/idelium/idelium-docker).

Idelium-CLI can be used through a continues integration software, such as Jenkins, GitLabs, Bamboo etc.

For more info: https://idelium.io

[![Introducing Idelium](https://img.youtube.com/vi/nGe3c_CU0NQ/0.jpg)](https://youtu.be/nGe3c_CU0NQ)

## Prerequisite

Idelium CLI supports CPython 3.10, 3.11, 3.12, and 3.13. Package metadata,
classifiers, tests, and the CI matrix use this same range.

## Installing

If you have pip on your system, you can simply install or upgrade the Python bindings:

```
pip install idelium
```

For development, install the quality and test extras and run the same gates as
CI:

```bash
python -m pip install -e '.[dev,test]'
ruff check src tests
ruff format --check src/idelium/_internal/commons/connection.py src/idelium/_internal/thirdparties/ideliumpostman.py tests
mypy --allow-untyped-defs --allow-any-generics --disable-error-code var-annotated src/idelium/_internal/commons/connection.py src/idelium/_internal/thirdparties/ideliumpostman.py
COVERAGE_OUTPUT_DIR=.coverage-data coverage run --source=src/idelium -m unittest discover -s tests
coverage combine .coverage-data
coverage report --fail-under=25
python -m build
```

## Run the command

idelium-cli can be used in two ways:

### HTTP security

Every Idelium, Postman, Jira, and Zephyr request verifies TLS certificates and
uses a 5-second connection timeout plus a 30-second read timeout by default.
Use `--caBundle=/path/to/internal-ca.pem` for a private certificate authority.
The timeout values can be changed with `--httpConnectTimeout` and
`--httpReadTimeout`.

`--insecure` disables certificate verification only when explicitly provided
and emits a visible warning. It is intended for isolated development systems,
not CI or production. Automatic retries are bounded and apply only to safe or
idempotent methods; POST requests are never retried. Verbose diagnostics show
the method, redacted URL, and status without printing credentials, headers,
payloads, or complete response bodies.

To directly launch a test cycle, useful for those who want to integrate integration tests with jenkins, bamboo or similar:

```
idelium --ideliumKey=1234 --idCycle=2 --idProject=8 --environment=prod
```

For use with [idelium-docker](https://github.com/idelium/idelium-docker):

```
idelium --ideliumKey=1234 --idCycle=2 --idProject=8 --environment=prod --ideliumwsBaseurl='https://localhost'
```

### idelium-cli server mode
for idelium-cli in server mode useful for those who want to buy idelium enterprise, and then configure different platforms and launch tests remotely:

```
idelium --ideliumServer
```

### options
```
    Usage: idelium [options]

    Options:

    --help                  show this help
    --idCycle               cycle id to associate to the execution "idCycle1,idCycle2,...."
    --idProject             force idProject
    --environment           environment json config file (required)
    --useragent             set useragent for the test
    --test                  for testing without store the results
    --verbose               for debugging 
    --dirChromedriver       default path of chromedriver path ("./chromedriver/last")
    --dirConfigurationStep  default path ("./configurationStep") for configuration steps 
    --dirStepFiles          default path ("./step") of directory for step files 
    --dirIdeliumScript      default path (".") of directory for step files
    --width                 default width of screen 1024
    --height                default height of screen 768
    --device                if is set useragent,height and width are ignored
    --url                   url for test 
    --ideliumwsBaseurl      idelium server url ex: https://localhost
    --reportingService      where the data will be save: idelium | zephyr
    --ideliumKey            is the key for access to the idelium api
    --idChannel             idChannel
    
    Idelium server
    --ideliumServer         with this option idelium-cli is in server mode
    --ideliumServerPort     default is 8691

    Zephir 
    --jiraApiUrl            for change the default jira url (https://<host jira>/rest/api/latest/)
    --idJira                jira id (required if idVersion and idCycle not setted)
    --idVersion             version id to associate the execution 
    --username              jira username (required)
    --password              jira password (required)

```


## Test Libraries used

### Selenium

For configure idelium-cli for test web application with chrome,firefox, windows, safari:

https://www.selenium.dev/documentation/webdriver/

#### Selenium Grid

Set `seleniumGridUrl` in the selected Idelium environment to run browser sessions
on Selenium Grid instead of downloading or starting a local driver. Optional
W3C capabilities belong in the `seleniumGridCapabilities` JSON object:

```json
{
  "browser": "chrome",
  "seleniumGridUrl": "http://selenium-grid:4444",
  "seleniumGridCapabilities": {
    "platformName": "linux",
    "se:name": "Idelium test"
  }
}
```

The command line can override both settings with `--seleniumGridUrl=...` and
`--seleniumGridCapabilities='{"platformName":"linux"}'`. Remote session
creation does not fall back to a local browser when Grid is unavailable, so an
infrastructure failure remains visible to automation. Grid URLs must use HTTP or
HTTPS; TLS termination and Grid authentication should be configured outside the
capability payload so credentials are not logged or stored with test results.

### Appium

For configure idelium-cli for test native, hybrid and mobile web apps with iOS, Android and Windows:

https://appium.io/

### Postman collections

Idelium executes Postman Collection v2.1 requests, including requests inside
nested folders. Collection variables are loaded first and enabled environment
values override them.

Saved Postman response examples define the assertions. When an example is
present, Idelium checks its HTTP status and response body; JSON bodies are
compared semantically, without depending on object key order. Without a saved
example, the request passes only for an HTTP status from 200 through 399. A
failed status or body assertion fails the containing Idelium step.

TLS certificate verification and finite connection/read timeouts are enabled by
default. An uploaded execution object may set `insecure` to `true` only for an
explicit development run; the CLI prints a warning. Stored results redact common
credential fields from JSON response bodies and sensitive URL query parameters.

## Webdriver

The webdriver is the interface to write instructions that work interchangeably across browsers, each browser has its own driver:

#### ChromeDriver

https://chromedriver.chromium.org/downloads

idelium-cli download automically the correct version

#### Geckodriver for Firefox

https://github.com/mozilla/geckodriver/releases

#### EDGE

https://developer.microsoft.com/en-us/microsoft-edge/tools/webdriver/

#### Internet Explorer 11

https://support.microsoft.com/en-us/topic/webdriver-support-for-internet-explorer-11-9e1331c5-3198-c835-f622-ada80fe8c1fa

#### Safari

https://developer.apple.com/documentation/webkit/testing_with_webdriver_in_safari

## Thanks

Special thanks to Marco Vernarecci, who supports me to make the product better
