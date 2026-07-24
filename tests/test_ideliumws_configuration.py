import unittest
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from idelium._internal.commons.connection import HttpTransportError
from idelium._internal.exitcodes import (
    EXIT_DEPENDENCY_ERROR,
    EXIT_TEST_FAILURE,
)
from idelium._internal.ideliumws import IdeliumWs


class IdeliumWsConfigurationTest(unittest.TestCase):
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
        create_step.assert_called_once()
        self.assertEqual("2", create_step.call_args.args[5])
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

        self.assertEqual(EXIT_TEST_FAILURE, exit_code)
        self.assertEqual("failed", report["run"]["status"])
        self.assertEqual(1, report["summary"]["failed"])
        serialized = json.dumps(report)
        self.assertNotIn("secret", serialized)
        self.assertNotIn("abc", serialized)
        self.assertIn("Idelium Execution Report", html_report_content)


if __name__ == "__main__":
    unittest.main()
