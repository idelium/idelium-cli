"""Shared, secure HTTP transport for Idelium integrations."""

import collections
import json
import warnings
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class HttpTransportError(RuntimeError):
    """Report a transport or response failure without exposing response data."""


class HttpClient:
    """Apply consistent TLS, timeout, retry, status, and logging behavior."""

    IDEMPOTENT_METHODS = frozenset({"DELETE", "GET", "HEAD", "OPTIONS", "PUT"})
    SENSITIVE_KEYS = {
        "api_key",
        "apikey",
        "authorization",
        "cookie",
        "idelium_key",
        "password",
        "secret",
        "session",
        "token",
    }

    def __init__(
        self,
        session=None,
        verify=True,
        timeout=(5, 30),
        retries=2,
    ):
        self.session = session or requests.Session()
        self.verify = verify
        self.timeout = timeout
        retry = Retry(
            total=retries,
            connect=retries,
            read=retries,
            status=retries,
            backoff_factor=0.25,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=self.IDEMPOTENT_METHODS,
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    @classmethod
    def _is_sensitive(cls, key):
        normalized = str(key).lower().replace("-", "_")
        return any(marker in normalized for marker in cls.SENSITIVE_KEYS)

    @classmethod
    def redact(cls, value):
        """Recursively redact credentials from structured diagnostic values."""
        if isinstance(value, dict):
            return {
                key: "[REDACTED]" if cls._is_sensitive(key) else cls.redact(item)
                for key, item in value.items()
            }
        if isinstance(value, (list, tuple)):
            return [cls.redact(item) for item in value]
        return value

    @classmethod
    def redact_url(cls, url):
        parts = urlsplit(url)
        query = [
            (key, "[REDACTED]" if cls._is_sensitive(key) else value)
            for key, value in parse_qsl(parts.query, keep_blank_values=True)
        ]
        return urlunsplit(
            (parts.scheme, parts.netloc, parts.path, urlencode(query), "")
        )

    def request(self, method, url, debug=False, raise_for_status=True, **kwargs):
        """Send one request with safe defaults and optional status validation."""
        method = method.upper()
        kwargs.setdefault("timeout", self.timeout)
        kwargs.setdefault("verify", self.verify)
        try:
            response = self.session.request(method, url, **kwargs)
        except requests.exceptions.SSLError as error:
            raise HttpTransportError(
                "{} request failed for {}: TLS certificate verification failed. "
                "Use --caBundle with a trusted CA bundle, or --insecure only for "
                "local development with self-signed certificates.".format(
                    method,
                    self.redact_url(url),
                )
            ) from error
        except requests.RequestException as error:
            raise HttpTransportError(
                "{} request failed for {}".format(method, self.redact_url(url))
            ) from error

        if debug:
            print(
                "HTTP {} {} -> {}".format(
                    method,
                    self.redact_url(url),
                    response.status_code,
                )
            )
        if raise_for_status and not 200 <= response.status_code < 300:
            raise HttpTransportError(
                "{} request returned HTTP {} for {}".format(
                    method,
                    response.status_code,
                    self.redact_url(url),
                )
            )
        return response

    def request_json(self, method, url, debug=False, **kwargs):
        """Send a validated request and decode a JSON response predictably."""
        response = self.request(method, url, debug=debug, **kwargs)
        try:
            return json.loads(
                response.text,
                object_pairs_hook=collections.OrderedDict,
            )
        except (TypeError, ValueError) as error:
            raise HttpTransportError(
                "{} response was not valid JSON (HTTP {})".format(
                    method.upper(),
                    response.status_code,
                )
            ) from error


class Connection:
    """Backward-compatible adapter used by the Idelium API client."""

    _client = HttpClient()

    @classmethod
    def configure(
        cls,
        ca_bundle=None,
        insecure=False,
        timeout=(5, 30),
        session=None,
    ):
        if insecure:
            warnings.warn(
                "TLS certificate verification is disabled by explicit request.",
                UserWarning,
                stacklevel=2,
            )
            verify = False
        else:
            verify = ca_bundle or True
        cls._client = HttpClient(session=session, verify=verify, timeout=timeout)

    @classmethod
    def request(cls, method, url, **kwargs):
        """Return a raw validated response for third-party integrations."""
        return cls._client.request(method, url, **kwargs)

    @classmethod
    def start(cls, method, url, payload=None, api_key=None, debug=False):
        """Call an Idelium JSON endpoint using the legacy method signature."""
        headers = {"Content-Type": "application/json", "Idelium-Key": api_key}
        kwargs = {"headers": headers}
        if payload is not None:
            kwargs["data"] = json.dumps(payload)
        return cls._client.request_json(method, url, debug=debug, **kwargs)
