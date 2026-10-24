"""
USITC HTS 数据下载：
1. exportList 按章区间拉品目条文+税率 JSON
2. getChapterNotes 按章拉章注结构化 HTML（已实测：li[value] 自带条款编号）
3. file 端点探测 section notes（格式待定，单独脚本处理）

用法：
    python -m src.ingest.download_hts          # 全量（品目+注释）
    python -m src.ingest.download_hts notes    # 仅注释
    python -m src.ingest.download_hts items 61 61
"""
import sys
import time
from pathlib import Path

import requests

from config import CHAPTER_BATCHES, DATA_HSCODES, DATA_RAW, USITC_EXPORT_URL

HEADERS = {"User-Agent": "Mozilla/5.0 (research; hs-tariff-agent)"}
NOTES_DIR = DATA_RAW / "notes"
ITEMS_DIR = DATA_RAW / "items"


def fetch_chapter_notes(chapter: int, session: requests.Session) -> str | None:
    """拉取单章章注 HTML。返回文本或 None。"""
    url = f"https://hts.usitc.gov/reststop/getChapterNotes?doc={chapter}"
    for attempt in range(3):
        try:
            r = session.get(url, timeout=60, headers=HEADERS)
            if r.status_code == 200 and "misc_title" in r.text:
                return r.text
            print(f"  ch{chapter:02d} attempt {attempt+1}: status={r.status_code} len={len(r.text)}")
        except requests.RequestException as e:
            print(f"  ch{chapter:02d} attempt {attempt+1}: {e}")
        time.sleep(2 * (attempt + 1))
    return None


def fetch_items(from_code: str, to_code: str, session: requests.Session) -> list | None:
    """拉取编码区间内的品目条文+税率记录。"""
    params = {"from": from_code, "to": to_code, "format": "JSON", "styles": "false"}
    for attempt in range(3):
        try:
            r = session.get(USITC_EXPORT_URL, params=params, timeout=120, headers=HEADERS)
            if r.status_code == 200:
                return r.json()
        except (requests.RequestException, ValueError) as e:
            print(f"  {from_code}-{to_code} attempt {attempt+1}: {e}")
        time.sleep(2 * (attempt + 1))
    return None


def download_notes(chapters: range | None = None) -> None:
    """下载全部章注到 data/raw/notes/chNN.html。"""
    NOTES_DIR.mkdir(parents=True, exist_ok=True)
    chapters = chapters or range(1, 100)
    session = requests.Session()
    ok = fail = 0
    for ch in chapters:
        out = NOTES_DIR / f"ch{ch:02d}.html"
        if out.exists() and out.stat().st_size > 500:  # 断点续传
            ok += 1
            continue
        text = fetch_chapter_notes(ch, session)
        if text:
            out.write_text(text, encoding="utf-8")
            ok += 1
            time.sleep(0.5)
        else:
            fail += 1
            print(f"  FAILED ch{ch:02d}")
    print(f"notes done: {ok} ok, {fail} failed -> {NOTES_DIR}")
    empty = sorted(f.name for f in NOTES_DIR.glob("ch*.html") if "<ul" not in f.read_text(encoding="utf-8"))
    if empty:
        # 少数章确实无注释（ch50 实测端点即空），但截断的下载也会长这样——需人工核对
        print(f"WARN 无注释列表的章注页: {empty}")


def download_items() -> None:
    """按章区间批量下载品目+税率 JSON。"""
    ITEMS_DIR.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    for lo, hi in CHAPTER_BATCHES:
        out = ITEMS_DIR / f"items_{lo}_{hi}.json"
        if out.exists() and out.stat().st_size > 100:
            print(f"  {lo}-{hi} exists, skip")
            continue
        data = fetch_items(lo, hi, session)
        if data:
            import json

            out.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            print(f"  {lo}-{hi}: {len(data)} records")
            time.sleep(1)
        else:
            print(f"  {lo}-{hi}: FAILED")


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    if cmd in ("all", "notes"):
        if len(sys.argv) > 3:
            download_notes(range(int(sys.argv[2]), int(sys.argv[3]) + 1))
        else:
            download_notes()
    if cmd in ("all", "items"):
        download_items()
    print(f"raw data dirs: {DATA_RAW}, eval set goes to {DATA_HSCODES}")


if __name__ == "__main__":
    main()
