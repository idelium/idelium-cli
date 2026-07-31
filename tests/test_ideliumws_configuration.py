import unittest
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from idelium._internal.commons.connection import HttpTransportError
from idelium._internal.exitcodes import (
    EXIT_DEPENDENCY_ERROR,
    EXIT_SUCCESS,
    EXIT_TEST_FAILURE,
    EXIT_VALIDATION_ERROR,
)
from idelium._internal.ideliumws import IdeliumWs


class IdeliumWsConfigurationTest(unittest.TestCase):
    def test_start_test_returns_validation_error_when_cycle_has_no_entries(self):
        web_service = IdeliumWs()
        printer = Mock()
        config = {
            "idCycle": "3",
            "idProject": "1",
            "test": False,
            "ideliumServer": False,
            "printer": printer,
        }
        idelium = Mock()
        idelium.get_wrapper.return_value = Mock()

        with (
            patch.object(web_service, "get_cycles", return_value=[]),
            patch.object(web_service, "create_folder") as create_folder,
        ):
            exit_code = web_service.start_test(idelium, {"steps": {}}, config)

        self.assertEqual(EXIT_VALIDATION_ERROR, exit_code)
        create_folder.assert_not_called()
        printer.danger.assert_called_once_with(
            "Remote test cycle configuration is inconsistent: "
            "test cycle 3 contains no executable tests."
        )

    def test_start_test_returns_validation_error_when_cycle_has_no_tests(self):
        web_service = IdeliumWs()
        printer = Mock()
        config = {
            "idCycle": "3",
            "idProject": "1",
            "test": False,
            "ideliumServer": False,
            "printer": printer,
        }
        idelium = Mock()
        idelium.get_wrapper.return_value = Mock()

        with (
            patch.object(
                web_service,
                "get_cycles",
                return_value=[
                    {"id": 3, "name": "empty cycle", "description": "empty cycle"}
                ],
            ),
            patch.object(web_service, "get_tests", return_value=[]),
            patch.object(
                web_service, "create_folder", return_value={"idCycle": 77}
            ),
            patch.object(web_service, "create_test") as create_test,
        ):
            exit_code = web_service.start_test(idelium, {"steps": {}}, config)

        self.assertEqual(EXIT_VALIDATION_ERROR, exit_code)
        create_test.assert_not_called()
        printer.danger.assert_called_once_with(
            "Remote test cycle configuration is inconsistent: "
            "test cycle 3 contains no executable tests."
        )

    def test_missing_cycle_explains_cycle_id_not_imported_test_id(self):
        web_service = IdeliumWs()
        config = {
            "api_idelium": "https://localhost/api/ideliumcl/",
            "idCycle": "5",
            "idProject": "1",
            "ideliumKey": "local-test-key",
            "is_debug": False,
            "local": False,
            "forcedownload": False,
            "ideliumServer": False,
            "dir_idelium_scripts": "/tmp/idelium-test",
            "printer": Mock(),
        }

        with (
            patch.object(web_service, "create_directories", return_value=[""] * 7),
            patch.object(
                web_service,
                "get_cycles",
                side_effect=HttpTransportError(
                    "GET request returned HTTP 404 for "
                    "https://localhost/api/ideliumcl/testcycle/5",
                    status_code=404,
                ),
            ),
        ):
            with self.assertRaises(HttpTransportError) as raised:
                web_service.get_configuration(config)

        message = str(raised.exception)
        self.assertIn("test cycle 5 was not found", message)
        self.assertIn("Use the test cycle ID, not the imported test ID", message)
        self.assertIn("verify project 1", message)

    def test_missing_referenced_step_returns_configuration_context(self):
        web_service = IdeliumWs()
        config = {
            "api_idelium": "https://localhost/api/ideliumcl/",
            "idCycle": "1",
            "idProject": "1",
            "ideliumKey": "local-test-key",
            "is_debug": False,
            "local": False,
            "forcedownload": False,
            "ideliumServer": False,
            "dir_idelium_scripts": "/tmp/idelium-test",
            "printer": Mock(),
        }

        with (
            patch.object(web_service, "create_directories", return_value=[""] * 7),
            patch.object(web_service, "get_cycles", return_value=[{"id": 1}]),
            patch.object(web_service, "get_tests", return_value=[{"id": 2}]),
            patch.object(
                web_service,
                "get_step",
                side_effect=HttpTransportError(
                    "GET request returned HTTP 404 for "
                    "https://localhost/api/ideliumcl/step/2",
                    status_code=404,
                ),
            ),
        ):
            with self.assertRaises(HttpTransportError) as raised:
                web_service.get_configuration(config)

        message = str(raised.exception)
        self.assertIn("Remote test cycle configuration is inconsistent", message)
        self.assertIn("test cycle 1 references missing step 2", message)

    def test_server_error_for_referenced_test_returns_api_failure_context(self):
        web_service = IdeliumWs()
        config = {
            "api_idelium": "https://localhost/api/ideliumcl/",
            "idCycle": "5",
            "idProject": "1",
            "ideliumKey": "local-test-key",
            "is_debug": False,
            "local": False,
            "forcedownload": False,
            "ideliumServer": False,
            "dir_idelium_scripts": "/tmp/idelium-test",
            "printer": Mock(),
        }

        with (
            patch.object(web_service, "create_directories", return_value=[""] * 7),
            patch.object(web_service, "get_cycles", return_value=[{"id": 2}]),
            patch.object(
                web_service,
                "get_tests",
                side_effect=HttpTransportError(
                    "GET request returned HTTP 500 for "
                    "https://localhost/api/ideliumcl/test/2",
                    status_code=500,
                ),
            ),
        ):
            with self.assertRaises(HttpTransportError) as raised:
                web_service.get_configuration(config)

        message = str(raised.exception)
        self.assertIn("Remote test cycle configuration is inconsistent", message)
        self.assertIn(
            "test cycle 5 could not load referenced test 2; "
            "the Idelium API returned an unexpected response",
            message,
        )
        self.assertNotIn("references missing test 2", message)

    def test_result_creation_uses_performed_cycle_and_source_resource_ids(self):
        config = {
            "api_idelium": "https://localhost/api/ideliumcl/",
            "idCycle": "2",
            "ideliumKey": "local-test-key",
            "is_debug": False,
        }

        with patch("idelium._internal.ideliumws.Connection.start") as start:
            start.side_effect = [{"idTest": 91}, {"idStep": 92}]

            created_test = IdeliumWs.create_test(
                config,
                id_cycle=77,
                id_test=16,
                name="postman",
            )
            created_step = IdeliumWs.create_step(
                config,
                id_cycle=77,
                id_test=91,
                id_step=16,
                name="postman request",
                status="1",
                data=[],
                typeofstep="postman",
            )

        self.assertEqual({"idTest": 91}, created_test)
        self.assertEqual({"idStep": 92}, created_step)
        self.assertEqual(
            {
                "testCycleId": 77,
                "testId": 16,
                "name": "postman",
            },
            start.call_args_list[0].args[2],
        )
        self.assertEqual(
            {
                "testCycleId": 77,
                "testId": 91,
                "stepId": 16,
                "name": "postman request",
                "status": 1,
                "data": "[]",
                "type": "postman",
                "screenshots": "[]",
            },
            start.call_args_list[1].args[2],
        )

    def test_performed_cycle_finalization_uses_terminal_status(self):
        config = {
            "api_idelium": "https://localhost/api/ideliumcl/",
            "idCycle": "2",
            "ideliumKey": "local-test-key",
            "is_debug": False,
        }

        with patch("idelium._internal.ideliumws.Connection.start") as start:
            start.return_value = {"idCycle": 77}

            result = IdeliumWs.update_folder(config, id_cycle=77, status=2)

        self.assertEqual({"idCycle": 77}, result)
        self.assertEqual("PUT", start.call_args.args[0])
        self.assertEqual(
            "https://localhost/api/ideliumcl/testcycle",
            start.call_args.args[1],
        )
        self.assertEqual(
            {
                "testCycleId": 77,
                "status": 2,
            },
            start.call_args.args[2],
        )

    def test_remote_execution_finalizes_failed_performed_cycle(self):
        web_service = IdeliumWs()
        printer = Mock()
        config = {
            "api_idelium": "https://localhost/api/ideliumcl/",
            "idCycle": "2",
            "idProject": "3",
            "ideliumKey": "local-test-key",
            "is_debug": False,
            "test": False,
            "ideliumServer": False,
            "printer": printer,
        }
        test_configurations = {
            "steps": {
                "postman_17": {
                    "name": "postman",
                    "attachScreenshot": False,
                    "failedExit": False,
                }
            }
        }
        idelium = Mock()
        idelium.get_wrapper.return_value = Mock()
        idelium.execute_step.return_value = {
            "status": "2",
            "driver": None,
            "postman_data": [],
            "type": "postman",
            "step_failed": {"stepType": "postman_collection"},
        }

        with (
            patch.object(web_service, "get_cycles") as get_cycles,
            patch.object(web_service, "get_tests") as get_tests,
            patch.object(web_service, "create_folder") as create_folder,
            patch.object(web_service, "create_test") as create_test,
            patch.object(web_service, "create_step") as create_step,
            patch.object(web_service, "update_test"),
            patch.object(web_service, "update_folder") as update_folder,
        ):
            get_cycles.return_value = [
                {"id": 11, "name": "postman cycle", "description": "postman cycle"}
            ]
            get_tests.return_value = [{"id": 17, "name": "postman"}]
            create_folder.return_value = {"idCycle": 77}
            create_test.return_value = {"idTest": 91}
            create_step.return_value = {"idStep": 92}

            exit_code = web_service.start_test(idelium, test_configurations, config)

        self.assertEqual(EXIT_TEST_FAILURE, exit_code)
        update_folder.assert_called_once_with(config, 77, 2)

    def test_remote_execution_reports_finalize_transport_failure(self):
        web_service = IdeliumWs()
        printer = Mock()
        config = {
            "api_idelium": "https://localhost/api/ideliumcl/",
            "idCycle": "2",
            "idProject": "3",
            "ideliumKey": "local-test-key",
            "is_debug": False,
            "test": False,
            "ideliumServer": False,
            "printer": printer,
        }

        with patch.object(
            web_service,
            "update_folder",
            side_effect=HttpTransportError("PUT request returned HTTP 500"),
        ):
            exit_code = web_service._finalize_performed_cycle(
                config,
                id_cycle=77,
                exit_code=EXIT_SUCCESS,
                printer=printer,
            )

        self.assertNotEqual(EXIT_SUCCESS, exit_code)
        printer.danger.assert_called_once_with(
            "Unable to finalize the remote performed test cycle 77: "
            "PUT request returned HTTP 500"
        )

    def test_step_creation_accepts_versioned_performed_trace_in_data_contract(self):
        config = {
            "api_idelium": "https://localhost/api/ideliumcl/",
            "idCycle": "2",
            "ideliumKey": "local-test-key",
            "is_debug": False,
        }
        performed_result = {
            "schemaVersion": "performed-step-result.v1",
            "trace": {
                "schemaVersion": "performed-step-trace.v1",
                "identity": {"kind": "click"},
                "timing": {"durationMilliseconds": 7},
                "status": "failed",
                "locator": {"strategy": "css", "value": "#login"},
                "page": {"url": "https://example.invalid/login", "title": "Login"},
                "diagnostics": [
                    {
                        "level": "error",
                        "code": "IDELIUM_DSL_RUNTIME_LOCATOR_NOT_FOUND",
                        "category": "locator",
                        "message": "Element was not found.",
                    }
                ],
            },
        }

        with patch("idelium._internal.ideliumws.Connection.start") as start:
            start.return_value = {"idStep": 93}

            IdeliumWs.create_step(
                config,
                id_cycle=77,
                id_test=91,
                id_step=16,
                name="click login",
                status="2",
                data=performed_result,
                typeofstep="seleniumOrAppium",
            )

        payload = start.call_args.args[2]
        serialized_data = json.loads(payload["data"])
        self.assertEqual("performed-step-result.v1", serialized_data["schemaVersion"])
        self.assertEqual(
            "performed-step-trace.v1",
            serialized_data["trace"]["schemaVersion"],
        )
        self.assertEqual(2, payload["status"])

    def test_test_mode_does_not_create_or_update_remote_results(self):
        web_service = IdeliumWs()
        printer = Mock()
        config = {
            "idCycle": "2",
            "idProject": "3",
            "test": True,
            "ideliumServer": False,
            "printer": printer,
        }
        test_configurations = {
            "steps": {
                "postman_17": {
                    "name": "postman",
                    "attachScreenshot": False,
                    "failedExit": False,
                },
                "should-not-run_18": {
                    "name": "should-not-run",
                    "type": "selenium",
                    "attachScreenshot": False,
                    "failedExit": False,
                }
            }
        }
        idelium = Mock()
        idelium.get_wrapper.return_value = Mock()
        idelium.execute_step.return_value = {
            "status": "1",
            "driver": None,
            "postman_data": [],
            "type": "postman",
            "step_failed": "",
        }

        with (
            patch.object(web_service, "get_cycles") as get_cycles,
            patch.object(web_service, "get_tests") as get_tests,
            patch.object(web_service, "create_folder") as create_folder,
            patch.object(web_service, "create_test") as create_test,
            patch.object(web_service, "create_step") as create_step,
            patch.object(web_service, "update_test") as update_test,
        ):
            get_cycles.return_value = [
                {"id": 11, "name": "postman cycle", "description": "postman cycle"}
            ]
            get_tests.return_value = [{"id": 17, "name": "postman"}]

            web_service.start_test(idelium, test_configurations, config)

        create_folder.assert_not_called()
        create_test.assert_not_called()
        create_step.assert_not_called()
        update_test.assert_not_called()

    def test_postman_failure_is_registered_and_stops_execution(self):
        web_service = IdeliumWs()
        printer = Mock()
        postman_data = [
            {
                "name": "Newman",
                "method": "NEWMAN",
                "status": "0",
                "passed": False,
                "assertions": [
                    {
                        "name": "newman",
                        "passed": False,
                        "message": "Newman was not found on PATH.",
                    }
                ],
            }
        ]
        config = {
            "idCycle": "2",
            "idProject": "3",
            "test": False,
            "ideliumServer": False,
            "printer": printer,
        }
        test_configurations = {
            "steps": {
                "postman_17": {
                    "name": "postman",
                    "attachScreenshot": False,
                    "failedExit": False,
                }
            }
        }
        idelium = Mock()
        idelium.get_wrapper.return_value = Mock()
        idelium.execute_step.return_value = {
            "status": "2",
            "driver": None,
            "postman_data": postman_data,
            "type": "postman",
            "step_failed": {"stepType": "postman_collection"},
        }

        with (
            patch.object(web_service, "get_cycles") as get_cycles,
            patch.object(web_service, "get_tests") as get_tests,
            patch.object(web_service, "create_folder") as create_folder,
            patch.object(web_service, "create_test") as create_test,
            patch.object(web_service, "create_step") as create_step,
            patch.object(web_service, "update_test") as update_test,
        ):
            get_cycles.return_value = [
                {"id": 11, "name": "postman cycle", "description": "postman cycle"}
            ]
            get_tests.return_value = [
                {"id": 17, "name": "postman"},
                {"id": 18, "name": "should-not-run"},
            ]
            create_folder.return_value = {"idCycle": 77}
            create_test.return_value = {"idTest": 91}
            create_step.return_value = {"idStep": 92}

            exit_code = web_service.start_test(idelium, test_configurations, config)

        self.assertEqual(EXIT_TEST_FAILURE, exit_code)
        self.assertEqual(2, create_step.call_count)
        self.assertEqual("2", create_step.call_args_list[0].args[5])
        self.assertEqual(18, create_step.call_args_list[1].args[3])
        self.assertEqual("should-not-run", create_step.call_args_list[1].args[4])
        self.assertEqual("5", create_step.call_args_list[1].args[5])
        self.assertEqual("seleniumOrAppium", create_step.call_args_list[1].args[7])
        self.assertEqual(
            "Step skipped because a previous required step failed.",
            create_step.call_args_list[1].args[6]["diagnostics"][0]["message"],
        )
        update_test.assert_called_once_with(config, 91, 2, postman_data)
        idelium.execute_step.assert_called_once()
        printer.danger.assert_called_with(
            "The test 'postman cycle' was interrupted because a required step failed"
        )

    def test_postman_dependency_failure_returns_dependency_exit_code(self):
        web_service = IdeliumWs()
        printer = Mock()
        postman_data = [
            {
                "name": "Newman",
                "method": "NEWMAN",
                "status": "0",
                "passed": False,
                "assertions": [
                    {
                        "name": "newman",
                        "passed": False,
                        "message": "Newman was not found on PATH.",
                    }
                ],
            }
        ]
        config = {
            "idCycle": "2",
            "idProject": "3",
            "test": False,
            "ideliumServer": False,
            "printer": printer,
        }
        test_configurations = {
            "steps": {
                "postman_17": {
                    "name": "postman",
                    "attachScreenshot": False,
                    "failedExit": False,
                }
            }
        }
        idelium = Mock()
        idelium.get_wrapper.return_value = Mock()
        idelium.execute_step.return_value = {
            "status": "2",
            "driver": None,
            "postman_data": postman_data,
            "type": "postman",
            "step_failed": {"stepType": "postman_collection"},
            "dependency_failed": True,
        }

        with (
            patch.object(web_service, "get_cycles") as get_cycles,
            patch.object(web_service, "get_tests") as get_tests,
            patch.object(web_service, "create_folder") as create_folder,
            patch.object(web_service, "create_test") as create_test,
            patch.object(web_service, "create_step") as create_step,
            patch.object(web_service, "update_test") as update_test,
        ):
            get_cycles.return_value = [
                {"id": 11, "name": "postman cycle", "description": "postman cycle"}
            ]
            get_tests.return_value = [{"id": 17, "name": "postman"}]
            create_folder.return_value = {"idCycle": 77}
            create_test.return_value = {"idTest": 91}
            create_step.return_value = {"idStep": 92}

            exit_code = web_service.start_test(idelium, test_configurations, config)

        self.assertEqual(EXIT_DEPENDENCY_ERROR, exit_code)
        create_step.assert_called_once()
        update_test.assert_called_once_with(config, 91, 2, postman_data)

    def test_unexpected_step_error_marks_remote_test_failed(self):
        web_service = IdeliumWs()
        printer = Mock()
        config = {
            "idCycle": "2",
            "idProject": "3",
            "test": False,
            "ideliumServer": False,
            "printer": printer,
        }
        test_configurations = {
            "steps": {
                "login_17": {
                    "name": "login",
                    "type": "selenium",
                    "attachScreenshot": False,
                    "failedExit": True,
                }
            }
        }
        idelium = Mock()
        idelium.get_wrapper.return_value = Mock()
        idelium.execute_step.side_effect = RuntimeError(
            "browser crashed token=secret-value"
        )

        with (
            patch.object(web_service, "get_cycles") as get_cycles,
            patch.object(web_service, "get_tests") as get_tests,
            patch.object(web_service, "create_folder") as create_folder,
            patch.object(web_service, "create_test") as create_test,
            patch.object(web_service, "create_step") as create_step,
            patch.object(web_service, "update_test") as update_test,
        ):
            get_cycles.return_value = [
                {"id": 11, "name": "regression", "description": "regression"}
            ]
            get_tests.return_value = [{"id": 17, "name": "login"}]
            create_folder.return_value = {"idCycle": 77}
            create_test.return_value = {"idTest": 91}
            create_step.return_value = {"idStep": 92}

            exit_code = web_service.start_test(idelium, test_configurations, config)

        self.assertEqual(EXIT_TEST_FAILURE, exit_code)
        create_step.assert_called_once()
        self.assertEqual("2", create_step.call_args.args[5])
        payload = create_step.call_args.args[6]
        self.assertEqual("failed", payload["summary"]["status"])
        self.assertIn("token=[REDACTED]", payload["diagnostics"][0]["message"])
        self.assertNotIn("secret-value", json.dumps(payload))
        update_test.assert_called_once_with(config, 91, 2, [])
        printer.danger.assert_any_call(
            "Step failed with an unexpected CLI error: "
            "browser crashed token=[REDACTED]"
        )
        printer.danger.assert_any_call(
            "The test 'regression' was interrupted because a required step failed"
        )

    def test_local_execution_reports_are_written_from_canonical_result(self):
        web_service = IdeliumWs()
        printer = Mock()
        postman_data = [
            {
                "name": "POST Raw Text",
                "method": "POST",
                "url": "https://example.invalid/post?token=secret",
                "status": "500",
                "passed": False,
                "time": 10,
                "assertions": [
                    {
                        "name": "status",
                        "passed": False,
                        "message": "token abc failed",
                    }
                ],
            }
        ]
        idelium = Mock()
        idelium.get_wrapper.return_value = Mock()
        idelium.execute_step.return_value = {
            "status": "2",
            "driver": None,
            "postman_data": postman_data,
            "type": "postman",
            "step_failed": {"stepType": "postman_collection"},
        }

        with tempfile.TemporaryDirectory() as directory:
            json_report = directory + "/report.json"
            html_report = directory + "/report.html"
            markdown_report = directory + "/report.md"
            junit_report = directory + "/report.xml"
            config = {
                "idCycle": "2",
                "idProject": "3",
                "environment": "envpost",
                "reportingService": "idelium",
                "test": True,
                "ideliumServer": False,
                "printer": printer,
                "jsonReport": json_report,
                "htmlReport": html_report,
                "markdownReport": markdown_report,
                "junitReport": junit_report,
            }
            test_configurations = {
                "steps": {
                    "postman_17": {
                        "name": "postman",
                        "attachScreenshot": False,
                        "failedExit": False,
                    }
                }
            }

            with (
                patch.object(web_service, "get_cycles") as get_cycles,
                patch.object(web_service, "get_tests") as get_tests,
            ):
                get_cycles.return_value = [
                    {
                        "id": 11,
                        "name": "postman cycle",
                        "description": "postman cycle",
                    }
                ]
                get_tests.return_value = [{"id": 17, "name": "postman"}]

                exit_code = web_service.start_test(idelium, test_configurations, config)

            report = json.loads(Path(json_report).read_text(encoding="utf-8"))
            html_report_content = Path(html_report).read_text(encoding="utf-8")
            markdown_report_content = Path(markdown_report).read_text(encoding="utf-8")
            junit_report_content = Path(junit_report).read_text(encoding="utf-8")

        self.assertEqual(EXIT_TEST_FAILURE, exit_code)
        self.assertEqual("failed", report["run"]["status"])
        self.assertEqual(1, report["summary"]["failed"])
        serialized = json.dumps(report)
        self.assertNotIn("secret", serialized)
        self.assertNotIn("abc", serialized)
        self.assertIn("Idelium Execution Report", html_report_content)
        self.assertIn("# Idelium Execution Report", markdown_report_content)
        self.assertIn("<testsuites", junit_report_content)

    def test_start_test_closes_bidi_lifecycle_before_quitting_driver(self):
        web_service = IdeliumWs()
        printer = Mock()
        driver = Mock()
        wrapper = Mock()
        idelium = Mock()
        idelium.get_wrapper.return_value = wrapper
        idelium.execute_step.return_value = {
            "status": "1",
            "driver": driver,
            "postman_data": [],
            "type": "seleniumOrAppium",
            "step_failed": "",
        }
        config = {
            "idCycle": "2",
            "idProject": "3",
            "test": True,
            "ideliumServer": False,
            "printer": printer,
        }
        test_configurations = {
            "steps": {
                "browser_17": {
                    "name": "browser",
                    "attachScreenshot": False,
                    "failedExit": False,
                }
            }
        }

        with (
            patch.object(web_service, "get_cycles") as get_cycles,
            patch.object(web_service, "get_tests") as get_tests,
        ):
            get_cycles.return_value = [
                {"id": 11, "name": "browser cycle", "description": "browser cycle"}
            ]
            get_tests.return_value = [{"id": 17, "name": "browser"}]

            web_service.start_test(idelium, test_configurations, config)

        wrapper.close_bidi_session.assert_called_once_with(config, printer)
        driver.quit.assert_called_once_with()

    def test_selenium_failure_adds_bounded_screenshot_artifact_to_report(self):
        web_service = IdeliumWs()
        printer = Mock()
        driver = Mock()
        wrapper = Mock()

        def write_screenshot(current_driver, path, is_server):
            Path(path).write_bytes(b"png")

        wrapper.screen_shot.side_effect = write_screenshot
        idelium = Mock()
        idelium.get_wrapper.return_value = wrapper
        idelium.execute_step.return_value = {
            "status": "2",
            "driver": driver,
            "postman_data": [],
            "type": "seleniumOrAppium",
            "step_failed": {"stepType": "click"},
        }

        with tempfile.TemporaryDirectory() as directory:
            previous_directory = os.getcwd()
            os.chdir(directory)
            try:
                json_report = Path(directory) / "report.json"
                config = {
                    "idCycle": "2",
                    "idProject": "3",
                    "test": True,
                    "ideliumServer": False,
                    "printer": printer,
                    "jsonReport": str(json_report),
                }
                test_configurations = {
                    "steps": {
                        "browser_17": {
                            "name": "browser",
                            "attachScreenshot": False,
                            "failedExit": False,
                        }
                    }
                }
                with (
                    patch.object(web_service, "get_cycles") as get_cycles,
                    patch.object(web_service, "get_tests") as get_tests,
                ):
                    get_cycles.return_value = [
                        {
                            "id": 11,
                            "name": "browser cycle",
                            "description": "browser cycle",
                        }
                    ]
                    get_tests.return_value = [{"id": 17, "name": "browser"}]

                    exit_code = web_service.start_test(
                        idelium,
                        test_configurations,
                        config,
                    )
            finally:
                os.chdir(previous_directory)

            report = json.loads(json_report.read_text(encoding="utf-8"))

        self.assertEqual(EXIT_TEST_FAILURE, exit_code)
        artifact = report["tests"][0]["steps"][0]["artifacts"][0]
        self.assertEqual("failure-screenshot.png", artifact["name"])
        self.assertEqual("image/png", artifact["type"])
        self.assertEqual("screenshots/11.png", artifact["path"])
        self.assertEqual("captured", artifact["data"]["captureOutcome"])
        self.assertEqual("image/png", artifact["data"]["mediaType"])
        self.assertEqual("3", artifact["data"]["sizeBytes"])
        self.assertEqual("pending-step", artifact["data"]["sourceStepId"])
        self.assertEqual("11", artifact["data"]["sourceTestId"])
        wrapper.screen_shot.assert_called_once()

    def test_screenshot_errors_do_not_hide_original_failure(self):
        web_service = IdeliumWs()
        printer = Mock()
        driver = Mock()
        wrapper = Mock()
        wrapper.screen_shot.side_effect = RuntimeError("screenshot unavailable")
        idelium = Mock()
        idelium.get_wrapper.return_value = wrapper
        idelium.execute_step.return_value = {
            "status": "2",
            "driver": driver,
            "postman_data": [],
            "type": "seleniumOrAppium",
            "step_failed": {"stepType": "click"},
        }

        with tempfile.TemporaryDirectory() as directory:
            previous_directory = os.getcwd()
            os.chdir(directory)
            try:
                json_report = Path(directory) / "report.json"
                config = {
                    "idCycle": "2",
                    "idProject": "3",
                    "test": True,
                    "ideliumServer": False,
                    "printer": printer,
                    "jsonReport": str(json_report),
                }
                test_configurations = {
                    "steps": {
                        "browser_17": {
                            "name": "browser",
                            "attachScreenshot": True,
                            "failedExit": False,
                        }
                    }
                }
                with (
                    patch.object(web_service, "get_cycles") as get_cycles,
                    patch.object(web_service, "get_tests") as get_tests,
                ):
                    get_cycles.return_value = [
                        {
                            "id": 11,
                            "name": "browser cycle",
                            "description": "browser cycle",
                        }
                    ]
                    get_tests.return_value = [{"id": 17, "name": "browser"}]

                    exit_code = web_service.start_test(
                        idelium,
                        test_configurations,
                        config,
                    )
            finally:
                os.chdir(previous_directory)

            report = json.loads(json_report.read_text(encoding="utf-8"))

        self.assertEqual(EXIT_TEST_FAILURE, exit_code)
        self.assertEqual([], report["tests"][0]["steps"][0]["artifacts"])
        self.assertEqual(
            "Step failed during execution.",
            report["tests"][0]["steps"][0]["diagnostics"][0]["message"],
        )
        printer.warning.assert_any_call(
            "Failure screenshot capture failed without changing the test result."
        )


if __name__ == "__main__":
    unittest.main()
