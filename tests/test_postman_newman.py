"""Unit tests for the optional Newman Postman runtime adapter."""

import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from idelium._internal.ideliumclib import InitIdelium
from idelium._internal.ideliummanager import StartManager
from idelium._internal.thirdparties.ideliumpostman import PostmanNewmanCollection


class PostmanNewmanCollectionTest(unittest.TestCase):
    def test_newman_command_includes_environment_and_iteration_data(self):
        calls = []

        def subprocess_runner(command, **kwargs):
            calls.append((command, kwargs))
            report_path = command[command.index("--reporter-json-export") + 1]
            collection_path = command[command.index("run") + 1]
            environment_path = command[command.index("--environment") + 1]
            data_path = command[command.index("--iteration-data") + 1]

            with open(collection_path, encoding="utf-8") as file_obj:
                self.assertEqual("Postman Echo", json.load(file_obj)["info"]["name"])
            with open(environment_path, encoding="utf-8") as file_obj:
                self.assertEqual("dev", json.load(file_obj)["name"])
            with open(data_path, encoding="utf-8") as file_obj:
                self.assertEqual([{"user": "demo"}], json.load(file_obj))

            with open(report_path, "w", encoding="utf-8") as file_obj:
                json.dump(
                    {
                        "run": {
                            "executions": [
                                {
                                    "item": {"id": "request-1", "name": "Echo"},
                                    "request": {
                                        "method": "GET",
                                        "url": {
                                            "raw": "https://example.test?token=secret"
                                        },
                                    },
                                    "response": {
                                        "code": 200,
                                        "responseTime": 34,
                                        "stream": json.dumps(
                                            {
                                                "ok": True,
                                                "access_token": "secret-token",
                                            }
                                        ),
                                    },
                                    "assertions": [
                                        {"assertion": "status is 200"},
                                    ],
                                }
                            ],
                            "failures": [],
                        }
                    },
                    file_obj,
                )
            return SimpleNamespace(returncode=0)

        runner = PostmanNewmanCollection(
            binary_resolver=lambda binary: "/usr/local/bin/" + binary,
            subprocess_runner=subprocess_runner,
            timeout=12,
        )

        results = runner.start_postman_test(
            {
                "collection": {"info": {"name": "Postman Echo"}, "item": []},
                "environment": {"name": "dev", "values": []},
                "iterationData": [{"user": "demo"}],
                "insecure": True,
            }
        )

        command, kwargs = calls[0]
        self.assertEqual("/usr/local/bin/newman", command[0])
        self.assertIn("--insecure", command)
        self.assertEqual(12, kwargs["timeout"])
        self.assertTrue(results[0]["passed"])
        self.assertEqual("200", results[0]["status"])
        self.assertEqual("https://example.test?token=%5BREDACTED%5D", results[0]["url"])
        self.assertEqual(
            {"ok": True, "access_token": "[REDACTED]"},
            json.loads(results[0]["response"]),
        )

    def test_missing_newman_binary_returns_failed_idelium_result(self):
        runner = PostmanNewmanCollection(binary_resolver=lambda binary: None)

        results = runner.start_postman_test(
            {"collection": {"info": {"name": "Postman Echo"}, "item": []}}
        )

        self.assertFalse(results[0]["passed"])
        self.assertIn("not installed", results[0]["assertions"][0]["message"])

    def test_newman_failures_are_mapped_to_failed_assertions(self):
        def subprocess_runner(command, **kwargs):
            report_path = command[command.index("--reporter-json-export") + 1]
            with open(report_path, "w", encoding="utf-8") as file_obj:
                json.dump(
                    {
                        "run": {
                            "executions": [
                                {
                                    "item": {"id": "request-1", "name": "Echo"},
                                    "request": {
                                        "method": "POST",
                                        "url": {"raw": "https://example.test"},
                                    },
                                    "response": {"code": 500, "stream": "{}"},
                                    "assertions": [
                                        {
                                            "assertion": "status is 200",
                                            "error": {
                                                "message": "expected 500 to equal 200"
                                            },
                                        }
                                    ],
                                }
                            ],
                            "failures": [
                                {
                                    "source": {"id": "request-1"},
                                    "at": "test-script",
                                    "error": {"message": "script failed"},
                                }
                            ],
                        }
                    },
                    file_obj,
                )
            return SimpleNamespace(returncode=1)

        runner = PostmanNewmanCollection(
            binary_resolver=lambda binary: "/usr/local/bin/" + binary,
            subprocess_runner=subprocess_runner,
        )

        results = runner.start_postman_test(
            {"collection": {"info": {"name": "Postman Echo"}, "item": []}}
        )

        self.assertFalse(results[0]["passed"])
        self.assertEqual(
            ["status is 200", "test-script"],
            [assertion["name"] for assertion in results[0]["assertions"]],
        )

    def test_missing_report_fails_safely(self):
        runner = PostmanNewmanCollection(
            binary_resolver=lambda binary: "/usr/local/bin/" + binary,
            subprocess_runner=lambda command, **kwargs: SimpleNamespace(returncode=0),
        )

        results = runner.start_postman_test(
            {"collection": {"info": {"name": "Postman Echo"}, "item": []}}
        )

        self.assertFalse(results[0]["passed"])
        self.assertIn("valid JSON report", results[0]["assertions"][0]["message"])


class PostmanNewmanManagerTest(unittest.TestCase):
    @patch("idelium._internal.ideliummanager.PostmanNewmanCollection")
    def test_postman_newman_runtime_is_selected_explicitly(self, newman_class):
        newman_class.return_value.start_postman_test.return_value = [
            {"passed": True, "assertions": [{"name": "newman", "passed": True}]}
        ]
        config = {
            "wrapper": Mock(),
            "printer": Mock(),
            "json_step": {
                "steps": [
                    {
                        "stepType": "postman_collection",
                        "collection": {
                            "runtime": "postman_newman",
                            "collection": {"item": []},
                        },
                    }
                ],
            },
            "is_debug": False,
        }

        result = StartManager.execute_step(None, config)

        self.assertEqual("1", result["status"])
        self.assertEqual("postman", result["type"])
        newman_class.return_value.start_postman_test.assert_called_once()

    def test_postman_newman_timeout_is_validated_with_http_timeouts(self):
        params = InitIdelium.get_default_parameters()
        params["postmanNewmanTimeout"] = "0"
        printer = Mock()

        with self.assertRaises(SystemExit):
            InitIdelium.configure_http(params, printer)

        printer.danger.assert_called_once_with(
            "HTTP timeouts must be greater than zero"
        )


if __name__ == "__main__":
    unittest.main()
