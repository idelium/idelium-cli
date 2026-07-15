"""System module."""
from __future__ import absolute_import
import sys
import importlib.util
from idelium._internal.commons.resultenum import Result
from idelium._internal.wrappers.ideliumselenium import IdeliumSelenium
from idelium._internal.wrappers.ideliumappium import IdeliumAppium
from idelium._internal.thirdparties.ideliumpostman import PostmanCollection

class StartManager:
    ''' Start manager '''
    @staticmethod
    def load_module(name):
        ''' load plugin '''
        print(name)
        name = name + ".plugin"
        print(name)
        mod = __import__(name, fromlist=["plugin"])
        return mod
    @staticmethod
    def get_wrapper(config):
        ''' return type of wrapper '''
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
    def execute_step(driver, config):
        ''' Execute single step '''
        status = "1"
        step_failed = ""
        wrapper = config["wrapper"]
        printer = config["printer"]
        typeOfStep='seleniumOrAppium'
        postman_data=None        
        for object_step in config["json_step"]["steps"]:
            if status != "1":
                printer.danger(object_step["stepType"] + ": skipped")
                continue

            if object_step['stepType'] == 'postman_collection':
                verify = config.get("caBundle") or not config.get("insecure", False)
                timeout = (
                    float(config.get("httpConnectTimeout", 5)),
                    float(config.get("httpReadTimeout", 30)),
                )
                postman=PostmanCollection(verify=verify, timeout=timeout)
                postman_data=postman.start_postman_test(object_step['collection'],config["is_debug"])
                typeOfStep='postman'
                if any(not result['passed'] for result in postman_data):
                    status = "2"
                    step_failed = object_step
                continue

            return_object_step = wrapper.command(object_step["stepType"], driver, config, object_step)
            if return_object_step is None:
                try:
                    module = importlib.import_module("plugin." + object_step["stepType"], package=__package__)
                    params = object_step.get("params", None)
                    plugin_response = module.init(driver, config["json_config"], params)
                    if plugin_response == Result.KO:
                        status = "2"
                        print("Plugin response: " + object_step["note"], end="->", flush=True)
                        printer.danger("FAILED")
                    if plugin_response == Result.NA:
                        status = "5"
                        print("Plugin response: " + object_step["note"], end="->", flush=True)
                        printer.warning("NA")
                except Exception as err:
                    printer.danger("----------")
                    print(err)
                    printer.danger("----------")
                    printer.danger("Warning stepType: " + object_step["stepType"] + " not exist or there is an error in your extra module")
                    if not config['ideliumServer']:
                        sys.exit(1)
                    else:
                        status=2
                continue

            if "config" in return_object_step:
                config = return_object_step["config"]
            if "driver" in return_object_step:
                driver = return_object_step["driver"]
            if return_object_step["returnCode"] == Result.KO:
                status = "2"

            if status == "2":
                step_failed = object_step

        return {"driver": driver, "status": status, "step_failed": step_failed, 'type': typeOfStep, 'postman_data': postman_data}
    def execute_single_step(self, test_configurations, config):
        """ execute single page """
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
                object_return = self.execute_step(driver,
                                                 config)
                driver = object_return["driver"]
                string_to_show = (file_step_name + " the return value " +
                                object_return["status"])
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
                printer.danger("Warning, the file step: " + file_step_name +
                               " not exist or is not a json (err 2)")
                if config['ideliumServer'] is False:
                    sys.exit(1)
