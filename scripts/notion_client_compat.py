"""Pace the legacy SDK and honor Notion's rate-limit Retry-After header."""

import json
import random
import time

from notion_client import Client as NotionClient
from notion_client.errors import HTTPResponseError


class Client(NotionClient):
    _next_request_at = 0

    def request(self, *args, **kwargs):
        for attempt in range(6):
            delay = self._next_request_at - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            self._next_request_at = time.monotonic() + 0.4
            try:
                return super().request(*args, **kwargs)
            except HTTPResponseError as error:
                if error.status not in (429, 529) or attempt == 5:
                    raise
                try:
                    extra = json.loads(error.body).get("additional_data", {})
                except (ValueError, AttributeError):
                    extra = {}
                if extra.get("rate_limit_reason") == "public_api_request_blocked":
                    raise
                try:
                    delay = float(error.headers.get("Retry-After", min(2 ** attempt, 30)))
                except ValueError:
                    delay = min(2 ** attempt, 30)
                self._next_request_at = time.monotonic() + max(0, delay) + random.uniform(0, 0.25)
