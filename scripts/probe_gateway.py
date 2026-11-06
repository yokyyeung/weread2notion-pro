"""Read-only gateway contract checks; no credentials or reading text in logs."""

import json

import pendulum

from gateway import GatewayClient


def describe(name, data):
    result = {"probe": name, "fields": sorted(data)}
    for key in ("books", "chapters", "updated", "reviews", "archive"):
        if isinstance(data.get(key), list):
            result[key + "_count"] = len(data[key])
            if data[key] and isinstance(data[key][0], dict):
                result[key + "_item_fields"] = sorted(data[key][0])
    for key in ("book", "readTimes", "dailyReadTimes"):
        if isinstance(data.get(key), dict):
            result[key + "_count"] = len(data[key])
            if key == "book":
                result[key + "_fields"] = sorted(data[key])
            elif data[key]:
                dates = [pendulum.from_timestamp(int(timestamp), tz="Asia/Shanghai").to_date_string()
                         for timestamp in data[key]]
                result[key + "_date_range"] = [min(dates), max(dates)]
    print(json.dumps(result))


if __name__ == "__main__":
    client = GatewayClient()
    shelf = client.request("/shelf/sync")
    describe("shelf", shelf)
    notebooks = client.request("/user/notebooks", count=100)
    describe("notebooks", notebooks)
    if notebooks.get("books"):
        book_id = notebooks["books"][0]["bookId"]
        for endpoint, parameters in [
            ("/book/info", {"bookId": book_id}),
            ("/book/getprogress", {"bookId": book_id}),
            ("/book/chapterinfo", {"bookId": book_id}),
            ("/book/bookmarklist", {"bookId": book_id}),
            ("/review/list/mine", {"bookid": book_id, "count": 100}),
        ]:
            describe(endpoint, client.request(endpoint, **parameters))
    for year in (2025, 2026):
        describe(f"annual_{year}", client.request("/readdata/detail", mode="annually",
                 baseTime=pendulum.datetime(year, 1, 1, tz="Asia/Shanghai").int_timestamp))
    describe("monthly", client.request("/readdata/detail", mode="monthly"))
    describe("overall", client.request("/readdata/detail", mode="overall"))
