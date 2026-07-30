"""System module."""

from __future__ import absolute_import
import sys
import shutil
from idelium._internal.commons.resultenum import Result
from idelium._internal.pluginapi import (
    PluginContractError,
    PluginRegistry,
    redact_plugin_error,
)
from idelium._internal.pluginrunner import execute_plugin_in_subprocess
from idelium._internal.wrappers.ideliumselenium import IdeliumSelenium
from idelium._internal.wrappers.ideliumappium import IdeliumAppium
from idelium._internal.thirdparties.ideliumpostman import (
    NEWMAN_MISSING_MESSAGE,
    PostmanCollection,
    PostmanNewmanCollection,
)


class StartManager:
    """Start manager"""

    POSTMAN_NEWMAN_RUNTIMES = {"newman", "postman", "postman_newman"}
    POSTMAN_AUTO_RUNTIMES = {"auto", "postman_auto"}

    @staticmethod
    def _postman_missing_newman_result():
        return [
            {
                "name": "Newman",
                "response": "",
                "status": "0",
                "method": "NEWMAN",
                "url": "",
                "time": 0,
                "passed": False,
                "assertions": [
                    {
                        "name": "newman",
                        "passed": False,
                        "message": NEWMAN_MISSING_MESSAGE,
                    }
                ],
            }
        ]

    @staticmethod
    def _postman_missing_collection_result():
        message = (
            "Postman step has no executable collection. Re-import the test with a "
            "postman_collection action that contains the Postman collection payload."
        )
        return [
            {
                "name": "Postman collection",
                "response": "",
                "status": "0",
                "method": "POSTMAN",
                "url": "",
                "time": 0,
                "passed": False,
                "assertions": [
                    {
                        "name": "postman collection",
                        "passed": False,
                        "message": message,
                    }
                ],
            }
        ]

    @staticmethod
    def load_module(name):
        """load plugin"""
        print(name)
        name = name + ".plugin"
        print(name)
        mod = __import__(name, fromlist=["plugin"])
        return mod

    @staticmethod
    def get_wrapper(config):
        """return type of wrapper"""
        wrapper = None
        if config["isRealDevice"] is False:
            if config["is_debug"] is True:
                print("Using wrapper Selenium")
            wrapper = IdeliumSelenium()
        else:
            if config["is_debug"] is True:
                print("Using wrapper Appium")
            wrapper = IdeliumAppium()
        return wrapper

    @staticmethod
    def _postman_event_has_script(event):
        """Return True when a Postman event contains executable script lines."""
        script = (event or {}).get("script") or {}
        exec_lines = script.get("exec") or []
        if isinstance(exec_lines, str):
            return bool(exec_lines.strip())
        return any(str(line).strip() for line in exec_lines)

    @staticmethod
    def _postman_item_requires_newman(item):
        """Detect Postman features that require Newman for compatibility."""
        for event in (item or {}).get("event") or []:
            if event.get("listen") in {
                "prerequest",
                "test",
            } and StartManager._postman_event_has_script(event):
                return True
        return any(
            StartManager._postman_item_requires_newman(child)
            for child in (item or {}).get("item") or []
        )

    @staticmethod
    def _postman_collection_stats(item):
        """Return safe, non-sensitive diagnostics for a Postman collection item."""
        stats = {"requests": 0, "events": 0}
        if not isinstance(item, dict):
            return stats
        if "request" in item:
            stats["requests"] += 1
        stats["events"] += len(item.get("event") or [])
        for child in item.get("item") or []:
            child_stats = StartManager._postman_collection_stats(child)
            stats["requests"] += child_stats["requests"]
            stats["events"] += child_stats["events"]
        return stats

    @staticmethod
    def _postman_requires_newman(postman_config):
        """Detect collection payloads that need the full Postman runtime."""
        if postman_config.get("iterationData") or postman_config.get("dataFile"):
            return True
        collection = postman_config.get("collection") or {}
        return StartManager._postman_item_requires_newman(collection)

    @staticmethod
    def _postman_runtime(object_step):
        """Resolve the requested Postman runtime."""
        postman_config = object_step.get("collection", {})
        runtime = (
            object_step.get("postmanRuntime")
            or object_step.get("runtime")
            or postman_config.get("runtime")
            or postman_config.get("mode")
            or "postman_auto"
        )
        return str(runtime).lower(), postman_config

    @staticmethod
    def _is_postman_step(object_step):
        """Detect Postman collection steps across legacy and normalized payloads."""
        step_markers = [
            object_step.get("editorType"),
            object_step.get("stepType"),
            object_step.get("type"),
            object_step.get("actionType"),
            object_step.get("runtime"),
        ]
        if any("postman" in str(marker).lower() for marker in step_markers if marker):
            return True
        collection = object_step.get("collection")
        if not isinstance(collection, dict):
            return False
        nested_collection = collection.get("collection")
        return bool(
            (isinstance(nested_collection, dict) and "item" in nested_collection)
            or ("info" in collection and "item" in collection)
            or ("item" in collection)
        )

    @staticmethod
    def _postman_assertion_summary(result):
        assertions = result.get("assertions") or []
        if not assertions:
            return "0/0 assertions"
        passed = sum(1 for assertion in assertions if assertion.get("passed") is True)
        return "{}/{} assertions".format(passed, len(assertions))

    @staticmethod
    def _print_postman_results(printer, postman_data):
        """Print one safe terminal line for every Postman request result."""
        if not postman_data:
            printer.warning("Postman calls: no request results were captured.")
            return

        printer.print_important_text("Postman calls:")
        total = len(postman_data)
        for index, result in enumerate(postman_data, start=1):
            status_label = "PASSED" if result.get("passed") is True else "FAILED"
            line = "[{}/{}] {} {} {} {}ms {} - {}".format(
                index,
                total,
                status_label,
                result.get("method", ""),
                result.get("status", ""),
                result.get("time", 0),
                result.get("url", "") or "(no url)",
                result.get("name", "Unnamed request"),
            )
            line = line + " (" + StartManager._postman_assertion_summary(result) + ")"
            if result.get("passed") is True:
                printer.success(line)
            else:
                printer.danger(line)

    @staticmethod
    def execute_step(driver, config):
        """Execute single step"""
        status = "1"
        step_failed = ""
        wrapper = config["wrapper"]
        printer = config["printer"]
        typeOfStep = "seleniumOrAppium"
        postman_data = None
        dependency_failed = False
        if not config["json_step"].get("steps") and StartManager._is_postman_step(
            config["json_step"]
        ):
            postman_data = StartManager._postman_missing_collection_result()
            printer.danger(postman_data[0]["assertions"][0]["message"])
            return {
                "driver": driver,
                "status": "2",
                "step_failed": config["json_step"],
                "type": "postman",
                "postman_data": postman_data,
                "dependency_failed": False,
            }

        for object_step in config["json_step"]["steps"]:
            if status != "1":
                printer.danger(object_step["stepType"] + ": skipped")
                continue

            if StartManager._is_postman_step(object_step):
                verify = config.get("caBundle") or not config.get("insecure", False)
                timeout = (
                    float(config.get("httpConnectTimeout", 5)),
                    float(config.get("httpReadTimeout", 30)),
                )
                runtime, postman_config = StartManager._postman_runtime(object_step)
                use_newman = runtime in StartManager.POSTMAN_NEWMAN_RUNTIMES or (
                    runtime in StartManager.POSTMAN_AUTO_RUNTIMES
                    and StartManager._postman_requires_newman(postman_config)
                )
                if config["is_debug"] is True:
                    stats = StartManager._postman_collection_stats(
                        postman_config.get("collection") or {}
                    )
                    runner = "newman" if use_newman else "safe"
                    printer.print_important_text(
                        "Postman runtime: requested={}, runner={}, requests={}, events={}".format(
                            runtime,
                            runner,
                            stats["requests"],
                            stats["events"],
                        )
                    )
                if use_newman:
                    if not shutil.which("newman"):
                        dependency_failed = True
                        printer.danger(NEWMAN_MISSING_MESSAGE)
                        postman_data = StartManager._postman_missing_newman_result()
                    else:
                        postman = PostmanNewmanCollection(
                            timeout=float(config.get("postmanNewmanTimeout", 300))
                        )
                        postman_data = postman.start_postman_test(
                            object_step["collection"], config["is_debug"]
                        )
                else:
                    postman = PostmanCollection(verify=verify, timeout=timeout)
                    postman_data = postman.start_postman_test(
                        object_step["collection"], config["is_debug"]
                    )
                StartManager._print_postman_results(printer, postman_data)
                for result in postman_data:
                    for assertion in result.get("assertions", []):
                        if assertion.get("passed") is False:
                            printer.danger(
                                "{}: {}".format(
                                    assertion.get("name", "postman assertion"),
                                    assertion.get("message", "Assertion failed."),
                                )
                            )
                typeOfStep = "postman"
                if any(not result["passed"] for result in postman_data):
                    status = "2"
                    step_failed = object_step
                continue

            return_object_step = wrapper.command(
                object_step["stepType"], driver, config, object_step
            )
            if return_object_step is None:
                try:
                    registry = PluginRegistry.from_config(config.get("plugins", {}))
                except PluginContractError as err:
                    printer.danger("Invalid plugin metadata: " + redact_plugin_error(err))
                    status = "2"
                    step_failed = object_step
                    continue
                plugin_definition = registry.get_step_plugin(object_step["stepType"])
                if plugin_definition is None:
                    printer.danger(
                        "Plugin step is not registered or does not declare the browser.step capability: "
                        + object_step["stepType"]
                    )
                    status = "2"
                    step_failed = object_step
                    continue
                try:
                    params = object_step.get("params", None)
                    plugin_response = execute_plugin_in_subprocess(
                        plugin_definition, config["json_config"], params
                    )
                    if plugin_response == Result.KO:
                        status = "2"
                        print(
                            "Plugin response: " + object_step["note"],
                            end="->",
                            flush=True,
                        )
                        printer.danger("FAILED")
                    if plugin_response == Result.NA:
                        status = "5"
                        print(
                            "Plugin response: " + object_step["note"],
                            end="->",
                            flush=True,
                        )
                        printer.warning("NA")
                except Exception as err:
                    printer.danger("----------")
                    printer.danger(redact_plugin_error(err))
                    printer.danger("----------")
                    printer.danger(
                        "Plugin step failed inside the isolated extension boundary: "
                        + object_step["stepType"]
                    )
                    if not config["ideliumServer"]:
                        sys.exit(1)
                    else:
                        status = "2"
                continue

            if "config" in return_object_step:
                config = return_object_step["config"]
            if "driver" in return_object_step:
                driver = return_object_step["driver"]
            if return_object_step["returnCode"] == Result.KO:
                status = "2"

            if status == "2":
                step_failed = object_step

        return {
            "driver": driver,
            "status": status,
            "step_failed": step_failed,
            "type": typeOfStep,
            "postman_data": postman_data,
            "dependency_failed": dependency_failed,
        }

    def execute_single_step(self, test_configurations, config):
        """execute single page"""
        printer = config["printer"]
        driver = None

        if config["isRealDevice"] is False:
            if config["is_debug"] is True:
                print("Using wrapper Selenium")
            wrapper = IdeliumSelenium()
        else:
            if config["is_debug"] is True:
                print("Using wrapper Appium")
            wrapper = IdeliumAppium()
        for file_step_name in config["file_steps"].split(","):
            try:
                json_step = test_configurations["steps"][file_step_name]
                printer.underline(json_step["name"])
                config["wrapper"] = wrapper
                config["printer"] = printer
                config["json_step"] = json_step
                object_return = self.execute_step(driver, config)
                driver = object_return["driver"]
                string_to_show = (
                    file_step_name + " the return value " + object_return["status"]
                )
                if object_return["status"] == "1":
                    printer.success(string_to_show)
                elif object_return["status"] == "5":
                    printer.warning(string_to_show)
                else:
                    printer.danger(string_to_show)

            except BaseException as err:
                printer.danger("---------- Execute step ------")
                print(err)
                printer.danger("----------")
                printer.danger(
                    "Warning, the file step: "
                    + file_step_name
                    + " not exist or is not a json (err 2)"
                )
                if config["ideliumServer"] is False:
                    sys.exit(1)
