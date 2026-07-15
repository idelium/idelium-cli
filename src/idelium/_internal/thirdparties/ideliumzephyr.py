"""System module."""
from __future__ import absolute_import
import json
import collections
import sys
import datetime
import time
import os
from urllib.parse import urlencode
from idelium._internal.commons.ideliumprinter import InitPrinter
from idelium._internal.commons.connection import Connection

class ZephyrConnection:
    ''' ZephyrConnection '''
    @staticmethod
    def get_date():
        ''' Get the date '''
        today = datetime.date.today()
        return today.strftime("%Y-%m-%d")
    @staticmethod
    def get_test_case(is_debug, is_test, api_url, zapi_url, issue,
                    username, password):
        ''' Get the test case '''
        os.environ["NO_PROXY"] = "<host>"
        printer = InitPrinter()
        is_ok = False
        #give all the step of testcase
        url_issue = api_url + "issue/" + issue
        req = Connection.request(
            "GET", url_issue, auth=(username, password), debug=is_debug
        )
        if req.status_code != 200:
            printer.danger("credential error o issue jira not exist")
            sys.exit(1)
        json_jira = json.loads(req.text,
                               object_pairs_hook=collections.OrderedDict)
        if "status" in json_jira["fields"]:
            if "name" in json_jira["fields"]["status"]:
                if (json_jira["fields"]["status"]["name"] == "Executable"
                        or is_test is True):
                    is_ok = True
                else:
                    printer.danger("The issue " + issue +
                                   " is not 'Executable' but '" +
                                   json_jira["fields"]["status"]["name"] +
                                   "' so is skipped")
        urlzephyr = zapi_url + "teststep/" + json_jira["id"]
        req = Connection.request(
            "GET", urlzephyr, auth=(username, password), debug=is_debug
        )
        json_zephyr = json.loads(req.text,
                                 object_pairs_hook=collections.OrderedDict)
        return {
            'zapyhrObject': json_zephyr,
            "jiraIssueId": json_jira["id"],
            "isGoodIssueForTest": is_ok,
        }
    def create_cycle(self, is_debug, zapi_url, project_id, version_id, name,
                    username, password):
        ''' create_cycle '''
        os.environ["NO_PROXY"] = "<host>"
        url = zapi_url + "cycle"
        if version_id is None:
            version_id = "-1"
        headers = {"Content-Type": "application/json"}
        payload = {
            "name": name,
            "startDate": self.get_date(),
            "endDate": self.get_date(),
            "projectId": project_id,
            "versionId": version_id,
            "sprintId": None,
        }
        req = Connection.request(
            "POST",
            url,
            headers=headers,
            data=json.dumps(payload),
            auth=(username, password),
            debug=is_debug,
        )
        return json.loads(req.text)
    @staticmethod
    def create_execution(
        is_debug,
        zapi_url,
        cycle_id,
        folder_id,
        issue_id,
        project_id,
        username,
        password,
    ):
        ''' create execution '''
        os.environ["NO_PROXY"] = "<host>"
        url = zapi_url + "execution"
        headers = {"Content-Type": "application/json"}
        payload = {
            "cycleId": cycle_id,
            "issueId": issue_id,
            "projectId": project_id,
        }
        if folder_id is not None:
            payload["folderId"] = folder_id
        req = Connection.request(
            "POST",
            url,
            headers=headers,
            data=json.dumps(payload),
            auth=(username, password),
            debug=is_debug,
        )
        return json.loads(req.text)

    def create_cycle_folder(
        self,
        is_debug,
        environment,
        zapi_url,
        cycle_id,
        version_id,
        project_id,
        username,
        password,
    ):
        ''' create folder cycle '''
        os.environ["NO_PROXY"] = "<host>"
        url = zapi_url + "folder/create"
        headers = {"Content-Type": "application/json"}
        name_folder = ("[" + environment + "] " +
                      datetime.datetime.fromtimestamp(
                          time.time()).strftime("%Y-%m-%d %H:%M:%S"))
        payload = {
            "cycleId": cycle_id,
            "name": name_folder,
            "description": "created test folder for this cycle",
            "projectId": project_id,
            "versionId": version_id,
        }
        req = Connection.request(
            "POST",
            url,
            headers=headers,
            data=json.dumps(payload),
            auth=(username, password),
            debug=is_debug,
        )
        return json.loads(req.text)
    @staticmethod
    def get_executions(
        is_debug,
        zapi_url,
        cycle_id,
        version_id,
        project_id,
        offset,
        username,
        password,
    ):
        ''' get_executions '''
        os.environ["NO_PROXY"] = "<host>"
        url = zapi_url + "execution"
        headers = {"Content-Type": "application/json"}
        payload = {
            "cycleId": cycle_id,
            "versionId": version_id,
            "action": "expand",
            "projectId": project_id,
            "offset": offset,
            "sorter": "OrderId:ASC",
        }
        query_string = urlencode(payload)
        url = url + "?" + query_string
        req = Connection.request(
            "GET",
            url,
            headers=headers,
            auth=(username, password),
            debug=is_debug,
        )
        return json.loads(req.text)
    @staticmethod
    def get_step_id(is_debug, zapi_url, execution_id, username, password):
        '''get_step_id'''
        os.environ["NO_PROXY"] = "<host>"
        url = zapi_url + "stepResult?execution_id=" + str(execution_id)
        req = Connection.request(
            "GET", url, auth=(username, password), debug=is_debug
        )
        return json.loads(req.text)
    @staticmethod
    def update_test_step(is_debug, zapi_url, step_id, status, step_failed,
                       username, password):
        ''' get test step'''
        os.environ["NO_PROXY"] = "<host>"
        url = zapi_url + "stepResult/" + str(step_id)
        headers = {"Content-Type": "application/json"}
        comment = ""
        if step_failed is not None:
            if "note" in step_failed:
                comment = "Error:" + step_failed["note"]
        payload = {"status": status, "comment": comment}
        req = Connection.request(
            "PUT",
            url,
            headers=headers,
            data=json.dumps(payload),
            auth=(username, password),
            debug=is_debug,
        )
        return json.loads(req.text)
    @staticmethod
    def update_execution(is_debug, zapi_url, execution_id, status,
                        username, password):
        ''' Update execution'''
        os.environ["NO_PROXY"] = "<host>"
        url = zapi_url + "execution/" + str(execution_id) + "/execute"
        headers = {"Content-Type": "application/json"}
        payload = {
            "status": status,
        }
        req = Connection.request(
            "PUT",
            url,
            headers=headers,
            data=json.dumps(payload),
            auth=(username, password),
            debug=is_debug,
        )
        return json.loads(req.text)
    @staticmethod
    def add_attachment_buffered(
        is_debug,
        zapi_url,
        path,
        file_name,
        step_id,
        entity_type,
        username,
        password,
    ):
        '''Add attachment buff'''
        os.environ["NO_PROXY"] = "<host>"
        #Possible types: EXECUTION, STEPRESULT
        url = (zapi_url + "attachment?entityId=" + str(step_id) +
               "&entityType=" + entity_type)
        file = open(path + file_name, "rb")
        files = {"file": (file_name, file, "multipart/form-data")}
        headers = {
            "X-Atlassian-Token": "nocheck",
            "Accept": "application/json",
        }
        req = Connection.request(
            "POST",
            url,
            headers=headers,
            files=files,
            auth=(username, password),
            debug=is_debug,
        )
        return json.loads(req.text)

    #
    #  Jira/Zaphyr interface
    #
    def go_execution(self, config):
        '''Execute'''
        printer = config["printer"]
        project_id = config["json_config"]["projectId"]
        for id_cycle in config['idCycle'].split(","):
            printer.success("Start cycleId:" + str(id_cycle))
            exit = False
            count = 0
            offset = 0
            folder_id = None

            if config["is_test"] is False:
                json_create_folder = self.create_cycle_folder(
                    config["is_debug"],
                    config["json_config"]["environment"],
                    config["zephyrApiUrl"],
                    id_cycle,
                    config["idVersion"],
                    config["project_id"],
                    config["username"],
                    config["password"],
                )
                if "id" in json_create_folder:
                    folder_id = json_create_folder["id"]
                else:
                    printer.danger("Jira Error:" + json_create_folder["error"])
                    sys.exit()
            while exit is False:
                return_execution = self.get_executions(
                    config["is_debug"],
                    config["zephyrApiUrl"],
                    id_cycle,
                    config["idVersion"],
                    project_id,
                    offset,
                    config["username"],
                    config["password"],
                )
                for execution in return_execution["executions"]:
                    id_jira = execution["issueKey"]
                    original_execution_id = execution["id"]
                    execution_name = execution["cycleName"]
                    id_cycle = execution["cycleId"]
                    printer.print_important_text(id_jira + ": " +
                                                 execution["summary"])
                    config["execution_name"] = execution_name
                    config["id_jira"] = id_jira
                    config["original_execution_id"] = original_execution_id
                    config["folder_id"] = folder_id
                    config['idCycle'] = id_cycle
                    self.start_test_case(config)
                    count += 1
                if count == return_execution["totalExecutions"]:
                    exit = True
                else:
                    offset += 10

    def start_test_case(self, idelium, test_configurations, config):
        ''' start test case'''
        printer = config["printer"]
        wrapper = idelium.getWrapper(config)
        #project_id = config["json_config"]["projectId"]
        zapyhr_object = self.get_test_case(
            config["is_debug"],
            config["is_test"],
            config["jiraApiUrl"],
            config["zephyrApiUrl"],
            config["idJira"],
            config["username"],
            config["password"],
        )
        if (len(zapyhr_object['zapyhrObject'])
                and zapyhr_object["isGoodIssueForTest"] is True):
            execution_id = None
            return_execution = None
            if config["is_test"] is False:
                if config['idCycle'] is None:
                    self.create_cycle(
                        config["is_debug"],
                        config["zephyrApiUrl"],
                        config["project_id"],
                        config["idVersion"],
                        config["execution_name"],
                        config["username"],
                        config["password"],
                    )
                    return_execution = self.create_execution(
                        config["is_debug"],
                        config["zephyrApiUrl"],
                        config["returnCycle"]["id"],
                        config["folder_id"],
                        config['zapyhrObject']["jiraIssueId"],
                        config["project_id"],
                        config["username"],
                        config["password"],
                    )
                else:
                    return_execution = self.create_execution(
                        config["is_debug"],
                        config["zephyrApiUrl"],
                        config['idCycle'],
                        config["folder_id"],
                        config['zapyhrObject']["jiraIssueId"],
                        config["project_id"],
                        config["username"],
                        config["password"],
                    )
                all_steps_execution = None
                for execution in return_execution:
                    execution_id = execution
                    all_steps_execution = self.get_step_id(
                        config["is_debug"],
                        config["zephyrApiUrl"],
                        config["execution"],
                        config["username"],
                        config["password"],
                    )
            driver = None
            index = 0
            execution_status = "1"
            stop_execute_steps = False
            for test_case in zapyhr_object['zapyhrObject']["stepBeanCollection"]:
                # if is_testis True:
                #   input("Test Mode Press Enter to continue...")
                step = test_case["step"].lower()
                if step not in config["json_step_config"]:
                    printer.danger("Warning, the  step: '" + step +
                                   "' is not defined")
                    sys.exit(1)
                try:
                    file_step = (config["dir_step_files"] + "/" +
                                 config["json_step_config"][step] + ".json")
                    with open(file_step) as json_data:
                        json_step = json.load(json_data)
                except BaseException as err:
                    printer.danger("Warning, the file step: " + file_step +
                                   " not exist or is not a json (err 1)")
                    print(err)
                    sys.exit(1)
                if stop_execute_steps is False:
                    printer.underline(config["json_step"]["name"] + " (" +
                                      str(test_case["id"]) + ")")
                    config["wrapper"] = wrapper
                    config["json_step"] = json_step
                    #object_return = self.execute_step(driver,
                    #                                 test_configurations,
                    #                                 config)
                    #status = object_return["status"]
                    #driver = object_return["driver"]
                    #step_failed = object_return['stepFailed']
                    step_failed = False
                    status = False
                    if config["is_test"] is False:
                        self.update_test_step(
                            config["is_debug"],
                            config["zephyrApiUrl"],
                            all_steps_execution[index]["id"],
                            status,
                            step_failed,
                            config["username"],
                            config["password"],
                        )
                    if status == "2" or status == "5":
                        execution_status = status
                        path = "screenshots/"
                        file_name = str(test_case["id"]) + ".png"
                        if not os.path.exists(path):
                            os.makedirs(path)
                        if config["json_step"]["attachScreenshot"] is True:
                            wrapper.screen_shot(driver, path + file_name,config['ideliumServer'])
                            if config["is_test"] is False:
                                self.add_attachment_buffered(
                                    config["is_debug"],
                                    config["zephyrApiUrl"],
                                    path,
                                    file_name,
                                    all_steps_execution[index]["id"],
                                    "STEPRESULT",
                                    config["username"],
                                    config["password"],
                                )
                            os.unlink(path + file_name)
                        if config["json_step"]["failedExit"] is True:
                            printer.danger(
                                "La issue " + config["idJira"] +
                                " e' forzamente interrotta causa fallimento bloccante dello step"
                            )
                            stop_execute_steps = True
                    index += 1
            driver.quit()
            if config["is_test"] is False:
                self.update_execution(
                    config["is_debug"],
                    config["zephyrApiUrl"],
                    execution_id,
                    execution_status,
                    config["username"],
                    config["password"],
                )
                if config["original_execution_id"] is not None:
                    self.update_execution(
                        config["is_debug"],
                        config["zephyrApiUrl"],
                        config["original_execution_id"],
                        execution_status,
                        config["username"],
                        config["password"],
                    )
