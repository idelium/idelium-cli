"""System module."""

from __future__ import absolute_import
import sys
import os
import json
import collections
import time
import re
import platform
from pathlib import Path
import base64
from idelium._internal.commons.connection import Connection, HttpTransportError
from idelium._internal.executionreport import (
    build_execution_report,
    write_html_report,
    write_junit_report,
    write_json_report,
    write_markdown_report,
)
from idelium._internal.exitcodes import (
    EXIT_CONNECTIVITY_ERROR,
    EXIT_DEPENDENCY_ERROR,
    EXIT_SUCCESS,
    EXIT_TEST_FAILURE,
    EXIT_VALIDATION_ERROR,
)
from idelium._internal.pluginapi import normalize_plugin_payload
from idelium._internal.webdriver_adapter import W3CWebDriverAdapter
from PIL import Image


_SENSITIVE_ERROR_PATTERNS = (
    re.compile(r"(?i)(authorization|cookie|key|password|secret|session|token)=\S+"),
    re.compile(r"(?i)(authorization|cookie|key|password|secret|session|token):\S+"),
)


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
            "executionContext": IdeliumWs.execution_context(config),
        }
        return Connection.start(
            "POST", url, payload, config["ideliumKey"], config["is_debug"]
        )

    @staticmethod
    def execution_context(config):
        """Build non-sensitive execution metadata for the performed run."""

        json_config = config.get("json_config") or {}
        appium_caps = json_config.get("appiumDesiredCaps") or {}
        capabilities = config.get("seleniumGridCapabilities") or {}
        host_platform_name = platform.system().lower() or None
        host_platform_version = platform.release() or None
        context = {
            "environment": config.get("environment"),
            "environmentName": (
                config.get("environmentResolution", {}).get("selected")
                or config.get("environment")
            ),
            "browser": (
                config.get("browser")
                or json_config.get("browser")
                or capabilities.get("browserName")
                or appium_caps.get("browserName")
            ),
            "browserVersion": (
                capabilities.get("browserVersion")
                or capabilities.get("version")
                or appium_caps.get("browserVersion")
            ),
            "device": config.get("device") or json_config.get("device"),
            "deviceName": appium_caps.get("deviceName") or json_config.get("deviceName"),
            "deviceType": json_config.get("deviceType"),
            "platformName": (
                json_config.get("platformName")
                or capabilities.get("platformName")
                or appium_caps.get("platformName")
                or host_platform_name
            ),
            "platformVersion": (
                json_config.get("platformVersion")
                or capabilities.get("platformVersion")
                or appium_caps.get("platformVersion")
                or host_platform_version
            ),
            "runtime": json_config.get("runtime"),
        }
        return {
            key: str(value)
            for key, value in context.items()
            if value is not None and str(value).strip() != ""
        }

    @staticmethod
    def update_folder(config, id_cycle, status):
        """Finalize the performed test cycle status."""
        url = config["api_idelium"] + "testcycle"
        payload = {
            "testCycleId": id_cycle,
            "status": status,
        }
        return Connection.start(
            "PUT", url, payload, config["ideliumKey"], config["is_debug"]
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
        # Step execution can outlive the server keep-alive timeout. Do not reuse
        # an idle connection for this non-idempotent request.
        Connection.reset_session()
        return Connection.start(
            "POST", url, payload, config["ideliumKey"], config["is_debug"]
        )

    @staticmethod
    def skipped_step_result(step_id, step_name, typeofstep, reason):
        """Build a safe skipped-step payload for remote result visibility."""
        return {
            "runtime": typeofstep,
            "schemaVersion": "performed-step-result.v1",
            "summary": {
                "status": "skipped",
                "stepId": step_id,
                "stepName": step_name,
            },
            "durationMilliseconds": 0,
            "diagnostics": [
                {
                    "level": "warning",
                    "message": reason,
                }
            ],
            "artifacts": [],
            "postmanResults": [],
        }

    @staticmethod
    def failed_step_result(step_id, step_name, typeofstep, reason, duration_ms):
        """Build a failed-step payload when the CLI aborts inside a step."""
        return {
            "runtime": typeofstep,
            "schemaVersion": "performed-step-result.v1",
            "summary": {
                "status": "failed",
                "stepId": step_id,
                "stepName": step_name,
            },
            "durationMilliseconds": duration_ms,
            "diagnostics": [
                {
                    "level": "error",
                    "message": reason,
                }
            ],
            "artifacts": [],
            "postmanResults": [],
        }

    @staticmethod
    def step_runtime(json_step):
        """Return the persisted runtime accepted by the Idelium API."""
        raw_runtime = (
            json_step.get("type")
            or json_step.get("runtime")
            or json_step.get("stepType")
            or json_step.get("wrapper")
            or "seleniumOrAppium"
        )
        runtime = str(raw_runtime)
        if runtime == "selenium":
            return "selenium"
        if runtime == "postman":
            return "postman"
        return "seleniumOrAppium"

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
        try:
            object_cycle = self.get_cycles(config)
        except HttpTransportError as error:
            if getattr(error, "status_code", None) == 404:
                raise HttpTransportError(
                    "Remote test cycle configuration is inconsistent: "
                    f"test cycle {config['idCycle']} was not found for the "
                    "provided Idelium key. Use the test cycle ID, not the "
                    f"imported test ID, and verify project {config['idProject']}. "
                    f"{error}",
                    status_code=error.status_code,
                    url=error.url,
                ) from error
            raise
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
                raise self._referenced_asset_error(
                    config["idCycle"],
                    "test",
                    cycle["id"],
                    error,
                ) from error
            for test in object_test:
                try:
                    step = self.get_step(config, test["id"])
                except HttpTransportError as error:
                    raise self._referenced_asset_error(
                        config["idCycle"],
                        "step",
                        test["id"],
                        error,
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

    @staticmethod
    def _referenced_asset_error(id_cycle, asset_type, asset_id, error):
        if getattr(error, "status_code", None) == 404:
            reason = f"references missing {asset_type} {asset_id}"
        else:
            reason = (
                f"could not load referenced {asset_type} {asset_id}; "
                "the Idelium API returned an unexpected response"
            )
        return HttpTransportError(
            "Remote test cycle configuration is inconsistent: "
            f"test cycle {id_cycle} {reason}. {error}",
            status_code=getattr(error, "status_code", None),
            url=getattr(error, "url", None),
        )

    def start_test(self, idelium, test_configurations, config):
        """start test"""
        exit_code = EXIT_SUCCESS
        report_events = []
        printer = config["printer"]
        if config["ideliumServer"] is True:
            Path(config["dir_idelium_scripts"] + "server").touch()
        wrapper = idelium.get_wrapper(config)
        object_cycle = self.get_cycles(config)
        if not object_cycle:
            printer.danger(
                "Remote test cycle configuration is inconsistent: "
                f"test cycle {config['idCycle']} contains no executable tests."
            )
            self._write_execution_reports(report_events, config, EXIT_VALIDATION_ERROR, printer)
            return EXIT_VALIDATION_ERROR
        driver = None
        id_cycle = None
        if config["test"] is False:
            id_cycle = self.create_folder(config)["idCycle"]
        try:
            for cycle in object_cycle:
                # search test for this cycle
                object_test = self.get_tests(config, cycle["id"])
                printer.success("Test: " + cycle["description"])
                if not object_test:
                    printer.danger(
                        "Remote test cycle configuration is inconsistent: "
                        f"test cycle {cycle['id']} contains no executable tests."
                    )
                    exit_code = EXIT_VALIDATION_ERROR
                    report_events.append(
                        {
                            "id": cycle["id"],
                            "name": cycle["name"],
                            "description": cycle["description"],
                            "steps": [],
                        }
                    )
                    continue
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
                        started_at = time.monotonic()
                        id_step = None
                        json_step = test_configurations["steps"].get(
                            test["name"] + "_" + str(test["id"]),
                            {
                                "name": test.get("name", "unknown"),
                                "attachScreenshot": False,
                                "failedExit": True,
                            },
                        )
                        typeofstep = self.step_runtime(json_step)
                        postman_data = []
                        step_failed = ""
                        bidi_artifacts = []
                        screenshot_artifacts = []
                        try:
                            printer.underline(
                                json_step["name"] + "(" + str(test["id"]) + ")"
                            )
                            config["wrapper"] = wrapper
                            config["printer"] = printer
                            config["json_step"] = json_step
                            config["plugins"] = test_configurations.get("plugins", {})
                            object_return = idelium.execute_step(driver, config)
                            duration_ms = int((time.monotonic() - started_at) * 1000)
                            status = object_return["status"]
                            driver = object_return["driver"]
                            postman_data = object_return["postman_data"]
                            typeofstep = object_return["type"]
                            step_failed = object_return["step_failed"]
                            bidi_artifacts = config.pop("bidiArtifacts", [])
                            dependency_failed = object_return.get(
                                "dependency_failed",
                                False,
                            )
                            config["status"] = status
                            config["step_failed"] = step_failed
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
                        except Exception as error:
                            duration_ms = int((time.monotonic() - started_at) * 1000)
                            status = "2"
                            safe_error = self._safe_error_message(error)
                            step_failed = {
                                "error": error.__class__.__name__,
                                "message": safe_error,
                            }
                            failed_payload = self.failed_step_result(
                                test["id"],
                                json_step.get("name", test.get("name", "unknown")),
                                typeofstep,
                                safe_error,
                                duration_ms,
                            )
                            printer.danger(
                                "Step failed with an unexpected CLI error: " + safe_error
                            )
                            config["status"] = status
                            config["step_failed"] = step_failed
                            if config["test"] is False:
                                id_step = self.create_step(
                                    config,
                                    id_cycle,
                                    id_test,
                                    test["id"],
                                    json_step.get("name", test.get("name", "unknown")),
                                    status,
                                    failed_payload,
                                    typeofstep,
                                )["idStep"]
                                self.update_test(config, id_test, 2, postman_data)
                            report_test["steps"].append(
                                self._report_step_event(
                                    test,
                                    json_step,
                                    status,
                                    duration_ms,
                                    typeofstep,
                                    postman_data,
                                    step_failed,
                                    bidi_artifacts,
                                    screenshot_artifacts,
                                )
                            )
                            if exit_code == EXIT_SUCCESS:
                                exit_code = EXIT_TEST_FAILURE
                            printer.danger(
                                "The test '"
                                + cycle["name"]
                                + "' was interrupted because a required step failed"
                            )
                            test_failed = True
                            continue
                        if status in ("2", "5"):
                            if dependency_failed:
                                exit_code = EXIT_DEPENDENCY_ERROR
                            elif exit_code == EXIT_SUCCESS:
                                exit_code = EXIT_TEST_FAILURE
                            if object_return["type"] == "seleniumOrAppium":
                                screenshot_artifacts = self._capture_failure_screenshot(
                                    wrapper,
                                    driver,
                                    config,
                                    id_test,
                                    id_step,
                                )

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
                                bidi_artifacts,
                                screenshot_artifacts,
                            )
                        )
                    else:
                        json_step = test_configurations["steps"].get(
                            test["name"] + "_" + str(test["id"]),
                            {"name": test["name"]},
                        )
                        skipped_reason = (
                            "Step skipped because a previous required step failed."
                        )
                        typeofstep = self.step_runtime(json_step)
                        skipped_payload = self.skipped_step_result(
                            test["id"],
                            json_step.get("name", test["name"]),
                            typeofstep,
                            skipped_reason,
                        )
                        if config["test"] is False:
                            self.create_step(
                                config,
                                id_cycle,
                                id_test,
                                test["id"],
                                json_step.get("name", test["name"]),
                                "5",
                                skipped_payload,
                                typeofstep,
                            )
                        report_test["steps"].append(
                            {
                                "id": test["id"],
                                "name": json_step.get("name", test["name"]),
                                "type": typeofstep,
                                "status": "5",
                                "durationMilliseconds": 0,
                                "diagnostics": [
                                    {
                                        "level": "warning",
                                        "message": skipped_reason,
                                    }
                                ],
                                "artifacts": [],
                                "postmanResults": [],
                            }
                        )
                report_events.append(report_test)
                if config["ideliumServer"] is True:
                    os.remove(config["dir_idelium_scripts"] + "server")
                if driver is not None:
                    try:
                        close_bidi_session = getattr(
                            wrapper,
                            "close_bidi_session",
                            None,
                        )
                        if close_bidi_session is not None:
                            close_bidi_session(config, printer)
                    finally:
                        cleanup_result = W3CWebDriverAdapter(driver).quit()
                        if cleanup_result.error is not None:
                            printer.danger(cleanup_result.error.message)
                        driver = None
        finally:
            finalize_exit_code = self._finalize_performed_cycle(
                config,
                id_cycle,
                exit_code,
                printer,
            )
            if exit_code == EXIT_SUCCESS and finalize_exit_code != EXIT_SUCCESS:
                exit_code = finalize_exit_code
        self._write_execution_reports(report_events, config, exit_code, printer)
        return exit_code

    def _finalize_performed_cycle(self, config, id_cycle, exit_code, printer):
        if config["test"] is True or id_cycle is None or not config.get("api_idelium"):
            return EXIT_SUCCESS
        status = 1
        if exit_code != EXIT_SUCCESS or sys.exc_info()[0] is not None:
            status = 2
        try:
            self.update_folder(config, id_cycle, status)
        except HttpTransportError as error:
            printer.danger(
                "Unable to finalize the remote performed test cycle "
                f"{id_cycle}: {error}"
            )
            return EXIT_CONNECTIVITY_ERROR
        return EXIT_SUCCESS

    @staticmethod
    def _report_step_event(
        test,
        json_step,
        status,
        duration_ms,
        typeofstep,
        postman_data,
        step_failed,
        artifacts=None,
        failure_artifacts=None,
    ):
        diagnostics = []
        if status in ("2", "5") and step_failed:
            message = (
                step_failed.get("message")
                if isinstance(step_failed, dict)
                else None
            )
            diagnostics.append(
                {
                    "level": "error" if status == "2" else "warning",
                    "message": message or "Step failed during execution.",
                }
            )
        return {
            "id": test["id"],
            "name": json_step.get("name", test["name"]),
            "type": typeofstep,
            "status": status,
            "durationMilliseconds": duration_ms,
            "diagnostics": diagnostics,
            "artifacts": (artifacts or []) + (failure_artifacts or []),
            "postmanResults": postman_data or [],
        }

    @staticmethod
    def _capture_failure_screenshot(wrapper, driver, config, id_test, id_step):
        """Capture one bounded failure screenshot artifact when available."""

        if driver is None:
            return []
        json_step = config.get("json_step", {})
        if (
            json_step.get("attachScreenshot") is not True
            and config.get("captureFailureScreenshots", True) is not True
        ):
            return []
        screenshot_dir = Path("screenshots")
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        screenshot_path = screenshot_dir / (IdeliumWs._safe_artifact_id(id_test) + ".png")
        printer = config.get("printer")
        try:
            wrapper.screen_shot(driver, str(screenshot_path), config["ideliumServer"])
            if config["test"] is False and id_step is not None:
                jpg_path = screenshot_path.with_suffix(".jpg")
                with Image.open(screenshot_path) as img:
                    rgb_im = img.convert("RGB")
                    rgb_im.save(jpg_path)
                with open(jpg_path, "rb") as img_file:
                    screenshot_base64 = base64.b64encode(img_file.read())
                IdeliumWs.update_step(
                    config,
                    id_step,
                    ["data:image/jpg;base64," + str(screenshot_base64)[2:-1]],
                )
                os.unlink(screenshot_path)
                os.unlink(jpg_path)
            size_bytes = (
                screenshot_path.stat().st_size if screenshot_path.exists() else 0
            )
            return [
                {
                    "name": "failure-screenshot.png",
                    "type": "image/png",
                    "path": str(screenshot_path),
                    "data": {
                        "captureOutcome": "captured",
                        "mediaType": "image/png",
                        "sizeBytes": size_bytes,
                        "sourceStepId": (
                            IdeliumWs._safe_artifact_id(id_step)
                            if id_step is not None
                            else "pending-step"
                        ),
                        "sourceTestId": IdeliumWs._safe_artifact_id(id_test),
                        "source": "webdriver-failure",
                    },
                }
            ]
        except BaseException as err:
            if printer is not None:
                printer.warning(
                    "Failure screenshot capture failed without changing the test result."
                )
                if config.get("is_debug"):
                    printer.warning(str(err))
            return []

    @staticmethod
    def _safe_artifact_id(value):
        """Return a filesystem-safe artifact id with no tenant metadata."""

        safe_value = "".join(
            char for char in str(value) if char.isalnum() or char in {"-", "_"}
        )
        return safe_value or "step"

    @staticmethod
    def _safe_error_message(error):
        """Return an observable error message without leaking credentials."""
        message = str(error).strip() or error.__class__.__name__
        for pattern in _SENSITIVE_ERROR_PATTERNS:
            message = pattern.sub(lambda match: match.group(1) + "=[REDACTED]", message)
        return message

    @staticmethod
    def _write_execution_reports(report_events, config, exit_code, printer):
        if (
            not config.get("jsonReport")
            and not config.get("htmlReport")
            and not config.get("markdownReport")
            and not config.get("junitReport")
        ):
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
        if config.get("markdownReport"):
            write_markdown_report(report, config["markdownReport"])
            printer.success(
                "Markdown execution report written to " + config["markdownReport"]
            )
        if config.get("junitReport"):
            write_junit_report(report, config["junitReport"])
            printer.success(
                "JUnit XML execution report written to " + config["junitReport"]
            )
