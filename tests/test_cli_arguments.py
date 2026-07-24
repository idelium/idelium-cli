import unittest
from unittest.mock import Mock, patch

from idelium._internal.ideliumclib import InitIdelium


class CliArgumentParsingTest(unittest.TestCase):
    def test_accepts_space_separated_option_values(self):
        loader = InitIdelium()
        printer = Mock()

        defined = loader.define_parameters(
            [
                "idelium",
                "--idProject",
                "1",
                "--idCycle",
                "2",
                "--environment",
                "demo",
                "--ideliumKey",
                "key==",
                "--ideliumwsBaseurl",
                "https://localhost",
                "--insecure",
            ],
            Mock(),
            printer,
        )

        cl_params = defined["cl_params"]
        self.assertEqual("1", cl_params["idProject"])
        self.assertEqual("2", cl_params["idCycle"])
        self.assertEqual("demo", cl_params["environment"])
        self.assertEqual("key==", cl_params["ideliumKey"])
        self.assertEqual("https://localhost", cl_params["ideliumwsBaseurl"])
        self.assertTrue(cl_params["insecure"])
        printer.warning.assert_called_with(
            "TLS certificate verification is disabled by explicit request."
        )

    def test_accepts_test_mode_as_flag(self):
        loader = InitIdelium()
        printer = Mock()

        defined = loader.define_parameters(
            [
                "idelium",
                "--idProject",
                "1",
                "--idCycle",
                "2",
                "--environment",
                "demo",
                "--ideliumKey",
                "key==",
                "--ideliumwsBaseurl",
                "https://localhost",
                "--test",
            ],
            Mock(),
            printer,
        )

        self.assertTrue(defined["cl_params"]["test"])

    def test_accepts_local_report_output_paths(self):
        loader = InitIdelium()
        printer = Mock()

        defined = loader.define_parameters(
            [
                "idelium",
                "--idProject",
                "1",
                "--idCycle",
                "2",
                "--environment",
                "demo",
                "--ideliumKey",
                "key==",
                "--ideliumwsBaseurl",
                "https://localhost",
                "--jsonReport",
                "reports/result.json",
                "--htmlReport=reports/result.html",
            ],
            Mock(),
            printer,
        )

        self.assertEqual("reports/result.json", defined["cl_params"]["jsonReport"])
        self.assertEqual("reports/result.html", defined["cl_params"]["htmlReport"])

    def test_missing_option_value_exits_with_clear_error(self):
        loader = InitIdelium()
        printer = Mock()

        with patch("builtins.print"), self.assertRaises(SystemExit) as raised:
            loader.define_parameters(
                [
                    "idelium",
                    "--idProject",
                    "1",
                    "--idCycle",
                    "2",
                    "--environment",
                    "demo",
                    "--ideliumKey",
                    "key==",
                    "--ideliumwsBaseurl",
                ],
                Mock(),
                printer,
            )

        self.assertEqual(1, raised.exception.code)
        printer.danger.assert_called_with("ideliumwsBaseurl requires a value")


if __name__ == "__main__":
    unittest.main()
