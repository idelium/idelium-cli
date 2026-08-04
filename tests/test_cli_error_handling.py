import unittest
from unittest.mock import patch

from idelium._internal.commons.connection import HttpTransportError
from idelium._internal.exitcodes import (
    EXIT_CONNECTIVITY_ERROR,
    EXIT_INTERNAL_ERROR,
    EXIT_SUCCESS,
    EXIT_TEST_FAILURE,
    EXIT_VALIDATION_ERROR,
)
from idelium._internal import main as cli_main


class CliErrorHandlingTest(unittest.TestCase):
    def test_startup_banner_uses_large_idelium_logo(self):
        banner = cli_main.startup_banner()

        self.assertTrue(banner.startswith(cli_main.IDELIUM_ORANGE))
        self.assertIn("___ ____  _____", banner)
        self.assertIn(cli_main.ANSI_RESET, banner)
        self.assertIn("Idelium Command Line " + cli_main.IDELIUM_VERSION, banner)

    def test_framework_versions_banner_reports_runtime_dependencies(self):
        with (
            patch.object(
                cli_main.idelium_cl_lib,
                "get_selenium_version",
                return_value="4.46.0",
            ),
            patch.object(
                cli_main,
                "_python_package_version",
                side_effect=lambda package: {
                    "Appium-Python-Client": "5.3.1",
                    "requests": "2.34.2",
                    "webdriver-manager": "4.1.2",
                }[package],
            ),
            patch.object(cli_main, "_newman_version", return_value="6.2.1"),
        ):
            banner = cli_main.framework_versions_banner()

        self.assertEqual(
            "Framework versions: Selenium 4.46.0 | Appium Python Client 5.3.1 "
            "| Newman 6.2.1 | Requests 2.34.2 | WebDriver Manager 4.1.2",
            banner,
        )

    def test_newman_version_reports_missing_binary(self):
        with patch.object(cli_main.shutil, "which", return_value=None):
            self.assertEqual("not found", cli_main._newman_version())

    def test_newman_version_reads_binary_version(self):
        completed = type(
            "CompletedProcess",
            (),
            {"stdout": "6.2.1\n", "stderr": ""},
        )()
        with (
            patch.object(cli_main.shutil, "which", return_value="/usr/local/bin/newman"),
            patch.object(cli_main.subprocess, "run", return_value=completed) as run,
        ):
            self.assertEqual("6.2.1", cli_main._newman_version())

        run.assert_called_once_with(
            ["/usr/local/bin/newman", "--version"],
            capture_output=True,
            check=False,
            text=True,
            timeout=3,
        )

    def test_transport_errors_return_controlled_exit_code(self):
        with (
            patch.object(
                cli_main.idelium_cl_lib,
                "define_parameters",
                return_value={"cl_params": {"ideliumServer": False}},
            ),
            patch.object(
                cli_main,
                "start_test",
                side_effect=HttpTransportError(
                    "GET request failed for https://localhost"
                ),
            ),
            patch.object(cli_main.printer, "print_important_text"),
            patch.object(cli_main.printer, "danger") as danger,
        ):
            exit_code = cli_main.main(["idelium"])

        self.assertEqual(EXIT_CONNECTIVITY_ERROR, exit_code)
        danger.assert_called_once_with("GET request failed for https://localhost")

    def test_test_failures_return_non_zero_exit_code(self):
        with (
            patch.object(
                cli_main.idelium_cl_lib,
                "define_parameters",
                return_value={"cl_params": {"ideliumServer": False}},
            ),
            patch.object(cli_main, "start_test", return_value=1),
            patch.object(cli_main.printer, "print_important_text"),
        ):
            exit_code = cli_main.main(["idelium"])

        self.assertEqual(EXIT_TEST_FAILURE, exit_code)

    def test_validation_errors_return_validation_exit_code(self):
        with (
            patch.object(
                cli_main.idelium_cl_lib,
                "define_parameters",
                side_effect=SystemExit(1),
            ),
            patch.object(cli_main.printer, "print_important_text"),
        ):
            exit_code = cli_main.main(["idelium", "--unknown"])

        self.assertEqual(EXIT_VALIDATION_ERROR, exit_code)

    def test_help_exit_remains_successful(self):
        with (
            patch.object(
                cli_main.idelium_cl_lib,
                "define_parameters",
                side_effect=SystemExit(0),
            ),
            patch.object(cli_main.printer, "print_important_text"),
        ):
            exit_code = cli_main.main(["idelium", "--help"])

        self.assertEqual(EXIT_SUCCESS, exit_code)

    def test_internal_errors_return_internal_exit_code_with_redacted_details(self):
        with (
            patch.object(
                cli_main.idelium_cl_lib,
                "define_parameters",
                return_value={"cl_params": {"ideliumServer": False}},
            ),
            patch.object(
                cli_main,
                "start_test",
                side_effect=RuntimeError("token=secret-value"),
            ),
            patch.object(cli_main.printer, "print_important_text"),
            patch.object(cli_main.printer, "danger") as danger,
        ):
            exit_code = cli_main.main(["idelium"])

        self.assertEqual(EXIT_INTERNAL_ERROR, exit_code)
        danger.assert_called_once_with(
            "Unexpected internal CLI error: RuntimeError: token=[REDACTED]"
        )

    def test_internal_error_formatter_falls_back_to_exception_type(self):
        error = RuntimeError()

        self.assertEqual(
            "Unexpected internal CLI error: RuntimeError: RuntimeError",
            cli_main.format_unexpected_error(error),
        )


if __name__ == "__main__":
    unittest.main()
