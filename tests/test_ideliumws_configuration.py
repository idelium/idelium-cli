import unittest
from unittest.mock import Mock, patch

from idelium._internal.commons.connection import HttpTransportError
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


if __name__ == "__main__":
    unittest.main()
