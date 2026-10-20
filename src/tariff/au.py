"""
澳大利亚关税查询：解析 ABF 官网 Schedule 3 章节页。

数据管线：download_tariff_au.py 下载 ch01..ch97 → 本模块 build() 解析
→ artifacts/tariff_au.json → lookup_au(code) 查询。

行结构（每章 HTML 表格）：
    <tr><th rowspan=N scope=row>6101.20.00</th><td>统计码</td><td>单位</td>
        <td>- Of cotton</td><td>5%</td><td>TCO…</td></tr>
rowspan>1 时后续行无 th（码沿用父行）。Rate# = General 普遍税率（MFN）；
FTAs（ChAFTA 等）优惠不在工作页展示，展示层注明。
"""
import json
import re
from pathlib import Path

from config import ARTIFACTS, DATA_RAW

RAW = DATA_RAW / "tariff_au"
OUT = ARTIFACTS / "tariff_au.json"
_TD = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
_TR = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
_TH = re.compile(r"<th[^>]*>(.*?)</th>", re.S)
_TAG = re.compile(r"<[^>]+>|&nbsp;|‌|​")  # 含零宽字符
_CODE = re.compile(r"^\d{4}\.\d{2}\.\d{2}$")


def _clean(s: str) -> str:
    return _TAG.sub(" ", s).replace("\r", " ").replace("\n", " ").strip()


def _parse_chapter(path: Path) -> list[dict]:
    out = []
    current_code = None
    for row in _TR.findall(path.read_text(encoding="utf-8", errors="ignore")):
        ths = [_clean(x) for x in _TH.findall(row)]
        tds = [_clean(x) for x in _TD.findall(row)]
        if ths and _CODE.match(ths[0].strip()):
            current_code = ths[0].strip()  # 新的 8 位码（可能 rowspan 覆盖后续行）
        elif ths and not _CODE.match(ths[0].strip()):
            current_code = None  # 章级/品目级标题行（如 "6101"）
            continue
        # th 在 row 里但不是码 → 标题行；无 th 且无 current → 跳过
        if not tds or current_code is None:
            continue
        if len(tds) < 4:
            continue
        stat, unit, goods, rate = tds[0], tds[1], tds[2], tds[3]
        # 税率必须非空，且是 Free 或含数字/百分号
        if not rate or ("free" not in rate.lower() and not re.search(r"[\d%]", rate)):
            continue
        out.append(
            {
                "code": current_code.replace(".", ""),
                "code_display": current_code,
                "stat": stat,            # 统计码
                "description": goods,
                "unit": unit,
                "general": rate,         # Schedule 3 General 普遍税率（MFN）
            }
        )
    return out


def build() -> None:
    all_lines: list[dict] = []
    for f in sorted(RAW.glob("ch*.html")):
        ch = _parse_chapter(f)
        all_lines.extend(ch)
        print(f"{f.name}: {len(ch)} lines")
    OUT.write_text(json.dumps(all_lines, ensure_ascii=False), encoding="utf-8")
    print(f"total {len(all_lines)} lines → {OUT}")


_index: dict[str, list[dict]] | None = None


def _get_index() -> dict[str, list[dict]]:
    global _index
    if _index is None:
        lines = json.loads(OUT.read_text(encoding="utf-8"))
        idx: dict[str, list[dict]] = {}
        for l in lines:
            d = l["code"]
            for k in {d[:4], d[:6], d}:
                idx.setdefault(k, []).append(l)
        _index = idx
    return _index


def lookup_au(code: str) -> dict:
    """澳大利亚税率查询：4/6/8 位码 → 税率线（General 普遍税率）。"""
    digits = "".join(ch for ch in code if ch.isdigit())
    if len(digits) < 4:
        return {"error": "至少 4 位"}
    lines = _get_index().get(digits, [])
    return {
        "country": "AU",
        "code": digits,
        "lines": lines[:40],
        "source_note": (
            "数据来源：ABF Customs Tariff Schedule 3 工作页（abf.gov.au，官方）；"
            "General=普遍税率（MFN，对中国适用）；ChAFTA 等自贸协定优惠税率不在工作页展示，"
            "申报以澳大利亚边境执法局裁定为准"
        ),
    }


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "build":
        build()
    else:
        res = lookup_au(sys.argv[1] if len(sys.argv) > 1 else "610120")
        for l in res["lines"]:
            print(f"{l['code_display']:12s} [{l['stat']:>3s}] G={l['general']:8s} {l['description'][:50]}")
