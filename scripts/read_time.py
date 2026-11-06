import argparse
from datetime import datetime
from datetime import timedelta
import json
import os
import re
import time

import pendulum

from notion_helper import NotionHelper
from weread_api import WeReadApi
from utils import (
    format_date,
    get_date,
    get_icon,
    get_number,
    get_relation,
    get_title,
    get_embed,
    get_rich_text,
)


def duration_property(seconds, property_type):
    if property_type == "number":
        return get_number(seconds)
    if property_type == "rich_text":
        hours, remainder = divmod(seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        text = (f"{hours:g}时" if hours else "") + (f"{minutes:g}分" if minutes else "")
        text += f"{seconds:g}秒" if seconds or not text else ""
        return get_rich_text(text)
    raise RuntimeError("日统计的时长字段必须是 number 或 rich_text；未更改数据库结构。")


def duration_seconds(property):
    if property["type"] == "number":
        return property.get("number")
    if property["type"] != "rich_text":
        raise RuntimeError("日统计时长字段类型不受支持。")
    text = "".join(item.get("plain_text", item.get("text", {}).get("content", ""))
                   for item in property["rich_text"]).strip()
    if not text:
        return 0
    if re.fullmatch(r"\d+(?:\.\d+)?", text):
        return float(text)
    match = re.fullmatch(r"(?:(\d+(?:\.\d+)?)(?:小时|时))?(?:(\d+(?:\.\d+)?)(?:分钟|分))?(?:(\d+(?:\.\d+)?)(?:秒钟|秒))?", text)
    if not match:
        raise RuntimeError("日统计存在无法识别的时长文本；停止同步以保留原值。")
    return sum(float(value or 0) * scale for value, scale in zip(match.groups(), (3600, 60, 1)))


def insert_to_notion(page_id, timestamp, duration):
    parent = {"database_id": notion_helper.day_database_id, "type": "database_id"}
    properties = {
        "标题": get_title(
            format_date(
                datetime.utcfromtimestamp(timestamp) + timedelta(hours=8),
                "%Y年%m月%d日",
            )
        ),
        "日期": get_date(
            start=format_date(datetime.utcfromtimestamp(timestamp) + timedelta(hours=8))
        ),
        "时长": duration_property(duration, duration_type),
        "时间戳": get_number(timestamp),
        "年": get_relation(
            [
                notion_helper.get_year_relation_id(
                    datetime.utcfromtimestamp(timestamp) + timedelta(hours=8)
                ),
            ]
        ),
        "月": get_relation(
            [
                notion_helper.get_month_relation_id(
                    datetime.utcfromtimestamp(timestamp) + timedelta(hours=8)
                ),
            ]
        ),
        "周": get_relation(
            [
                notion_helper.get_week_relation_id(
                    datetime.utcfromtimestamp(timestamp) + timedelta(hours=8)
                ),
            ]
        ),
    }
    if page_id != None:
        notion_helper.client.pages.update(page_id=page_id, properties=properties)
    else:
        notion_helper.client.pages.create(
            parent=parent,
            icon=get_icon("https://www.notion.so/icons/target_red.svg"),
            properties=properties,
        )


def get_file():
    # 设置文件夹路径
    folder_path = "./OUT_FOLDER"

    # 检查文件夹是否存在
    if os.path.exists(folder_path) and os.path.isdir(folder_path):
        entries = os.listdir(folder_path)

        file_name = entries[0] if entries else None
        return file_name
    else:
        print("OUT_FOLDER does not exist.")
        return None

HEATMAP_GUIDE = "https://mp.weixin.qq.com/s?__biz=MzI1OTcxOTI4NA==&mid=2247484145&idx=1&sn=81752852420b9153fc292b7873217651&chksm=ea75ebeadd0262fc65df100370d3f983ba2e52e2fcde2deb1ed49343fbb10645a77570656728&token=157143379&lang=zh_CN#rd"
if __name__ == "__main__":
    notion_helper = NotionHelper()
    duration_type = notion_helper.client.databases.retrieve(
        database_id=notion_helper.day_database_id)["properties"]["时长"]["type"]
    duration_property(0, duration_type)
    weread_api = WeReadApi()
    image_file = get_file()
    if image_file:
        image_url = f"https://raw.githubusercontent.com/{os.getenv('REPOSITORY')}/{os.getenv('REF').split('/')[-1]}/OUT_FOLDER/{image_file}"
        heatmap_url = f"https://heatmap.malinkang.com/?image={image_url}"
        if notion_helper.heatmap_block_id:
            response = notion_helper.update_heatmap(
                block_id=notion_helper.heatmap_block_id, url=heatmap_url
            )
        else:
            raise RuntimeError(f"更新热力图失败，没有添加热力图占位。具体参考：{HEATMAP_GUIDE}")
    else:
        raise RuntimeError(f"更新热力图失败，没有生成热力图。具体参考：{HEATMAP_GUIDE}")
    api_data = weread_api.get_api_data()
    readTimes = {int(key): value for key, value in api_data.get("readTimes").items()}
    now = pendulum.now("Asia/Shanghai").start_of("day")
    today_timestamp = now.int_timestamp
    if today_timestamp not in readTimes:
        readTimes[today_timestamp] = 0
    readTimes = dict(sorted(readTimes.items()))
    results = notion_helper.query_all(database_id=notion_helper.day_database_id)
    for result in results:
        stored_timestamp = result.get("properties").get("时间戳").get("number")
        date = (result["properties"]["日期"].get("date") or {}).get("start")
        timestamp = (pendulum.parse(date, tz="Asia/Shanghai").in_timezone("Asia/Shanghai").start_of("day").int_timestamp
                     if date else stored_timestamp)
        duration = duration_seconds(result["properties"]["时长"])
        id = result.get("id")
        if timestamp in readTimes:
            value = readTimes.pop(timestamp)
            if value != duration or timestamp != stored_timestamp:
                insert_to_notion(page_id=id, timestamp=timestamp, duration=value)
    for key, value in readTimes.items():
        insert_to_notion(None, int(key), value)
