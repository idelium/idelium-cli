"""System module."""

from __future__ import absolute_import
import sys
import ssl
import os
import re
import shutil
import subprocess
import warnings
from importlib import metadata
from typing import List, Optional

from http.server import HTTPServer

from idelium._internal.ideliummanager import StartManager
from idelium._internal.ideliumserver import IdeliumServer
from idelium._internal.ideliumws import IdeliumWs
from idelium._internal.ideliumclib import InitIdelium
from idelium._internal.thirdparties.ideliumzephyr import ZephyrConnection
from idelium._internal.commons.ideliumprinter import InitPrinter
from idelium._internal.commons.connection import HttpTransportError
from idelium._internal.astexport import export_ast_report
from idelium._internal.dsl import lint_file
from idelium._internal.exitcodes import (
    EXIT_CONNECTIVITY_ERROR,
    EXIT_INTERNAL_ERROR,
    EXIT_SUCCESS,
    EXIT_VALIDATION_ERROR,
)


idelium = StartManager()
printer = InitPrinter()
ideliumws = IdeliumWs()
idelium_cl_lib = InitIdelium()
IDELIUM_VERSION = "1.0.15.dev1"
IDELIUM_ORANGE = "\033[38;2;255;92;31m"
ANSI_RESET = "\033[0m"
IDELIUM_ASCII_LOGO = r"""
 ___ ____  _____ _     ___ _   _ __  __
|_ _|  _ \| ____| |   |_ _| | | |  \/  |
 | || | | |  _| | |    | || | | | |\/| |
 | || |_| | |___| |___ | || |_| | |  | |
|___|____/|_____|_____|___|\___/|_|  |_|
"""
_SENSITIVE_ERROR_PATTERNS = (
    re.compile(r"(?i)(authorization|cookie|key|password|secret|session|token)=\S+"),
    re.compile(r"(?i)(authorization|cookie|key|password|secret|session|token):\S+"),
)


def format_unexpected_error(error: Exception) -> str:
    """Return a safe diagnostic for unexpected CLI failures."""

    message = str(error).strip() or error.__class__.__name__
    for pattern in _SENSITIVE_ERROR_PATTERNS:
        message = pattern.sub(lambda match: match.group(1) + "=[REDACTED]", message)
    return f"Unexpected internal CLI error: {error.__class__.__name__}: {message}"


def startup_banner() -> str:
    """Return the startup banner shown before CLI execution."""

    return (
        IDELIUM_ORANGE
        + IDELIUM_ASCII_LOGO.strip("\n")
        + ANSI_RESET
        + "\n"
        + f"Idelium Command Line {IDELIUM_VERSION}"
    )


def _python_package_version(package_name: str) -> str:
    """Return an installed Python package version or a readable fallback."""

    try:
        return metadata.version(package_name)
    except metadata.PackageNotFoundError:
        return "not installed"


def _newman_version() -> str:
    """Return the Newman CLI version when the binary is available."""

    binary = shutil.which("newman")
    if not binary:
        return "not found"
    try:
        completed = subprocess.run(
            [binary, "--version"],
            capture_output=True,
            check=False,
            text=True,
            timeout=3,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "not available"
    version = (completed.stdout or completed.stderr).strip().splitlines()
    return version[0].strip() if version else "not available"


def framework_versions_banner() -> str:
    """Return runtime framework versions used by the CLI."""

    frameworks = (
        ("Selenium", idelium_cl_lib.get_selenium_version()),
        ("Appium Python Client", _python_package_version("Appium-Python-Client")),
        ("Newman", _newman_version()),
        ("Requests", _python_package_version("requests")),
        ("WebDriver Manager", _python_package_version("webdriver-manager")),
    )
    return "Framework versions: " + " | ".join(
        f"{name} {version}" for name, version in frameworks
    )


def start_server(cl_params):
    if os.path.exists(cl_params["dir_idelium_scripts"] + "server"):
        os.remove(cl_params["dir_idelium_scripts"] + "server")
    server_address = ("0.0.0.0", cl_params["ideliumServerPort"])
    IdeliumServer.init(idelium, cl_params, ideliumws, idelium_cl_lib, printer)
    sslctx = ssl.SSLContext()
    sslctx.check_hostname = False
    sslctx.load_cert_chain(certfile="cert/cert.pem", keyfile="cert/key.pem")
    httpd = HTTPServer(server_address, IdeliumServer)
    httpd.socket = sslctx.wrap_socket(httpd.socket, server_side=True)
    printer.success("Server start on port:" + str(cl_params["ideliumServerPort"]))
    printer.success(f"Server start on port: {cl_params['ideliumServerPort']}")
    httpd.serve_forever()


def start_test(cl_params):
    define_parameters = idelium_cl_lib.load_parameters(cl_params, ideliumws, printer)
    cl_params = define_parameters["cl_params"]
    test_config = define_parameters["test_config"]
    exit_code = EXIT_SUCCESS
    if cl_params["reportingService"] == "idelium":
        exit_code = ideliumws.start_test(idelium, test_config, cl_params)
    elif cl_params["reportingService"] == "zephyr":
        zephyr = ZephyrConnection()
        if cl_params["idJira"] is not None:
            zephyr.start_test_case(idelium, test_config, cl_params)
        else:
            zephyr.go_execution(idelium, cl_params)
    else:
        printer.danger(f"Error: {cl_params['reportingService']} has a wrong value")
        exit_code = EXIT_VALIDATION_ERROR
    if exit_code == EXIT_SUCCESS:
        printer.success("Finish test")
    else:
        printer.danger("Finish test with failures")
    return exit_code


def main(args: Optional[List[str]] = None) -> int:
    printer.print_important_text(startup_banner())
    printer.print_important_text(
        f"Selenium version: {idelium_cl_lib.get_selenium_version()}"
    )
    printer.print_important_text(framework_versions_banner())
    if args is None:
        args = sys.argv

    try:
        define_parameters = idelium_cl_lib.define_parameters(args, ideliumws, printer)
        cl_params = define_parameters["cl_params"]
        if cl_params.get("dslSource") or cl_params.get("astReport"):
            export_ast_report(cl_params["dslSource"], cl_params["astReport"], printer)
            return EXIT_SUCCESS
        if cl_params.get("dslLint"):
            return lint_file(
                cl_params["dslLint"],
                cl_params.get("dslLintReport"),
                printer,
            )
        if cl_params["ideliumServer"] is False:
            return start_test(cl_params)
        else:
            start_server(cl_params)
    except SystemExit as error:
        code = error.code if isinstance(error.code, int) else EXIT_VALIDATION_ERROR
        if code == EXIT_SUCCESS:
            return EXIT_SUCCESS
        return EXIT_VALIDATION_ERROR
    except HttpTransportError as error:
        printer.danger(str(error))
        return EXIT_CONNECTIVITY_ERROR
    except Exception as error:
        printer.danger(format_unexpected_error(error))
        return EXIT_INTERNAL_ERROR
    return EXIT_SUCCESS
