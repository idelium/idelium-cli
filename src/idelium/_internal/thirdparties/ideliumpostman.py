"""Execute Postman v2.1 collections and evaluate saved response examples."""

from __future__ import absolute_import

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

from requests.auth import HTTPBasicAuth, HTTPDigestAuth
from requests_hawk import HawkAuth
from requests_oauthlib import OAuth1

from idelium._internal.commons.ideliumprinter import InitPrinter
from idelium._internal.commons.connection import HttpClient, HttpTransportError


printer = InitPrinter()

NEWMAN_MISSING_MESSAGE = (
    "Newman is required to run this Postman collection but was not found on PATH. "
    "Install it with `npm install -g newman`, then verify it with `newman --version`. "
    "If it is already installed, make sure the directory containing the `newman` "
    "executable is available in the PATH used by the idelium command."
)


class PostmanCollection:
    """Run collection requests without executing arbitrary Postman scripts."""

    BODYLESS_METHODS = {"GET", "HEAD"}
    SENSITIVE_KEYS = {
        "api_key",
        "apikey",
        "authorization",
        "cookie",
        "password",
        "secret",
        "session",
        "token",
    }
    VARIABLE_PATTERN = re.compile(r"{{\s*([^{}]+?)\s*}}")

    def __init__(self, session=None, verify=True, timeout=(5, 30)):
        self.client = HttpClient(session=session, verify=verify, timeout=timeout)
        self.verify = verify
        self.timeout = timeout
        self.variables = {}

    @staticmethod
    def _enabled_values(values):
        variables = {}
        for value in values or []:
            if value.get("enabled", True) is False or value.get("disabled", False):
                continue
            key = value.get("key")
            if key:
                variables[str(key)] = value.get("value", "")
        return variables

    def _substitute(self, value):
        if isinstance(value, str):
            return self.VARIABLE_PATTERN.sub(
                lambda match: str(self.variables.get(match.group(1), match.group(0))),
                value,
            )
        if isinstance(value, list):
            return [self._substitute(item) for item in value]
        if isinstance(value, dict):
            return {key: self._substitute(item) for key, item in value.items()}
        return value

    @classmethod
    def _is_sensitive(cls, key):
        normalized = str(key).lower().replace("-", "_")
        return any(marker in normalized for marker in cls.SENSITIVE_KEYS)

    @classmethod
    def _redact(cls, value):
        if isinstance(value, dict):
            return {
                key: "[REDACTED]" if cls._is_sensitive(key) else cls._redact(item)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [cls._redact(item) for item in value]
        return value

    @classmethod
    def _redact_body(cls, body):
        try:
            parsed = json.loads(body)
        except (TypeError, ValueError):
            return body
        return json.dumps(cls._redact(parsed), separators=(",", ":"))

    @classmethod
    def _redact_url(cls, url):
        parts = urlsplit(url)
        query = [
            (key, "[REDACTED]" if cls._is_sensitive(key) else value)
            for key, value in parse_qsl(parts.query, keep_blank_values=True)
        ]
        return urlunsplit(
            (parts.scheme, parts.netloc, parts.path, urlencode(query), "")
        )

    @staticmethod
    def _pairs_to_dict(values):
        return {
            item["key"]: item.get("value", "")
            for item in values or []
            if item.get("key") and not item.get("disabled", False)
        }

    def _request_url(self, request):
        url = request.get("url", "")
        if isinstance(url, dict):
            return self._substitute(PostmanNewmanCollection._request_url(request))
        return self._substitute(url)

    def _request_headers(self, request):
        headers = self._pairs_to_dict(self._substitute(request.get("header", [])))
        return {str(key): str(value) for key, value in headers.items()}

    def _request_body(self, request):
        body = self._substitute(request.get("body") or {})
        mode = body.get("mode") or body.get("method")
        if mode == "raw":
            return body.get("raw", body.get("value", "")), None
        if mode in {"urlencoded", "formdata"}:
            return self._pairs_to_dict(body.get(mode, [])), None
        if mode == "graphql":
            return json.dumps(body.get("graphql", {})), None
        return None, None

    def _authentication(self, auth, headers, has_body=True):
        if not auth or auth.get("type") in {None, "noauth"}:
            return None

        auth_type = auth["type"]
        values = self._pairs_to_dict(self._substitute(auth.get(auth_type, [])))
        if auth_type == "basic":
            return HTTPBasicAuth(values.get("username", ""), values.get("password", ""))
        if auth_type == "digest":
            return HTTPDigestAuth(
                values.get("username", ""), values.get("password", "")
            )
        if auth_type == "oauth1":
            return OAuth1(
                values.get("consumerKey", ""),
                values.get("consumerSecret", ""),
                values.get("token", ""),
                values.get("tokenSecret", ""),
                signature_method=values.get("signatureMethod", "HMAC-SHA1"),
            )
        if auth_type == "hawk":
            return HawkAuth(
                id=values.get("authId", ""),
                key=values.get("authKey", ""),
                algorithm=values.get("algorithm", "sha256"),
                always_hash_content=has_body,
            )
        if auth_type in {"bearer", "oauth2"}:
            token = values.get("token", values.get("accessToken", ""))
            headers["Authorization"] = "Bearer " + token
        if auth_type == "apikey" and values.get("in", "header") == "header":
            headers[values.get("key", "X-API-Key")] = values.get("value", "")
        return None

    @staticmethod
    def _iter_requests(items):
        for item in items or []:
            if "request" in item:
                yield item
            yield from PostmanCollection._iter_requests(item.get("item", []))

    @staticmethod
    def _expected_response(item, actual_status):
        examples = item.get("response") or []
        for example in examples:
            if int(example.get("code", -1)) == actual_status:
                return example
        return examples[0] if examples else None

    @staticmethod
    def _body_matches(actual, expected):
        try:
            return json.loads(actual) == json.loads(expected)
        except (TypeError, ValueError):
            return str(actual).strip() == str(expected).strip()

    def _assertions(self, item, response):
        expected = self._expected_response(item, response.status_code)
        expected_status = expected.get("code") if expected else None
        status_passed = (
            response.status_code == int(expected_status)
            if expected_status is not None
            else 200 <= response.status_code < 400
        )
        assertions = [
            {
                "name": "status",
                "passed": status_passed,
                "message": (
                    "Status matched."
                    if status_passed
                    else "Unexpected HTTP status code."
                ),
            }
        ]

        if expected is not None and expected.get("body") is not None:
            body_passed = self._body_matches(response.text, expected["body"])
            assertions.append(
                {
                    "name": "body",
                    "passed": body_passed,
                    "message": (
                        "Body matched."
                        if body_passed
                        else "Response body did not match the saved Postman example."
                    ),
                }
            )

        return assertions

    def connection_test(self, item, debug=False, inherited_auth=None):
        """Execute one request item and return its redacted assertion result."""
        request = self._substitute(item["request"])
        method = str(request.get("method", "GET")).upper()
        url = self._request_url(request)
        headers = self._request_headers(request)
        data, files = self._request_body(request)
        has_body = method not in self.BODYLESS_METHODS and (
            data is not None or files is not None
        )
        auth = self._authentication(
            request.get("auth", inherited_auth),
            headers,
            has_body=has_body,
        )
        request_options = {
            "debug": debug,
            "raise_for_status": False,
            "headers": headers,
            "auth": auth,
            "allow_redirects": True,
            "verify": self.verify,
            "timeout": self.timeout,
        }
        if method not in self.BODYLESS_METHODS:
            request_options["data"] = data
            request_options["files"] = files
        started_at = time.monotonic()

        try:
            response = self.client.request(
                method,
                url,
                **request_options,
            )
            duration = time.monotonic() - started_at
            assertions = self._assertions(item, response)
            result = {
                "name": item.get("name", "Unnamed request"),
                "response": self._redact_body(response.text),
                "status": str(response.status_code),
                "method": method,
                "url": self._redact_url(url),
                "time": duration,
                "passed": all(assertion["passed"] for assertion in assertions),
                "assertions": assertions,
            }
        except HttpTransportError:
            result = {
                "name": item.get("name", "Unnamed request"),
                "response": "Request failed.",
                "status": "0",
                "method": method,
                "url": self._redact_url(url),
                "time": time.monotonic() - started_at,
                "passed": False,
                "assertions": [
                    {
                        "name": "network",
                        "passed": False,
                        "message": "The HTTP request could not be completed.",
                    }
                ],
            }

        if debug:
            printer.print_important_text(
                "{} {} -> {}".format(method, result["url"], result["status"])
            )
        return result

    def parse_collection(self, collection, debug=False, environment=None):
        """Execute all requests, including requests inside nested folders."""
        self.variables = self._enabled_values(collection.get("variable", []))
        self.variables.update(
            self._enabled_values((environment or {}).get("values", []))
        )
        inherited_auth = collection.get("auth")
        return [
            self.connection_test(item, debug, inherited_auth)
            for item in self._iter_requests(collection.get("item", []))
        ]

    def start_postman_test(self, postman, debug=False):
        """Execute the uploaded collection and its optional environment."""
        if postman.get("insecure", False):
            printer.warning("Postman TLS certificate verification is disabled.")
            self.verify = False
            self.client.verify = False
        return self.parse_collection(
            postman["collection"],
            debug,
            postman.get("environment"),
        )


class PostmanNewmanCollection:
    """Run Postman collections through Newman and map reports to Idelium results."""

    NEWMAN_MISSING_MESSAGE = NEWMAN_MISSING_MESSAGE

    def __init__(
        self,
        newman_binary="newman",
        binary_resolver=None,
        subprocess_runner=None,
        timeout=300,
    ):
        self.newman_binary = newman_binary
        self.binary_resolver = binary_resolver or shutil.which
        self.subprocess_runner = subprocess_runner or subprocess.run
        self.timeout = timeout

    @staticmethod
    def _write_json(directory, name, value):
        path = os.path.join(directory, name)
        with open(path, "w", encoding="utf-8") as file_obj:
            json.dump(value, file_obj)
        return path

    def _materialize_input(self, directory, postman, key, filename):
        value = postman.get(key)
        if value is None:
            return None
        if isinstance(value, str):
            return value
        return self._write_json(directory, filename, value)

    def _command(self, directory, postman, report_path):
        binary = self.binary_resolver(self.newman_binary)
        if not binary:
            raise FileNotFoundError(self.newman_binary)

        collection_path = self._materialize_input(
            directory,
            postman,
            "collection",
            "collection.json",
        )
        if not collection_path:
            raise ValueError("A Postman collection is required for Newman execution.")

        command = [
            binary,
            "run",
            collection_path,
            "--reporters",
            "json",
            "--reporter-json-export",
            report_path,
        ]

        environment_path = self._materialize_input(
            directory,
            postman,
            "environment",
            "environment.json",
        )
        if environment_path:
            command.extend(["--environment", environment_path])

        data_path = self._materialize_input(
            directory,
            postman,
            "iterationData",
            "iteration-data.json",
        )
        if not data_path:
            data_path = self._materialize_input(
                directory,
                postman,
                "dataFile",
                "iteration-data.json",
            )
        if data_path:
            command.extend(["--iteration-data", data_path])

        if postman.get("insecure", False):
            command.append("--insecure")

        return command

    @staticmethod
    def _request_method(request):
        return str(request.get("method", "GET")).upper()

    @staticmethod
    def _request_url(request):
        url = request.get("url", "")
        if isinstance(url, dict):
            if url.get("raw"):
                return str(url.get("raw", ""))
            protocol = str(url.get("protocol") or "")
            host = url.get("host") or []
            path = url.get("path") or []
            query = url.get("query") or []
            host_value = ".".join(str(part) for part in host)
            path_value = "/".join(quote(str(part), safe="") for part in path)
            query_values = [
                (item["key"], item.get("value", ""))
                for item in query
                if item.get("key") and not item.get("disabled", False)
            ]
            query_value = urlencode(query_values)
            scheme = protocol + "://" if protocol else ""
            path_separator = "/" if host_value and path_value else ""
            return "{}{}{}{}{}".format(
                scheme,
                host_value,
                path_separator,
                path_value,
                "?" + query_value if query_value else "",
            )
        return str(url)

    @staticmethod
    def _response_body(response):
        if response is None:
            return ""
        body = response.get("stream", response.get("body", ""))
        if isinstance(body, list):
            try:
                return bytes(body).decode("utf-8", errors="replace")
            except ValueError:
                return ""
        if isinstance(body, dict):
            data = body.get("data")
            if isinstance(data, list):
                try:
                    return bytes(data).decode("utf-8", errors="replace")
                except ValueError:
                    return ""
            return json.dumps(body, separators=(",", ":"))
        if isinstance(body, bytes):
            return body.decode("utf-8", errors="replace")
        return str(body or "")

    @staticmethod
    def _response_status(response):
        if response is None:
            return "0"
        return str(response.get("code", response.get("status", "0")))

    @staticmethod
    def _response_time(response):
        if response is None:
            return 0
        return response.get("responseTime", response.get("response_time", 0)) or 0

    @staticmethod
    def _assertions(execution):
        assertions = []
        for assertion in execution.get("assertions") or []:
            error = assertion.get("error")
            skipped = assertion.get("skipped", False)
            assertions.append(
                {
                    "name": assertion.get("assertion", "postman assertion"),
                    "passed": error is None and skipped is False,
                    "message": (
                        "Skipped."
                        if skipped
                        else (error or {}).get("message", "Assertion passed.")
                    ),
                }
            )
        return assertions

    @staticmethod
    def _failure_assertion(failure):
        error = failure.get("error") or {}
        return {
            "name": failure.get("at", "newman failure"),
            "passed": False,
            "message": error.get("message", "Newman reported a failure."),
        }

    @staticmethod
    def _failure_key(failure):
        source = failure.get("source") or {}
        return source.get("id") or source.get("name")

    def _failure_map(self, failures):
        mapped = {}
        for failure in failures:
            key = self._failure_key(failure)
            if key:
                mapped.setdefault(str(key), []).append(failure)
        return mapped

    def _execution_key(self, execution):
        item = execution.get("item") or {}
        return item.get("id") or item.get("name")

    def _result_from_execution(self, execution, failures):
        item = execution.get("item") or {}
        request = execution.get("request") or {}
        response = execution.get("response")
        assertions = self._assertions(execution)
        has_failed_assertions = any(
            assertion.get("passed") is False for assertion in assertions
        )
        key = self._execution_key(execution)
        if not has_failed_assertions:
            for failure in failures.get(str(key), []) if key else []:
                assertions.append(self._failure_assertion(failure))
        if not assertions:
            assertions.append(
                {
                    "name": "newman request",
                    "passed": response is not None,
                    "message": (
                        "Request completed."
                        if response is not None
                        else "Newman did not produce a response."
                    ),
                }
            )

        return {
            "name": item.get("name", "Unnamed request"),
            "response": PostmanCollection._redact_body(self._response_body(response)),
            "status": self._response_status(response),
            "method": self._request_method(request),
            "url": PostmanCollection._redact_url(self._request_url(request)),
            "time": self._response_time(response),
            "passed": all(assertion["passed"] for assertion in assertions),
            "assertions": assertions,
        }

    def _failure_result(self, name, message):
        return [
            {
                "name": name,
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
                        "message": message,
                    }
                ],
            }
        ]

    def _parse_report(self, report_path, return_code):
        try:
            with open(report_path, encoding="utf-8") as file_obj:
                report = json.load(file_obj)
        except (OSError, ValueError):
            return self._failure_result(
                "Newman report",
                "Newman did not produce a valid JSON report.",
            )

        run = report.get("run") or {}
        executions = run.get("executions") or []
        failures = run.get("failures") or []
        failure_map = self._failure_map(failures)
        results = [
            self._result_from_execution(execution, failure_map)
            for execution in executions
        ]

        execution_keys = {
            self._execution_key(execution)
            for execution in executions
            if self._execution_key(execution)
        }
        for failure in failures:
            if self._failure_key(failure) in execution_keys:
                continue
            assertion = self._failure_assertion(failure)
            results.append(
                {
                    "name": str(self._failure_key(failure) or "Newman failure"),
                    "response": "",
                    "status": "0",
                    "method": "NEWMAN",
                    "url": "",
                    "time": 0,
                    "passed": False,
                    "assertions": [assertion],
                }
            )

        if not results:
            return self._failure_result(
                "Newman report",
                "Newman completed without request executions.",
            )
        if return_code != 0 and all(result["passed"] for result in results):
            results[-1]["passed"] = False
            results[-1]["assertions"].append(
                {
                    "name": "newman exit code",
                    "passed": False,
                    "message": "Newman exited with code {}.".format(return_code),
                }
            )
        return results

    def _run_in_directory(self, directory, postman, debug):
        report_path = os.path.join(directory, "newman-report.json")
        try:
            command = self._command(directory, postman, report_path)
        except FileNotFoundError:
            printer.danger(self.NEWMAN_MISSING_MESSAGE)
            return self._failure_result(
                "Newman",
                self.NEWMAN_MISSING_MESSAGE,
            )
        except ValueError as error:
            return self._failure_result("Newman", str(error))

        if debug:
            printer.print_important_text("Running Newman Postman runtime.")
            printer.print_important_text("Newman working directory: " + directory)

        try:
            completed = self.subprocess_runner(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
        except FileNotFoundError:
            printer.danger(self.NEWMAN_MISSING_MESSAGE)
            return self._failure_result(
                "Newman",
                self.NEWMAN_MISSING_MESSAGE,
            )
        except subprocess.TimeoutExpired:
            return self._failure_result(
                "Newman",
                "Newman execution exceeded the configured timeout.",
            )

        return self._parse_report(report_path, completed.returncode)

    def start_postman_test(self, postman, debug=False):
        """Execute a Postman collection with Newman and return Idelium results."""
        debug_root = os.environ.get("IDELIUM_POSTMAN_DEBUG_DIR")
        if debug and debug_root:
            os.makedirs(debug_root, exist_ok=True)
            directory = tempfile.mkdtemp(prefix="idelium-newman-", dir=debug_root)
            return self._run_in_directory(directory, postman, debug)

        with tempfile.TemporaryDirectory(prefix="idelium-newman-") as directory:
            return self._run_in_directory(directory, postman, debug)
