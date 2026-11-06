"""Offline checks for legacy Notion compatibility and history preservation."""

import copy
import importlib.metadata
import os
import runpy
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

import httpx
from notion_client import Client


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
# Importing the application must never load a local .env or use real credentials.
with patch.dict(os.environ, {}, clear=True), patch("dotenv.load_dotenv"):
    import notion_helper
    import weread


def book_properties():
    properties = {
        name: {"type": "relation", "relation": {"database_id": f"db-{index}"}}
        for index, name in enumerate(
            ["读书笔记", "划线", "日", "周", "月", "年", "分类", "作者", "章节"]
        )
    }
    properties.update(
        {
            name: {"type": kind, kind: {}}
            for name, kind in {
                "阅读时长": "number",
                "书架分类": "select",
                "豆瓣链接": "url",
                "我的评分": "select",
                "豆瓣短评": "rich_text",
            }.items()
        }
    )
    return properties


class NotionCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.requests = []
        self.properties = book_properties()
        self.include_read_database = True
        self.env = patch.dict(
            os.environ,
            {
                "NOTION_TOKEN": "offline-test-token",
                "NOTION_PAGE": "00000000000000000000000000000001",
            },
            clear=True,
        )
        self.env.start()
        self.addCleanup(self.env.stop)
        # The application stores discovery results on the class; isolate each run.
        for name, value in {
            "database_id_dict": {},
            "property_dict": {},
            "database_name_dict": {
                "BOOK_DATABASE_NAME": "书架",
                "CHAPTER_DATABASE_NAME": "章节",
                "READ_DATABASE_NAME": "阅读记录",
            },
            "heatmap_block_id": None,
        }.items():
            patcher = patch.object(notion_helper.NotionHelper, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.http_client = httpx.Client(
            transport=httpx.MockTransport(self.respond), trust_env=False
        )
        self.addCleanup(self.http_client.close)
        client_factory = patch.object(
            notion_helper,
            "Client",
            side_effect=lambda **kwargs: Client(client=self.http_client, **kwargs),
        )
        client_factory.start()
        self.addCleanup(client_factory.stop)

    def respond(self, request):
        self.requests.append(request)
        path = request.url.path
        if request.method == "GET" and path.endswith("/children"):
            children = [
                {
                    "id": "book-db",
                    "type": "child_database",
                    "child_database": {"title": "书架"},
                    "has_children": False,
                }
            ]
            if self.include_read_database:
                children.append(
                    {
                        "id": "read-db",
                        "type": "child_database",
                        "child_database": {"title": "阅读记录"},
                        "has_children": False,
                    }
                )
            return httpx.Response(200, json={"results": children, "has_more": False})
        if request.method == "GET" and path == "/v1/databases/book-db":
            result = {"id": "book-db", "object": "database"}
            if request.headers.get("Notion-Version") == "2022-06-28":
                result["properties"] = self.properties
            return httpx.Response(200, json=result)
        if request.method == "POST" and path == "/v1/databases/book-db/query":
            return httpx.Response(200, json={"results": [], "has_more": False})
        self.fail(f"Unexpected request, including any schema write: {request.method} {path}")

    def assert_no_schema_write(self):
        self.assertTrue(self.requests)
        self.assertTrue(all(request.method == "GET" for request in self.requests))

    def test_pinned_sdk_retrieve_and_query_use_legacy_api(self):
        self.assertEqual(importlib.metadata.version("notion-client"), "2.5.0")
        helper = notion_helper.NotionHelper()
        self.assertEqual(helper.read_database_id, "read-db")
        self.assertEqual(helper.property_dict["阅读时长"]["type"], "number")
        self.assertEqual(helper.query(database_id="book-db")["results"], [])
        self.assertTrue(
            any(
                request.method == "GET" and request.url.path == "/v1/databases/book-db"
                for request in self.requests
            )
        )
        self.assertEqual(self.requests[-1].url.path, "/v1/databases/book-db/query")
        for request in self.requests:
            self.assertEqual(request.headers["Notion-Version"], "2022-06-28")

    def test_missing_property_stops_without_changing_schema(self):
        del self.properties["阅读时长"]
        with self.assertRaisesRegex(RuntimeError, "阅读时长"):
            notion_helper.NotionHelper()
        self.assert_no_schema_write()

    def test_wrong_property_type_stops_without_changing_schema(self):
        self.properties["阅读时长"] = {"type": "rich_text", "rich_text": {}}
        with self.assertRaisesRegex(RuntimeError, "阅读时长"):
            notion_helper.NotionHelper()
        self.assert_no_schema_write()

    def test_missing_read_database_stops_without_creating_database(self):
        self.include_read_database = False
        with self.assertRaisesRegex(RuntimeError, "阅读记录"):
            notion_helper.NotionHelper()
        self.assert_no_schema_write()


def history_row(item_id, block_id, id_property):
    return {
        "id": f"row-{item_id}",
        "properties": {
            id_property: {"rich_text": [{"plain_text": item_id}]},
            "blockId": {"rich_text": [{"plain_text": block_id}]},
        },
    }


class HistoryPreservationTests(unittest.TestCase):
    def test_shared_shelf_sort_does_not_skip_independent_notes(self):
        helper = Mock()
        helper.get_all_book.return_value = {"book-id": {"pageId": "book-page", "Sort": 42}}
        api = Mock()
        api.get_notebooklist.return_value = [{"bookId": "book-id", "book": {"title": "Offline book"}, "sort": 42}]
        api.get_chapter_info.side_effect = RuntimeError("entered-independent-note-sync")
        with patch.dict(os.environ, {"REF": "refs/heads/main", "REPOSITORY": "offline/repo"}, clear=True), patch("sys.argv", ["weread.py"]), patch("notion_helper.NotionHelper", return_value=helper), patch("weread_api.WeReadApi", return_value=api):
            with self.assertRaisesRegex(RuntimeError, "entered-independent-note-sync"):
                runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts/weread.py"), run_name="__main__")
        api.get_chapter_info.assert_called_once_with("book-id")
        helper.delete_block.assert_not_called()

    def check_remote_notes(self, function_name, id_property, database_attribute):
        for incoming in [[], [{id_property: "keep"}, {id_property: "new"}]]:
            with self.subTest(incoming=incoming):
                helper = Mock()
                setattr(helper, database_attribute, "notes-db")
                helper.query_all_by_book.return_value = [
                    history_row("keep", "keep-block", id_property),
                    history_row("missing-remotely", "old-block", id_property),
                ]
                api = Mock()
                getattr(api, function_name).return_value = copy.deepcopy(incoming)
                with patch.object(weread, "notion_helper", helper, create=True), patch.object(
                    weread, "weread_api", api, create=True
                ):
                    result = getattr(weread, function_name)("book-page", "book-id")
                helper.delete_block.assert_not_called()
                self.assertEqual([item[id_property] for item in result], [item[id_property] for item in incoming])
                if result:
                    self.assertEqual(result[0]["blockId"], "keep-block")
                    self.assertNotIn("blockId", result[1])

    def test_bookmarks_keep_history_and_reuse_existing_blocks(self):
        self.check_remote_notes("get_bookmark_list", "bookmarkId", "bookmark_database_id")

    def test_reviews_keep_history_and_reuse_existing_blocks(self):
        self.check_remote_notes("get_review_list", "reviewId", "review_database_id")

    def test_chapters_keep_history_and_reuse_existing_blocks(self):
        for incoming in [[], [{"chapterUid": 10}, {"chapterUid": 30}]]:
            with self.subTest(incoming=incoming):
                helper = Mock(chapter_database_id="chapters-db")
                helper.query_all_by_book.return_value = [
                    {
                        "id": f"row-{uid}",
                        "properties": {
                            "chapterUid": {"number": uid},
                            "blockId": {"rich_text": [{"plain_text": f"chapter-{uid}"}]},
                        },
                    }
                    for uid in [10, 20]
                ]
                chapters = {
                    10: {"chapterUid": 10, "title": "Existing chapter"},
                    30: {"chapterUid": 30, "title": "New chapter"},
                }
                with patch.object(weread, "notion_helper", helper, create=True):
                    result = weread.sort_notes("book-page", chapters, copy.deepcopy(incoming))
                helper.delete_block.assert_not_called()
                if incoming:
                    self.assertEqual(len(result), 4)
                    self.assertEqual(result[0]["blockId"], "chapter-10")
                    self.assertEqual(result[1], incoming[0])
                    self.assertEqual(result[2]["title"], "New chapter")
                    self.assertNotIn("blockId", result[2])
                    self.assertEqual(result[3], incoming[1])
                else:
                    self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
