"""
日本关税表下载：Japan Customs 官方英文版关税表（HTML，按章分文件）。

来源：https://www.customs.go.jp/english/tariff/{edition}/data/e_{NN}.htm
（edition 形如 2026_08_08，官方季度滚动更新）
列结构：CSTNO(6位码) | HSCODE(国别后缀) | ITEM_NAME | General | Temporary |
WTO(括号) | 17 个 EPA 列 | …

用法：
    python -m src.ingest.download_tariff_jp            # 下载全部章 → data/raw/tariff_jp/
    python -m src.ingest.download_tariff_jp latest      # 只打印最新 edition
"""
import re
import sys
import time
from pathlib import Path

import requests

from config import DATA_RAW

INDEX = "https://www.customs.go.jp/english/tariff/"
RAW = DATA_RAW / "tariff_jp"
H = {"User-Agent": "Mozilla/5.0"}
# HS 只有 1-97 章（77 保留）
CHAPTERS = [f"{c:02d}" for c in range(1, 98) if c != 77]


def latest_edition() -> str:
    r = requests.get(INDEX, timeout=20, headers=H)
    r.raise_for_status()
    eds = re.findall(r"/english/tariff/(\d{4}_\d{2}_\d{2})/", r.text)
    if not eds:
        raise RuntimeError("edition 未找到")
    # 日期字符串排序即时间序
    return max(eds)


def download(edition: str | None = None) -> None:
    ed = edition or latest_edition()
    RAW.mkdir(parents=True, exist_ok=True)
    (RAW / "edition.txt").write_text(ed, encoding="utf-8")
    print(f"edition: {ed}")
    for ch in CHAPTERS:
        out = RAW / f"e_{ch}.htm"
        if out.exists() and out.stat().st_size > 10000:
            continue
        url = f"{INDEX}{ed}/data/e_{ch}.htm"
        for attempt in range(3):
            try:
                r = requests.get(url, timeout=60, headers=H)
                if r.status_code == 404:
                    print(f"  e_{ch}: 404（该章可能为空），跳过")
                    break
                r.raise_for_status()
                out.write_bytes(r.content)
                print(f"  e_{ch}: {len(r.content)//1024} KB")
                break
            except Exception as e:  # noqa: BLE001
                print(f"  e_{ch} attempt{attempt+1} FAIL: {type(e).__name__}")
                time.sleep(5 * (attempt + 1))
        time.sleep(1)  # 礼貌限速
    print("done →", RAW)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "latest":
        print(latest_edition())
    else:
        download(sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] != "all" else None)
