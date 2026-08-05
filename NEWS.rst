Idelium CLI release notes
=========================

1.0.15.dev1 (2026-08-05)
------------------------

Development release
~~~~~~~~~~~~~~~~~~~

* Improves DSL execution failure reporting so remote step-result errors do not
  hide the original test failure.
* Refreshes the API session before posting step results, improving reliability
  for longer-running browser and DSL executions.
* Remains a development release for validation before the stable 1.0.15
  release.

1.0.15.dev0 (2026-08-04)
------------------------

Development release
~~~~~~~~~~~~~~~~~~~

* Published as a development release while the CLI execution, reporting, and
  browser/runtime integration features continue to evolve.
* Keeps the package installable for local validation without declaring the next
  stable 1.0.15 release complete.

1.0.14 (2026-07-22)
-------------------

Security and reliability
~~~~~~~~~~~~~~~~~~~~~~~~

* Centralized HTTP transport now verifies TLS by default, applies finite
  connection and response timeouts, bounds retries to safe operations, and
  redacts sensitive diagnostic values.
* The project is now distributed under the Apache License 2.0.
* Package metadata, supported Python versions, and local verification scripts
  are kept consistent through automated tests.

Selenium
~~~~~~~~

* Added Selenium Grid support with validated remote URLs and W3C capabilities.
* Expanded the allow-listed WebDriver command and W3C Actions dispatchers.
* Added explicit wait conditions, modern window, frame, cookie, alert, shadow
  DOM, file upload, and BiDi-ready capability support.
* Preserved existing Selenium step behavior while rejecting unsupported
  commands safely.

Appium
~~~~~~

* Expanded Appium 2 support for UiAutomator2, Espresso, and XCUITest.
* Added W3C capability normalization while retaining legacy Idelium capability
  compatibility.
* Added allow-listed mobile command handling, context management, gestures,
  application lifecycle operations, and device actions.

Postman
~~~~~~~

* Added the optional Newman runtime for full Postman Collection execution.
* Added a configurable Newman timeout, structured execution result mapping,
  temporary artifact cleanup, and credential redaction.
* Retained the built-in network-safe Postman runtime as the default for
  backward compatibility.

Packaging
~~~~~~~~~

* Fixed PyPI publishing compatibility with the Bash version shipped by macOS.
* Added repeatable package build, validation, and local test scripts.
