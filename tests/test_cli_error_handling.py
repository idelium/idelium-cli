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

    def test_internal_errors_return_internal_exit_code_without_details(self):
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
        danger.assert_called_once_with("Unexpected internal CLI error.")


if __name__ == "__main__":
    unittest.main()
