"""
TARIC 商品描述解析（CIRCABC Nomenclature EN 导出）→ artifacts/taric_descriptions.json。

输入：data/raw/taric/nomenclature_en.xlsx（25,867 行：
      Goods code（'0101210000 80' = 10 位码 + 行后缀）+ Description + 起止日期）

产出：{ code10: description }（同码多版本取最新生效的；后缀 80 优先）

用法：python -m src.ingest.parse_taric_nomen
"""
import json
from datetime import date

import openpyxl

from config import ARTIFACTS, DATA_RAW

XLSX = DATA_RAW / "taric" / "nomenclature_en.xlsx"
OUT = ARTIFACTS / "taric_descriptions.json"

TODAY = date.today()


def _parse_date(v) -> date | None:
    if v is None:
        return None
    if isinstance(v, date):
        return v
    s = str(v).strip()
    parts = s.split("-")
    if len(parts) != 3:
        return None
    try:
        return date(int(parts[2]), int(parts[1]), int(parts[0]))  # DD-MM-YYYY
    except (ValueError, TypeError):
        return None


def main() -> None:
    wb = openpyxl.load_workbook(XLSX, read_only=True)
    ws = wb[wb.sheetnames[0]]
    best: dict[str, tuple[date, str]] = {}  # code10 -> (descr_start_date, desc)
    n = 0
    for row in ws.iter_rows(min_row=2, values_only=True):
        code_raw, start_v, end_v, lang, _pos, _indent, desc, descr_start_v = row[:8]
        n += 1
        if lang != "EN" or not desc:
            continue
        end = _parse_date(end_v)
        if end and end < TODAY:
            continue
        code = str(code_raw or "").split(" ")[0].strip()
        if len(code) < 8:
            continue
        dstart = _parse_date(descr_start_v) or date(1900, 1, 1)
        if code not in best or dstart > best[code][0]:
            best[code] = (dstart, str(desc).strip())
    print(f"总行 {n}，有效描述 {len(best)} 码")
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({k: v[1] for k, v in best.items()}, ensure_ascii=False), encoding="utf-8")
    print(f"saved -> {OUT}")


if __name__ == "__main__":
    main()
