"""System module."""

from __future__ import absolute_import
import time
import sys
from urllib.parse import urlsplit
from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.firefox import GeckoDriverManager
from webdriver_manager.microsoft import EdgeChromiumDriverManager
from webdriver_manager.microsoft import IEDriverManager
from webdriver_manager.opera import OperaDriverManager
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.ie.service import Service as IeService
from selenium.webdriver.common.action_chains import ActionChains
from idelium._internal.commons.ideliumprinter import InitPrinter
from idelium._internal.commons.resultenum import Result
from idelium._internal.commons.seleniumkeyevent import EventKey
from idelium._internal.commons.seleniumby import SelBy
from idelium._internal.bidi import (
    BidiLifecycleError,
    BidiSessionLifecycle,
    negotiate_bidi_capabilities,
)
from idelium._internal.selector_diagnostics import collect_step_selector_diagnostics


printer = InitPrinter()


class IdeliumSelenium:
    """IdeliumSelenium"""

    SELENIUM_GENERIC_COMMANDS = {
        "accept_alert",
        "add_cookie",
        "back",
        "delete_all_cookies",
        "delete_cookie",
        "dismiss_alert",
        "element_state",
        "execute_script",
        "file_upload",
        "forward",
        "get_alert_text",
        "get_cookie",
        "get_cookies",
        "get_title",
        "get_url",
        "navigate_to",
        "new_window",
        "refresh",
        "shadow_find_element",
        "switch_window",
    }
    SELENIUM_ACTIONS = {
        "click",
        "context_click",
        "double_click",
        "drag_and_drop",
        "key_down",
        "key_up",
        "move_by_offset",
        "move_to",
        "pause",
        "scroll_by",
        "send_keys",
    }

    @staticmethod
    def _selenium_capabilities(config):
        """Return configured Selenium W3C capabilities."""
        capabilities = (
            config.get("seleniumGridCapabilities")
            or config.get("json_config", {}).get("seleniumGridCapabilities")
            or {}
        )
        browser = config.get("browser") or config.get("json_config", {}).get("browser")
        negotiation = negotiate_bidi_capabilities(
            browser=browser,
            mode=config.get("bidiMode", "disabled"),
            capabilities=capabilities,
        )
        config["bidiNegotiation"] = negotiation.as_dict()
        if negotiation.state == "failed":
            raise ValueError(negotiation.message)
        return negotiation.capabilities

    @staticmethod
    def _apply_selenium_capabilities(options, config):
        """Apply user-provided Selenium W3C capabilities to browser options."""
        for key, value in IdeliumSelenium._selenium_capabilities(config).items():
            options.set_capability(key, value)
        return options

    @staticmethod
    def _start_bidi_session(driver, config):
        """Start optional BiDi lifecycle tracking for a created WebDriver session."""
        lifecycle = BidiSessionLifecycle(config.get("bidiNegotiation"))
        try:
            lifecycle.open(driver)
        except BidiLifecycleError:
            config["bidiLifecycle"] = lifecycle.as_dict()
            raise
        config["bidiLifecycle"] = lifecycle.as_dict()
        config["_bidiSession"] = lifecycle
        return lifecycle

    @staticmethod
    def close_bidi_session(config, printer_instance=None):
        """Close optional BiDi resources without exposing session data."""
        lifecycle = config.pop("_bidiSession", None)
        if lifecycle is None:
            return
        try:
            lifecycle.close()
            config["bidiLifecycle"] = lifecycle.as_dict()
        except BidiLifecycleError as err:
            config["bidiLifecycle"] = lifecycle.as_dict()
            active_printer = printer_instance or printer
            active_printer.danger(str(err))

    @staticmethod
    def _local_driver(factory, manager, options=None, service_class=None):
        """Create a Selenium 4 local driver and fall back to a system driver."""
        try:
            if manager is not None and service_class is not None:
                return factory(
                    service=service_class(manager().install()), options=options
                )
            if options is not None:
                return factory(options=options)
            return factory()
        except BaseException:
            printer.warning("webdriver not found, try locally")
            if options is not None:
                return factory(options=options)
            return factory()

    @staticmethod
    def sleep(driver, config, object_step):
        """Sleep"""
        time.sleep(object_step["seconds"])
        return {"returnCode": Result.OK}

    def wait_and_click(self, driver, config, object_step):
        """wait and click"""
        wait_result = self.wait_for_next_step(driver, config, object_step)
        if wait_result["returnCode"] == Result.KO:
            return wait_result
        return self.click(driver, config, object_step)

    @staticmethod
    def find_element_by_xpath(driver, config, object_step):
        """find element by xpath condition"""
        try:
            driver.find_element(SelBy().get_by("XPATH"), object_step["xpath"])
            return {"returnCode": Result.OK}
        except BaseException as err:
            printer.danger("FAILED")
            print(err)
            return {"returnCode": Result.KO}

    @staticmethod
    def find_elements_by_xpath(driver, config, object_step):
        """find elements by xpath condition"""
        try:
            elements = driver.find_elements(
                SelBy().get_by("XPATH"), object_step["xpath"]
            )
            return {"returnCode": Result.OK if len(elements) > 0 else Result.KO}
        except BaseException as err:
            printer.danger("FAILED")
            print(err)
            return {"returnCode": Result.KO}

    @staticmethod
    def find_element(driver, config, object_step):
        """find element"""
        try:
            driver.find_element(
                SelBy().get_by(object_step["findBy"]), object_step["target"]
            )
            return {"returnCode": Result.OK}
        except BaseException as err:
            printer.danger("FAILED")
            print(err)
            return {"returnCode": Result.KO}

    @staticmethod
    def find_elements(driver, config, object_step):
        """find elements"""
        try:
            elements = driver.find_elements(
                SelBy().get_by(object_step["findBy"]),
                object_step["target"],
            )
            return {"returnCode": Result.OK if len(elements) > 0 else Result.KO}
        except BaseException as err:
            printer.danger("FAILED")
            print(err)
            return {"returnCode": Result.KO}

    @staticmethod
    def page_source(driver, config, object_step):
        """page source for debug is useful"""
        print(driver.page_source)
        return {"returnCode": Result.OK, "value": driver.page_source}

    @staticmethod
    def switch_to_frame(driver, config, object_step):
        """switch_to_frame"""
        try:
            by = SelBy()
            if "xpath" in object_step:
                frame = driver.find_element(by.get_by("XPATH"), object_step["xpath"])
            else:
                frame = driver.find_element(
                    by.get_by(object_step["findBy"]),
                    object_step["target"],
                )
            driver.switch_to.frame(frame)
            return {"returnCode": Result.OK}
        except BaseException as err:
            printer.danger("FAILED")
            print(err)
            return {"returnCode": Result.KO}

    @staticmethod
    def switch_to_default_content(driver, config, object_step):
        """switch_to_default_content"""
        driver.switch_to.default_content()
        return {"returnCode": Result.OK}

    @staticmethod
    def find_object_element(driver, config, object_step):
        """find_object_element"""
        return IdeliumSelenium.find_element_by_xpath(driver, config, object_step)

    @staticmethod
    def click_object(driver, config, object_step):
        """click_object"""
        try:
            print(object_step["note"], end="->", flush=True)
            time.sleep(1)
            by = SelBy()
            if "xpath" in object_step:
                element = driver.find_element(by.get_by("XPATH"), object_step["xpath"])
            else:
                element = driver.find_element(
                    by.get_by(object_step["findBy"]),
                    object_step["target"],
                )
            element.click()
            printer.success("ok")
            return {"returnCode": Result.OK}
        except BaseException as err:
            printer.danger("FAILED")
            print(err)
            # sys.exit(1)
            return {"returnCode": Result.KO}

    @staticmethod
    def drag_and_drop(driver, config, object_step):
        """drag_and_drop"""
        try:
            drag_element = driver.find_element_by_xpath(object_step["xpathDrag"])
            drop_element = driver.find_element_by_xpath(object_step["xpathDrop"])
            action = ActionChains(driver)
            action.drag_and_drop(drag_element, drop_element).perform()
            return {"returnCode": Result.OK}
        except BaseException as err:
            printer.danger("FAILED")
            print(err)
            # sys.exit(1)
            return {"returnCode": Result.KO}

    def open_browser(self, driver, config, object_step):
        """open browser"""
        driver = None
        return_code = Result.OK
        """ only for server mode """
        if "browser" in config:
            config["json_config"]["browser"] = config["browser"]
        if config.get("seleniumGridUrl"):
            try:
                driver = self.create_remote_driver(config)
            except (ValueError, TypeError, WebDriverException) as err:
                printer.danger("Unable to create Selenium Grid session")
                if config["is_debug"]:
                    printer.danger(str(err))
                return_code = Result.KO
        elif config["json_config"]["browser"] == "chrome":
            chrome_options = webdriver.ChromeOptions()
            if config["device"] is not None:
                mobile_emulation = {"deviceName": config["device"]}
                chrome_options = webdriver.ChromeOptions()
                chrome_options.add_experimental_option(
                    "mobileEmulation", mobile_emulation
                )
            else:
                if config["useragent"] is not None:
                    chrome_options.add_argument("user-agent=" + config["useragent"])
            if "accept_self_certificate" in config["json_config"]:
                if config["json_config"]["accept_self_certificate"] is True:
                    chrome_options.add_argument("ignore-certificate-errors")
                    chrome_options.accept_insecure_certs = True
            self._apply_selenium_capabilities(chrome_options, config)
            try:
                driver = self._local_driver(
                    webdriver.Chrome,
                    ChromeDriverManager,
                    chrome_options,
                    ChromeService,
                )
            except BaseException as err:
                printer.danger("webdriver error")
                print(
                    "probably you need to download manually the webdriver\nfrom https://googlechromelabs.github.io/chrome-for-testing"
                )
                if config["ideliumServer"] is False:
                    return_code = Result.KO
                    sys.exit(1)
                return_code = Result.KO
        elif config["json_config"]["browser"] == "firefox":
            firefox_options = webdriver.FirefoxOptions()
            if config["useragent"] is not None:
                firefox_options.set_preference(
                    "general.useragent.override", config["useragent"]
                )
            if "accept_self_certificate" in config["json_config"]:
                if config["json_config"]["accept_self_certificate"] is True:
                    firefox_options.accept_insecure_certs = True
            self._apply_selenium_capabilities(firefox_options, config)
            try:
                driver = self._local_driver(
                    webdriver.Firefox,
                    GeckoDriverManager,
                    firefox_options,
                    FirefoxService,
                )
            except BaseException as err:
                printer.danger("webdriver error")
                if config["ideliumServer"] is False:
                    return_code = Result.KO
                    sys.exit(1)
                return_code = Result.KO
        elif config["json_config"]["browser"] == "safari":
            try:
                driver = webdriver.Safari()
            except BaseException as err:
                printer.danger("webriver error")
                print(err)
                return_code = Result.KO
                if config["ideliumServer"] is False:
                    sys.exit(1)
        elif config["json_config"]["browser"] == "opera":
            try:
                webdriver_service = ChromeService(OperaDriverManager().install())
                webdriver_service.start()
                driver = webdriver.Remote(
                    webdriver_service.service_url, webdriver.DesiredCapabilities.OPERA
                )
            except BaseException as err:
                printer.danger("webriver error")
                print(err)
                return_code = Result.KO
                if config["ideliumServer"] is False:
                    sys.exit(1)
        elif config["json_config"]["browser"] == "edge":
            edge_options = webdriver.EdgeOptions()
            if config["useragent"] is not None:
                edge_options.add_argument("user-agent=" + config["useragent"])
            if "accept_self_certificate" in config["json_config"]:
                edge_options.accept_insecure_certs = bool(
                    config["json_config"]["accept_self_certificate"]
                )
            self._apply_selenium_capabilities(edge_options, config)
            try:
                driver = self._local_driver(
                    webdriver.Edge,
                    EdgeChromiumDriverManager,
                    edge_options,
                    EdgeService,
                )
            except BaseException as err:
                printer.danger("webdriver error")
                if config["ideliumServer"] is False:
                    return_code = Result.KO
                    sys.exit(1)
                return_code = Result.KO
        elif config["json_config"]["browser"] == "iexplorer":
            capabilities = webdriver.DesiredCapabilities().INTERNETEXPLORER
            if "accept_self_certificate" in config["json_config"]:
                if config["json_config"]["accept_self_certificate"] is True:
                    capabilities["acceptSslCerts"] = True
            try:
                driver = self._local_driver(
                    webdriver.Ie,
                    IEDriverManager,
                    None,
                    IeService,
                )
            except BaseException as err:
                printer.danger("webdriver error")
                if config["ideliumServer"] is False:
                    return_code = Result.KO
                    sys.exit(1)
                return_code = Result.KO
        else:
            printer.danger("driver not selected")
            if config["ideliumServer"] is False:
                sys.exit(1)
        if return_code == Result.OK:
            try:
                self._start_bidi_session(driver, config)
                driver.set_window_size(config["width"], config["height"])
                if "url" in object_step:
                    driver.get(object_step["url"])
                else:
                    driver.get(config["json_config"]["url"])
                return_code = Result.OK
                object_step["xpath"] = config["json_config"]["xpath_check_url"]
                if object_step["xpath"] == "":
                    object_step["xpath"] = "/html"
                if (
                    self.wait_for_next_step(driver, config, object_step)["returnCode"]
                    == Result.KO
                ):
                    return_code = Result.KO
                    config["json_step"]["attachScreenshot"] = True
                    config["json_step"]["failedExit"] = True
            except BidiLifecycleError as err:
                printer.danger(str(err))
                return_code = Result.KO
                config["json_step"]["attachScreenshot"] = True
                config["json_step"]["failedExit"] = True
        return {"driver": driver, "returnCode": return_code, "config": config}

    @staticmethod
    def create_remote_driver(config):
        """Create a Selenium Grid session from validated remote settings."""
        grid_url = config["seleniumGridUrl"]
        parsed_url = urlsplit(grid_url)
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            raise ValueError("seleniumGridUrl must be an HTTP or HTTPS URL")
        if parsed_url.username or parsed_url.password:
            raise ValueError("seleniumGridUrl must not contain embedded credentials")

        browser = config["json_config"]["browser"].lower()
        option_factories = {
            "chrome": webdriver.ChromeOptions,
            "edge": webdriver.EdgeOptions,
            "firefox": webdriver.FirefoxOptions,
            "iexplorer": webdriver.IeOptions,
            "safari": webdriver.SafariOptions,
        }
        if browser not in option_factories:
            raise ValueError("The selected browser is not supported by Selenium Grid")

        options = option_factories[browser]()
        if config.get("useragent"):
            if browser in {"chrome", "edge"}:
                options.add_argument("user-agent=" + config["useragent"])
            elif browser == "firefox":
                options.set_preference(
                    "general.useragent.override",
                    config["useragent"],
                )
        if config.get("device") and browser == "chrome":
            options.add_experimental_option(
                "mobileEmulation",
                {"deviceName": config["device"]},
            )
        options.accept_insecure_certs = bool(
            config["json_config"].get("accept_self_certificate", False)
        )
        IdeliumSelenium._apply_selenium_capabilities(options, config)

        return webdriver.Remote(command_executor=grid_url, options=options)

    @staticmethod
    def write_localstorage(driver, config, object_step):
        """write_localstorage"""

        try:
            print(object_step["note"], end="->", flush=True)
            script_js = ""
            for object_data in object_step["dataLocalStorage"]:
                for key in object_data:
                    script_js = (
                        script_js
                        + 'localStorage.setItem("'
                        + key
                        + "\", '"
                        + object_data[key]
                        + "')\n"
                    )
            script_js = (
                script_js
                + "return Array.apply(0, new Array(localStorage.length)).map(function (o, i)"
                + "{ return localStorage.getItem(localStorage.key(i)); })"
            )
            driver.execute_script(script_js)
            printer.success("ok")
            return {"returnCode": Result.OK}
        except BaseException as err:
            printer.danger("FAILED")
            print(err)
            # sys.exit(1)
            return {"returnCode": Result.KO}

    def screen_shot(self, driver, file_name, is_server):
        """screenshot"""

        try:
            driver.get_screenshot_as_file(file_name)
            return Result.OK
        except BaseException as err:
            printer.danger("FAILED")
            print(err)
            if is_server is False:
                sys.exit(1)

    def click(self, driver, config, object_step):
        """click"""

        by = SelBy()
        try:
            print(object_step["note"], end="->", flush=True)
            time.sleep(1)
            # for retrocompat
            if "xpath" in object_step:
                object_step["findBy"] = "XPATH"
                object_step["target"] = object_step["xpath"]
            driver.find_element(
                by.get_by(object_step["findBy"]), object_step["target"]
            ).click()
            printer.success("ok")
            return {"returnCode": Result.OK}
        except BaseException as err:
            printer.danger("FAILED")
            print(err)
            return {"returnCode": Result.KO}

    def select(self, driver, config, object_step):
        """select"""

        by = SelBy()
        print(object_step)
        try:
            print(object_step["note"], end="->", flush=True)
            time.sleep(1)
            # for retrocompat
            if "xpath" in object_step:
                object_step["findBy"] = "XPATH"
                object_step["target"] = object_step["xpath"]
            select = Select(
                driver.find_element(
                    by.get_by(object_step["findBy"]), object_step["target"]
                )
            )
            if "selectType" in object_step:
                if object_step["selectType"] == "label":
                    select.select_by_visible_text(object_step["value"])
                elif object_step["selectType"] == "value":
                    select.select_by_value(object_step["value"])
                elif object_step["selectType"] == "index":
                    select.select_by_index(object_step["value"])
                else:
                    printer.danger(
                        "selectType:"
                        + object_step["selectType"]
                        + " not supported in this moment"
                    )
            else:
                select.select_by_visible_text(object_step["value"])
            printer.success("ok")
            return {"returnCode": Result.OK}
        except BaseException as err:
            printer.danger("FAILED")
            printer.danger(err)
            return {"returnCode": Result.KO}

    def clear(self, driver, config, object_step):
        """clear"""

        by = SelBy()
        try:
            print(object_step["note"], end="->", flush=True)
            time.sleep(1)
            if "xpath" in object_step:
                object_step["findBy"] = "XPATH"
                object_step["target"] = object_step["xpath"]
            driver.find_element(
                by.get_by(object_step["findBy"]), object_step["target"]
            ).clear()
            printer.success("ok")
            return {"returnCode": Result.OK}
        except BaseException as err:
            printer.danger("FAILED")
            print(err)
            return {"returnCode": Result.KO}

    def send_keys(self, driver, config, object_step):
        """send keys"""

        selenium_key = EventKey()
        by = SelBy()
        try:
            string_to_input = object_step["text"]
            key = selenium_key.get_key(string_to_input)
            if key is None:
                if object_step["text"][:1] == "%":
                    string_to_input = config["json_config"][object_step["text"][1:]]
            else:
                string_to_input = key
            print(object_step["note"], end="->", flush=True)
            time.sleep(1)
            if "xpath" in object_step:
                object_step["findBy"] = "XPATH"
                object_step["target"] = object_step["xpath"]
            driver.find_element(
                by.get_by(object_step["findBy"]), object_step["target"]
            ).send_keys(string_to_input)
            printer.success("ok")
            return {"returnCode": Result.OK}
        except BaseException as err:
            printer.danger("FAILED")
            print(err)
            # sys.exit(1)
            return {"returnCode": Result.KO}

    def wait_for_next_step(self, driver, config, object_step):
        """wait for next step"""
        by = SelBy()
        if "xpath" in object_step:
            object_step["findBy"] = "XPATH"
            object_step["target"] = object_step["xpath"]
        wait_seconds = object_step.get("waitSeconds", object_step.get("timeout", 20))
        wait_condition = object_step.get("waitCondition", "presence")
        if (
            self.wait_for_next_step_real(
                driver,
                by.get_by(object_step["findBy"]),
                object_step["target"],
                object_step["note"],
                wait_seconds,
                wait_condition,
            )
            == Result.KO
        ):
            return {"returnCode": Result.KO}
        return {"returnCode": Result.OK}

    def wait_for_next_step_real(
        self, driver, by, target, note, wait_seconds=20, wait_condition="presence"
    ):
        """wait for next step"""
        failed = False

        try:
            print(note, end="->", flush=True)
            WebDriverWait(driver, wait_seconds).until(
                self._expected_condition(driver, by, target, wait_condition)
            )
        except BaseException as err:
            printer.danger("FAILED")
            print(err)
            failed = True
            return Result.KO
        finally:
            if failed is False:
                printer.success("ok")
                return Result.OK
            return Result.KO

    @staticmethod
    def _expected_condition(driver, by, target, wait_condition):
        """Build a Selenium expected condition from an Idelium wait name."""
        condition = str(wait_condition or "presence").lower()
        locator = (by, target)
        if condition in {"presence", "present", "exists"}:
            return EC.presence_of_element_located(locator)
        if condition in {"visible", "visibility"}:
            return EC.visibility_of_element_located(locator)
        if condition in {"clickable", "element_to_be_clickable"}:
            return EC.element_to_be_clickable(locator)
        if condition in {"url_contains", "url"}:
            return EC.url_contains(target)
        if condition == "url_to_be":
            return EC.url_to_be(target)
        if condition in {"title_contains", "title"}:
            return EC.title_contains(target)
        if condition == "title_is":
            return EC.title_is(target)
        if condition in {"frame", "frame_available"}:
            return EC.frame_to_be_available_and_switch_to_it(locator)
        if condition == "staleness":
            return EC.staleness_of(driver.find_element(by, target))
        raise ValueError("Unsupported Selenium wait condition: " + condition)

    def selenium_command(self, driver, config, object_step):
        """Execute an allow-listed generic Selenium WebDriver command."""
        operation = object_step.get("operation") or object_step.get("command")
        if operation not in self.SELENIUM_GENERIC_COMMANDS:
            return {"returnCode": Result.KO, "error": "Unsupported Selenium command"}
        try:
            value = self._execute_selenium_command(driver, object_step, operation)
            response = {"returnCode": Result.OK}
            if value is not None:
                response["value"] = value
            return response
        except BaseException as err:
            printer.danger("Idelium Selenium | command failed:" + operation)
            print(err)
            return {"returnCode": Result.KO}

    def _execute_selenium_command(self, driver, object_step, operation):
        """Dispatch a validated generic Selenium WebDriver operation."""
        if operation == "navigate_to":
            driver.get(object_step["url"])
            return None
        if operation == "back":
            driver.back()
            return None
        if operation == "forward":
            driver.forward()
            return None
        if operation == "refresh":
            driver.refresh()
            return None
        if operation == "get_url":
            return driver.current_url
        if operation == "get_title":
            return driver.title
        if operation == "execute_script":
            return driver.execute_script(
                object_step["script"],
                *object_step.get("args", []),
            )
        if operation == "add_cookie":
            driver.add_cookie(object_step["cookie"])
            return None
        if operation == "get_cookie":
            return driver.get_cookie(object_step["name"])
        if operation == "get_cookies":
            return driver.get_cookies()
        if operation == "delete_cookie":
            driver.delete_cookie(object_step["name"])
            return None
        if operation == "delete_all_cookies":
            driver.delete_all_cookies()
            return None
        if operation == "accept_alert":
            driver.switch_to.alert.accept()
            return None
        if operation == "dismiss_alert":
            driver.switch_to.alert.dismiss()
            return None
        if operation == "get_alert_text":
            return driver.switch_to.alert.text
        if operation == "switch_window":
            driver.switch_to.window(object_step["handle"])
            return None
        if operation == "new_window":
            driver.switch_to.new_window(object_step.get("windowType", "tab"))
            return None
        if operation == "element_state":
            element = self._element_for_generic_command(driver, object_step)
            state = object_step.get("state", "displayed")
            if state == "enabled":
                return element.is_enabled()
            if state == "selected":
                return element.is_selected()
            return element.is_displayed()
        if operation == "file_upload":
            element = self._element_for_generic_command(driver, object_step)
            element.send_keys(object_step["path"])
            return None
        if operation == "shadow_find_element":
            host = self._element_for_generic_command(driver, object_step)
            shadow_by = object_step.get(
                "shadowFindBy", object_step.get("findBy", "css")
            )
            shadow_target = object_step["shadowTarget"]
            host.shadow_root.find_element(SelBy().get_by(shadow_by), shadow_target)
            return None
        raise ValueError("Unsupported Selenium command: " + operation)

    @staticmethod
    def _element_for_generic_command(driver, object_step):
        """Find the element targeted by a generic Selenium command."""
        by = SelBy()
        if "xpath" in object_step:
            return driver.find_element(by.get_by("XPATH"), object_step["xpath"])
        return driver.find_element(
            by.get_by(object_step["findBy"]),
            object_step["target"],
        )

    def selenium_actions(self, driver, config, object_step):
        """Execute an allow-listed Selenium W3C Actions chain."""
        try:
            chain = ActionChains(driver)
            for action in object_step.get("actions", []):
                action_type = action.get("type")
                if action_type not in self.SELENIUM_ACTIONS:
                    return {
                        "returnCode": Result.KO,
                        "error": "Unsupported Selenium action",
                    }
                self._apply_selenium_action(driver, chain, action)
            chain.perform()
            return {"returnCode": Result.OK}
        except BaseException as err:
            printer.danger("Idelium Selenium | actions failed")
            print(err)
            return {"returnCode": Result.KO}

    def _apply_selenium_action(self, driver, chain, action):
        """Apply a single validated action to the Selenium action chain."""
        action_type = action["type"]
        if action_type == "send_keys":
            chain.send_keys(action["text"])
        elif action_type == "key_down":
            chain.key_down(action["key"])
        elif action_type == "key_up":
            chain.key_up(action["key"])
        elif action_type == "move_by_offset":
            chain.move_by_offset(action.get("x", 0), action.get("y", 0))
        elif action_type == "scroll_by":
            chain.scroll_by_amount(action.get("deltaX", 0), action.get("deltaY", 0))
        elif action_type == "pause":
            chain.pause(action.get("seconds", 0))
        elif action_type == "drag_and_drop":
            source = self._element_for_action(driver, action, "source")
            target = self._element_for_action(driver, action, "target")
            chain.drag_and_drop(source, target)
        elif action_type in {"click", "double_click", "context_click", "move_to"}:
            element = None
            if "findBy" in action or "xpath" in action:
                element = self._element_for_action(driver, action)
            if action_type == "click":
                chain.click(element)
            elif action_type == "double_click":
                chain.double_click(element)
            elif action_type == "context_click":
                chain.context_click(element)
            else:
                chain.move_to_element(element)

    @staticmethod
    def _element_for_action(driver, action, prefix=None):
        """Find an action target element from direct or prefixed locator fields."""
        by = SelBy()

        def field(name):
            if prefix is None:
                return action.get(name)
            return action.get(prefix + name[0].upper() + name[1:])

        xpath = field("xpath")
        if xpath:
            return driver.find_element(by.get_by("XPATH"), xpath)
        return driver.find_element(by.get_by(field("findBy")), field("target"))

    def command(self, command, driver, obj_config, object_step):
        """command"""

        commands = {
            "wait_and_click": self.wait_and_click,
            "wait_for_next_step": self.wait_for_next_step,
            "wait_for_next_step_real": self.wait_for_next_step_real,
            "find_element_by_xpath": self.find_element_by_xpath,
            "find_elements_by_xpath": self.find_elements_by_xpath,
            "find_element": self.find_element,
            "find_elements": self.find_elements,
            "page_source": self.page_source,
            "switch_to_frame": self.switch_to_frame,
            "switch_to_default_content": self.switch_to_default_content,
            "find_object_element": self.find_object_element,
            "click_object": self.click_object,
            "click": self.click,
            "select": self.select,
            "clear": self.clear,
            "write": self.send_keys,
            "open_browser": self.open_browser,
            "write_localstorage": self.write_localstorage,
            "screen_shot": self.screen_shot,
            "sleep": self.sleep,
            "selenium_command": self.selenium_command,
            "selenium_actions": self.selenium_actions,
        }
        if command in commands.keys():
            self._emit_selector_diagnostics(obj_config, object_step)
            return commands[command](driver, obj_config, object_step)
        printer.warning("Idelium Selenium | action nof found try as plugin:" + command)
        return None

    @staticmethod
    def _emit_selector_diagnostics(config, object_step):
        """Emit non-blocking selector-quality diagnostics before execution."""
        if config and config.get("selectorDiagnostics") is False:
            return
        for diagnostic in collect_step_selector_diagnostics(object_step):
            printer.warning(diagnostic.format())
