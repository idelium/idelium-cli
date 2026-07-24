"""Tests for canonical JSON and HTML execution reports."""

import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from jsonschema import Draft202012Validator

from idelium._internal.executionreport import (
    build_execution_report,
    render_html_report,
    render_junit_report,
    write_html_report,
    write_junit_report,
    write_json_report,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
REPORT_SCHEMA = REPOSITORY_ROOT / "docs" / "reports" / "execution-report.schema.json"


class ExecutionReportTest(unittest.TestCase):
    def _sample_events(self):
        return [
            {
                "id": 2,
                "name": "postman cycle",
                "description": "Cycle <with untrusted text>",
                "steps": [
                    {
                        "id": 17,
                        "name": "postman <script>",
                        "type": "postman",
                        "status": "2",
                        "durationMilliseconds": 123,
                        "diagnostics": [
                            {"level": "error", "message": "token abc should fail"}
                        ],
                        "artifacts": [
                            {
                                "name": "response",
                                "type": "json",
                                "path": "reports/response.json",
                            }
                        ],
                        "postmanResults": [
                            {
                                "name": "POST Raw Text",
                                "method": "POST",
                                "url": "https://example.invalid/post?token=secret&debug=1",
                                "status": "500",
                                "passed": False,
                                "time": 42,
                                "assertions": [
                                    {
                                        "name": "status",
                                        "passed": False,
                                        "message": "password hunter2 failed",
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
        ]

    def test_json_report_validates_against_schema_and_redacts_sensitive_values(self):
        report = build_execution_report(
            self._sample_events(),
            config={
                "idProject": "3",
                "idCycle": "2",
                "environment": "envpost",
                "reportingService": "idelium",
            },
            exit_code=1,
        )

        schema = json.loads(REPORT_SCHEMA.read_text(encoding="utf-8"))
        Draft202012Validator(schema).validate(report)
        serialized = json.dumps(report)
        self.assertNotIn("secret", serialized)
        self.assertNotIn("hunter2", serialized)
        self.assertNotIn("abc", serialized)
        self.assertIn("token=[REDACTED]", serialized)
        self.assertEqual("failed", report["run"]["status"])
        self.assertEqual(1, report["summary"]["failed"])

    def test_html_report_escapes_untrusted_content(self):
        report = build_execution_report(
            self._sample_events(),
            config={"idProject": "3", "idCycle": "2", "environment": "envpost"},
            exit_code=1,
        )

        html = render_html_report(report)

        self.assertIn("Idelium Execution Report", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertNotIn("<script>", html)
        self.assertNotIn("hunter2", html)

    def test_junit_report_maps_failures_timing_and_redacts_values(self):
        report = build_execution_report(
            self._sample_events(),
            config={"idProject": "3", "idCycle": "2", "environment": "envpost"},
            exit_code=1,
        )

        xml = render_junit_report(report)
        root = ET.fromstring(xml)
        failure = root.find("./testsuite/testcase/failure")

        self.assertEqual("testsuites", root.tag)
        self.assertEqual("1", root.attrib["tests"])
        self.assertEqual("1", root.attrib["failures"])
        self.assertEqual("0.123", root.attrib["time"])
        self.assertIsNotNone(failure)
        self.assertIn("token [REDACTED]", failure.text)
        self.assertNotIn("hunter2", xml)
        self.assertNotIn("abc", xml)
        self.assertNotIn("<script>", xml)

    def test_report_writers_create_parent_directories(self):
        report = build_execution_report(
            self._sample_events(),
            config={"idProject": "3", "idCycle": "2", "environment": "envpost"},
            exit_code=1,
        )

        with tempfile.TemporaryDirectory() as directory:
            json_path = Path(directory) / "nested" / "report.json"
            html_path = Path(directory) / "nested" / "report.html"
            junit_path = Path(directory) / "nested" / "report.xml"

            write_json_report(report, json_path)
            write_html_report(report, html_path)
            write_junit_report(report, junit_path)

            self.assertTrue(json_path.exists())
            self.assertTrue(html_path.exists())
            self.assertTrue(junit_path.exists())


if __name__ == "__main__":
    unittest.main()
