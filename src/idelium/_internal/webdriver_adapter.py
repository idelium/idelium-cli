"""Stable W3C WebDriver adapter contract for Idelium runtimes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from selenium.common.exceptions import (
    InvalidSelectorException,
    NoSuchElementException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.common.by import By

from idelium._internal.commons.resultenum import Result


LOCATOR_STRATEGIES = {
    "class": By.CLASS_NAME,
    "class name": By.CLASS_NAME,
    "class_name": By.CLASS_NAME,
    "css": By.CSS_SELECTOR,
    "css selector": By.CSS_SELECTOR,
    "css_selector": By.CSS_SELECTOR,
    "id": By.ID,
    "link text": By.LINK_TEXT,
    "link_text": By.LINK_TEXT,
    "name": By.NAME,
    "partial link text": By.PARTIAL_LINK_TEXT,
    "partial_link_text": By.PARTIAL_LINK_TEXT,
    "tag": By.TAG_NAME,
    "tag name": By.TAG_NAME,
    "tag_name": By.TAG_NAME,
    "xpath": By.XPATH,
}


TRANSIENT_ERROR_CLASSES = (
    TimeoutException,
)


@dataclass(frozen=True)
class WebDriverLocator:
    """A validated locator passed across the WebDriver adapter boundary."""

    strategy: str
    value: str

    def as_selenium(self) -> tuple[str, str]:
        """Return the Selenium strategy/value tuple."""

        return (self.strategy, self.value)


@dataclass(frozen=True)
class WebDriverAdapterError:
    """Serializable error contract for WebDriver operations."""

    code: str
    message: str
    transient: bool = False
    diagnostic: str | None = None

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable, redacted diagnostic payload."""

        payload: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
            "transient": self.transient,
        }
        if self.diagnostic:
            payload["diagnostic"] = self.diagnostic
        return payload


@dataclass(frozen=True)
class WebDriverAdapterResult:
    """Stable result envelope for command execution."""

    return_code: int
    value: Any = None
    error: WebDriverAdapterError | None = None

    def as_step_result(self) -> dict[str, Any]:
        """Return the legacy Idelium step result shape."""

        payload: dict[str, Any] = {"returnCode": self.return_code}
        if self.value is not None:
            payload["value"] = self.value
        if self.error is not None:
            payload["error"] = self.error.as_dict()
        return payload


class WebDriverContractError(ValueError):
    """Raised when an Idelium step violates the adapter contract."""


def normalize_locator_strategy(strategy: Any) -> str:
    """Normalize an Idelium locator strategy to a Selenium W3C strategy."""

    key = str(strategy or "").strip().lower().replace("_", " ")
    if key not in LOCATOR_STRATEGIES:
        raise WebDriverContractError(
            "Unsupported locator strategy. Use css, xpath, id, name, class, "
            "tag, link text, or partial link text."
        )
    return LOCATOR_STRATEGIES[key]


def build_locator(strategy: Any, value: Any) -> WebDriverLocator:
    """Validate and build a WebDriver locator."""

    if value is None or str(value).strip() == "":
        raise WebDriverContractError("Locator target must not be empty.")
    return WebDriverLocator(normalize_locator_strategy(strategy), str(value))


def resolve_step_locator(object_step: dict[str, Any], prefix: str = "") -> WebDriverLocator:
    """Resolve current and legacy Idelium step locator fields.

    Legacy steps that only provide ``xpath`` remain supported. New steps should
    pass explicit ``findBy`` and ``target`` fields, or prefixed variants such as
    ``sourceFindBy``/``sourceTarget`` for W3C Actions.
    """

    if prefix:
        strategy = object_step.get(prefix + "FindBy")
        target = object_step.get(prefix + "Target")
    else:
        strategy = object_step.get("findBy")
        target = object_step.get("target")

    if not strategy and not target and not prefix and object_step.get("xpath"):
        return build_locator("xpath", object_step["xpath"])
    if not strategy or target is None:
        raise WebDriverContractError(
            "Step locator must include both findBy and target fields."
        )
    return build_locator(strategy, target)


