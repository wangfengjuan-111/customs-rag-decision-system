"""
TARIC 措施数据解析（CIRCABC 导出）→ artifacts/taric_duties.json。

输入：data/raw/taric/duties_import.xlsx（circabc.europa.eu "Duties Import 01-99" 导出，
      146k 行 TARIC 措施：Goods code / Origin / Measure type / Duty / Start-End date / Legal base）

产出：按 10 位 TARIC 码组织的紧凑索引：
    { code10: { "mfn": {...}, "cn_measures": [...] } }
    - mfn: ERGA OMNES 第三国关税（欧盟基础税率）
    - cn_measures: China 专属措施（反倾销/反补贴/额外关税）

处理规则：
- 日期过滤：start_date <= 今天 <= end_date（end 为空视为长期有效）
- 条件性税率（"Cond:" 开头）保留原文展示但标注 conditional，不参与数值计算
- 从量/复合税率保留原文（EUR/DTN 等），从价解析出数值

用法：python -m src.ingest.parse_taric
"""
import json
import re
from collections import defaultdict
from datetime import date
from pathlib import Path

import openpyxl

from config import ARTIFACTS, DATA_RAW

XLSX = DATA_RAW / "taric" / "duties_import.xlsx"
OUT = ARTIFACTS / "taric_duties.json"

TODAY = date.today()

# 只保留与关税相关的措施类型（跳过进口管制/兽医/统计等非税率措施）
KEEP_MEASURES = {
    "Third country duty": "mfn",
    "Definitive anti-dumping duty": "anti_dumping",
    "Definitive countervailing duty": "countervailing",
    "Additional duties": "additional",
    "Customs Union Duty": "customs_union",
}
RE_ADVAL = re.compile(r"(\d+(?:\.\d+)?)\s*%")
RE_EUR_UNIT = re.compile(r"([\d.]+)\s*EUR\s*([A-Z]+)")


def parse_duty(duty: str | None) -> dict:
    """解析 Duty 文本 → {raw, adval, specific, conditional}。"""
    raw = (duty or "").strip()
    if not raw or raw == "NIHIL":
        return {"raw": raw or "—", "adval": None, "specific": None, "conditional": False}
    conditional = raw.startswith("Cond") or raw.startswith("B cert") or raw.startswith("A cert")
    m = RE_ADVAL.search(raw)
    s = RE_EUR_UNIT.search(raw)
    return {
        "raw": raw,
        "adval": float(m.group(1)) if m else None,
        "specific": f"{s.group(1)} EUR/{s.group(2)}" if s else None,
        "conditional": conditional,
    }


def _parse_date(v) -> date | None:
    """TARIC 导出日期格式为 'DD-MM-YYYY' 字符串。"""
    if v is None:
        return None
    if isinstance(v, date):
        return v
    s = str(v).strip()
    for order in ((2, 1, 0), (0, 1, 2)):  # DD-MM-YYYY 或 YYYY-MM-DD
        parts = s.split("-")
        if len(parts) != 3:
            return None
        try:
            y, m, d = (int(parts[i]) for i in order)
            return date(y, m, d)
        except (ValueError, TypeError):
            continue
    return None


def main() -> None:
    print("加载 TARIC 措施工作簿（146k 行，约 1-2 分钟）...")
    wb = openpyxl.load_workbook(XLSX, read_only=True)
    ws = wb["Export Worksheet"]

    idx: dict[str, dict] = defaultdict(dict)
    n_total = n_kept = n_expired = 0
    for row in ws.iter_rows(min_row=2, values_only=True):
        n_total += 1
        code, _, _, start_v, end_v, _, origin, mtype, legal, duty_raw, _, _ = row[:12]
        if mtype not in KEEP_MEASURES:
            continue
        # 日期有效性
        start = _parse_date(start_v)
        end = _parse_date(end_v)
        if (start and start > TODAY) or (end and end < TODAY):
            n_expired += 1
            continue
        code10 = str(code or "").strip()
        if len(code10) < 8:
            continue
        entry = {
            "type": KEEP_MEASURES[mtype],
            "origin": str(origin or "").strip(),
            "duty": parse_duty(duty_raw),
            "legal": str(legal or "").strip(),
        }
        key = KEEP_MEASURES[mtype]
        if key == "mfn":
            # 同码多行 mfn（不同日期版本）取第一个有效的
            if "mfn" not in idx[code10]:
                idx[code10]["mfn"] = entry
        else:
            idx[code10].setdefault("measures", []).append(entry)
        n_kept += 1

    # 汇总
    n_mfn = sum(1 for v in idx.values() if "mfn" in v)
    n_meas = sum(len(v.get("measures", [])) for v in idx.values())
    n_cn = sum(1 for v in idx.values() for m in v.get("measures", []) if m["origin"] == "China")
    print(f"总行 {n_total}，有效关税措施 {n_kept}（过期跳过 {n_expired}）")
    print(f"含基础税率码 {n_mfn}，附加措施 {n_meas} 条（其中 China {n_cn}）")

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(idx, ensure_ascii=False), encoding="utf-8")
    print(f"saved -> {OUT}")


if __name__ == "__main__":
    main()
