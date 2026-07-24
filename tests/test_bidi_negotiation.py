"""Tests for optional WebDriver BiDi capability negotiation."""

import unittest

from idelium._internal.bidi import negotiate_bidi_capabilities, normalize_bidi_mode
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


if __name__ == "__main__":
    unittest.main()
