"""
欧盟（EU TARIC）关税查询：基础第三国关税 + 原产国附加措施（反倾销等）+ 分层商品描述。

数据（全部离线工件）：
- artifacts/taric_duties.json       措施（CIRCABC Duties 导出解析，含日期过滤）
- artifacts/taric_descriptions.json 描述（CIRCABC Nomenclature EN 导出解析）

层级语义（TARIC 官方行为一致）：
- 10 位查询：单行
- 8 位查询：该 8 位下全部 10 位行聚合展示
- 6 位查询：按 8 位子目分组展示多行（各行税率可能不同，用户按商品对号入座）
- 4 位查询：按 6 位子目分组
描述 = 品目级 + 6 位级 + 8 位级 + 10 位级逐级拼接（TARIC nomenclature 分层结构）。
"""
import json
import re
from collections import defaultdict
from functools import lru_cache

from config import ARTIFACTS

TARIC_JSON = ARTIFACTS / "taric_duties.json"
DESC_JSON = ARTIFACTS / "taric_descriptions.json"

# 用户国家代码 → TARIC Origin 字段名
ORIGIN_NAMES = {
    "CN": "China",
    "VN": "Viet Nam",
    "TR": "Türkiye",
    "IN": "India",
    "RU": "Russian Federation",
    "KR": "Korea, Republic of",
    "TH": "Thailand",
    "US": "United States",
    "JP": "Japan",
    "IR": "Iran",
    "BY": "Belarus",
}


def _load() -> dict:
    return json.loads(TARIC_JSON.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _descs() -> dict:
    return json.loads(DESC_JSON.read_text(encoding="utf-8"))


def _match_origins(origin_code: str) -> list[str]:
    if not origin_code:
        return []
    if origin_code in ORIGIN_NAMES:
        return [ORIGIN_NAMES[origin_code]]
    return [origin_code]


def full_description(code10: str) -> str:
    """逐级拼接描述：品目(4) + 子目(6) + 子目(8) + 统计行(10)。"""
    d = _descs()
    parts = []
    for level in (code10[:4] + "000000", code10[:6] + "0000", code10[:8] + "00", code10):
        t = d.get(level)
        if t and t.lower() not in ("other",):
            parts.append(t)
    # 'other' 若是唯一描述也保留
    if not parts and d.get(code10):
        parts.append(d[code10])
    return " – ".join(parts).replace("|", " ").strip()


def lookup_eu(code: str, origin: str = "") -> dict:
    """EU 税率查询。code 4-10 位；origin 两位国家代码（CN 触发反倾销匹配）。"""
    idx = _load()
    digits = re.sub(r"\D", "", code)
    if len(digits) < 4:
        return {"error": "EU 查询需要至少 4 位 HS 码"}
    prefix = digits[:10]

    keys = sorted(k for k in idx if k.startswith(prefix))
    if not keys:
        return {"error": f"TARIC 中没有 {prefix} 对应的关税措施记录"}

    # 分组粒度：查询码的下一层级（6 位查 → 8 位组；8 位查 → 10 位组；4 位查 → 6 位组）
    if len(prefix) <= 4:
        grp_len = 6
    elif len(prefix) <= 6:
        grp_len = 8
    elif len(prefix) <= 8:
        grp_len = 10
    else:
        grp_len = 10
    groups: dict[str, list[str]] = defaultdict(list)
    for k in keys:
        groups[k[:grp_len]].append(k)

    origin_names = _match_origins(origin.strip().upper())
    lines = []
    for gk in sorted(groups)[:14]:  # 上限防渲染爆炸
        gkeys = groups[gk]
        mfn = next((idx[k]["mfn"] for k in gkeys if "mfn" in idx[k]), None)
        measures, seen = [], set()
        for k in gkeys:
            for m in idx[k].get("measures", []):
                if origin_names and m["origin"] in origin_names:
                    key = (m["type"], m["duty"]["raw"], m["legal"])
                    if key not in seen:
                        seen.add(key)
                        measures.append(m)
        lines.append({
            "code": f"{gk[:4]} {gk[4:6]} {gk[6:8]}" + (f" {gk[8:]}" if len(gk) > 8 else ""),
            "description": full_description(gkeys[0]),
            "mfn_raw": mfn["duty"]["raw"] if mfn else "—",
            "mfn_pct": mfn["duty"]["adval"] if mfn else None,
            "measures": measures[:10],
        })

    return {
        "code": digits,
        "country": "EU",
        "origin": origin.strip().upper(),
        "lines": lines,
        "source_note": (
            "数据来源：EU TARIC（CIRCABC 措施数据库导出，已按生效日期过滤）；"
            "反倾销税率以原文为准，申报以欧盟委员会 TARIC 数据库为准"
        ),
    }
