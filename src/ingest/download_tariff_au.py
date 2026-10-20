"""
澳大利亚关税表下载：ABF 官网 Customs Tariff Act 1995 Schedule 3 章节页。

来源：https://www.abf.gov.au/importing-exporting-and-manufacturing/tariff-classification/
      current-tariff/schedule-3/section-{roman}/chapter-{NN}
（每章 HTML：Reference Number=8位码 | Statistical Code | Unit | Goods | Rate# | TCO）
HS 章→节 标准映射硬编码；404 章节自动跳过。

用法：
    python -m src.ingest.download_tariff_au     # → data/raw/tariff_au/
"""
import time
from pathlib import Path

import requests

from config import DATA_RAW

RAW = DATA_RAW / "tariff_au"
H = {"User-Agent": "Mozilla/5.0"}
BASE = (
    "https://www.abf.gov.au/importing-exporting-and-manufacturing/"
    "tariff-classification/current-tariff/schedule-3"
)

# HS 标准 章→节（罗马数字小写，ABF URL 用）
SECTION_OF_CHAPTER = {}
_sections = [
    ("i", 1, 5), ("ii", 6, 14), ("iii", 15, 15), ("iv", 16, 24), ("v", 25, 27),
    ("vi", 28, 38), ("vii", 39, 40), ("viii", 41, 43), ("ix", 44, 46), ("x", 47, 49),
    ("xi", 50, 63), ("xii", 64, 67), ("xiii", 68, 70), ("xiv", 71, 71), ("xv", 72, 83),
    ("xvi", 84, 85), ("xvii", 86, 89), ("xviii", 90, 92), ("xix", 93, 93),
    ("xx", 94, 96), ("xxi", 97, 97),
]
for roman, lo, hi in _sections:
    for c in range(lo, hi + 1):
        SECTION_OF_CHAPTER[c] = roman


def download() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    (RAW / "source.txt").write_text(BASE, encoding="utf-8")
    for ch in range(1, 98):
        if ch == 77:
            continue
        out = RAW / f"ch{ch:02d}.html"
        if out.exists() and out.stat().st_size > 20000:
            continue
        url = f"{BASE}/section-{SECTION_OF_CHAPTER[ch]}/chapter-{ch}"
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
                time.sleep(8 * (attempt + 1))
        time.sleep(1)  # ABF 站点较慢，礼貌限速
    print("done →", RAW)


if __name__ == "__main__":
    download()
