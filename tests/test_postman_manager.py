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


if __name__ == "__main__":
    unittest.main()
