"""System module."""

from __future__ import absolute_import
import sys
import os
import json
import collections
import time
from pathlib import Path
import base64
from idelium._internal.commons.connection import Connection, HttpTransportError
from idelium._internal.executionreport import (
    build_execution_report,
    write_html_report,
    write_json_report,
)
from idelium._internal.pluginapi import normalize_plugin_payload
from PIL import Image


class TypeDir:
    """Type Dir"""

    PROJECT_MAIN_DIR = 0
    PROJECT_DIR = 1
    IDCYCLE_DIR = 2
    STEP_DIR = 3
    CONFIGURATIONSTEP_DIR = 4
    PLUGIN_DIR = 5
    ENVIRONMENTS_DIR = 6


class IdeliumWs:
    """IdeliumWs"""

    @staticmethod
    def create_folder(config):
        """create folder"""
        url = config["api_idelium"] + "testcycle"
        payload = {
            "testCycleId": config["idCycle"],
        }
        return Connection.start(
            "POST", url, payload, config["ideliumKey"], config["is_debug"]
        )

    @staticmethod
    def create_test(config, id_cycle, id_test, name):
        """create test"""
        url = config["api_idelium"] + "test"
        payload = {
            "testCycleId": id_cycle,
            "testId": id_test,
            "name": name,
        }
        return Connection.start(
            "POST", url, payload, config["ideliumKey"], config["is_debug"]
        )

    @staticmethod
    def update_test(config, id_test, status, postman_data):
        """create test"""
        url = config["api_idelium"] + "test"
        payload = {
            "testId": id_test,
            "status": status,
            "postmanData": postman_data,
        }
        return Connection.start(
            "PUT", url, payload, config["ideliumKey"], config["is_debug"]
        )

    @staticmethod
    def create_step(config, id_cycle, id_test, id_step, name, status, data, typeofstep):
        """create step"""
        url = config["api_idelium"] + "step"
        payload = {
            "testCycleId": id_cycle,
            "testId": id_test,
            "stepId": id_step,
            "name": name,
            "status": int(status),
            "data": json.dumps(data),
            "type": typeofstep,
            "screenshots": "[]",
        }
        return Connection.start(
            "POST", url, payload, config["ideliumKey"], config["is_debug"]
        )

    @staticmethod
    def update_step(config, id_step, screenshots):
        """update step"""
        url = config["api_idelium"] + "step"
        payload = {
            "stepId": id_step,
            "screenshots": json.dumps(screenshots),
        }
        return Connection.start(
            "PUT", url, payload, config["ideliumKey"], config["is_debug"]
        )

    @staticmethod
    def get_environments(config):
        """get environment"""
        url = config["api_idelium"] + "environments/" + str(config["idProject"])
        return Connection.start(
            "GET", url, None, config["ideliumKey"], config["is_debug"]
        )

    @staticmethod
    def get_cycles(config):
        """get cycles"""
        url = config["api_idelium"] + "testcycle/" + config["idCycle"]
        json_cycle = Connection.start(
            "GET", url, None, config["ideliumKey"], config["is_debug"]
        )
        if "config" in json_cycle:
            return json.loads(json_cycle["config"])
        return -1

    @staticmethod
    def get_tests(config, id_test):
        """get tests"""
        url = config["api_idelium"] + "test/" + str(id_test)
        json_test = Connection.start(
            "GET", url, None, config["ideliumKey"], config["is_debug"]
        )
        return json.loads(json_test["config"])

    @staticmethod
    def get_step(config, id_step):
        """get step"""
        url = config["api_idelium"] + "step/" + str(id_step)
        json_step = Connection.start(
            "GET", url, None, config["ideliumKey"], config["is_debug"]
        )
        return {
            "objectStep": json.loads(json_step["config"]),
            "step_json_name": json_step["name"] + "_" + str(id_step),
            "step_json_description": json_step["name"],
        }

    @staticmethod
    def create_directories(config):
        """create directories"""
        configuration_directories = [
            config["dir_idelium_scripts"],
            config["dir_idelium_scripts"] + "/" + config["idProject"],
            config["dir_idelium_scripts"]
            + "/"
            + config["idProject"]
            + "/"
            + config["idCycle"],
            config["dir_idelium_scripts"]
            + "/"
            + config["idProject"]
            + "/"
            + config["idCycle"]
            + "/step",
            config["dir_idelium_scripts"]
            + "/"
            + config["idProject"]
            + "/"
            + config["idCycle"]
            + "/configurationStep",
            config["dir_idelium_scripts"]
            + "/"
            + config["idProject"]
            + "/"
            + config["idCycle"]
            + "/plugin",
            config["dir_idelium_scripts"]
            + "/"
            + config["idProject"]
            + "/"
            + config["idCycle"]
            + "/environments",
        ]
        print("start download configuration")
        return configuration_directories

    def get_configuration(self, config):
        """download configuration files"""
        printer = config["printer"]
        configuration_step = {}
        configuration_directories = self.create_directories(config)
        object_cycle = self.get_cycles(config)
        if object_cycle == -1:
            printer.danger("The id_cycle " + str(config["idCycle"]) + " not exist")
            if config["ideliumServer"] is False:
                sys.exit(1)
            else:
                return False
        array_steps = {}
        array_environments = {}
        array_plugins = {}
        config_step = None
        # search cycle for this cycle
        for cycle in object_cycle:
            try:
                object_test = self.get_tests(config, cycle["id"])
            except HttpTransportError as error:
                raise HttpTransportError(
                    "Remote test cycle configuration is inconsistent: "
                    "test cycle {} references missing test {}. {}".format(
                        config["idCycle"],
                        cycle["id"],
                        error,
                    )
                ) from error
            for test in object_test:
                try:
                    step = self.get_step(config, test["id"])
                except HttpTransportError as error:
                    raise HttpTransportError(
                        "Remote test cycle configuration is inconsistent: "
                        "test cycle {} references missing step {}. {}".format(
                            config["idCycle"],
                            test["id"],
                            error,
                        )
                    ) from error
                # write step
                array_steps[step["step_json_name"]] = step["objectStep"]
                print(step["step_json_name"])
                json_file_path = (
                    configuration_directories[TypeDir.STEP_DIR]
                    + "/"
                    + step["step_json_name"]
                    + ".json"
                )
                if config["local"] is True and (
                    Path(json_file_path).exists() is False
                    or config["forcedownload"] is True
                ):
                    with open(json_file_path, "w") as file:
                        json.dump(step["objectStep"], file, indent=4, sort_keys=False)
        # write_configuration_step
        config_step = None
        json_file_path = (
            configuration_directories[TypeDir.CONFIGURATIONSTEP_DIR]
            + "/config_step.json"
        )
        if config["local"] is True and (
            Path(json_file_path).exists() is False or config["forcedownload"] is True
        ):
            with open(json_file_path, "w") as file:
                json.dump(configuration_step, file, indent=4, sort_keys=False)
        # search  plugins for projectId
        url = config["api_idelium"] + "plugins/" + str(config["idProject"])
        json_plugins = Connection.start(
            "GET", url, None, config["ideliumKey"], config["is_debug"]
        )
        for plugin_det in json_plugins:
            url = config["api_idelium"] + "plugin/" + str(plugin_det["id"])
            json_plugin = Connection.start(
                "GET", url, None, config["ideliumKey"], config["is_debug"]
            )
            # save  plugin for projectId
            plugin_definition = normalize_plugin_payload(
                json_plugin["name"], json_plugin["code"]
            )
            array_plugins[plugin_definition.name] = plugin_definition.as_config()
            plugins_dir = (
                config["dir_idelium_scripts"] + "/" + config["idProject"] + "/plugin"
            )
            py_file_path = plugins_dir + "/" + plugin_definition.name + ".py"
            if Path(plugins_dir).exists() is False:
                os.makedirs(plugins_dir)
                if config["is_debug"] is True:
                    print("created temporary directory", plugins_dir)
            if config["is_debug"] is True:
                print("plugin file saved in:", py_file_path)
            py_file = open(py_file_path, "wt")
            py_file.write(plugin_definition.source)
            py_file.close()
        # download environments
        json_environments = self.get_environments(config)
        printer.success("finish download file")
        for env in json_environments:
            url = config["api_idelium"] + "environment/" + str(env["id"])
            json_environment = Connection.start(
                "GET", url, None, config["ideliumKey"], config["is_debug"]
            )
            file_name_env = json_environment["code"]
            code_environment = json.loads(
                json_environment["config"], object_pairs_hook=collections.OrderedDict
            )
            array_environments[file_name_env] = code_environment
            json_file_path = (
                configuration_directories[TypeDir.ENVIRONMENTS_DIR]
                + "/"
                + file_name_env
                + ".json"
            )
            if config["local"] is True and (
                Path(json_file_path).exists() is False
                or config["forcedownload"] is True
            ):
                with open(json_file_path, "w") as file:
                    json.dump(code_environment, file, indent=4, sort_keys=False)
        return {
            "steps": array_steps,
            "environments": array_environments,
            "plugins": array_plugins,
            "configStep": config_step,
            "environmentDir": configuration_directories[TypeDir.ENVIRONMENTS_DIR],
            "stepDir": configuration_directories[TypeDir.STEP_DIR],
            "config_stepDir": configuration_directories[TypeDir.CONFIGURATIONSTEP_DIR],
            "id_cycleDir": configuration_directories[TypeDir.IDCYCLE_DIR],
        }

    def start_test(self, idelium, test_configurations, config):
        """start test"""
        exit_code = 0
        report_events = []
        if config["ideliumServer"] is True:
            Path(config["dir_idelium_scripts"] + "server").touch()
        wrapper = idelium.get_wrapper(config)
        object_cycle = self.get_cycles(config)
        driver = None
        id_cycle = None
        if config["test"] is False:
            id_cycle = self.create_folder(config)["idCycle"]
        for cycle in object_cycle:
            # search test for this cycle
            printer = config["printer"]
            object_test = self.get_tests(config, cycle["id"])
            printer.success("Test: " + cycle["description"])
            id_test = cycle["id"]
            if config["test"] is False:
                id_test = self.create_test(
                    config,
                    id_cycle,
                    cycle["id"],
                    cycle["name"],
                )["idTest"]
            test_failed = False
            report_test = {
                "id": cycle["id"],
                "name": cycle["name"],
                "description": cycle["description"],
                "steps": [],
            }
            for test in object_test:
                if test_failed is False:
                    json_step = test_configurations["steps"][
                        test["name"] + "_" + str(test["id"])
                    ]
                    printer.underline(json_step["name"] + "(" + str(test["id"]) + ")")
                    config["wrapper"] = wrapper
                    config["printer"] = printer
                    config["json_step"] = json_step
                    config["plugins"] = test_configurations.get("plugins", {})
                    started_at = time.monotonic()
                    object_return = idelium.execute_step(driver, config)
                    duration_ms = int((time.monotonic() - started_at) * 1000)
                    status = object_return["status"]
                    driver = object_return["driver"]
                    postman_data = object_return["postman_data"]
                    typeofstep = object_return["type"]
                    step_failed = object_return["step_failed"]
                    config["status"] = status
                    config["step_failed"] = step_failed
                    id_step = None
                    # test["name"],
                    if config["test"] is False:
                        id_step = self.create_step(
                            config,
                            id_cycle,
                            id_test,
                            test["id"],
                            json_step["name"],
                            status,
                            postman_data,
                            typeofstep,
                        )["idStep"]
                    if status in ("2", "5"):
                        exit_code = 1
                        if object_return["type"] == "seleniumOrAppium":
                            path = "screenshots/"
                            file_name = str(id_test) + ".png"
                            if not os.path.exists(path):
                                os.makedirs(path)
                            if config["json_step"]["attachScreenshot"] is True:
                                wrapper.screen_shot(
                                    driver, path + file_name, config["ideliumServer"]
                                )
                            if config["test"] is False:
                                file_name_jpg = path + str(id_test) + ".jpg"
                                with Image.open(path + file_name) as img:
                                    rgb_im = img.convert("RGB")
                                    rgb_im.save(file_name_jpg)
                                    with open(file_name_jpg, "rb") as img_file:
                                        screenshot_base64 = base64.b64encode(
                                            img_file.read()
                                        )
                                        self.update_step(
                                            config,
                                            id_step,
                                            [
                                                "data:image/jpg;base64,"
                                                + str(screenshot_base64)[2:-1]
                                            ],
                                        )

                                os.unlink(path + file_name)
                                os.unlink(file_name_jpg)

                        should_stop = (
                            object_return["type"] == "postman"
                            or config["json_step"]["failedExit"] is True
                        )
                        if config["test"] is False:
                            self.update_test(config, id_test, 2, postman_data)
                        if should_stop:
                            printer.danger(
                                "The test '"
                                + cycle["name"]
                                + "' was interrupted because a required step failed"
                            )
                            test_failed = True
                    else:
                        if config["test"] is False:
                            self.update_test(config, id_test, 1, postman_data)
                    report_test["steps"].append(
                        self._report_step_event(
                            test,
                            json_step,
                            status,
                            duration_ms,
                            typeofstep,
                            postman_data,
                            step_failed,
                        )
                    )
                else:
                    report_test["steps"].append(
                        {
                            "id": test["id"],
                            "name": test["name"],
                            "type": "skipped",
                            "status": "5",
                            "durationMilliseconds": 0,
                            "diagnostics": [
                                {
                                    "level": "warning",
                                    "message": "Step skipped because a previous required step failed.",
                                }
                            ],
                            "artifacts": [],
                            "postmanResults": [],
                        }
                    )
            report_events.append(report_test)
            if config["ideliumServer"] is True:
                os.remove(config["dir_idelium_scripts"] + "server")
            if driver != None:
                driver.quit()
        self._write_execution_reports(report_events, config, exit_code, printer)
        return exit_code

    @staticmethod
    def _report_step_event(
        test,
        json_step,
        status,
        duration_ms,
        typeofstep,
        postman_data,
        step_failed,
    ):
        diagnostics = []
        if status in ("2", "5") and step_failed:
            diagnostics.append(
                {
                    "level": "error" if status == "2" else "warning",
                    "message": "Step failed during execution.",
                }
            )
        return {
            "id": test["id"],
            "name": json_step.get("name", test["name"]),
            "type": typeofstep,
            "status": status,
            "durationMilliseconds": duration_ms,
            "diagnostics": diagnostics,
            "artifacts": [],
            "postmanResults": postman_data or [],
        }

    @staticmethod
    def _write_execution_reports(report_events, config, exit_code, printer):
        if not config.get("jsonReport") and not config.get("htmlReport"):
            return
        report = build_execution_report(
            report_events,
            config=config,
            exit_code=exit_code,
        )
        if config.get("jsonReport"):
            write_json_report(report, config["jsonReport"])
            printer.success("JSON execution report written to " + config["jsonReport"])
        if config.get("htmlReport"):
            write_html_report(report, config["htmlReport"])
            printer.success("HTML execution report written to " + config["htmlReport"])
