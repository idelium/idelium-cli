"""System module."""

from __future__ import absolute_import
import sys
import tempfile
import json
from pathlib import Path
import selenium

from idelium._internal.commons.connection import Connection


class InitIdelium:
    """init"""

    @staticmethod
    def get_selenium_version():
        """version selenium"""
        return selenium.__version__

    @staticmethod
    def get_syntax():
        """help command line"""
        return """
    \033[1mUsage\033[0m: idelium [options]

    Options:

    --help                  show this help
    --idCycle               cycle id to associate to the execution "idCycle1,idCycle2,...."
    --idProject             force idProject
    --environment           environment json config file (required)
    --useragent             set useragent for the test
    --test                  for testing without store the results
    --verbose               for debugging 
    --dirChromedriver       default path of chromedriver path ("./chromedriver/last")
    --dirConfigurationStep  default path ("./configurationStep") for configuration steps 
    --dirStepFiles          default path ("./step") of directory for step files 
    --dirIdeliumScript      default path (".") of directory for step files
    --width                 default width of screen 1024
    --height                default height of screen 768
    --device                if is set useragent,height and width are ignored
    --url                   url for test 
    --ideliumwsBaseurl      idelium server url ex: https://localhost
    --seleniumGridUrl       Selenium Grid endpoint, for example http://grid:4444
    --seleniumGridCapabilities JSON object merged into remote browser capabilities
    --caBundle              path to a trusted CA bundle
    --insecure              disable TLS verification for development only
    --httpConnectTimeout    HTTP connection timeout in seconds (default 5)
    --httpReadTimeout       HTTP read timeout in seconds (default 30)
    --postmanNewmanTimeout  Newman execution timeout in seconds (default 300)
    --reportingService      where the data will be save: idelium | zephyr
    --ideliumKey            is the key for access to the idelium api
    --idChannel             idChannel
    
    Idelium server
    --ideliumServer         with this option idelium-cli is in server mode
    --ideliumServerPort     default is 8691

    Zephir 
    --jiraApiUrl            for change the default jira url (https://<host jira>/rest/api/latest/)
    --idJira                jira id (required if idVersion and idCycle not setted)
    --idVersion             version id to associate the execution 
    --username              jira username (required)
    --password              jira password (required)



    For Example: 

    Options accept both --name=value and --name value forms.

    default reporting service: idelium --ideliumKey=1234 --idCycle=2 --idProject=8 --environment=prod

    working with jira/zephyr: idelium --reportingService=zephyr --idJira=prj-1234 --username=user --password=secret --environment=prod.json --useragent='apple 1134'

    """

    @staticmethod
    def get_reguired_parameters():
        """Returns a dictionary of the required parameters for Idelium."""
        return {
            "idProject": 0,
            "idCycle": 0,
            "environment": 0,
            "ideliumKey": 0,
        }

    @staticmethod
    def get_default_parameters():
        """Returns a dictionary of the default parameters for Idelium."""
        return {
            "execution_name": "automation test python",
            "reportingService": "idelium",
            "ideliumwsBaseurl": None,
            "base_url": None,
            "zephyrApiUrl": None,
            "jiraApiUrl": None,
            "dir_plugins": "plugin",
            "test": False,
            "is_debug": False,
            "device": None,
            "width": 1920,
            "height": 1080,
            "username": None,
            "password": None,
            "environment": None,
            "idJira": None,
            "fileSteps": None,
            "idVersion": None,
            "idCycle": None,
            "useragent": None,
            "idProject": None,
            "idChannel": None,
            "url": None,
            "isRealDevice": False,
            "os": None,
            "appiumServer": None,
            "appiumDesiredCaps": None,
            "seleniumGridUrl": None,
            "seleniumGridCapabilities": None,
            "caBundle": None,
            "insecure": False,
            "httpConnectTimeout": 5,
            "httpReadTimeout": 30,
            "postmanNewmanTimeout": 300,
            "count": 0,
            "ideliumKey": None,
            "forcedownload": False,
            "local": False,
            "ideliumServer": False,
            "ideliumServerPort": 8691,
        }

    @staticmethod
    def _parse_cli_args(args, known_parameters, flag_parameters, printer):
        tokens = list(args)
        if tokens and not tokens[0].startswith("--"):
            tokens = tokens[1:]
        parsed_args = []
        index = 0
        while index < len(tokens):
            token = tokens[index]
            if not token.startswith("--"):
                print(InitIdelium.get_syntax())
                printer.danger(token + ": is not a valid option")
                sys.exit(1)
            option = token[2:]
            if "=" in option:
                command, value = option.split("=", 1)
            else:
                command = option
                if command in flag_parameters or command in {"help", "verbose"}:
                    value = None
                elif command in known_parameters:
                    if index + 1 >= len(tokens) or tokens[index + 1].startswith("--"):
                        print(InitIdelium.get_syntax())
                        printer.danger(command + " requires a value")
                        sys.exit(1)
                    value = tokens[index + 1]
                    index += 1
                else:
                    value = None
            parsed_args.append((command, value, token))
            index += 1
        return parsed_args

    def define_parameters(self, args, ideliumws, printer):
        """set all necessary parameters"""
        cl_params = self.get_default_parameters()
        check_required = self.get_reguired_parameters()
        cl_params["dir_idelium_scripts"] = tempfile.mkdtemp()
        flag_parameters = {"forcedownload", "ideliumServer", "insecure", "test"}
        parsed_args = self._parse_cli_args(args, cl_params, flag_parameters, printer)
        for command, value, token in parsed_args:
            if command in cl_params:
                if command == "ideliumKey":
                    cl_params["ideliumKey"] = value
                elif command in flag_parameters:
                    cl_params[command] = True
                elif command == "ideliumServerPort":
                    cl_params["ideliumServerPort"] = int(value)
                else:
                    cl_params[command] = value
                if command in check_required:
                    check_required[command] = 1
            elif command == "verbose":
                cl_params["is_debug"] = True
            elif command == "help":
                print(self.get_syntax())
                sys.exit(0)
            else:
                print(self.get_syntax())
                print("\n" + token + ": is not a valid option")
                sys.exit(1)
        count_req = 0
        for i in check_required:
            count_req = count_req + check_required[i]
        if cl_params["ideliumServer"] is False:
            if cl_params["ideliumKey"] is None:
                file_idelium_key = str(Path.home()) + "/.idelium"
                if Path(file_idelium_key).is_file() is True:
                    file = open(file_idelium_key, "r")
                    cl_params["ideliumKey"] = file.read()
                else:
                    print(self.get_syntax())
                    printer.danger("ideliumKey is not setted !")
                    sys.exit(1)
        if cl_params["ideliumServer"] is False:
            if cl_params["reportingService"] == "idelium":
                if cl_params["idProject"] is None or cl_params["idCycle"] is None:
                    print(self.get_syntax())
                    printer.danger("\nidProject and idCycle are mandatory")
                    sys.exit(1)
                if cl_params["reportingService"] == "zephyr":
                    if count_req < 4:
                        print(self.get_syntax())
                        printer.danger("\nMissed required options")
                        sys.exit(1)
                if cl_params["environment"] is None:
                    print(self.get_syntax())
                    printer.danger("\nenvironment must be set")
                    sys.exit(1)
                if cl_params["ideliumwsBaseurl"] is None:
                    print(self.get_syntax())
                    printer.danger("\nideliumwsBaseurl must be set")
                    sys.exit(1)
        self.configure_http(cl_params, printer)
        return {
            "cl_params": cl_params,
        }

    @staticmethod
    def configure_http(cl_params, printer):
        """Configure secure HTTP behavior for CLI and server modes."""
        try:
            timeout = (
                float(cl_params["httpConnectTimeout"]),
                float(cl_params["httpReadTimeout"]),
            )
            postman_newman_timeout = float(cl_params["postmanNewmanTimeout"])
        except (TypeError, ValueError):
            printer.danger("HTTP timeouts must be numbers")
            sys.exit(1)
        if timeout[0] <= 0 or timeout[1] <= 0 or postman_newman_timeout <= 0:
            printer.danger("HTTP timeouts must be greater than zero")
            sys.exit(1)
        Connection.configure(
            ca_bundle=cl_params["caBundle"],
            insecure=cl_params["insecure"],
            timeout=timeout,
        )
        if cl_params["insecure"]:
            printer.warning(
                "TLS certificate verification is disabled by explicit request."
            )

    def load_parameters(self, cl_params, ideliumws, printer):

        sys.path.append(cl_params["dir_idelium_scripts"] + "/" + cl_params["idProject"])

        cl_params["api_idelium"] = cl_params["ideliumwsBaseurl"] + "/api/ideliumcl/"
        cl_params["printer"] = printer
        test_config = None
        json_config = None
        json_step_config = None
        test_config = ideliumws.get_configuration(cl_params)
        if test_config is False:
            return False
        print("Environment:" + cl_params["environment"])
        if cl_params["environment"] in test_config["environments"]:
            json_config = test_config["environments"][cl_params["environment"]]
        else:
            printer.danger(
                'Environment "'
                + cl_params["environment"]
                + '" or idProject '
                + cl_params["idProject"]
                + " not exist"
            )
            sys.exit(1)
        if "userAgent" in json_config:
            cl_params["user_agent"] = json_config["userAgent"]
        if "isRealDevice" in json_config:
            cl_params["isRealDevice"] = json_config["isRealDevice"]
        if "appiumServer" in json_config:
            cl_params["appiumServer"] = json_config["appiumServer"]
        if "isRealDevice" in json_config:
            cl_params["appiumDesiredCaps"] = json_config["appiumDesiredCaps"]
        if cl_params["seleniumGridUrl"] is None and "seleniumGridUrl" in json_config:
            cl_params["seleniumGridUrl"] = json_config["seleniumGridUrl"]
        if (
            cl_params["seleniumGridCapabilities"] is None
            and "seleniumGridCapabilities" in json_config
        ):
            cl_params["seleniumGridCapabilities"] = json_config[
                "seleniumGridCapabilities"
            ]
        if isinstance(cl_params["seleniumGridCapabilities"], str):
            try:
                cl_params["seleniumGridCapabilities"] = json.loads(
                    cl_params["seleniumGridCapabilities"]
                )
            except json.JSONDecodeError:
                printer.danger("seleniumGridCapabilities must be a JSON object")
                sys.exit(1)
        if cl_params["seleniumGridCapabilities"] is not None and not isinstance(
            cl_params["seleniumGridCapabilities"], dict
        ):
            printer.danger("seleniumGridCapabilities must be a JSON object")
            sys.exit(1)
        if cl_params["idProject"] is not None:
            json_config["projectId"] = cl_params["idProject"]

        json_step_config = test_config["configStep"]
        if cl_params["idProject"] is not None and json_step_config is not None:
            json_step_config["idProject"] = cl_params["idProject"]
        if "device" in json_config:
            cl_params["device"] = json_config["device"]
        if cl_params["url"] is not None:
            json_config["url"] = cl_params["url"]
        cl_params["json_config"] = json_config
        cl_params["json_step_config"] = json_step_config

        return {"cl_params": cl_params, "test_config": test_config}
