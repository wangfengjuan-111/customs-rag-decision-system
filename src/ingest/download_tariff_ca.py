"""
加拿大关税表下载：CBSA 官方 HTML 章节页。

来源：https://www.cbsa-asfc.gc.ca/trade-commerce/tariff-tarif/{year}/html/00/ch{NN}-eng.html
（CBSA Customs Tariff HTML 版；accdb 版在 01-99-*-eng.zip，纯 Python 解析器不完整故走 HTML）
列结构：Tariff Item（8位.2位后缀）| SS | Description | Unit | MFN Tariff | Preferential Tariffs

用法：
    python -m src.ingest.download_tariff_ca            # 默认 2026 全部章 → data/raw/tariff_ca/
"""
import sys
import time
from pathlib import Path

import requests

from config import DATA_RAW

RAW = DATA_RAW / "tariff_ca"
H = {"User-Agent": "Mozilla/5.0"}
CHAPTERS = [f"{c:02d}" for c in range(1, 98) if c != 77]


def download(year: str = "2026") -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    (RAW / "year.txt").write_text(year, encoding="utf-8")
    for ch in CHAPTERS:
        out = RAW / f"ch{ch}.html"
        if out.exists() and out.stat().st_size > 5000:
            continue
        url = f"https://www.cbsa-asfc.gc.ca/trade-commerce/tariff-tarif/{year}/html/00/ch{ch}-eng.html"
        for attempt in range(3):
            try:
                r = requests.get(url, timeout=60, headers=H)
                if r.status_code == 404:
                    print(f"  ch{ch}: 404 跳过")
                    break
                r.raise_for_status()
                out.write_bytes(r.content)
                print(f"  ch{ch}: {len(r.content)//1024} KB")
                break
            except Exception as e:  # noqa: BLE001
                print(f"  ch{ch} attempt{attempt+1} FAIL {type(e).__name__}")
                time.sleep(5 * (attempt + 1))
        time.sleep(0.8)
    print("done →", RAW)


if __name__ == "__main__":
    download(sys.argv[1] if len(sys.argv) > 1 else "2026")
