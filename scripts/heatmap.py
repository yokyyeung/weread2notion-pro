"""Use the existing Cookie API with github-heatmap's JSON renderer."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import pendulum

from weread_api import WeReadApi


def heatmap_years(configured, current_year):
    """Keep the configured history and include the current year after rollover."""
    if not configured or configured == "all":
        return configured or str(current_year)
    years = [int(year) for year in configured.split("-")]
    if len(years) not in (1, 2) or min(years) < 1 or years[-1] < years[0]:
        raise ValueError("YEAR must be a year, a year range, or all")
    return f"{min(years[0], current_year)}-{max(years[-1], current_year)}"


def generate_heatmap(api, arguments):
    data = api.get_api_data()
    if not isinstance(data.get("readTimes"), dict) or data.get("errcode", 0):
        raise RuntimeError("微信读书未返回阅读记录；请在 GitHub Secrets 更新 WEREAD_COOKIE。")
    tracks = {
        pendulum.from_timestamp(int(timestamp), tz="Asia/Shanghai").to_date_string():
        round(duration / 60.0, 2)
        for timestamp, duration in data["readTimes"].items()
    }
    output = Path("OUT_FOLDER/json.svg")
    output.unlink(missing_ok=True)
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "reading.json"
        path.write_text(json.dumps(tracks), encoding="utf-8")
        subprocess.run(
            ["github_heatmap", "json", "--json_file", str(path), "--unit", "mins",
             "--year", heatmap_years(os.getenv("YEAR", ""), pendulum.now("Asia/Shanghai").year),
             *arguments],
            check=True,
        )
    if not output.is_file() or output.stat().st_size == 0:
        raise RuntimeError("热力图生成失败：没有生成有效的 SVG 文件。")
    output.replace("OUT_FOLDER/weread.svg")


if __name__ == "__main__":
    generate_heatmap(WeReadApi(), sys.argv[1:])
