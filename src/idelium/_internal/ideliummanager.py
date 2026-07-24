"""System module."""

from __future__ import absolute_import
import sys
import importlib.util
import shutil
from idelium._internal.commons.resultenum import Result
from idelium._internal.pluginapi import (
    PluginContractError,
    PluginRegistry,
    redact_plugin_error,
)
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
    def execute_step(driver, config):
        """Execute single step"""
        status = "1"
        step_failed = ""
        wrapper = config["wrapper"]
        printer = config["printer"]
        typeOfStep = "seleniumOrAppium"
        postman_data = None
        dependency_failed = False
        for object_step in config["json_step"]["steps"]:
            if status != "1":
                printer.danger(object_step["stepType"] + ": skipped")
                continue

            if object_step["stepType"] == "postman_collection":
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
                if config["is_debug"] is True:
                    for result in postman_data:
                        status_label = "PASSED" if result["passed"] else "FAILED"
                        printer.print_important_text(
                            "Postman result: {} {} {} {}".format(
                                status_label,
                                result.get("method", ""),
                                result.get("status", ""),
                                result.get("name", "Unnamed request"),
                            )
                        )
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
                    module = importlib.import_module(
                        "plugin." + object_step["stepType"], package=__package__
                    )
                    entrypoint = getattr(module, plugin_definition.entrypoint)
                    params = object_step.get("params", None)
                    plugin_response = entrypoint(driver, config["json_config"], params)
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
