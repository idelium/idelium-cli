"""Unit tests for Postman collection execution."""

import json
import unittest
from unittest.mock import Mock

from idelium._internal.thirdparties.ideliumpostman import PostmanCollection


class PostmanCollectionTest(unittest.TestCase):
    def response(self, status, body):
        response = Mock()
        response.status_code = status
        response.text = body
        return response

    def test_saved_status_and_json_body_are_checked_semantically(self):
        session = Mock()
        session.request.return_value = self.response(200, '{"value":1,"ok":true}')
        runner = PostmanCollection(session=session)
        collection = {
            "item": [{
                "name": "Echo",
                "request": {
                    "method": "GET",
                    "url": {"raw": "https://example.test/echo"},
                    "header": [],
                },
                "response": [{
                    "code": 200,
                    "body": '{"ok":true,"value":1}',
                }],
            }],
        }

        results = runner.parse_collection(collection)

        self.assertTrue(results[0]["passed"])
        self.assertEqual(["status", "body"], [item["name"] for item in results[0]["assertions"]])
        self.assertTrue(session.request.call_args.kwargs["verify"])
        self.assertEqual((5, 30), session.request.call_args.kwargs["timeout"])

    def test_body_mismatch_fails_the_request_result(self):
        session = Mock()
        session.request.return_value = self.response(200, '{"message":"actual"}')
        runner = PostmanCollection(session=session)
        item = {
            "name": "Echo",
            "request": {
                "method": "GET",
                "url": {"raw": "https://example.test/echo"},
                "header": [],
            },
            "response": [{"code": 200, "body": '{"message":"expected"}'}],
        }

        result = runner.connection_test(item)

        self.assertFalse(result["passed"])
        self.assertFalse(result["assertions"][1]["passed"])

    def test_environment_variables_nested_folders_and_redaction_are_supported(self):
        session = Mock()
        session.request.return_value = self.response(
            200,
            json.dumps({"message": "ok", "access_token": "sensitive-token"}),
        )
        runner = PostmanCollection(session=session)
        collection = {
            "variable": [{"key": "host", "value": "collection.test"}],
            "item": [{
                "name": "Folder",
                "item": [{
                    "name": "Nested request",
                    "request": {
                        "method": "GET",
                        "url": {"raw": "https://{{host}}/echo?token=secret"},
                        "header": [],
                    },
                    "response": [{
                        "code": 200,
                        "body": json.dumps({
                            "message": "ok",
                            "access_token": "sensitive-token",
                        }),
                    }],
                }],
            }],
        }
        environment = {
            "values": [{"key": "host", "value": "environment.test", "enabled": True}],
        }

        result = runner.parse_collection(collection, environment=environment)[0]

        self.assertEqual("https://environment.test/echo?token=%5BREDACTED%5D", result["url"])
        self.assertEqual({"message": "ok", "access_token": "[REDACTED]"}, json.loads(result["response"]))
        self.assertEqual("https://environment.test/echo?token=secret", session.request.call_args.args[1])


if __name__ == "__main__":
    unittest.main()
