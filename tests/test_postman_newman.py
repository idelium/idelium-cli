"""Unit tests for the optional Newman Postman runtime adapter."""

import json
import os
import tempfile
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

    def test_debug_directory_preserves_newman_inputs_and_report(self):
        def subprocess_runner(command, **kwargs):
            report_path = command[command.index("--reporter-json-export") + 1]
            with open(report_path, "w", encoding="utf-8") as file_obj:
                json.dump(
                    {
                        "run": {
                            "executions": [
                                {
                                    "item": {"name": "Echo"},
                                    "request": {
                                        "method": "GET",
                                        "url": {"raw": "https://example.test"},
                                    },
                                    "response": {"code": 200, "stream": "{}"},
                                    "assertions": [],
                                }
                            ],
                            "failures": [],
                        }
                    },
                    file_obj,
                )
            return SimpleNamespace(returncode=0)

        with tempfile.TemporaryDirectory() as debug_root:
            with patch.dict(os.environ, {"IDELIUM_POSTMAN_DEBUG_DIR": debug_root}):
                runner = PostmanNewmanCollection(
                    binary_resolver=lambda binary: "/usr/local/bin/" + binary,
                    subprocess_runner=subprocess_runner,
                )

                results = runner.start_postman_test(
                    {
                        "collection": {
                            "info": {"name": "Postman Echo"},
                            "item": [],
                        },
                    },
                    debug=True,
                )

            debug_runs = os.listdir(debug_root)
            self.assertTrue(results[0]["passed"])
            self.assertEqual(1, len(debug_runs))
            debug_run_dir = os.path.join(debug_root, debug_runs[0])
            self.assertTrue(
                os.path.exists(os.path.join(debug_run_dir, "collection.json"))
            )
            self.assertTrue(
                os.path.exists(os.path.join(debug_run_dir, "newman-report.json"))
            )

    def test_missing_newman_binary_returns_failed_idelium_result(self):
        runner = PostmanNewmanCollection(binary_resolver=lambda binary: None)

        results = runner.start_postman_test(
            {"collection": {"info": {"name": "Postman Echo"}, "item": []}}
        )

        self.assertFalse(results[0]["passed"])
        self.assertIn("was not found on PATH", results[0]["assertions"][0]["message"])
        self.assertIn("npm install -g newman", results[0]["assertions"][0]["message"])
        self.assertIn("newman --version", results[0]["assertions"][0]["message"])

    @patch("idelium._internal.thirdparties.ideliumpostman.printer")
    def test_missing_newman_binary_is_visible_in_debug_output(self, printer_mock):
        runner = PostmanNewmanCollection(binary_resolver=lambda binary: None)

        results = runner.start_postman_test(
            {"collection": {"info": {"name": "Postman Echo"}, "item": []}},
            debug=True,
        )

        self.assertFalse(results[0]["passed"])
        message = printer_mock.danger.call_args.args[0]
        self.assertIn("Newman is required", message)
        self.assertIn("npm install -g newman", message)
        self.assertIn("newman --version", message)

    @patch("idelium._internal.thirdparties.ideliumpostman.printer")
    def test_missing_newman_binary_is_visible_without_debug(self, printer_mock):
        runner = PostmanNewmanCollection(binary_resolver=lambda binary: None)

        results = runner.start_postman_test(
            {"collection": {"info": {"name": "Postman Echo"}, "item": []}},
            debug=False,
        )

        self.assertFalse(results[0]["passed"])
        printer_mock.danger.assert_called_once()
        self.assertIn("npm install -g newman", printer_mock.danger.call_args.args[0])

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
    def manager_config(self, step):
        return {
            "wrapper": Mock(),
            "printer": Mock(),
            "json_step": {"steps": [step]},
            "is_debug": False,
        }

    @patch("idelium._internal.ideliummanager.PostmanNewmanCollection")
    def test_postman_newman_runtime_is_selected_explicitly(self, newman_class):
        newman_class.return_value.start_postman_test.return_value = [
            {"passed": True, "assertions": [{"name": "newman", "passed": True}]}
        ]
        config = self.manager_config(
            {
                "stepType": "postman_collection",
                "collection": {
                    "runtime": "postman_newman",
                    "collection": {"item": []},
                },
            }
        )

        result = StartManager.execute_step(None, config)

        self.assertEqual("1", result["status"])
        self.assertEqual("postman", result["type"])
        newman_class.return_value.start_postman_test.assert_called_once()

    @patch("idelium._internal.ideliummanager.PostmanCollection")
    @patch("idelium._internal.ideliummanager.PostmanNewmanCollection")
    def test_postman_runtime_uses_newman_for_web_imported_collections(
        self, newman_class, safe_class
    ):
        newman_class.return_value.start_postman_test.return_value = [
            {"passed": True, "assertions": [{"name": "pm.test", "passed": True}]}
        ]
        config = self.manager_config(
            {
                "stepType": "postman_collection",
                "runtime": "postman",
                "collection": {
                    "collection": {
                        "item": [
                            {
                                "name": "scripted request",
                                "request": {
                                    "method": "GET",
                                    "url": "https://example.test",
                                },
                                "event": [
                                    {
                                        "listen": "test",
                                        "script": {
                                            "exec": ["pm.test('status', () => {})"]
                                        },
                                    }
                                ],
                            }
                        ],
                    },
                },
            }
        )

        result = StartManager.execute_step(None, config)

        self.assertEqual("1", result["status"])
        newman_class.return_value.start_postman_test.assert_called_once()
        safe_class.assert_not_called()

    @patch("idelium._internal.ideliummanager.PostmanCollection")
    @patch("idelium._internal.ideliummanager.PostmanNewmanCollection")
    def test_postman_auto_runtime_uses_newman_for_postman_scripts(
        self, newman_class, safe_class
    ):
        newman_class.return_value.start_postman_test.return_value = [
            {"passed": True, "assertions": [{"name": "pm.test", "passed": True}]}
        ]
        config = self.manager_config(
            {
                "stepType": "postman_collection",
                "collection": {
                    "runtime": "postman_auto",
                    "collection": {
                        "item": [
                            {
                                "name": "scripted request",
                                "request": {
                                    "method": "GET",
                                    "url": "https://example.test",
                                },
                                "event": [
                                    {
                                        "listen": "test",
                                        "script": {
                                            "exec": ["pm.test('status', () => {})"]
                                        },
                                    }
                                ],
                            }
                        ],
                    },
                },
            }
        )

        result = StartManager.execute_step(None, config)

        self.assertEqual("1", result["status"])
        newman_class.return_value.start_postman_test.assert_called_once()
        safe_class.assert_not_called()

    @patch("idelium._internal.ideliummanager.PostmanCollection")
    @patch("idelium._internal.ideliummanager.PostmanNewmanCollection")
    def test_postman_auto_runtime_uses_newman_for_legacy_postman_tests(
        self, newman_class, safe_class
    ):
        newman_class.return_value.start_postman_test.return_value = [
            {"passed": True, "assertions": [{"name": "legacy tests", "passed": True}]}
        ]
        config = self.manager_config(
            {
                "stepType": "postman_collection",
                "collection": {
                    "runtime": "postman_auto",
                    "collection": {
                        "info": {"name": "Postman Echo"},
                        "item": [
                            {
                                "name": "POST Raw Text",
                                "request": {
                                    "method": "POST",
                                    "url": "https://postman-echo.com/post",
                                    "body": {
                                        "mode": "raw",
                                        "raw": "Duis posuere augue vel cursus.",
                                    },
                                },
                                "event": [
                                    {
                                        "listen": "test",
                                        "script": {
                                            "exec": [
                                                "tests['response is valid JSON'] = true;",
                                                "postman.setGlobalVariable('echo', 'ok');",
                                            ]
                                        },
                                    }
                                ],
                            }
                        ],
                    },
                },
            }
        )

        result = StartManager.execute_step(None, config)

        self.assertEqual("1", result["status"])
        newman_class.return_value.start_postman_test.assert_called_once()
        safe_class.assert_not_called()

    @patch("idelium._internal.ideliummanager.PostmanCollection")
    @patch("idelium._internal.ideliummanager.PostmanNewmanCollection")
    def test_verbose_postman_runtime_diagnostics_are_non_sensitive(
        self, newman_class, safe_class
    ):
        newman_class.return_value.start_postman_test.return_value = [
            {
                "name": "request",
                "method": "POST",
                "status": "200",
                "passed": True,
                "assertions": [{"name": "status", "passed": True}],
            }
        ]
        config = self.manager_config(
            {
                "stepType": "postman_collection",
                "runtime": "postman",
                "collection": {
                    "collection": {
                        "item": [
                            {
                                "name": "request",
                                "request": {
                                    "method": "POST",
                                    "url": "https://example.test?token=secret",
                                },
                                "event": [
                                    {
                                        "listen": "test",
                                        "script": {"exec": ["tests['ok'] = true;"]},
                                    }
                                ],
                            }
                        ],
                    },
                },
            }
        )
        config["is_debug"] = True

        result = StartManager.execute_step(None, config)

        self.assertEqual("1", result["status"])
        config["printer"].print_important_text.assert_any_call(
            "Postman runtime: requested=postman, runner=newman, requests=1, events=1"
        )
        config["printer"].print_important_text.assert_any_call(
            "Postman result: PASSED POST 200 request"
        )
        safe_class.assert_not_called()

    @patch("idelium._internal.ideliummanager.PostmanCollection")
    @patch("idelium._internal.ideliummanager.PostmanNewmanCollection")
    def test_verbose_postman_runtime_prints_failed_assertions(
        self, newman_class, safe_class
    ):
        newman_class.return_value.start_postman_test.return_value = [
            {
                "name": "Newman",
                "method": "NEWMAN",
                "status": "0",
                "passed": False,
                "assertions": [
                    {
                        "name": "newman",
                        "passed": False,
                        "message": PostmanNewmanCollection.NEWMAN_MISSING_MESSAGE,
                    }
                ],
            }
        ]
        config = self.manager_config(
            {
                "stepType": "postman_collection",
                "runtime": "postman",
                "collection": {"collection": {"item": []}},
            }
        )
        config["is_debug"] = True

        result = StartManager.execute_step(None, config)

        self.assertEqual("2", result["status"])
        config["printer"].print_important_text.assert_any_call(
            "Postman result: FAILED NEWMAN 0 Newman"
        )
        config["printer"].danger.assert_called_with(
            "newman: " + PostmanNewmanCollection.NEWMAN_MISSING_MESSAGE
        )
        safe_class.assert_not_called()

    @patch("idelium._internal.ideliummanager.PostmanCollection")
    @patch("idelium._internal.ideliummanager.PostmanNewmanCollection")
    def test_postman_runtime_prints_failed_assertions_without_verbose(
        self, newman_class, safe_class
    ):
        newman_class.return_value.start_postman_test.return_value = [
            {
                "name": "Newman",
                "method": "NEWMAN",
                "status": "0",
                "passed": False,
                "assertions": [
                    {
                        "name": "newman",
                        "passed": False,
                        "message": PostmanNewmanCollection.NEWMAN_MISSING_MESSAGE,
                    }
                ],
            }
        ]
        config = self.manager_config(
            {
                "stepType": "postman_collection",
                "runtime": "postman",
                "collection": {"collection": {"item": []}},
            }
        )
        config["is_debug"] = False

        result = StartManager.execute_step(None, config)

        self.assertEqual("2", result["status"])
        config["printer"].danger.assert_called_with(
            "newman: " + PostmanNewmanCollection.NEWMAN_MISSING_MESSAGE
        )
        config["printer"].print_important_text.assert_not_called()
        safe_class.assert_not_called()

    @patch("idelium._internal.ideliummanager.PostmanCollection")
    @patch("idelium._internal.ideliummanager.PostmanNewmanCollection")
    def test_postman_auto_runtime_keeps_safe_runner_for_simple_collections(
        self, newman_class, safe_class
    ):
        safe_class.return_value.start_postman_test.return_value = [
            {"passed": True, "assertions": [{"name": "status", "passed": True}]}
        ]
        config = self.manager_config(
            {
                "stepType": "postman_collection",
                "collection": {
                    "collection": {
                        "item": [
                            {
                                "name": "simple request",
                                "request": {
                                    "method": "GET",
                                    "url": "https://example.test",
                                },
                            }
                        ],
                    },
                },
            }
        )

        result = StartManager.execute_step(None, config)

        self.assertEqual("1", result["status"])
        safe_class.return_value.start_postman_test.assert_called_once()
        newman_class.assert_not_called()

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
