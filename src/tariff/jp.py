"""
日本关税查询：解析 Japan Customs 官方英文关税表 HTML。

数据管线：download_tariff_jp.py 下载 e_01..e_99 → 本模块 build() 解析全部章
→ artifacts/tariff_jp.json → lookup_jp(code) 查询。

行结构（每章 HTML 表格）：
    <td CSTNO>6101.20</td><td HSCODE>000</td><td ITEM_NAME>Of cotton</td>
    <td>General 10.9%</td><td>Temporary</td><td>(WTO 10.9%)</td><td>EPA×17…</td>
CSTNO 空的行是分组标题行，跳过。码 = 6 位 + 国别后缀（000 → 9 位码）。
"""
import json
import re
from pathlib import Path

from config import ARTIFACTS, DATA_RAW

RAW = DATA_RAW / "tariff_jp"
OUT = ARTIFACTS / "tariff_jp.json"
_TD = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
_TAG = re.compile(r"<[^>]+>|&nbsp;")
_CODE = re.compile(r"^\d{4}\.\d{2}$")


def _clean(s: str) -> str:
    return _TAG.sub(" ", s).replace("\r", " ").replace("\n", " ").strip()


def _parse_chapter(path: Path) -> list[dict]:
    rows = re.findall(r"<tr[^>]*>.*?</tr>", path.read_text(encoding="utf-8", errors="ignore"), re.S)
    out = []
    current6 = None  # rowspan 父码：子行 CSTNO 为空，沿用父码
    for row in rows:
        tds = [_clean(x) for x in _TD.findall(row)]
        if len(tds) < 6:
            continue
        code6, suffix, desc, general, temporary, wto = tds[0], tds[1], tds[2], tds[3], tds[4], tds[5]
        if _CODE.match(code6):
            current6 = code6
        elif code6 == "" and suffix and current6 and (general or temporary):
            code6 = current6  # 子行（如 6101.90 父行下的 -100/-900）
        else:
            continue
        if not (general or temporary):
            continue  # 分组行 / 空行
        digits = (code6 + suffix.replace("-", "")).replace(".", "")
        out.append(
            {
                "code": digits[:6] + (digits[6:9] if len(digits) > 6 else ""),  # 6 位 + 后缀 → 9 位
                "code_display": f"{code6}-{suffix}",
                "description": desc,
                "general": general,      # 国内法税率（WTO 约定上限内）
                "temporary": temporary,  # 暂定税率（更低时适用）
                "wto": wto.strip("()"),  # WTO 约定税率
            }
        )
    return out


def build() -> None:
    all_lines: list[dict] = []
    for f in sorted(RAW.glob("e_*.htm")):
        ch = _parse_chapter(f)
        all_lines.extend(ch)
        print(f"{f.name}: {len(ch)} lines")
    OUT.write_text(json.dumps(all_lines, ensure_ascii=False), encoding="utf-8")
    print(f"total {len(all_lines)} lines → {OUT}")


_index: dict[str, list[dict]] | None = None


def _get_index() -> dict[str, list[dict]]:
    """归一化码（去点、截 4/6/9 位）→ 数据行。"""
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


def lookup_jp(code: str) -> dict:
    """日本税率查询：4/6/9 位码 → 税率线（general/temporary/WTO）。"""
    digits = "".join(ch for ch in code if ch.isdigit())
    if len(digits) < 4:
        return {"error": "至少 4 位"}
    lines = _get_index().get(digits, [])
    return {
        "country": "JP",
        "code": digits,
        "lines": lines[:30],
        "source_note": (
            "数据来源：Japan Customs 英文关税表（customs.go.jp，官方），edition "
            + (RAW / "edition.txt").read_text(encoding="utf-8").strip()
            if (RAW / "edition.txt").exists() else
            "数据来源：Japan Customs 英文关税表（customs.go.jp，官方）"
        )
        + "；General=国内法税率，Temporary=暂定税率（更低时优先适用），WTO=协定约定税率。申报以日本关税局裁定为准",
    }


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "build":
        build()
    else:
        res = lookup_jp(sys.argv[1] if len(sys.argv) > 1 else "610120")
        for l in res["lines"]:
            print(f"{l['code_display']:14s} G={l['general']:8s} T={l['temporary']:8s} WTO={l['wto']:8s} {l['description'][:40]}")
