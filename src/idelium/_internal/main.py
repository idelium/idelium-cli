"""System module."""

from __future__ import absolute_import
import sys
import ssl
import os
import warnings
from typing import List, Optional

from http.server import HTTPServer

from idelium._internal.ideliummanager import StartManager
from idelium._internal.ideliumserver import IdeliumServer
from idelium._internal.ideliumws import IdeliumWs
from idelium._internal.ideliumclib import InitIdelium
from idelium._internal.thirdparties.ideliumzephyr import ZephyrConnection
from idelium._internal.commons.ideliumprinter import InitPrinter
from idelium._internal.commons.connection import HttpTransportError
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
IDELIUM_VERSION = "1.0.14"


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
    printer.print_important_text(f"Idelium Command Line {IDELIUM_VERSION}")
    printer.print_important_text(
        f"Selenium version: {idelium_cl_lib.get_selenium_version()}"
    )
    if args is None:
        args = sys.argv

    try:
        define_parameters = idelium_cl_lib.define_parameters(args, ideliumws, printer)
        cl_params = define_parameters["cl_params"]
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
    except Exception:
        printer.danger("Unexpected internal CLI error.")
        return EXIT_INTERNAL_ERROR
    return EXIT_SUCCESS
