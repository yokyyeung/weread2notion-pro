"""Adapt the official WeRead Gateway to the existing Pro sync interface."""

import hashlib
import os
import re

import pendulum

from gateway import GatewayClient, GatewayError


class WeReadApi(GatewayClient):
    def __init__(self):
        super().__init__()
        self._shelf = None
        self._notebooks = None

    @staticmethod
    def _list(data, name):
        value = data.get(name)
        if not isinstance(value, list):
            raise GatewayError(f"微信读书返回缺少列表字段：{name}")
        return value

    def get_bookshelf(self):
        if self._shelf is None:
            self._shelf = self.request("/shelf/sync")
            self._list(self._shelf, "books")
        return self._shelf

    def get_notebooklist(self):
        if self._notebooks is not None:
            return self._notebooks
        books, cursor, seen = [], None, set()
        while True:
            parameters = {"count": 100}
            if cursor is not None:
                parameters["lastSort"] = cursor
            data = self.request("/user/notebooks", **parameters)
            batch = self._list(data, "books")
            books.extend(batch)
            if not data.get("hasMore"):
                break
            next_cursor = batch[-1].get("sort") if batch else None
            if next_cursor is None or next_cursor in seen:
                raise GatewayError("笔记本分页游标未前进，同步已停止以避免漏数据。")
            seen.add(next_cursor)
            cursor = next_cursor
        self._notebooks = sorted(books, key=lambda book: book.get("sort") or 0)
        return self._notebooks

    def get_bookinfo(self, bookId):
        return self.request("/book/info", bookId=bookId)

    def get_bookmark_list(self, bookId):
        return self._list(self.request("/book/bookmarklist", bookId=bookId), "updated")

    def get_read_info(self, bookId):
        data = self.request("/book/getprogress", bookId=bookId)
        book = data.get("book")
        if not isinstance(book, dict):
            raise GatewayError("微信读书未返回书籍阅读进度。")
        result = {}
        if "progress" in book:
            progress = book["progress"]
            if not isinstance(progress, (int, float)) or not 0 <= progress <= 100:
                raise GatewayError("微信读书返回了无效阅读进度。")
            result["readingProgress"] = progress
            result["markedStatus"] = 4 if progress == 100 else 2 if book.get("isStartReading") or progress else 1
        for source, target in (("recordReadingTime", "readingTime"),
                               ("finishTime", "finishedDate"), ("updateTime", "lastReadingDate")):
            if source in book:
                result[target] = book[source]
        return result

    def get_review_list(self, bookId):
        reviews, cursor, seen = [], 0, set()
        while True:
            data = self.request("/review/list/mine", bookid=bookId, synckey=cursor, count=100)
            batch = self._list(data, "reviews")
            for item in batch:
                review = item.get("review")
                if not isinstance(review, dict) or not review.get("reviewId"):
                    raise GatewayError("微信读书返回了无效个人笔记。")
                review = {"bookId": bookId, **review}
                if review.get("type") == 4 or review.get("chapterUid") is None:
                    review["chapterUid"] = 1000000
                reviews.append(review)
            if not data.get("hasMore"):
                break
            next_cursor = data.get("synckey")
            if next_cursor is None or next_cursor == cursor or next_cursor in seen:
                raise GatewayError("个人笔记分页游标未前进，同步已停止以避免漏数据。")
            seen.add(next_cursor)
            cursor = next_cursor
        return reviews

    def get_chapter_info(self, bookId):
        data = self.request("/book/chapterinfo", bookId=bookId)
        chapters = self._list(data, "chapters")
        result = {chapter["chapterUid"]: chapter for chapter in chapters}
        result[1000000] = {"chapterUid": 1000000, "chapterIdx": 1000000,
                           "title": "点评", "level": 1}
        return result

    @staticmethod
    def _daily_times(values, year, month=None):
        if not isinstance(values, dict):
            raise GatewayError("微信读书未返回每日阅读时长。")
        result = {}
        for timestamp, duration in values.items():
            day = pendulum.from_timestamp(int(timestamp), tz="Asia/Shanghai")
            if day.year != year or (month is not None and day.month != month):
                raise GatewayError("阅读时长分桶超出请求周期，停止写入以保护历史数据。")
            if day != day.start_of("day") or isinstance(duration, bool) or not isinstance(duration, (int, float)) or duration < 0:
                raise GatewayError("每日阅读时长的日期或秒数无效。")
            if day <= pendulum.now("Asia/Shanghai"):
                result[str(day.int_timestamp)] = duration
        return result

    def get_api_data(self):
        overall = self.request("/readdata/detail", mode="overall")
        current = pendulum.now("Asia/Shanghai")
        origins = [pendulum.from_timestamp(int(timestamp), tz="Asia/Shanghai").year
                   for timestamp in (overall.get("readTimes") or {})]
        if overall.get("registTime"):
            origins.append(pendulum.from_timestamp(overall["registTime"], tz="Asia/Shanghai").year)
        configured = os.getenv("YEAR", "").split("-")[0]
        if configured.isdigit():
            origins.append(int(configured))
        if not origins:
            raise GatewayError("无法确定阅读历史起点，停止同步以避免漏数据。")
        first_year = min(origins)
        if not 2000 <= first_year <= current.year:
            raise GatewayError("阅读历史起点无效。")
        read_times = {}
        for year in range(first_year, current.year + 1):
            annual = self.request("/readdata/detail", mode="annually",
                                  baseTime=pendulum.datetime(year, 1, 1, tz="Asia/Shanghai").int_timestamp)
            daily = annual.get("dailyReadTimes")
            if isinstance(daily, dict) and (daily or annual.get("totalReadTime") == 0):
                read_times.update(self._daily_times(daily, year))
                continue
            last_month = current.month if year == current.year else 12
            for month in range(1, last_month + 1):
                data = self.request("/readdata/detail", mode="monthly",
                                    baseTime=pendulum.datetime(year, month, 1, tz="Asia/Shanghai").int_timestamp)
                read_times.update(self._daily_times(data.get("readTimes"), year, month))
        return {"readTimes": read_times}

    def transform_id(self,book_id):
        id_length = len(book_id)
        if re.match("^\d*$", book_id):
            ary = []
            for i in range(0, id_length, 9):
                ary.append(format(int(book_id[i : min(i + 9, id_length)]), "x"))
            return "3", ary

        result = ""
        for i in range(id_length):
            result += format(ord(book_id[i]), "x")
        return "4", [result]


    def calculate_book_str_id(self,book_id):
        md5 = hashlib.md5()
        md5.update(book_id.encode("utf-8"))
        digest = md5.hexdigest()
        result = digest[0:3]
        code, transformed_ids = self.transform_id(book_id)
        result += code + "2" + digest[-2:]

        for i in range(len(transformed_ids)):
            hex_length_str = format(len(transformed_ids[i]), "x")
            if len(hex_length_str) == 1:
                hex_length_str = "0" + hex_length_str

            result += hex_length_str + transformed_ids[i]

            if i < len(transformed_ids) - 1:
                result += "g"

        if len(result) < 20:
            result += digest[0 : 20 - len(result)]

        md5 = hashlib.md5()
        md5.update(result.encode("utf-8"))
        result += md5.hexdigest()[0:3]
        return result
    def get_url(self,book_id):
        return f"https://weread.qq.com/web/reader/{self.calculate_book_str_id(book_id)}"
