import os
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

import pendulum
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from gateway import GatewayClient, GatewayError
from weread_api import WeReadApi


class GatewayTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, {"WEREAD_API_KEY": "offline-test-value"}, clear=True)
        env.start()
        self.addCleanup(env.stop)

    def test_flat_parameters_and_version(self):
        client = GatewayClient()
        client.session = Mock()
        client.session.post.return_value = Mock(ok=True, status_code=200)
        client.session.post.return_value.json.return_value = {"books": []}
        self.assertEqual(client.request("/user/notebooks", count=100, lastSort=42), {"books": []})
        payload = client.session.post.call_args.kwargs["json"]
        self.assertEqual(payload, {"api_name": "/user/notebooks", "skill_version": "1.0.5", "count": 100, "lastSort": 42})

    def test_upgrade_stops_and_does_not_echo_server_message(self):
        client = GatewayClient()
        client.session = Mock()
        client.session.post.return_value = Mock(ok=True, status_code=200)
        client.session.post.return_value.json.return_value = {"upgrade_info": {"message": "private-response"}}
        with self.assertRaisesRegex(GatewayError, "升级") as error:
            client.request("/user/notebooks")
        self.assertNotIn("private-response", str(error.exception))
        self.assertEqual(client.session.post.call_count, 1)

    def test_transport_error_does_not_expose_credentials(self):
        client = GatewayClient()
        client.session = Mock()
        client.session.post.side_effect = requests.ConnectionError("offline-test-value")
        with patch("gateway.time.sleep"), self.assertRaises(GatewayError) as error:
            client.request("/shelf/sync")
        self.assertNotIn("offline-test-value", str(error.exception))
        self.assertEqual(client.session.post.call_count, 3)

    def test_notebook_pagination_and_cache(self):
        api = WeReadApi()
        api.request = Mock(side_effect=[
            {"books": [{"bookId": "new", "sort": 10}], "hasMore": 1},
            {"books": [{"bookId": "old", "sort": 5}], "hasMore": 0},
        ])
        self.assertEqual([book["bookId"] for book in api.get_notebooklist()], ["old", "new"])
        api.get_notebooklist()
        self.assertEqual(api.request.call_count, 2)
        self.assertEqual(api.request.call_args.kwargs, {"count": 100, "lastSort": 10})

    def test_non_advancing_notebook_cursor_fails(self):
        api = WeReadApi()
        api.request = Mock(return_value={"books": [{"sort": 10}], "hasMore": 1})
        with self.assertRaisesRegex(GatewayError, "游标"):
            api.get_notebooklist()

    def test_reviews_pagination_and_missing_chapter(self):
        api = WeReadApi()
        api.request = Mock(side_effect=[
            {"reviews": [{"review": {"reviewId": "one", "type": 4}}], "hasMore": 1, "synckey": 12},
            {"reviews": [{"review": {"reviewId": "two", "chapterUid": 7}}], "hasMore": 0},
        ])
        reviews = api.get_review_list("book")
        self.assertEqual([review["reviewId"] for review in reviews], ["one", "two"])
        self.assertEqual(reviews[0]["chapterUid"], 1000000)
        self.assertEqual(api.request.call_args.kwargs, {"bookid": "book", "synckey": 12, "count": 100})

    def test_progress_one_means_one_percent(self):
        api = WeReadApi()
        api.request = Mock(return_value={"book": {"progress": 1, "isStartReading": True}})
        result = api.get_read_info("book")
        self.assertEqual(result["readingProgress"], 1)
        self.assertEqual(result["markedStatus"], 2)
        self.assertNotIn("readingTime", result)

    def test_daily_history_uses_monthly_buckets_when_annual_is_monthly(self):
        api = WeReadApi()
        now = pendulum.datetime(2026, 2, 6, tz="Asia/Shanghai")
        jan = pendulum.datetime(2026, 1, 1, tz="Asia/Shanghai").int_timestamp
        feb = pendulum.datetime(2026, 2, 1, tz="Asia/Shanghai").int_timestamp
        api.request = Mock(side_effect=[
            {"readTimes": {str(jan): 9999}},
            {"readTimes": {str(jan): 9999}, "totalReadTime": 9999},
            {"readTimes": {str(jan): 60}},
            {"readTimes": {str(feb): 120}},
        ])
        with patch("weread_api.pendulum.now", return_value=now):
            result = api.get_api_data()["readTimes"]
        self.assertEqual(result, {str(jan): 60, str(feb): 120})
        self.assertEqual([call.kwargs["mode"] for call in api.request.call_args_list], ["overall", "annually", "monthly", "monthly"])

    def test_daily_history_uses_explicit_daily_detail(self):
        api = WeReadApi()
        now = pendulum.datetime(2026, 2, 6, tz="Asia/Shanghai")
        day = str(now.start_of("day").int_timestamp)
        api.request = Mock(side_effect=[
            {"readTimes": {day: 99}},
            {"dailyReadTimes": {day: 60}},
        ])
        with patch("weread_api.pendulum.now", return_value=now):
            self.assertEqual(api.get_api_data()["readTimes"], {day: 60})
        self.assertEqual(api.request.call_count, 2)

    def test_daily_bucket_outside_period_fails(self):
        api = WeReadApi()
        stamp = pendulum.datetime(2025, 1, 1, tz="Asia/Shanghai").int_timestamp
        with self.assertRaisesRegex(GatewayError, "周期"):
            api._daily_times({str(stamp): 60}, 2026)


if __name__ == "__main__":
    unittest.main()
