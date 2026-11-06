"""Read-only probes. Never print request headers, cookies or response contents."""

import json
from requests.cookies import RequestsCookieJar

from weread_api import WeReadApi


if __name__ == "__main__":
    api = WeReadApi()
    names = {cookie.name for cookie in api.session.cookies}
    print(json.dumps({"required_cookie_fields": {
        name: name in names for name in ("wr_vid", "wr_skey", "wr_rt")
    }}))
    api.session.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Referer": "https://weread.qq.com/",
        "Origin": "https://weread.qq.com",
    })
    # Domain-scoped cookies prevent stale unscoped duplicates after renewal.
    jar = RequestsCookieJar()
    for cookie in api.session.cookies:
        jar.set(cookie.name, cookie.value, domain=".weread.qq.com", path="/")
    api.session.cookies = jar
    try:
        response = api.session.post(
            "https://weread.qq.com/web/login/renewal",
            json={"rq": "%2Fweb%2Fbook%2Fread", "ql": False},
            timeout=20,
        )
        data = response.json()
        print(json.dumps({"probe": "web_renewal", "http_status": response.status_code,
                          "renewed": data.get("succ") == 1,
                          "error_code": data.get("errcode", data.get("errCode"))
                          if isinstance(data.get("errcode", data.get("errCode")), (int, type(None))) else "non-numeric"}))
    except Exception as error:
        print(json.dumps({"probe": "web_renewal", "exception_type": type(error).__name__}))
    probes = [
        ("legacy_notebooks", "https://i.weread.qq.com/user/notebooks"),
        ("web_notebooks", "https://weread.qq.com/web/user/notebooks"),
        ("legacy_summary", "https://i.weread.qq.com/readdata/summary?synckey=0"),
        ("web_summary", "https://weread.qq.com/web/readdata/summary?synckey=0"),
        ("web_book", "https://weread.qq.com/web/book/info?bookId=855812"),
    ]
    for name, url in probes:
        try:
            response = api.session.get(url, timeout=20, allow_redirects=False)
            result = {"probe": name, "http_status": response.status_code}
            try:
                data = response.json()
                if isinstance(data, dict):
                    code = data.get("errcode", data.get("errCode"))
                    result["error_code"] = code if isinstance(code, (int, type(None))) else "non-numeric"
                    result["has_books"] = isinstance(data.get("books"), list)
                    result["has_read_times"] = isinstance(data.get("readTimes"), dict)
                    result["has_title"] = isinstance(data.get("title"), str)
                else:
                    result["json_object"] = False
            except ValueError:
                result["json_response"] = False
            print(json.dumps(result))
        except Exception as error:
            print(json.dumps({"probe": name, "exception_type": type(error).__name__}))
