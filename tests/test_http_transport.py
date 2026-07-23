"""Unit tests for the shared secure HTTP transport."""

import io
import unittest
import warnings
from contextlib import redirect_stdout
from unittest.mock import Mock

import requests

from idelium._internal.commons.connection import (
    Connection,
    HttpClient,
    HttpTransportError,
)


class HttpTransportTest(unittest.TestCase):
    def response(self, status=200, text='{"status":"ok"}'):
        response = Mock()
        response.status_code = status
        response.text = text
        return response

    def test_tls_and_finite_timeouts_are_enabled_by_default(self):
        session = Mock()
        session.request.return_value = self.response()
        client = HttpClient(session=session)

        client.request("GET", "https://example.test")

        self.assertTrue(session.request.call_args.kwargs["verify"])
        self.assertEqual((5, 30), session.request.call_args.kwargs["timeout"])

    def test_custom_ca_bundle_and_explicit_insecure_mode_are_supported(self):
        session = Mock()
        session.request.return_value = self.response()
        Connection.configure(ca_bundle="/certificates/internal-ca.pem", session=session)
        Connection.request("GET", "https://example.test")
        self.assertEqual(
            "/certificates/internal-ca.pem",
            session.request.call_args.kwargs["verify"],
        )

        insecure_session = Mock()
        insecure_session.request.return_value = self.response()
        with warnings.catch_warnings(record=True) as recorded:
            warnings.simplefilter("always")
            Connection.configure(insecure=True, session=insecure_session)
        Connection.request("GET", "https://example.test")
        self.assertFalse(insecure_session.request.call_args.kwargs["verify"])
        self.assertIn("verification is disabled", str(recorded[0].message))

    def test_non_json_and_http_errors_do_not_expose_response_bodies(self):
        session = Mock()
        session.request.return_value = self.response(200, "secret upstream page")
        client = HttpClient(session=session)

        with self.assertRaises(HttpTransportError) as invalid_json:
            client.request_json("GET", "https://example.test")
        self.assertNotIn("secret upstream page", str(invalid_json.exception))

        session.request.return_value = self.response(500, "secret failure body")
        with self.assertRaises(HttpTransportError) as http_error:
            client.request("GET", "https://example.test")
        self.assertNotIn("secret failure body", str(http_error.exception))

    def test_tls_failures_return_actionable_error_without_trace_details(self):
        session = Mock()
        session.request.side_effect = requests.exceptions.SSLError(
            "certificate verify failed: self-signed certificate"
        )
        client = HttpClient(session=session)

        with self.assertRaises(HttpTransportError) as transport_error:
            client.request("GET", "https://localhost/api/ideliumcl/testcycle/1")

        message = str(transport_error.exception)
        self.assertIn("TLS certificate verification failed", message)
        self.assertIn("--caBundle", message)
        self.assertIn("--insecure", message)
        self.assertNotIn("Traceback", message)

    def test_retries_are_bounded_and_only_allow_idempotent_methods(self):
        session = Mock()
        HttpClient(session=session, retries=2)

        adapter = session.mount.call_args_list[0].args[1]
        retry = adapter.max_retries
        self.assertEqual(2, retry.total)
        self.assertIn("GET", retry.allowed_methods)
        self.assertIn("PUT", retry.allowed_methods)
        self.assertNotIn("POST", retry.allowed_methods)

    def test_verbose_output_redacts_sensitive_query_values_and_headers(self):
        session = Mock()
        session.request.return_value = self.response()
        Connection.configure(session=session)
        output = io.StringIO()

        with redirect_stdout(output):
            Connection.start(
                "GET",
                "https://example.test/resource?token=sensitive-token",
                api_key="sensitive-api-key",
                debug=True,
            )

        diagnostics = output.getvalue()
        self.assertNotIn("sensitive-token", diagnostics)
        self.assertNotIn("sensitive-api-key", diagnostics)
        self.assertIn("%5BREDACTED%5D", diagnostics)


if __name__ == "__main__":
    unittest.main()
