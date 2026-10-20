"""
加拿大关税查询：解析 CBSA 官方 HTML 章节页。

数据管线：download_tariff_ca.py 下载 ch01..ch99 → 本模块 build() 解析
→ artifacts/tariff_ca.json → lookup_ca(code) 查询。

行结构（每章 HTML 表格，官方列名）：
    <td>6101.20.00</td><td>00</td><td>描述</td><td>NMB</td><td>18%</td>
    <td>CCCT, LDCT, ...: Free<br>AUT 11%</td>
列：Tariff Item（8位.2位统计后缀）| SS | Description | Unit | MFN | Preferential。
"""
import json
import re
from pathlib import Path

from config import ARTIFACTS, DATA_RAW

RAW = DATA_RAW / "tariff_ca"
OUT = ARTIFACTS / "tariff_ca.json"
_TD = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
_TR = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
_TAG = re.compile(r"<[^>]+>|&nbsp;")
_CODE = re.compile(r"^\d{4}\.\d{2}\.\d{2}$")


def _clean(s: str) -> str:
    return _TAG.sub(" ", s).replace("\r", " ").replace("\n", " ").strip()


def _parse_chapter(path: Path) -> list[dict]:
    out = []
    for row in _TR.findall(path.read_text(encoding="utf-8", errors="ignore")):
        tds = [_clean(x) for x in _TD.findall(row)]
        if len(tds) < 6 or not _CODE.match(tds[0]):
            continue
        item, ss, desc, unit, mfn, prefs = tds[:6]
        if not mfn:
            continue
        digits = item.replace(".", "")  # 10 位：8 位 + 2 位统计后缀
        out.append(
            {
                "code": digits[:8],
                "code_display": item,
                "ss": ss,                # 统计后缀
                "description": desc,
                "unit": unit,
                "mfn": mfn,              # 最惠国税率（对非优惠原产国适用）
                "preferential": prefs,   # 优惠协定（CCCT 加美墨 / LDCT 最不发达 / UKT 英澳 等代号+税率）
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


def lookup_ca(code: str) -> dict:
    """加拿大税率查询：4/6/8 位码 → 税率线（MFN + 优惠协定）。"""
    digits = "".join(ch for ch in code if ch.isdigit())
    if len(digits) < 4:
        return {"error": "至少 4 位"}
    lines = _get_index().get(digits, [])
    return {
        "country": "CA",
        "code": digits,
        "lines": lines[:30],
        "source_note": (
            "数据来源：CBSA Customs Tariff（cbsa-asfc.gc.ca，官方，"
            + (RAW / "year.txt").read_text(encoding="utf-8").strip()
            if (RAW / "year.txt").exists() else "数据来源：CBSA Customs Tariff（cbsa-asfc.gc.ca，官方）"
        )
        + "）；MFN=最惠国税率（对中国适用），优惠列 CCCT/LDCT/UKT 等为各协定伙伴。申报以加拿大边境服务局裁定为准",
    }


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "build":
        build()
    else:
        res = lookup_ca(sys.argv[1] if len(sys.argv) > 1 else "610120")
        for l in res["lines"]:
            print(f"{l['code_display']:12s} MFN={l['mfn']:8s} {l['description'][:50]}")
            print(f"             优惠: {l['preferential'][:70]}")
