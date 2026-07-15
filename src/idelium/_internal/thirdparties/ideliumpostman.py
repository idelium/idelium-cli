"""Execute Postman v2.1 collections and evaluate saved response examples."""

from __future__ import absolute_import

import json
import re
import time
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from requests.auth import HTTPBasicAuth, HTTPDigestAuth
from requests_hawk import HawkAuth
from requests_oauthlib import OAuth1

from idelium._internal.commons.ideliumprinter import InitPrinter
from idelium._internal.commons.connection import HttpClient, HttpTransportError


printer = InitPrinter()


class PostmanCollection:
    """Run collection requests without executing arbitrary Postman scripts."""

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
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))

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
            url = url.get("raw", "")
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

    def _authentication(self, auth, headers):
        if not auth or auth.get("type") in {None, "noauth"}:
            return None

        auth_type = auth["type"]
        values = self._pairs_to_dict(self._substitute(auth.get(auth_type, [])))
        if auth_type == "basic":
            return HTTPBasicAuth(values.get("username", ""), values.get("password", ""))
        if auth_type == "digest":
            return HTTPDigestAuth(values.get("username", ""), values.get("password", ""))
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
        assertions = [{
            "name": "status",
            "passed": status_passed,
            "message": (
                "Status matched."
                if status_passed
                else "Unexpected HTTP status code."
            ),
        }]

        if expected is not None and expected.get("body") is not None:
            body_passed = self._body_matches(response.text, expected["body"])
            assertions.append({
                "name": "body",
                "passed": body_passed,
                "message": (
                    "Body matched."
                    if body_passed
                    else "Response body did not match the saved Postman example."
                ),
            })

        return assertions

    def connection_test(self, item, debug=False, inherited_auth=None):
        """Execute one request item and return its redacted assertion result."""
        request = self._substitute(item["request"])
        method = str(request.get("method", "GET")).upper()
        url = self._request_url(request)
        headers = self._request_headers(request)
        auth = self._authentication(request.get("auth", inherited_auth), headers)
        data, files = self._request_body(request)
        started_at = time.monotonic()

        try:
            response = self.client.request(
                method,
                url,
                debug=debug,
                raise_for_status=False,
                headers=headers,
                auth=auth,
                data=data,
                files=files,
                allow_redirects=True,
                verify=self.verify,
                timeout=self.timeout,
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
                "assertions": [{
                    "name": "network",
                    "passed": False,
                    "message": "The HTTP request could not be completed.",
                }],
            }

        if debug:
            printer.print_important_text(
                "{} {} -> {}".format(method, result["url"], result["status"])
            )
        return result

    def parse_collection(self, collection, debug=False, environment=None):
        """Execute all requests, including requests inside nested folders."""
        self.variables = self._enabled_values(collection.get("variable", []))
        self.variables.update(self._enabled_values((environment or {}).get("values", [])))
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
