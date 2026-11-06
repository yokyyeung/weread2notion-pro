import unittest
from pathlib import Path
import sys
from datetime import datetime
from unittest.mock import Mock

import pendulum

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from read_time import duration_property, duration_seconds
from notion_helper import NotionHelper


class DurationTests(unittest.TestCase):
    def test_aware_and_naive_dates_share_one_shanghai_day(self):
        for date in (datetime(2026, 11, 6, 20, 0), pendulum.datetime(2026, 11, 6, 20, tz="Asia/Shanghai")):
            helper = object.__new__(NotionHelper)
            helper.get_relation_id = Mock(return_value="day")
            helper.get_year_relation_id = Mock(return_value="year")
            helper.get_month_relation_id = Mock(return_value="month")
            helper.get_week_relation_id = Mock(return_value="week")
            helper.day_database_id = "day-db"
            helper.get_day_relation_id(date)
            props = helper.get_relation_id.call_args.args[3]
            self.assertEqual(props["时间戳"]["number"], pendulum.datetime(2026, 11, 6, tz="Asia/Shanghai").int_timestamp)
            self.assertEqual(props["日期"]["date"]["start"], "2026-11-06 00:00:00")

    def test_round_trip_text_seconds(self):
        for seconds in (0, 1, 59, 60, 3661, 7200, 1.5):
            with self.subTest(seconds=seconds):
                property = {"type": "rich_text", **duration_property(seconds, "rich_text")}
                self.assertEqual(duration_seconds(property), seconds)

    def test_existing_number_schema(self):
        property = {"type": "number", **duration_property(3661, "number")}
        self.assertEqual(duration_seconds(property), 3661)

    def test_existing_text_formats(self):
        for text, expected in (("1小时2分钟3秒", 3723), ("1时2分", 3720), ("120", 120), ("", 0)):
            with self.subTest(text=text):
                self.assertEqual(duration_seconds({"type": "rich_text", "rich_text": [{"plain_text": text}]}), expected)

    def test_unknown_text_stops_without_overwriting(self):
        with self.assertRaisesRegex(RuntimeError, "保留原值"):
            duration_seconds({"type": "rich_text", "rich_text": [{"plain_text": "manual note"}]})

    def test_read_only_property_types_are_not_modified(self):
        with self.assertRaises(RuntimeError):
            duration_property(60, "formula")