def classify_webdriver_error(err: BaseException) -> WebDriverAdapterError:
    """Classify a WebDriver failure without exposing session or credential data."""

    if isinstance(err, WebDriverContractError):
        return WebDriverAdapterError(
            code="IDELIUM_WEBDRIVER_CONTRACT_ERROR",
            message=str(err),
            transient=False,
        )
    if isinstance(err, NoSuchElementException):
        return WebDriverAdapterError(
            code="IDELIUM_WEBDRIVER_LOCATOR_NOT_FOUND",
            message="The configured locator did not match an element.",
            transient=False,
        )
    if isinstance(err, InvalidSelectorException):
        return WebDriverAdapterError(
            code="IDELIUM_WEBDRIVER_INVALID_SELECTOR",
            message="The configured selector is invalid for the selected strategy.",
            transient=False,
        )
    if isinstance(err, TimeoutException):
        return WebDriverAdapterError(
            code="IDELIUM_WEBDRIVER_TIMEOUT",
            message="The WebDriver operation timed out.",
            transient=True,
        )
    if isinstance(err, WebDriverException):
        return WebDriverAdapterError(
            code="IDELIUM_WEBDRIVER_ERROR",
            message="The WebDriver runtime reported an execution failure.",
            transient=isinstance(err, TRANSIENT_ERROR_CLASSES),
        )
    return WebDriverAdapterError(
        code="IDELIUM_WEBDRIVER_UNEXPECTED_ERROR",
        message="The WebDriver operation failed unexpectedly.",
        transient=False,
    )


class W3CWebDriverAdapter:
    """Adapter boundary between Idelium steps and a Selenium WebDriver object."""

    def __init__(self, driver: Any, capabilities: dict[str, Any] | None = None):
        self.driver = driver
        self.capabilities = capabilities or {}

    def find_element(self, locator: WebDriverLocator):
        """Find one element through an explicit W3C locator contract."""

        return self.driver.find_element(*locator.as_selenium())

    def find_elements(self, locator: WebDriverLocator):
        """Find elements through an explicit W3C locator contract."""

        return self.driver.find_elements(*locator.as_selenium())

    def is_session_healthy(self) -> WebDriverAdapterResult:
        """Check whether an existing WebDriver session is responsive."""

        try:
            getattr(self.driver, "current_window_handle")
            return WebDriverAdapterResult(Result.OK)
        except BaseException as err:
            return WebDriverAdapterResult(
                Result.KO,
                error=WebDriverAdapterError(
                    code="IDELIUM_WEBDRIVER_SESSION_UNHEALTHY",
                    message="The WebDriver session is no longer responsive.",
                    transient=classify_webdriver_error(err).transient,
                ),
            )

    def quit(self) -> WebDriverAdapterResult:
        """Close a WebDriver session and report cleanup errors safely."""

        if self.driver is None:
            return WebDriverAdapterResult(Result.OK)
        try:
            self.driver.quit()
            return WebDriverAdapterResult(Result.OK)
        except BaseException:
            return WebDriverAdapterResult(
                Result.KO,
                error=WebDriverAdapterError(
                    code="IDELIUM_WEBDRIVER_SESSION_CLEANUP_FAILED",
                    message="The WebDriver session could not be closed cleanly.",
                    transient=False,
                ),
            )

    def execute(self, operation: str, func, *args, **kwargs) -> WebDriverAdapterResult:
        """Execute an allow-listed operation behind a stable result envelope."""

        if not operation:
            return WebDriverAdapterResult(
                Result.KO,
                error=WebDriverAdapterError(
                    code="IDELIUM_WEBDRIVER_MISSING_OPERATION",
                    message="A WebDriver operation name is required.",
                    transient=False,
                ),
            )
        try:
            value = func(*args, **kwargs)
            return WebDriverAdapterResult(Result.OK, value=value)
        except BaseException as err:
            return WebDriverAdapterResult(
                Result.KO,
                error=classify_webdriver_error(err),
            )
