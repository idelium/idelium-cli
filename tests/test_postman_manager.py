"""Integration tests between the Postman runner and the step manager."""

import unittest
from unittest.mock import Mock, patch

from idelium._internal.ideliummanager import StartManager


class PostmanManagerTest(unittest.TestCase):
    @patch("idelium._internal.ideliummanager.PostmanCollection")
    def test_failed_postman_assertion_fails_the_idelium_step(self, postman_class):
        postman_class.return_value.start_postman_test.return_value = [
            {
                "passed": False,
                "assertions": [{"name": "body", "passed": False}],
            }
        ]
        step = {
            "stepType": "postman_collection",
            "collection": {"collection": {"item": []}},
        }
        config = {
            "wrapper": Mock(),
            "printer": Mock(),
            "json_step": {"steps": [step]},
            "is_debug": False,
        }

        result = StartManager.execute_step(None, config)

        self.assertEqual("2", result["status"])
        self.assertEqual(step, result["step_failed"])
        self.assertEqual("postman", result["type"])

    @patch("idelium._internal.ideliummanager.PostmanCollection")
    def test_successful_postman_assertions_keep_the_step_successful(
        self, postman_class
    ):
        postman_class.return_value.start_postman_test.return_value = [
            {
                "passed": True,
                "assertions": [{"name": "body", "passed": True}],
            }
        ]
        config = {
            "wrapper": Mock(),
            "printer": Mock(),
            "json_step": {
                "steps": [
                    {
                        "stepType": "postman_collection",
                        "collection": {"collection": {"item": []}},
                    }
                ],
            },
            "is_debug": False,
        }

        result = StartManager.execute_step(None, config)

        self.assertEqual("1", result["status"])
        self.assertEqual("", result["step_failed"])

    @patch("idelium._internal.ideliummanager.PostmanCollection")
    def test_postman_step_is_detected_from_normalized_type(self, postman_class):
        postman_result = [
            {
                "name": "Get health",
                "method": "GET",
                "status": 200,
                "passed": True,
                "assertions": [{"name": "status", "passed": True}],
            }
        ]
        postman_class.return_value.start_postman_test.return_value = postman_result
        config = {
            "wrapper": Mock(),
            "printer": Mock(),
            "json_step": {
                "steps": [
                    {
                        "type": "postman_collection",
                        "collection": {"collection": {"item": []}},
                    }
                ],
            },
            "is_debug": False,
        }

        result = StartManager.execute_step(None, config)

        self.assertEqual("1", result["status"])
        self.assertEqual("postman", result["type"])
        self.assertEqual(postman_result, result["postman_data"])
        config["wrapper"].command.assert_not_called()

    def test_empty_postman_step_fails_with_actionable_diagnostic(self):
        printer = Mock()
        config = {
            "wrapper": Mock(),
            "printer": printer,
            "json_step": {
                "name": "Postman",
                "editorType": "postman",
                "steps": [],
            },
            "is_debug": False,
        }

        result = StartManager.execute_step(None, config)

        self.assertEqual("2", result["status"])
        self.assertEqual("postman", result["type"])
        self.assertEqual(config["json_step"], result["step_failed"])
        self.assertFalse(result["postman_data"][0]["passed"])
        printer.danger.assert_called_once_with(
            "Postman step has no executable collection. Re-import the test with a "
            "postman_collection action that contains the Postman collection payload."
        )
        config["wrapper"].command.assert_not_called()

    def test_postman_request_results_are_printed_without_debug_mode(self):
        printer = Mock()
        results = [
            {
                "name": "Echo GET",
                "method": "GET",
                "status": "200",
                "url": "https://postman-echo.com/get?source=idelium",
                "time": 42,
                "passed": True,
                "assertions": [{"name": "status", "passed": True}],
            },
            {
                "name": "Echo POST",
                "method": "POST",
                "status": "500",
                "url": "https://postman-echo.com/post",
                "time": 60,
                "passed": False,
                "assertions": [{"name": "status", "passed": False}],
            },
        ]

        StartManager._print_postman_results(printer, results)

        printer.print_important_text.assert_called_once_with("Postman calls:")
        printer.success.assert_called_once_with(
            "[1/2] PASSED GET 200 42ms https://postman-echo.com/get?source=idelium - Echo GET (1/1 assertions)"
        )
        printer.danger.assert_called_once_with(
            "[2/2] FAILED POST 500 60ms https://postman-echo.com/post - Echo POST (0/1 assertions)"
        )


if __name__ == "__main__":
    unittest.main()
