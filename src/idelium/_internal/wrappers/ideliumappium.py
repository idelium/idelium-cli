"""System module."""
from __future__ import absolute_import
import sys
import time
import base64
from appium import webdriver
from appium.options.android import EspressoOptions
from appium.options.android import UiAutomator2Options
from appium.options.ios import XCUITestOptions
from selenium.webdriver.common.by import By
from idelium._internal.commons.ideliumprinter import InitPrinter
from idelium._internal.commons.androideventkey import EventKey
from idelium._internal.commons.resultenum import Result

class IdeliumAppium():
    ''' Idelium Appium'''
    SAFE_MOBILE_COMMANDS = {
        "batteryInfo",
        "deviceInfo",
        "getDeviceTime",
        "getNotifications",
        "listSms",
        "viewportScreenshot",
    }
    SENSITIVE_PARAMETER_NAMES = {
        "api_key",
        "apikey",
        "authorization",
        "cookie",
        "password",
        "secret",
        "token",
        "access_key",
        "accesskey",
    }
    STANDARD_W3C_CAPABILITIES = {
        "acceptInsecureCerts",
        "browserName",
        "browserVersion",
        "pageLoadStrategy",
        "platformName",
        "proxy",
        "setWindowRect",
        "strictFileInteractability",
        "timeouts",
        "unhandledPromptBehavior",
        "webSocketUrl",
    }
    APPIUM_EXTENSION_CAPABILITIES = {
        "app",
        "appActivity",
        "appPackage",
        "autoGrantPermissions",
        "automationName",
        "bundleId",
        "chromedriverExecutable",
        "deviceName",
        "fullReset",
        "language",
        "locale",
        "newCommandTimeout",
        "noReset",
        "orientation",
        "platformVersion",
        "udid",
        "xcodeOrgId",
        "xcodeSigningId",
    }
    APPIUM_DRIVER_ALIASES = {
        "espresso": "espresso",
        "uiautomator2": "uiautomator2",
        "xcuitest": "xcuitest",
    }

    @staticmethod
    def _result(return_code=Result.OK, **kwargs):
        """Build the standard Idelium command response."""
        response = {"returnCode": return_code}
        response.update(kwargs)
        return response

    @staticmethod
    def _normalize_result(value):
        """Normalize Appium driver values to the manager command contract."""
        if isinstance(value, dict) and "returnCode" in value:
            return value
        if value == Result.KO:
            return {"returnCode": Result.KO}
        if value in (Result.OK, None):
            return {"returnCode": Result.OK}
        return {"returnCode": Result.OK, "value": value}

    @staticmethod
    def _appium_options(config):
        """Create Appium client options from the stored environment capabilities."""
        capabilities = IdeliumAppium._normalize_appium_capabilities(
            config.get("appiumDesiredCaps") or {},
        )
        platform = str(capabilities.get("platformName", "")).lower()
        automation_name = IdeliumAppium._selected_driver_name(capabilities)
        if platform == "ios" or automation_name == "xcuitest":
            return XCUITestOptions().load_capabilities(capabilities)
        if automation_name == "espresso":
            return EspressoOptions().load_capabilities(capabilities)
        return UiAutomator2Options().load_capabilities(capabilities)

    @classmethod
    def _normalize_appium_capabilities(cls, capabilities):
        """Return Appium 2 compatible W3C capabilities."""
        normalized = {}
        for key, value in capabilities.items():
            if ":" in key or key in cls.STANDARD_W3C_CAPABILITIES:
                normalized[key] = value
            elif key in cls.APPIUM_EXTENSION_CAPABILITIES:
                normalized["appium:" + key] = value
            else:
                normalized[key] = value
        return normalized

    @classmethod
    def _selected_driver_name(cls, capabilities):
        """Return the normalized Appium automation driver name."""
        automation_name = str(
            capabilities.get("appium:automationName", capabilities.get("automationName", "")),
        ).lower()
        return cls.APPIUM_DRIVER_ALIASES.get(automation_name, automation_name)

    @classmethod
    def _metadata_list(cls, config, name):
        """Read Appium environment metadata from the root or json_config."""
        values = []
        for source in (config, config.get("json_config", {})):
            source_value = source.get(name)
            if source_value is None:
                continue
            if isinstance(source_value, str):
                values.append(source_value)
            elif isinstance(source_value, list):
                values.extend(source_value)
        return [str(value).lower() for value in values if str(value).strip()]

    @classmethod
    def _validate_appium_environment_metadata(cls, config):
        """Validate declared Appium driver and plugin requirements."""
        capabilities = cls._normalize_appium_capabilities(
            config.get("appiumDesiredCaps") or {},
        )
        selected_driver = cls._selected_driver_name(capabilities)
        required_drivers = cls._metadata_list(config, "appiumRequiredDrivers")
        if required_drivers and selected_driver and selected_driver not in required_drivers:
            return cls._result(
                Result.KO,
                error=(
                    "Appium required driver metadata does not include "
                    + selected_driver
                ),
            )
        return cls._result(Result.OK)

    @classmethod
    def _has_declared_appium_plugin(cls, config, plugin_name):
        """Return whether an Appium plugin is declared in environment metadata."""
        if not plugin_name:
            return True
        normalized = str(plugin_name).lower()
        declared_plugins = set(cls._metadata_list(config, "appiumRequiredPlugins"))
        declared_plugins.update(cls._metadata_list(config, "appiumInstalledPlugins"))
        return normalized in declared_plugins

    @staticmethod
    def _find_element(driver, config, object_step):
        """Find an Appium element with modern Selenium/Appium locators."""
        if 'xpath' in object_step:
            return driver.find_element(By.XPATH, object_step['xpath'])
        if 'accessibilityId' in object_step:
            return driver.find_element("accessibility id", object_step['accessibilityId'])
        if 'native_interface_element' in object_step:
            native_interface_element = (
                config['appiumDesiredCaps']['appPackage'] + ":id/" +
                object_step['native_interface_element']
            )
            return driver.find_element(By.ID, native_interface_element)
        return None

    @staticmethod
    def wait_for_elements(driver,config, object_step):
        ''' wait for elements'''
        wait_time=5
        if 'waitTime' in config['json_config']:
            wait_time=config['json_config']['waitTime']
        print ("Waiting for Login dialog to open, max wait =" + str(wait_time) + " seconds")
        timeout = time.time() + wait_time   # Timer based on wait_time to prevent infinite loops
        element=None
        while True:
            time.sleep(1)   # Prevent CPU slamming with short timeout between loops
            if time.time() > timeout:
                print ('timeout exception')
                break
            try:
                element = IdeliumAppium._find_element(driver, config, object_step)
                break
            except BaseException as err:
                print ('still waiting')
                print (err)
        return element
    @staticmethod
    def connect_appium(driver,config,object_step):
        '''Connect appium '''
        return_code=Result.OK
        driver=None
        printer=InitPrinter()
        if config['is_debug'] is True:
            print ('try to connect:' + config['appiumServer'])
        print (object_step['note'],end="->", flush=True)
        try:
            metadata_result = IdeliumAppium._validate_appium_environment_metadata(config)
            if metadata_result["returnCode"] == Result.KO:
                printer.danger(metadata_result["error"])
                return {"driver": driver, "config": config, "returnCode": Result.KO}
            try:
                driver = webdriver.Remote(
                    config['appiumServer'],
                    options=IdeliumAppium._appium_options(config),
                    keep_alive=False,
                )
            except TypeError:
                driver = webdriver.Remote(config['appiumServer'],
                                          config['appiumDesiredCaps'],
                                          keep_alive=False)
            printer.success('ok')
            contexts=driver.contexts
            printer.warning ('Context name:')
            index=0
            for i in contexts:
                index += 1
                printer.warning (str(index) + ")" + i)
        except BaseException as err:
            printer.danger('ko')
            print (err)
            config['json_step']['attachScreenshot'] = False
            config['json_step']['failedExit'] = False
            printer.danger('Verify if Appium server is running')
            printer.danger('The test is stopped')
            if config['ideliumServer'] is False:
                sys.exit(1)
            return_code=Result.KO
        return {"driver" : driver,"config" : config, "returnCode" : return_code}
    def appium_send_keys(self,driver,config,object_step):
        ''' appium_send_keys '''
        return_code=Result.OK
        printer=InitPrinter()
        print (object_step['note'],end="->", flush=True)
        element=self.wait_for_elements(driver,config,object_step)
        if element is None:
            return_code=Result.KO
        else:
            if config['json_config']['appiumDesiredCaps']['platformName'].lower() == 'android':
                element.click()
                time.sleep(1)
                event_key=EventKey()
                for string in object_step['keys']:
                    for key_command in event_key.get_array_of_char(string):
                        array_command=key_command.split(',')
                        if len(array_command) == 1:
                            driver.press_keycode(key_command)
                        else:
                            driver.press_keycode(array_command[0],array_command[1])
            else:
                for string in object_step['keys']:
                    element.send_keys(string)
        return {"returnCode" : return_code}
    def appium_click(self,driver,config,object_step):
        ''' appium click'''
        return_code=Result.OK
        printer=InitPrinter()
        print (object_step['note'],end="->", flush=True)
        element=self.wait_for_elements(driver,config,object_step)
        if element is None:
            return_code=Result.KO
        else:
            element.click()

        return {"returnCode" : return_code}




    def appium_switch_context(self,driver,config,object_step):
        ''' appium_switch_context '''
        return_code=Result.OK
        printer=InitPrinter()
        print (object_step['note'],end="->", flush=True)
        try:
            driver.switch_to.context(object_step['contextName'])
            driver.wait_activity
            printer.success('ok')
        except BaseException as err:
            return_code=Result.KO
            printer.danger('ko')
            print(err)
        return {"returnCode": return_code}

    def appium_execute_script(self,driver,config,object_step):
        """
            for more info:
            https://appium.io/docs/en/commands/mobile-command/
        """
        return_code=Result.OK
        driver.execute_script(object_step['script'])
        return return_code

    def appium_mobile_command(self,driver,config,object_step):
        """Execute an allow-listed Appium mobile command."""
        mobile_command = object_step.get("mobileCommand") or object_step.get("command")
        if not mobile_command or not isinstance(mobile_command, str):
            return self._result(Result.KO, error="mobileCommand is required")
        if mobile_command.startswith("mobile:"):
            mobile_command = mobile_command.split(":", 1)[1].strip()

        allowed_commands = set(self.SAFE_MOBILE_COMMANDS)
        for source in (config, config.get("json_config", {})):
            allowed_commands.update(source.get("appiumMobileCommandsAllowed", []))
        if mobile_command not in allowed_commands:
            return self._result(
                Result.KO,
                error="Appium mobile command is not allow-listed",
            )

        params = object_step.get("params", {})
        if params is None:
            params = {}
        if not isinstance(params, dict):
            return self._result(Result.KO, error="params must be an object")
        unsafe_keys = self._sensitive_parameter_keys(params)
        if unsafe_keys:
            return self._result(
                Result.KO,
                error="Appium mobile command parameters contain sensitive fields",
            )
        required_plugin = object_step.get("requiredPlugin")
        if not self._has_declared_appium_plugin(config, required_plugin):
            return self._result(
                Result.KO,
                error="Required Appium plugin is not declared in environment metadata",
            )
        return driver.execute_script("mobile: " + mobile_command, params)

    @classmethod
    def _sensitive_parameter_keys(cls, value):
        """Return sensitive parameter keys found in nested dictionaries."""
        if not isinstance(value, dict):
            return set()
        sensitive = set()
        for key, child in value.items():
            normalized = str(key).replace("-", "_").lower()
            if normalized in cls.SENSITIVE_PARAMETER_NAMES:
                sensitive.add(str(key))
            sensitive.update(cls._sensitive_parameter_keys(child))
        return sensitive

    def appium_desired_capabilities(self,driver,config,object_step):
        """
            for more info:
            https://appium.io/docs/en/commands/session/get/
        """
        return driver.desired_capabilities
    def appium_back(self,driver,config,object_step):
        """
            for more info:
            https://appium.io/docs/en/commands/session/back/
        """
        return_code=Result.OK
        driver.back()
        return return_code
    def appium_page_source(self,driver,config,object_step):
        """
            for more info:
            https://appium.io/docs/en/commands/session/source/
        """
        print (driver.page_source)
        return driver.page_source
    def appium_set_page_load_timeout(self,driver,config,object_step):
        """
            for more info:
            https://appium.io/docs/en/commands/session/timeouts/timeouts/
        """
        return_code=Result.OK
        driver.set_page_load_timeout(object_step['milliseconds'])
        return return_code
    def appium_implicitly_wait(self,driver,config,object_step):
        """
            for more info:
            https://appium.io/docs/en/commands/session/timeouts/implicit-wait/
        """
        return_code=Result.OK
        driver.implicitly_wait(object_step['milliseconds'])
        return return_code
    def appium_set_script_timeout(self,driver,config,object_step):
        """
            for more info:
            https://appium.io/docs/en/commands/session/timeouts/async-script/
        """
        return_code=Result.OK
        driver.set_script_timeout(object_step['milliseconds'])
        return return_code
    def appium_orientation(self,driver,config,object_step):
        """
            orientation: LANDSCAPE,PORTRAIT
            for more info:
            https://appium.io/docs/en/commands/session/orientation/set-orientation/
        """
        return_code=Result.OK
        driver.orientation = object_step['orientation']
        return return_code
    def appium_location(self,driver,config,object_step):
        """
            for more info:
            https://appium.io/docs/en/commands/session/geolocation/get-geolocation/
        """
        if {'latitude', 'longitude', 'altitude'}.issubset(object_step):
            driver.set_location(
                object_step['latitude'],
                object_step['longitude'],
                object_step['altitude'],
            )
            return Result.OK
        return driver.location
    def appium_log_types(self,driver,config,object_step):
        """
            for more info:
            https://appium.io/docs/en/commands/session/logs/get-log-types/
        """
        return driver.log_types()
    def appium_get_log(self,driver,config,object_step):
        """
            for more info:
            https://appium.io/docs/en/commands/session/logs/get-log/
        """
        return driver.get_log(object_step['typeString'])
    def appium_update_settings(self,driver,config,object_step):
        """
            orientation: LANDSCAPE,PORTRAIT
            for more info:
            https://appium.io/docs/en/commands/session/settings/update-settings/
        """
        return_code=Result.OK
        driver.update_settings(object_step['jsonSettings'])
        return return_code
    def appium_get_settings(self,driver,config,object_step):
        """
            for more info:
            https://appium.io/docs/en/commands/session/settings/get-settings/
        """
        return driver.get_settings()
    def start_start_activity(self,driver,config,object_step):
        """
            for more info:
            https://appium.io/docs/en/commands/device/activity/start-activity/
        """
        params = object_step['jsonActivityParameters']
        if isinstance(params, dict):
            return driver.start_activity(**params)
        return driver.start_activity(params)
    def appium_current_activity(self,driver,config,object_step):
        """
            for more info:
            https://appium.io/docs/en/commands/device/activity/current-activity/
        """
        return driver.current_activity
    def appium_current_package(self,driver,config,object_step):
        """
            for more info:
            https://appium.io/docs/en/commands/device/app/current-package/
        """
        return driver.current_package
    def appium_is_app_installed(self,driver,config,object_step):
        """
            for more info:
            https://appium.io/docs/en/commands/device/app/is-app-installed/
        """
        return driver.is_app_installed(object_step['appPackage'])
    def appium_launch_app(self,driver,config,object_step):
        """
            for more info:
            https://appium.io/docs/en/commands/device/app/launch-app/
        """
        return_code=Result.OK
        driver.launch_app()
        return return_code
    def appium_background_app(self,driver,config,object_step):
        """
            for more info:
            https://appium.io/docs/en/commands/device/app/background-app/
        """
        return_code=Result.OK
        driver.background_app(object_step['seconds'])
        return return_code
    def appium_close_app(self,driver,config,object_step):
        """
            for more info:
            https://appium.io/docs/en/commands/device/app/close-app/
        """
        return_code=Result.OK
        driver.close_app()
        return return_code
    def appium_reset_app(self,driver,config,object_step):
        """
            for more info:
            https://appium.io/docs/en/commands/device/app/reset-app/
        """
        return_code=Result.OK
        driver.reset()
        return return_code
    def appium_remove_app(self,driver,config,object_step):
        """
            for more info:
            https://appium.io/docs/en/commands/device/app/remove-app/
        """
        return_code=Result.OK
        driver.remove_app()
        return return_code
    def appium_activate_app(self,driver,config,object_step):
        """
            examples:
            driver.appium_activate_app('com.apple.Preferences')
            driver.appium_activate_app('io.appium.android.apis')
            for more info:
            https://appium.io/docs/en/commands/device/app/activate-app/
        """
        return_code=Result.OK
        driver.activate_app(object_step['bundleId'])
        return return_code
    def appium_terminate_app(self,driver,config,object_step):
        """
            examples:
            driver.appium_terminate_app('com.apple.Preferences')
            driver.appium_terminate_app('io.appium.android.apis')
            for more info:
            https://appium.io/docs/en/commands/device/app/terminate-app/
        """
        return_code=Result.OK
        driver.terminate_app(object_step['bundleId'])
        return return_code
    def appium_query_app_state(self,driver,config,object_step):
        """
            examples:
            driver.appium_query_app_state('com.apple.Preferences')
            driver.appium_query_app_state('io.appium.android.apis')
            for more info:
            https://appium.io/docs/en/commands/device/app/app-state/
        """
        return_code=Result.OK
        driver.query_app_state(object_step['bundleId'])
        return return_code
    def appium_app_strings(self,driver,config,object_step):
        """
            for more info:
            https://appium.io/docs/en/commands/device/app/get-app-strings/
        """
        return_code=Result.OK
        driver.app_strings(object_step['language'],object_step['pathFile'])
        return return_code
    def appium_end_test_coverage(self,driver,config,object_step):
        """
            for more info:
            https://appium.io/docs/en/commands/device/app/end-test-coverage/
        """
        return_code=Result.OK
        driver.end_test_coverage(object_step['intent'],object_step['path'])
        return return_code
    def appium_set_clipboard(self,driver,config,object_step):
        """
            for more info:
            https://appium.io/docs/en/commands/device/clipboard/set-clipboard/
        """
        return_code=Result.OK
        driver.set_clipboard(object_step['string'])
        return return_code
    def appium_set_power_ac(self,driver,config,object_step):
        """
            Examples:
            self.driver.set_power_ac(Power.AC_OFF)
            for more info:
            https://appium.io/docs/en/commands/device/emulator/power_ac/
        """
        return_code=Result.OK
        driver.set_power_ac(object_step['powerOnOff'])
        return return_code
    def appium_set_power_capacity(self,driver,config,object_step):
        """
            for more info:
            https://appium.io/docs/en/commands/device/emulator/power_capacity/
        """
        return_code=Result.OK
        driver.set_power_capacity(object_step['percent'])
        return return_code
    def appium_push_file(self,driver,config,object_step):
        """
            for more info:
            https://appium.io/docs/en/commands/device/files/push-file/
        """
        return_code=Result.OK
        driver.push_file(object_step['path'],object_step['data'])
        return return_code
    def appium_pull_file(self,driver,config,object_step):
        """
            for more info:
            https://appium.io/docs/en/commands/device/files/pull-file/
        """
        return driver.pull_file(object_step['path'])
    def appium_pull_folder(self,driver,config,object_step):
        """
            for more info:
            https://appium.io/docs/en/commands/device/files/pull-folder/
        """
        return driver.pull_folder(object_step['path'])
    def appium_shake(self,driver,config,object_step):
        """
            for more info:
            https://appium.io/docs/en/commands/device/interactions/shake/
        """
        return_code=Result.OK
        driver.shake()
        return return_code
    def appium_lock(self,driver,config,object_step):
        """
            for more info:
            https://appium.io/docs/en/commands/device/interactions/lock/
        """
        return_code=Result.OK
        driver.lock()
        return return_code
    def appium_unlock(self,driver,config,object_step):
        """
            for more info:
            https://appium.io/docs/en/commands/device/interactions/unlock/
        """
        return_code=Result.OK
        driver.unlock()
        return return_code
    def appium_is_locked(self,driver,config,object_step):
        """
            for more info:
            https://appium.io/docs/en/commands/device/interactions/is-locked/
        """
        return_code=Result.OK
        driver.is_locked()
        return return_code
    def appium_press_keycode(self,driver,config,object_step):
        """
            for more info:
            https://appium.io/docs/en/commands/device/keys/press-keycode/
        """
        return_code=Result.OK
        driver.press_keycode(object_step['keyCode'])
        return return_code
    def appium_long_press_keycode(self,driver,config,object_step):
        """
            for more info:
            https://appium.io/docs/en/commands/device/keys/long_press-keycode/
        """
        return_code=Result.OK
        driver.long_press_keycode(object_step['keyCode'])
        return return_code
    def appium_hide_keyboard(self,driver,config,object_step):
        """
            for more info:
            https://appium.io/docs/en/commands/device/keys/hide-keyboard/
        """
        return_code=Result.OK
        driver.hide_keyboard()
        return return_code
    def appium_is_keyboard_shown(self,driver,config,object_step):
        """
            for more info:
            https://appium.io/docs/en/commands/device/keys/is-keyboard-shown/
        """
        return driver.is_keyboard_shown()
    def appium_toggle_wifi(self,driver,config,object_step):
        """
            for more info:
            https://appium.io/docs/en/commands/device/network/toggle-wifi/
        """
        return_code=Result.OK
        driver.toggle_wifi()
        return return_code
    def appium_toggle_location_services(self,driver,config,object_step):
        """
            for more info:
            https://appium.io/docs/en/commands/device/network/toggle-location-services/
        """
        return_code=Result.OK
        driver.toggle_location_services()
        return return_code
    def appium_send_sms(self,driver,config,object_step):
        """
            for more info:
            https://appium.io/docs/en/commands/device/network/send-sms/
        """
        return_code=Result.OK
        driver.send_sms(object_step['phoneNumber'],object_step['message'])
        return return_code
    def appium_make_gsm_call(self,driver,config,object_step):
        """
            for more info:
            https://appium.io/docs/en/commands/device/network/gsm-call/
        """
        return_code=Result.OK
        driver.make_gsm_call(object_step['phoneNumber'],object_step['gsmAction'])
        return return_code
    def appium_set_gsm_signal(self,driver,config,object_step):
        """
            for more info:
            https://appium.io/docs/en/commands/device/network/gsm-signal/
        """
        return_code=Result.OK
        driver.set_gsm_signal(object_step['gsmSignalStrength'])
        return return_code
    def appium_set_gsm_voice(self,driver,config,object_step):
        """
            for more info:
            https://appium.io/docs/en/commands/device/network/gsm-voice/
        """
        return_code=Result.OK
        driver.set_gsm_voice(object_step['gsmVoiceState'])
        return return_code
    def appium_set_network_speed(self,driver,config,object_step):
        """
            for more info:
            https://appium.io/docs/en/commands/device/network/network-speed/
        """
        return_code=Result.OK
        driver.set_network_speed(object_step['netSpeed'])
        return return_code
    def appium_get_performance_data(self,driver,config,object_step):
        """
            for more info:
            https://appium.io/docs/en/commands/device/performance-data/get-performance-data/
        """
        return_code=Result.OK
        read_timeout = object_step.get(
            'dataReadTimeout',
            object_step.get('dataReatTimeOut'),
        )
        driver.get_performance_data(object_step['packageName'],
                                    object_step['dataType'],
                                    read_timeout)
        return return_code
    def appium_get_performance_data_types(self,driver,config,object_step):
        """
            for more info:
            https://appium.io/docs/en/commands/device/performance-data/performance-data-types/
        """
        return driver.get_performance_data_types()
    def appium_start_recording_screen(self,driver,config,object_step):
        """
            for more info:
            https://appium.io/docs/en/commands/device/recording-screen/start-recording-screen/
        """
        return_code=Result.OK
        if object_step['options'] is None:
            driver.start_recording_screen()
        else:
            driver.start_recording_screen(object_step['options'])
        return return_code
    def appium_stop_recording_screen(self,driver,config,object_step):
        """
            for more info:
            https://appium.io/docs/en/commands/device/recording-screen/stop-recording-screen/
        """
        return_code=Result.OK
        driver.stop_recording_screen()
        return return_code
    def appium_touch_id(self,driver,config,object_step):
        """
            self.driver.touch_id(false); # Simulates a failed touch
            self.driver.touch_id(true); # Simulates a passing touch
            for more info:
            https://appium.io/docs/en/commands/device/simulator/touch-id/
        """
        return_code=Result.OK
        driver.touch_id(object_step['touch'])
        return return_code
    def appium_toggle_touch_id_enrollment(self,driver,config,object_step):
        """
            for more info:
            https://appium.io/docs/en/commands/device/simulator/toggle-touch-id-enrollment/
        """
        return_code=Result.OK
        driver.toggle_touch_id_enrollment()
        return return_code
    def appium_open_notifications(self,driver,config,object_step):
        """
            for more info:
            https://appium.io/docs/en/commands/device/system/open-notifications/
        """
        return_code=Result.OK
        driver.open_notifications()
        return return_code
    def appium_get_system_bars(self,driver,config,object_step):
        """
            for more info:
            https://appium.io/docs/en/commands/device/system/system-bars/
        """
        return_code=Result.OK
        driver.get_system_bars()
        return return_code
    def appium_get_system_time(self,driver,config ,object_step):
        """
            for more info:
            https://appium.io/docs/en/commands/device/system/system-time/
        """
        return_string=None
        if object_step['date'] is None:
            return_string=driver.get_device_time()
        else:
            return_string=driver.get_device_time(object_step['date'])
        return return_string
    def appium_get_device_density(self,driver,config,object_step):
        """
            for more info:
            https://appium.io/docs/en/commands/device/system/display-density/
        """
        return_code=Result.OK
        driver.get_device_density()
        return return_code
    def appium_finger_print(self,driver,config,object_step):
        """
            for more info:
            https://appium.io/docs/en/commands/device/authentication/finger-print/
        """
        return_code=Result.OK
        driver.finger_print(object_step['number'])
        return return_code
    def appium_find_element_by_accessibility_id(self,driver,config,object_step):
        """
            for more info:
           https://appium.io/docs/en/commands/element/find-element/
        """
        return self._find_element(driver, config, object_step)
    def appium_switch_to(self,driver,config,object_step):
        """
        """
        return driver.switch_to
    def screen_shot(self,driver,file_name):
        """
                screenshot appium
        """
        printer=InitPrinter()
        try:
            current_context=driver.current_context
            fake_object_step={}
            fake_object_step['contextName']='NATIVE_APP'
            fake_object_step['note']='take screenshot'
            self.appium_switch_context(driver,None,fake_object_step)
            screenshot=driver.get_screenshot_as_base64()
            fake_object_step['contextName']=current_context
            self.appium_switch_context(driver,None,fake_object_step)
            screenshot_data = base64.b64decode(screenshot)
            new_file = open(file_name, "wb")
            new_file.write(screenshot_data)
            new_file.close()
            return Result.OK
        except BaseException as err:
            printer.danger('FAILED APP SCREENSHOT')
            print(err)
            return Result.KO

    def  command (self,command,driver,obj_config,object_step):
        '''Command'''
        printer=InitPrinter()
        commands= {
                "connect_appium" : self.connect_appium,
                "appium_send_keys" : self.appium_send_keys,
                "appium_send_keys_xpath": self.appium_send_keys,
                "appium_click" : self.appium_click,
                "appium_click_xpath" : self.appium_click,
                "appium_switch_context" : self.appium_switch_context,
                "appium_execute_script" : self.appium_execute_script,
                "appium_mobile_command" : self.appium_mobile_command,
                "appium_desired_capabilities" : self.appium_desired_capabilities,
                "appium_back" : self.appium_back,
                "appium_page_source" : self.appium_page_source,
                "appium_set_page_load_timeout" : self.appium_set_page_load_timeout,
                "appium_implicitly_wait" : self.appium_implicitly_wait,
                "appium_set_script_timeout" : self.appium_set_script_timeout,
                "appium_location" : self.appium_location,
                "appium_orientation" : self.appium_orientation,
                "appium_log_types" : self.appium_log_types,
                "appium_get_log" : self.appium_get_log,
                "appium_update_settings" : self.appium_update_settings,
                "appium_get_settings" : self.appium_get_settings,
                "appium_start_start_activity" : self.start_start_activity,
                "appium_current_activity" : self.appium_current_activity,
                "appium_current_package" : self.appium_current_package,
                "appium_is_app_installed" : self.appium_is_app_installed,
                "appium_launch_app" : self.appium_launch_app,
                "appium_background_app" : self.appium_background_app,
                "appium_close_app" : self.appium_close_app,
                "appium_reset_app" : self.appium_reset_app,
                "appium_remove_app" : self.appium_remove_app,
                "appium_activate_app" : self.appium_activate_app,
                "appium_terminate_app" : self.appium_terminate_app,
                "appium_query_app_state" : self.appium_query_app_state,
                "appium_app_strings" : self.appium_app_strings,
                "appium_end_test_coverage" : self.appium_end_test_coverage,
                "appium_set_clipboard" : self.appium_set_clipboard,
                "appium_set_power_ac" : self.appium_set_power_ac,
                "appium_set_power_capacity" : self.appium_set_power_capacity,
                "appium_push_file" : self.appium_push_file,
                "appium_pull_file" : self.appium_pull_file,
                "appium_pull_folder" : self.appium_pull_folder,
                "appium_shake" : self.appium_shake,
                "appium_lock" : self.appium_lock,
                "appium_unlock" : self.appium_unlock,
                "appium_is_locked" : self.appium_is_locked,
                "appium_press_keycode" : self.appium_press_keycode,
                "appium_long_press_keycode" : self.appium_long_press_keycode,
                "appium_hide_keyboard" : self.appium_hide_keyboard,
                "appium_is_keyboard_shown" : self.appium_is_keyboard_shown,
                "appium_toggle_wifi" : self.appium_toggle_wifi,
                "appium_toggle_location_services" : self.appium_toggle_location_services,
                "appium_send_sms" : self.appium_send_sms,
                "appium_make_gsm_call" : self.appium_make_gsm_call,
                "appium_set_gsm_signal" : self.appium_set_gsm_signal,
                "appium_set_gsm_voice" : self.appium_set_gsm_voice,
                "appium_set_network_speed" : self.appium_set_network_speed,
                "appium_get_performance_data" : self.appium_get_performance_data,
                "appium_get_performance_data_types" : self.appium_get_performance_data_types,
                "appium_start_recording_screen" : self.appium_start_recording_screen,
                "appium_stop_recording_screen" : self.appium_stop_recording_screen,
                "appium_touch_id" : self.appium_touch_id,
                "appium_toggle_touch_id_enrollment" : self.appium_toggle_touch_id_enrollment,
                "appium_open_notifications" : self.appium_open_notifications,
                "appium_get_system_bars" : self.appium_get_system_bars,
                "appium_get_system_time" : self.appium_get_system_time,
                "appium_get_device_density" : self.appium_get_device_density,
                "appium_finger_print" : self.appium_finger_print,
                "appium_find_element_by_accessibility_id" :
                    self.appium_find_element_by_accessibility_id,
                "appium_switch_to" : self.appium_switch_to,
        }
        if command in commands.keys():
            try:
                return self._normalize_result(commands[command](driver,obj_config,object_step))
            except BaseException as err:
                printer.danger('Idelium Appium | action failed:' + command)
                print(err)
                return self._result(Result.KO)
        printer.danger ('Idelium Appium | action not found:' + command)
        return None
