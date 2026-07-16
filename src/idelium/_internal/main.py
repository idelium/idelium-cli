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


idelium=StartManager()
printer=InitPrinter()
ideliumws=IdeliumWs()
idelium_cl_lib=InitIdelium()
IDELIUM_VERSION='1.0.13'


def start_server(cl_params):
        if os.path.exists(cl_params['dir_idelium_scripts'] + 'server'):
            os.remove(cl_params['dir_idelium_scripts'] + 'server')
        server_address = ('0.0.0.0', cl_params['ideliumServerPort'])
        IdeliumServer.init(idelium, cl_params, ideliumws, idelium_cl_lib,printer)
        sslctx = ssl.SSLContext()
        sslctx.check_hostname = False
        sslctx.load_cert_chain(certfile='cert/cert.pem', keyfile="cert/key.pem")
        httpd = HTTPServer(server_address, IdeliumServer)
        httpd.socket = sslctx.wrap_socket(httpd.socket, server_side=True)
        printer.success('Server start on port:' +
            str(cl_params['ideliumServerPort']))
        printer.success(f'Server start on port: {cl_params["ideliumServerPort"]}')
        httpd.serve_forever()

def start_test(cl_params):
        define_parameters = idelium_cl_lib.load_parameters(cl_params, ideliumws, printer)
        cl_params = define_parameters['cl_params']
        test_config = define_parameters['test_config']
        if cl_params['reportingService'] == 'idelium':
            ideliumws.start_test(idelium,test_config,cl_params)
        elif cl_params['reportingService'] == 'zephyr':
            zephyr=ZephyrConnection()
            if cl_params['idJira'] is not None:
                zephyr.start_test_case(idelium,test_config,cl_params)
            else:
                zephyr.go_execution(idelium,cl_params)
        else:
            printer.danger(f'Error: {cl_params["reportingService"]} has a wrong value')
        printer.success('Finish test')


def main(args: Optional[List[str]] = None) -> int:
    printer.print_important_text(f"Idelium Command Line {IDELIUM_VERSION}")
    printer.print_important_text(f"Selenium version: {idelium_cl_lib.get_selenium_version()}")
    if args is None:
        args = sys.argv
    define_parameters= idelium_cl_lib.define_parameters(args,ideliumws,printer)
    cl_params=define_parameters['cl_params']

    if cl_params['ideliumServer'] is False:
         start_test(cl_params)
    else:
        start_server(cl_params)
