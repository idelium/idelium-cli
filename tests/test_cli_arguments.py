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
                "--markdownReport",
                "reports/result.md",
                "--junitReport",
                "reports/result.xml",
            ],
            Mock(),
            printer,
        )

        self.assertEqual("reports/result.json", defined["cl_params"]["jsonReport"])
        self.assertEqual("reports/result.html", defined["cl_params"]["htmlReport"])
        self.assertEqual("reports/result.md", defined["cl_params"]["markdownReport"])
        self.assertEqual("reports/result.xml", defined["cl_params"]["junitReport"])

    def test_accepts_offline_ast_export_without_api_credentials(self):
        loader = InitIdelium()
        printer = Mock()

        defined = loader.define_parameters(
            [
                "idelium",
                "--dslSource=tests/login.idelium",
                "--astReport",
                "reports/login.ast.json",
            ],
            Mock(),
            printer,
        )

        self.assertEqual("tests/login.idelium", defined["cl_params"]["dslSource"])
        self.assertEqual("reports/login.ast.json", defined["cl_params"]["astReport"])

    def test_accepts_dsl_parameters_from_file_and_cli(self):
        loader = InitIdelium()
        printer = Mock()

        with patch("pathlib.Path.read_text") as read_text:
            read_text.return_value = (
                '{"variables": {"baseUrl": "https://file.example.invalid"}, '
                '"secrets": {"password": "file-secret"}}'
            )
            defined = loader.define_parameters(
                [
                    "idelium",
                    "--dslSource",
                    "tests/login.idelium",
                    "--astReport",
                    "reports/login.ast.json",
                    "--dslParamsFile",
                    "params.json",
                    "--dslParam",
                    "baseUrl=https://cli.example.invalid",
                    "--dslSecret",
                    "token=cli-secret",
                ],
                Mock(),
                printer,
            )

        self.assertEqual(
            {
                "baseUrl": "https://cli.example.invalid",
                "password": "file-secret",
                "token": "cli-secret",
            },
            defined["cl_params"]["dslParameters"]["variables"],
        )
        self.assertEqual(
            ["password", "token"],
            defined["cl_params"]["dslParameters"]["secretNames"],
        )

    def test_invalid_dsl_parameter_exits_with_stable_code(self):
        loader = InitIdelium()
        printer = Mock()

        with patch("builtins.print"), self.assertRaises(SystemExit) as raised:
            loader.define_parameters(
                [
                    "idelium",
                    "--dslSource",
                    "tests/login.idelium",
                    "--astReport",
                    "reports/login.ast.json",
                    "--dslParam",
                    "not-an-assignment",
                ],
                Mock(),
                printer,
            )

        self.assertEqual(1, raised.exception.code)
        self.assertIn(
            "IDELIUM_DSL_PARAMETER_ASSIGNMENT_INVALID",
            printer.danger.call_args.args[0],
        )

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
