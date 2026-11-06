"""Verify live Notion dates and public SVG; never print credentials or note text."""

import json
from urllib.parse import parse_qs, urlparse
import xml.etree.ElementTree as ET

import pendulum
import requests

from gateway import GatewayClient
from notion_helper import NotionHelper
from read_time import duration_seconds
from weread_api import WeReadApi


if __name__ == "__main__":
    helper = NotionHelper()
    schema = helper.client.databases.retrieve(database_id=helper.day_database_id)["properties"]
    print(json.dumps({"verification": "day_duration_schema", "type": schema["时长"]["type"]}))
    for label, attribute, date_property in (
        ("reviews", "review_database_id", "Date"),
        ("highlights", "bookmark_database_id", "Date"),
        ("days", "day_database_id", "日期"),
        ("weeks", "week_database_id", "日期"),
        ("months", "month_database_id", "日期"),
        ("years", "year_database_id", "日期"),
    ):
        data = helper.query(database_id=getattr(helper, attribute), page_size=1,
                            sorts=[{"property": date_property, "direction": "descending"}])
        rows = data["results"]
        latest = ((rows[0]["properties"][date_property].get("date") or {}).get("start")
                  if rows else None)
        print(json.dumps({"verification": label, "latest_date": latest}))

    today = pendulum.now("Asia/Shanghai").start_of("day")
    source = GatewayClient().request("/readdata/detail", mode="monthly")
    expected = source.get("readTimes", {}).get(str(today.int_timestamp), 0)
    rows = helper.query(database_id=helper.day_database_id,
                        filter={"property": "时间戳", "number": {"equals": today.int_timestamp}})["results"]
    print(json.dumps({"verification": "today_duration", "date": today.to_date_string(),
                      "matching_rows": len(rows),
                      "matches_source": len(rows) == 1 and duration_seconds(rows[0]["properties"]["时长"]) == expected}))

    if not helper.heatmap_block_id:
        raise RuntimeError("未找到 Notion 热力图嵌入块。")
    block = helper.client.blocks.retrieve(block_id=helper.heatmap_block_id)
    image_url = parse_qs(urlparse(block["embed"]["url"]).query).get("image", [""])[0]
    parsed = urlparse(image_url)
    if parsed.scheme != "https" or parsed.netloc != "raw.githubusercontent.com" or not parsed.path.startswith("/yokyyeung/weread2notion-pro/main/OUT_FOLDER/"):
        raise RuntimeError("Notion 热力图未指向 Pro 仓库发布的 SVG。")
    response = requests.get(image_url, timeout=30)
    response.raise_for_status()
    root = ET.fromstring(response.content)
    titles = [node.text or "" for node in root.iter("{http://www.w3.org/2000/svg}title")]
    print(json.dumps({"verification": "heatmap", "embed_points_to_published_svg": True,
                      "svg_file": parsed.path.rsplit("/", 1)[-1],
                      "reading_cells_2025": sum(title.startswith("2025-") and len(title) > 10 for title in titles),
                      "reading_cells_2026": sum(title.startswith("2026-") and len(title) > 10 for title in titles)}))

    # Latest dates alone cannot distinguish a stale sync from no new source data.
    api = WeReadApi()
    source_ids = set()
    latest = None
    for book in api.get_notebooklist():
        for note in api.get_bookmark_list(book["bookId"]):
            source_ids.add(str(note["bookmarkId"]))
            if note.get("createTime"):
                latest = max(latest or 0, int(note["createTime"]))
    notion_ids = set()
    for row in helper.query_all(helper.bookmark_database_id):
        value = "".join(part.get("plain_text", "") for part in row["properties"]["bookmarkId"]["rich_text"])
        if value:
            notion_ids.add(value)
    missing = source_ids - notion_ids
    print(json.dumps({"verification": "highlight_source_coverage",
                      "source_highlights": len(source_ids), "missing_in_notion": len(missing),
                      "source_latest_date": pendulum.from_timestamp(latest, tz="Asia/Shanghai").to_date_string() if latest else None}))
    if missing:
        raise RuntimeError("存在尚未同步到独立数据库的划线；未完成验收。")
