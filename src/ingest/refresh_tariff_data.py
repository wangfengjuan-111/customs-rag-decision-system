"""
关税数据手动刷新：重拉 99 章 + 重建 overlay 工件。

HTS 每年修订数次（301/IEEPA/232 措施变化更频繁），税率计算前先刷新。

用法：python -m src.ingest.refresh_tariff_data
"""
import json

import requests

from config import DATA_RAW

CH99_ITEMS = DATA_RAW / "items" / "items_99_full.json"
CH99_NOTES = DATA_RAW / "notes" / "ch99.html"
HEADERS = {"User-Agent": "Mozilla/5.0 (research; hs-tariff-agent)"}


def fetch_json(url: str, params: dict, timeout: int = 180) -> dict | None:
    for attempt in range(3):
        try:
            r = requests.get(url, params=params, timeout=timeout, headers=HEADERS)
            if r.status_code == 200:
                return r.json()
        except requests.RequestException as e:
            print(f"  attempt {attempt+1}: {e}")
    return None


def fetch_text(url: str, params: dict, timeout: int = 120) -> str | None:
    for attempt in range(3):
        try:
            r = requests.get(url, params=params, timeout=timeout, headers=HEADERS)
            if r.status_code == 200:
                return r.text
        except requests.RequestException as e:
            print(f"  attempt {attempt+1}: {e}")
    return None


def main() -> None:
    print("[1/4] 拉取 99 章条目+税率 (exportList 9901-9999)...")
    data = fetch_json(
        "https://hts.usitc.gov/reststop/exportList",
        {"from": "9901", "to": "9999", "format": "JSON", "styles": "false"},
    )
    if not data:
        raise SystemExit("99 章条目拉取失败")
    CH99_ITEMS.parent.mkdir(parents=True, exist_ok=True)
    CH99_ITEMS.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    print(f"      {len(data)} 条记录")

    print("[2/4] 拉取 99 章注释 (getChapterNotes doc=99)...")
    notes = fetch_text("https://hts.usitc.gov/reststop/getChapterNotes", {"doc": 99})
    if not notes or "misc_title" not in notes:
        raise SystemExit("99 章注释拉取失败")
    CH99_NOTES.write_text(notes, encoding="utf-8")
    print(f"      {len(notes)//1024} KB")

    print("[3/4] 解析 9903 overlay...")
    from src.ingest.parse_ch99 import main as parse_main

    parse_main()

    print("[4/4] 完成。ch99_overlays.json 已更新。")
    print("      提示：01-97 章基础税率变化时另跑 python -m src.ingest.download_hts items")


if __name__ == "__main__":
    main()
