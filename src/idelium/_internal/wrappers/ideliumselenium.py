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
from selenium.webdriver.chrome import service
from webdriver_manager.opera import OperaDriverManager
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.action_chains import ActionChains
from idelium._internal.commons.ideliumprinter import InitPrinter
from idelium._internal.commons.resultenum import Result
from idelium._internal.commons.seleniumkeyevent import EventKey
from idelium._internal.commons.seleniumby import SelBy


printer = InitPrinter()
class IdeliumSelenium:
    ''' IdeliumSelenium '''
    @staticmethod
    def sleep(driver, config, object_step):
        ''' Sleep '''
        time.sleep(object_step["seconds"])
        return {'returnCode': Result.OK}

    def wait_and_click(self,driver, xpath_condition, note):
        ''' wait and click '''
        if self.wait_for_next_step_real(driver, xpath_condition,
                                        note) == Result.OK:
            if self.click_xpath(driver, xpath_condition, note) == Result.KO:
                return {'returnCode': Result.KO}
            else:
                return {'returnCode': Result.OK}
        else:
            return {'returnCode': Result.OK}

    @staticmethod
    def find_element_by_xpath(driver, xpath_condition, note=None):
        ''' find element by xpath condition '''
        return driver.find_element_by_xpath(xpath_condition)
    @staticmethod
    def find_elements_by_xpath(self, driver, xpath_condition, note=None):
        '''find elements by xpath condition'''
        return driver.find_elements_by_xpath(xpath_condition)
    @staticmethod
    def find_element(driver, by, target, note=None):
        ''' find element'''
        return driver.find_element(by, target)
    @staticmethod
    def find_elements(driver, by, target, note=None):
        ''' find elements'''
        return driver.find_elements(by, target)
    @staticmethod
    def page_source(driver, note=None):
        ''' page source for debug is useful '''
        return driver.page_source
    @staticmethod
    def switch_to_frame(driver, object_driver, note=None):
        ''' switch_to_frame '''
        driver.switch_to_frame(object_driver)
        return Result.OK
    @staticmethod
    def switch_to_default_content(driver, object, note=None):
        ''' switch_to_default_content '''
        driver.switch_to_default_content()
        return Result.OK
    @staticmethod
    def find_object_element(self, selenium_object, xpath_condition, note=None):
        ''' find_object_element '''
        return selenium_object.find_element_by_xpath(xpath_condition)
    @staticmethod
    def click_object(selenium_object, note):
        ''' click_object '''
        try:
            print(note, end="->", flush=True)
            time.sleep(1)
            selenium_object.click()
            printer.success("ok")
            return Result.OK
        except BaseException as err:
            printer.danger("FAILED")
            print(err)
            # sys.exit(1)
            return Result.KO
    @staticmethod
    def drag_and_drop(driver, config, object_step):
        ''' drag_and_drop '''    
        try:
            drag_element = driver.find_element_by_xpath(
                object_step["xpathDrag"])
            drop_element = driver.find_element_by_xpath(
                object_step["xpathDrop"])
            action = ActionChains(driver)
            action.drag_and_drop(drag_element, drop_element).perform()
            return {'returnCode': Result.OK}
        except BaseException as err:
            printer.danger("FAILED")
            print(err)
            # sys.exit(1)
            return {'returnCode': Result.KO}
    def open_browser(self, driver, config, object_step):
        ''' open browser '''  
        driver = None
        return_code = Result.OK
        ''' only for server mode '''
        if 'browser' in config:
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
                chrome_options.add_experimental_option("mobileEmulation",
                                                       mobile_emulation)
            else:
                if config["useragent"] is not None:
                    chrome_options.add_argument("user-agent=" +
                                                config["useragent"])
            if "accept_self_certificate" in config["json_config"]:
                if config["json_config"]["accept_self_certificate"] is True:
                    chrome_options.add_argument("ignore-certificate-errors")
            try:
                driver = webdriver.Chrome(ChromeDriverManager().install())
            except BaseException as err:
                
                printer.warning("webdriver not found, try locally")
                try: 
                    driver=webdriver.Chrome()
                except:
                    printer.danger("webriver error")
                    print(
                        "probably you need to download mannualy the webdriver\nfrom https://googlechromelabs.github.io/chrome-for-testing")
                    if config['ideliumServer'] is False:
                        return_code = Result.KO
                        sys.exit(1)
        elif config["json_config"]["browser"] == "firefox":
            profile = webdriver.FirefoxProfile()
            if config["useragent"] is not None:
                profile.set_preference("general.useragent.override",
                                       config["useragent"])
            if "accept_self_certificate" in config["json_config"]:
                if config["json_config"]["accept_self_certificate"] is True:
                    profile.accept_untrusted_certs = True
            try:
                driver = webdriver.Firefox(GeckoDriverManager().install())
            except BaseException as err:
                printer.warning("webdriver not found, try locally")
                try:
                    driver = webdriver.Firefox()
                except:
                    printer.danger("webriver error")
                    if config['ideliumServer'] is False:
                        return_code = Result.KO
                        sys.exit(1)
        elif config["json_config"]["browser"] == "safari":
            try:
                driver = webdriver.Safari()
            except BaseException as err:
                printer.danger("webriver error")
                print(err)
                return_code = Result.KO
                if config['ideliumServer'] is False:
                    sys.exit(1)
        elif config["json_config"]["browser"] == "opera":
            try:
                webdriver_service = service.Service(OperaDriverManager().install())
                webdriver_service.start()
                driver = webdriver.Remote(webdriver_service.service_url, webdriver.DesiredCapabilities.OPERA)
            except BaseException as err:
                printer.danger("webriver error")
                print(err)
                return_code = Result.KO
                if config['ideliumServer'] is False:
                    sys.exit(1)
        elif config["json_config"]["browser"] == "edge":
            try:
                driver = webdriver.Edge(EdgeChromiumDriverManager().install())
            except BaseException as err:
                printer.warning("webdriver not found, try locally")
                try:
                    driver = webdriver.Edge()
                except:
                    printer.danger("webriver error")
                    if config['ideliumServer'] is False:
                        return_code = Result.KO
                        sys.exit(1)
        elif config["json_config"]["browser"] == "iexplorer":
            capabilities = webdriver.DesiredCapabilities().INTERNETEXPLORER
            if "accept_self_certificate" in config["json_config"]:
                if config["json_config"]["accept_self_certificate"] is True:
                    capabilities["acceptSslCerts"] = True
            try:
                driver=webdriver.Ie(IEDriverManager().install())
            except BaseException as err:
                printer.warning("webdriver not found, try locally")
                try:
                    driver = webdriver.Ie()
                except:
                    printer.danger("webriver error")
                    if config['ideliumServer'] is False:
                        return_code = Result.KO
                        sys.exit(1)
        else:
            printer.danger("driver not selected")
            if config['ideliumServer'] is False:
                sys.exit(1)
        if return_code == Result.OK:
            driver.set_window_size(config["width"], config["height"])
            if "url" in object_step:
                driver.get(object_step["url"])
            else:
                driver.get(config["json_config"]["url"])
            return_code = Result.OK
            object_step["xpath"] = config["json_config"]["xpath_check_url"]
            if object_step['xpath'] == '':
                object_step['xpath'] = '/html'
            if (self.wait_for_next_step(driver, config,
                                        object_step)['returnCode'] == Result.KO):
                return_code = Result.KO
                config["json_step"]["attachScreenshot"] = True
                config["json_step"]["failedExit"] = True
        return {"driver": driver, 'returnCode': return_code, "config": config}

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
        for key, value in (config.get("seleniumGridCapabilities") or {}).items():
            options.set_capability(key, value)

        return webdriver.Remote(command_executor=grid_url, options=options)
    @staticmethod
    def write_localstorage(driver, config, object_step):
        ''' write_localstorage '''
        
        try:
            print(object_step["note"], end="->", flush=True)
            script_js = ""
            for object_data in object_step["dataLocalStorage"]:
                for key in object_data:
                    script_js = (script_js+ 'localStorage.setItem("' + key +
                                "\", '" + object_data[key] + "')\n")
            script_js = (
                script_js +
                "return Array.apply(0, new Array(localStorage.length)).map(function (o, i)" +
                "{ return localStorage.getItem(localStorage.key(i)); })"
            )
            driver.execute_script(script_js)
            printer.success("ok")
            return {'returnCode': Result.OK}
        except BaseException as err:
            printer.danger("FAILED")
            print(err)
            # sys.exit(1)
            return {'returnCode': Result.KO}

    def screen_shot(self, driver, file_name,is_server):
        """ screenshot """
        
        try:
            driver.get_screenshot_as_file(file_name)
            return Result.OK
        except BaseException as err:
            printer.danger("FAILED")
            print(err)
            if is_server is False:
                sys.exit(1)

    def click(self, driver, config, object_step):
        '''click '''
        
        by = SelBy()
        try:
            print(object_step["note"], end="->", flush=True)
            time.sleep(1)
            #for retrocompat
            if "xpath" in object_step:
                object_step["findBy"] = "XPATH"
                object_step["target"] = object_step["xpath"]
            driver.find_element(by.get_by(object_step["findBy"]),
                                object_step["target"]).click()
            printer.success("ok")
            return {'returnCode': Result.OK}
        except BaseException as err:
            printer.danger("FAILED")
            print(err)
            return {'returnCode': Result.KO}

    def select(self, driver, config, object_step):
        ''' select '''
        
        by = SelBy()
        print(object_step)
        try:
            print(object_step["note"], end="->", flush=True)
            time.sleep(1)
            #for retrocompat
            if "xpath" in object_step:
                object_step["findBy"] = "XPATH"
                object_step["target"] = object_step["xpath"]
            select = Select(
                driver.find_element(by.get_by(object_step["findBy"]),
                                    object_step["target"]))
            if "selectType" in object_step:
                if object_step["selectType"] == "label":
                    select.select_by_visible_text(object_step["value"])
                elif object_step["selectType"] == "value":
                    select.select_by_value(object_step["value"])
                elif object_step["selectType"] == "index":
                    select.select_by_index(object_step["value"])
                else:
                    printer.danger("selectType:" + object_step["selectType"] +
                                   " not supported in this moment")
            else:
                select.select_by_visible_text(object_step["value"])
            printer.success("ok")
            return {'returnCode': Result.OK}
        except BaseException as err:
            printer.danger("FAILED")
            printer.danger(err)
            return {'returnCode': Result.KO}

    def clear(self, driver, config, object_step):
        ''' clear '''
        
        by = SelBy()
        try:
            print(object_step["note"], end="->", flush=True)
            time.sleep(1)
            if "xpath" in object_step:
                object_step["findBy"] = "XPATH"
                object_step["target"] = object_step["xpath"]
            driver.find_element(by.get_by(object_step["findBy"]),
                                object_step["target"]).clear()
            printer.success("ok")
            return {'returnCode': Result.OK}
        except BaseException as err:
            printer.danger("FAILED")
            print(err)
            return {'returnCode': Result.KO}

    def send_keys(self, driver, config, object_step):
        ''' send keys '''
        
        selenium_key = EventKey()
        by = SelBy()
        try:
            string_to_input = object_step["text"]
            key = selenium_key.get_key(string_to_input)
            if key is None:
                if object_step["text"][:1] == "%":
                    string_to_input = config["json_config"][object_step["text"]
                                                            [1:]]
            else:
                string_to_input = key
            print(object_step["note"], end="->", flush=True)
            time.sleep(1)
            if "xpath" in object_step:
                object_step["findBy"] = "XPATH"
                object_step["target"] = object_step["xpath"]
            driver.find_element(
                by.get_by(object_step["findBy"]),
                object_step["target"]).send_keys(string_to_input)
            printer.success("ok")
            return {'returnCode': Result.OK}
        except BaseException as err:
            printer.danger("FAILED")
            print(err)
            # sys.exit(1)
            return {'returnCode': Result.KO}

    def wait_for_next_step(self, driver, config, object_step):
        ''' wait for next step'''
        by = SelBy()
        if "xpath" in object_step:
            object_step["findBy"] = "XPATH"
            object_step["target"] = object_step["xpath"]
        if (self.wait_for_next_step_real(
                driver,
                by.get_by(object_step["findBy"]),
                object_step["target"],
                object_step["note"],
        ) == Result.KO):
            return {'returnCode': Result.KO}
        return {'returnCode': Result.OK}

    def wait_for_next_step_real(self,
                                driver,
                                by,
                                target,
                                note,
                                wait_seconds=20):
        '''wait for next step'''
        failed = False
        
        try:
            print(note, end="->", flush=True)
            WebDriverWait(driver, wait_seconds).until(
                EC.presence_of_element_located((by, target)))
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

    def command(self, command, driver, obj_config, object_step):
        ''' command '''
        
        commands = {
            "wait_and_click": self.wait_and_click,
            "wait_for_next_step": self.wait_for_next_step,
            "wait_for_next_step_real": self.wait_for_next_step_real,
            "find_element_by_xpath": self.find_element_by_xpath,
            "find_elements_by_xpath": self.find_elements_by_xpath,
            "find_element": self.find_element_by_xpath,
            "find_elements": self.find_elements_by_xpath,
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
        }
        if command in commands.keys():
            return commands[command](driver, obj_config, object_step)
        printer.warning("Idelium Selenium | action nof found try as plugin:" + command)
        return None
