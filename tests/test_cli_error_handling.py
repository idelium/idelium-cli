import unittest
from unittest.mock import patch

from idelium._internal.commons.connection import HttpTransportError
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

        self.assertEqual(2, exit_code)
        danger.assert_called_once_with("GET request failed for https://localhost")


if __name__ == "__main__":
    unittest.main()
