import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from notion_client_compat import Client
from notion_client.errors import APIResponseError


class RateLimitTests(unittest.TestCase):
    def run_responses(self, responses):
        seen = []
        def respond(request):
            seen.append(request)
            return responses[min(len(seen) - 1, len(responses) - 1)]
        http = httpx.Client(transport=httpx.MockTransport(respond), trust_env=False)
        self.addCleanup(http.close)
        return Client(auth="offline-token", client=http, notion_version="2022-06-28"), seen

    def test_retry_after_waits_before_retrying_rejected_create(self):
        client, seen = self.run_responses([
            httpx.Response(429, headers={"Retry-After": "12"}, json={"code": "rate_limited", "message": "wait"}),
            httpx.Response(200, json={"id": "new-page"}),
        ])
        with patch("notion_client_compat.time.monotonic", return_value=100), patch("notion_client_compat.time.sleep") as sleep, patch("notion_client_compat.random.uniform", return_value=0):
            result = client.pages.create(parent={"database_id": "db"}, properties={})
        self.assertEqual(result["id"], "new-page")
        self.assertEqual(len(seen), 2)
        sleep.assert_called_once_with(12)

    def test_bad_request_is_not_retried(self):
        client, seen = self.run_responses([httpx.Response(400, json={"code": "validation_error", "message": "bad property"})])
        with self.assertRaises(APIResponseError):
            client.pages.create(parent={"database_id": "db"}, properties={})
        self.assertEqual(len(seen), 1)

    def test_blocked_api_is_not_retried(self):
        client, seen = self.run_responses([httpx.Response(429, json={"code": "rate_limited", "message": "blocked", "additional_data": {"rate_limit_reason": "public_api_request_blocked"}})])
        with self.assertRaises(APIResponseError):
            client.databases.query(database_id="db")
        self.assertEqual(len(seen), 1)

    def test_rate_limit_retries_are_bounded(self):
        client, seen = self.run_responses([httpx.Response(429, headers={"Retry-After": "0"}, json={"code": "rate_limited", "message": "wait"})])
        with patch("notion_client_compat.time.sleep"), self.assertRaises(APIResponseError):
            client.databases.query(database_id="db")
        self.assertEqual(len(seen), 6)

    def test_write_server_error_is_not_blindly_replayed(self):
        client, seen = self.run_responses([httpx.Response(503, json={"code": "service_unavailable", "message": "unknown write state"})])
        with self.assertRaises(APIResponseError):
            client.pages.create(parent={"database_id": "db"}, properties={})
        self.assertEqual(len(seen), 1)
