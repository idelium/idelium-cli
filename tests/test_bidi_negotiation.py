"""Tests for optional WebDriver BiDi capability negotiation."""

import unittest
from unittest.mock import Mock

from idelium._internal.bidi import (
    BIDI_LIFECYCLE_CLOSED,
    BIDI_LIFECYCLE_INACTIVE,
    BIDI_LIFECYCLE_OPEN,
    BidiLifecycleError,
    BidiSessionLifecycle,
    build_bidi_console_artifact,
    build_bidi_diagnostic_artifact,
    build_bidi_network_artifact,
    negotiate_bidi_capabilities,
    normalize_bidi_console_event,
    normalize_bidi_diagnostic_event,
    normalize_bidi_network_event,
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

    def test_lifecycle_connection_loss_is_reported_as_cleanup_failure(self):
        resource = Mock()
        resource.close.side_effect = RuntimeError("socket closed")
        driver = Mock()
        driver.capabilities = {"webSocketUrl": "ws://grid/session/secret"}
        lifecycle = BidiSessionLifecycle({"state": "supported", "mode": "auto"})
        lifecycle.open(driver)
        lifecycle.register_resource(resource)

        with self.assertRaisesRegex(BidiLifecycleError, "cleanup failed"):
            lifecycle.close()

        self.assertEqual("failed", lifecycle.as_dict()["state"])

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

    def test_wrapper_connection_loss_does_not_raise_to_test_assertions(self):
        config = {
            "bidiNegotiation": {"state": "supported", "mode": "auto"},
        }
        driver = Mock()
        driver.capabilities = {"webSocketUrl": "ws://grid/session/secret"}
        lifecycle = IdeliumSelenium._start_bidi_session(driver, config)
        resource = Mock()
        resource.close.side_effect = RuntimeError("connection lost")
        lifecycle.register_resource(resource)
        printer = Mock()

        IdeliumSelenium.close_bidi_session(config, printer)

        self.assertEqual("failed", config["bidiLifecycle"]["state"])
        printer.danger.assert_called_once()

    def test_console_event_normalization_redacts_sensitive_values(self):
        normalized = normalize_bidi_console_event(
            {
                "type": "log.entryAdded",
                "params": {
                    "level": "warn",
                    "text": "token=abc123 customer-secret",
                    "timestamp": 123,
                    "source": {
                        "url": "https://example.test/path?token=abc123&query=ok",
                        "lineNumber": 12,
                        "columnNumber": 3,
                    },
                },
            },
            sensitive_values=["customer-secret"],
        )

        self.assertEqual("warning", normalized["level"])
        self.assertEqual("token=[REDACTED] [REDACTED]", normalized["text"])
        self.assertEqual(
            "https://example.test/path?token=%5BREDACTED%5D&query=ok",
            normalized["url"],
        )
        self.assertEqual(12, normalized["lineNumber"])

    def test_unsupported_console_event_is_ignored(self):
        self.assertIsNone(
            normalize_bidi_console_event({"type": "network.beforeRequestSent"})
        )

    def test_console_artifact_is_bounded(self):
        events = [
            normalize_bidi_console_event(
                {
                    "type": "log.entryAdded",
                    "params": {"level": "info", "text": str(index)},
                }
            )
            for index in range(3)
        ]

        artifact = build_bidi_console_artifact(events, limit=2)

        self.assertEqual("bidi-console-events", artifact["name"])
        self.assertTrue(artifact["data"]["truncated"])
        self.assertEqual(3, artifact["data"]["totalEvents"])
        self.assertEqual(2, len(artifact["data"]["events"]))

    def test_lifecycle_console_artifact_is_added_on_close(self):
        config = {
            "bidiNegotiation": {"state": "supported", "mode": "auto"},
        }
        driver = Mock()
        driver.capabilities = {"webSocketUrl": "ws://grid/session/secret"}
        lifecycle = IdeliumSelenium._start_bidi_session(driver, config)
        lifecycle.record_console_event(
            {
                "type": "log.entryAdded",
                "params": {"level": "error", "text": "password=hunter2"},
            }
        )

        IdeliumSelenium.close_bidi_session(config)

        artifact = config["bidiArtifacts"][0]
        self.assertEqual("application/vnd.idelium.bidi.console+json", artifact["type"])
        self.assertEqual(
            "password=[REDACTED]",
            artifact["data"]["events"][0]["text"],
        )

    def test_network_event_normalization_uses_allow_list_and_redaction(self):
        normalized = normalize_bidi_network_event(
            {
                "type": "network.responseCompleted",
                "params": {
                    "requestId": "request-1",
                    "request": {
                        "method": "post",
                        "url": "https://example.test/api?token=abc&debug=1",
                        "headers": {
                            "Content-Type": "application/json",
                            "Authorization": "Bearer abc",
                            "Cookie": "sid=secret",
                            "X-Internal": "drop-me",
                        },
                    },
                    "response": {
                        "status": 200,
                        "statusText": "OK",
                        "timingMilliseconds": 42,
                    },
                    "body": "must not be captured",
                },
            }
        )

        self.assertEqual("POST", normalized["method"])
        self.assertEqual(
            "https://example.test/api?token=%5BREDACTED%5D&debug=1",
            normalized["url"],
        )
        self.assertEqual(200, normalized["status"])
        self.assertEqual({"content-type": "application/json"}, normalized["headers"])
        self.assertFalse(normalized["bodyCaptured"])
        self.assertNotIn("body", normalized)

    def test_network_artifact_tracks_truncated_and_dropped_events(self):
        events = [
            normalize_bidi_network_event(
                {
                    "type": "network.beforeRequestSent",
                    "params": {
                        "request": {"method": "GET", "url": f"https://e.test/{index}"}
                    },
                }
            )
            for index in range(3)
        ]

        artifact = build_bidi_network_artifact(events, dropped_events=2, limit=1)

        self.assertEqual("bidi-network-events", artifact["name"])
        self.assertEqual(3, artifact["data"]["totalEvents"])
        self.assertEqual(2, artifact["data"]["droppedEvents"])
        self.assertTrue(artifact["data"]["truncated"])
        self.assertEqual(1, len(artifact["data"]["events"]))

    def test_lifecycle_network_artifact_is_added_on_close(self):
        config = {
            "bidiNegotiation": {"state": "supported", "mode": "auto"},
        }
        driver = Mock()
        driver.capabilities = {"webSocketUrl": "ws://grid/session/secret"}
        lifecycle = IdeliumSelenium._start_bidi_session(driver, config)
        lifecycle.record_network_event({"type": "network.fetchError"})

        IdeliumSelenium.close_bidi_session(config)

        artifact_types = {artifact["type"] for artifact in config["bidiArtifacts"]}
        self.assertIn("application/vnd.idelium.bidi.network+json", artifact_types)

    def test_javascript_error_diagnostic_is_redacted_and_bounded(self):
        normalized = normalize_bidi_diagnostic_event(
            {
                "type": "script.exceptionThrown",
                "params": {
                    "timestamp": 123,
                    "exceptionDetails": {
                        "text": "Uncaught token=abc123 private-value",
                        "url": "https://app.test/page?session=secret&view=1",
                        "lineNumber": 10,
                        "columnNumber": 5,
                    },
                },
            },
            sequence=7,
            sensitive_values=["private-value"],
        )

        self.assertEqual(7, normalized["sequence"])
        self.assertEqual("javascript-error", normalized["kind"])
        self.assertEqual("Uncaught token=[REDACTED] [REDACTED]", normalized["message"])
        self.assertEqual(
            "https://app.test/page?session=%5BREDACTED%5D&view=1",
            normalized["url"],
        )
        self.assertEqual(10, normalized["lineNumber"])

    def test_navigation_diagnostic_preserves_ordering_fields(self):
        normalized = normalize_bidi_diagnostic_event(
            {
                "type": "browsingContext.navigationStarted",
                "params": {
                    "timestamp": 456,
                    "context": "context-1",
                    "navigation": "navigation-2",
                    "url": "https://app.test/home?token=abc",
                },
            },
            sequence=2,
        )

        self.assertEqual(2, normalized["sequence"])
        self.assertEqual("navigation", normalized["kind"])
        self.assertEqual("context-1", normalized["context"])
        self.assertEqual("navigation-2", normalized["navigation"])
        self.assertIn("token=%5BREDACTED%5D", normalized["url"])

    def test_diagnostic_artifact_tracks_truncated_and_dropped_events(self):
        events = [
            normalize_bidi_diagnostic_event(
                {
                    "type": "browsingContext.load",
                    "params": {"url": f"https://app.test/{index}"},
                },
                sequence=index,
            )
            for index in range(3)
        ]

        artifact = build_bidi_diagnostic_artifact(events, dropped_events=1, limit=2)

        self.assertEqual("bidi-diagnostics", artifact["name"])
        self.assertEqual(3, artifact["data"]["totalEvents"])
        self.assertEqual(1, artifact["data"]["droppedEvents"])
        self.assertTrue(artifact["data"]["truncated"])
        self.assertEqual(
            [0, 1], [event["sequence"] for event in artifact["data"]["events"]]
        )

    def test_lifecycle_diagnostic_artifact_is_added_on_close(self):
        config = {
            "bidiNegotiation": {"state": "supported", "mode": "auto"},
        }
        driver = Mock()
        driver.capabilities = {"webSocketUrl": "ws://grid/session/secret"}
        lifecycle = IdeliumSelenium._start_bidi_session(driver, config)
        lifecycle.record_diagnostic_event(
            {
                "type": "runtime.exceptionThrown",
                "params": {"message": "password=hunter2"},
            }
        )

        IdeliumSelenium.close_bidi_session(config)

        artifacts = {artifact["type"]: artifact for artifact in config["bidiArtifacts"]}
        diagnostic = artifacts["application/vnd.idelium.bidi.diagnostics+json"]
        self.assertEqual(
            "password=[REDACTED]",
            diagnostic["data"]["events"][0]["message"],
        )


if __name__ == "__main__":
    unittest.main()
