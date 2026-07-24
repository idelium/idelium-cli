"""Tests for optional WebDriver BiDi capability negotiation."""

import unittest
from unittest.mock import Mock

from idelium._internal.bidi import (
    BIDI_LIFECYCLE_CLOSED,
    BIDI_LIFECYCLE_INACTIVE,
    BIDI_LIFECYCLE_OPEN,
    BidiLifecycleError,
    BidiSessionLifecycle,
    negotiate_bidi_capabilities,
    normalize_bidi_mode,
)
from idelium._internal.wrappers.ideliumselenium import IdeliumSelenium


class BidiNegotiationTest(unittest.TestCase):
    def test_disabled_mode_preserves_classic_capabilities(self):
        negotiation = negotiate_bidi_capabilities(
            browser="chrome",
            mode="disabled",
            capabilities={"platformName": "linux"},
        )

        self.assertEqual("disabled", negotiation.state)
        self.assertFalse(negotiation.requested)
        self.assertFalse(negotiation.fallback_to_classic)
        self.assertEqual({"platformName": "linux"}, negotiation.capabilities)

    def test_auto_mode_requests_websocket_for_supported_browser(self):
        negotiation = negotiate_bidi_capabilities(
            browser="firefox",
            mode="auto",
            capabilities={"platformName": "linux"},
        )

        self.assertEqual("supported", negotiation.state)
        self.assertTrue(negotiation.requested)
        self.assertTrue(negotiation.capabilities["webSocketUrl"])

    def test_auto_mode_falls_back_for_unsupported_browser(self):
        negotiation = negotiate_bidi_capabilities(
            browser="safari",
            mode="auto",
            capabilities={"platformName": "macos"},
        )

        self.assertEqual("unsupported", negotiation.state)
        self.assertTrue(negotiation.fallback_to_classic)
        self.assertNotIn("webSocketUrl", negotiation.capabilities)

    def test_required_mode_fails_for_unsupported_browser(self):
        negotiation = negotiate_bidi_capabilities(
            browser="iexplorer",
            mode="required",
            capabilities={"platformName": "windows"},
        )

        self.assertEqual("failed", negotiation.state)
        self.assertFalse(negotiation.fallback_to_classic)
        self.assertIn("not supported", negotiation.message)

    def test_invalid_mode_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "bidiMode"):
            normalize_bidi_mode("always")

    def test_selenium_capability_builder_records_supported_negotiation(self):
        config = {
            "browser": "chrome",
            "bidiMode": "auto",
            "seleniumGridCapabilities": {"platformName": "linux"},
            "json_config": {},
        }

        capabilities = IdeliumSelenium._selenium_capabilities(config)

        self.assertTrue(capabilities["webSocketUrl"])
        self.assertEqual("supported", config["bidiNegotiation"]["state"])

    def test_selenium_capability_builder_fails_required_unsupported_browser(self):
        config = {
            "browser": "safari",
            "bidiMode": "required",
            "seleniumGridCapabilities": {},
            "json_config": {},
        }

        with self.assertRaisesRegex(ValueError, "not supported"):
            IdeliumSelenium._selenium_capabilities(config)

        self.assertEqual("failed", config["bidiNegotiation"]["state"])

    def test_lifecycle_stays_inactive_without_supported_negotiation(self):
        lifecycle = BidiSessionLifecycle({"state": "disabled"})

        lifecycle.open(Mock())

        self.assertEqual(BIDI_LIFECYCLE_INACTIVE, lifecycle.as_dict()["state"])

    def test_lifecycle_opens_when_endpoint_is_available(self):
        driver = Mock()
        driver.capabilities = {"webSocketUrl": "ws://grid/session/secret"}
        lifecycle = BidiSessionLifecycle({"state": "supported", "mode": "auto"})

        lifecycle.open(driver)

        metadata = lifecycle.as_dict()
        self.assertEqual(BIDI_LIFECYCLE_OPEN, metadata["state"])
        self.assertTrue(metadata["endpointAvailable"])
        self.assertNotIn("ws://", str(metadata))

    def test_lifecycle_required_mode_fails_without_endpoint(self):
        driver = Mock()
        driver.capabilities = {}
        lifecycle = BidiSessionLifecycle({"state": "supported", "mode": "required"})

        with self.assertRaisesRegex(BidiLifecycleError, "did not return"):
            lifecycle.open(driver)

        self.assertEqual("failed", lifecycle.as_dict()["state"])

    def test_lifecycle_auto_mode_falls_back_without_endpoint(self):
        driver = Mock()
        driver.capabilities = {}
        lifecycle = BidiSessionLifecycle({"state": "supported", "mode": "auto"})

        lifecycle.open(driver)

        self.assertEqual(BIDI_LIFECYCLE_INACTIVE, lifecycle.as_dict()["state"])

    def test_lifecycle_closes_registered_resources(self):
        resource = Mock()
        driver = Mock()
        driver.capabilities = {"webSocketUrl": "ws://grid/session/secret"}
        lifecycle = BidiSessionLifecycle({"state": "supported", "mode": "auto"})
        lifecycle.open(driver)
        lifecycle.register_resource(resource)

        lifecycle.close()

        resource.close.assert_called_once_with()
        self.assertEqual(BIDI_LIFECYCLE_CLOSED, lifecycle.as_dict()["state"])

    def test_wrapper_records_bidi_lifecycle_metadata(self):
        config = {
            "bidiNegotiation": {"state": "supported", "mode": "auto"},
        }
        driver = Mock()
        driver.capabilities = {"webSocketUrl": "ws://grid/session/secret"}

        IdeliumSelenium._start_bidi_session(driver, config)

        self.assertEqual(BIDI_LIFECYCLE_OPEN, config["bidiLifecycle"]["state"])
        self.assertIn("_bidiSession", config)

    def test_wrapper_close_bidi_session_cleans_config_resource(self):
        config = {
            "bidiNegotiation": {"state": "supported", "mode": "auto"},
        }
        driver = Mock()
        driver.capabilities = {"webSocketUrl": "ws://grid/session/secret"}
        IdeliumSelenium._start_bidi_session(driver, config)

        IdeliumSelenium.close_bidi_session(config)

        self.assertEqual(BIDI_LIFECYCLE_CLOSED, config["bidiLifecycle"]["state"])
        self.assertNotIn("_bidiSession", config)


if __name__ == "__main__":
    unittest.main()
