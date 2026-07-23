Idelium CLI release notes
=========================

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
