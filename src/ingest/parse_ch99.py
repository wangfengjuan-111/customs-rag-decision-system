"""
Chapter 99 解析：9903 系列附加关税 → 结构化映射表 ch99_overlays.json。

数据源（全部本地）：
- data/raw/items/items_99_full.json  9903 税率文本（general 字段含 '+ 25%' 等）
- data/raw/notes/ch99.html           U.S. Note 20/21... 子条目按 8 位码枚举适用清单

产出：
- artifacts/ch99_overlays.json  [{overlay_code, series, rate_pct, origin_scope, applies_to_8d[], exclusions[], note_ref}]
  applies_to_8d：note 里枚举的 8 位码（4 位前缀索引 + 完整码双索引，查询层用）

用法：python -m src.ingest.parse_ch99
"""
import json
import re
from collections import defaultdict
from pathlib import Path

from bs4 import BeautifulSoup

from config import ARTIFACTS, DATA_RAW

CH99_ITEMS = DATA_RAW / "items" / "items_99_full.json"
CH99_NOTES = DATA_RAW / "notes" / "ch99.html"

RE_RATE = re.compile(r"(?:plus|\+)\s*(\d+(?:\.\d+)?)\s*%")
RE_CODE8 = re.compile(r"\b(\d{4}\.\d{2}\.\d{2})\b")
RE_ORIGIN = re.compile(r"product of ([A-Za-z ,]+?)(?:,| that| as provided)", )


def parse_rate(general: str) -> float | None:
    m = RE_RATE.search(general or "")
    return float(m.group(1)) if m else None


def load_items() -> list[dict]:
    return json.loads(CH99_ITEMS.read_text(encoding="utf-8"))


# 宽松模式：码表存在无分隔粘连形态（"0101.21.000101.29.00" = 两个 8 位码直连，
# 编译注记 "read from left to right"）。该语料无日期等干扰形态，宽松安全。
RE_CODE_FULL = re.compile(r"(\d{4}\.\d{2}\.\d{2})")
# overlay 描述里的清单引用与豁免配对
RE_ENUM_REF = re.compile(r"enumerated in U\.?S\.?\s*note\s*(\d+)\(([a-z]+)\)")
RE_EXCL_PAIR = re.compile(r"heading\s+(9903\.\d{2}\.\d{2})\s+and\s+U\.?S\.?\s*note\s*(\d+)\(([a-z]+)\)")
RE_APPLIES_TO = re.compile(r"[Hh]eading\s+(9903\.\d{2}\.\d{2})\s+applies")
RE_RATE_LETTER = re.compile(r"For the purposes of heading\s+(9903\.\d{2}\.\d{2})")
# 交叉引用："heading 9903.88.05 and U.S. note 20(h)" → 豁免款 (h) 的码归 9903.88.05 的豁免集


def norm8(code: str) -> str:
    """任意码型 → 8 位 XXXX.XX.XX（'8412.21.0075'/'8412.21.00.75'/'8412.21.00' → '8412.21.00'）。"""
    digits = re.sub(r"\D", "", code)
    return f"{digits[:4]}.{digits[4:6]}.{digits[6:8]}" if len(digits) >= 8 else code


def _own_text(li) -> str:
    """li 直接文本（不含嵌套子条目）。"""
    parts: list[str] = []
    for child in li.contents:
        if hasattr(child, "name") and child.name in ("ul", "li"):
            break
        parts.append(child.get_text() if hasattr(child, "get_text") else str(child))
    return re.sub(r"\s+", " ", "".join(parts)).strip()


def extract_note_lists(items: list[dict]) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """解析 99 章注释（按文档顺序做区间切分，HTML 嵌套不可靠）。

    映射源 = overlay 描述自身的引用（比 note 正文更精确）：
    - applies：desc 里 "enumerated in U.S. note NN(letter)" → 该字母款下的码归本税号
    - exclusion：desc 里 "heading 9903.xx.xx and U.S. note NN(letter)" → 豁免配对

    区间切换（文档顺序，<li> 切区间，<table> 归当前区间）：
    1. anchor 款 "Heading X applies"      → target=(X, applies)
    2. 豁免款（配对命中 + "Trade Representative" 措辞防罗马数字误撞）→ target=(X, exclusion)
    3. enum 引用款（(note, letter) 命中）  → target=(overlay, applies)
    4. 税率款 "For the purposes of heading X"（未命中 enum）→ target=None（关闭区间）

    返回 (applies_map, exclusion_map)：9903 税号 → 8 位码清单。
    """
    soup = BeautifulSoup(CH99_NOTES.read_text(encoding="utf-8"), "html.parser")

    # 预扫 overlay 描述：applies 清单引用 (note_no, letter) → overlay
    enum_refs: dict[tuple[int, str], str] = {}
    for x in items:
        desc = re.sub(r"\s+", " ", x.get("description") or "")
        for nn, letter in RE_ENUM_REF.findall(desc):
            enum_refs[(int(nn), letter)] = x["htsno"]

    applies_map: dict[str, set[str]] = defaultdict(set)
    exclusion_map: dict[str, set[str]] = defaultdict(set)

    for note_li in soup.find_all("li"):
        val = re.sub(r"\s+", "", note_li.get("value") or "")
        mn = re.match(r"^(\d{1,2})\.", val)
        if not mn:
            continue
        note_no = int(mn.group(1))
        # 预扫 note 正文：豁免配对 "heading 9903.88.05 and U.S. note 20(h)" → (letter → 豁免税号)
        # （此引用存在于 note (a)/(b) 款正文，不在 HTS 条目 desc 里）
        note_text = note_li.get_text()
        excl_pairs: dict[tuple[int, str], str] = {}
        for oc, nn, letter in RE_EXCL_PAIR.findall(note_text):
            excl_pairs[(int(nn), letter)] = oc

        target: tuple[str, str] | None = None   # (overlay_code, "applies"|"exclusion")

        def add_codes(text: str) -> None:
            if not target:
                return
            for c in RE_CODE_FULL.findall(text):
                if not c.startswith("99"):
                    code8 = norm8(c)
                    if target[1] == "applies":
                        applies_map[target[0]].add(code8)
                    else:
                        exclusion_map[target[0]].add(code8)

        # 文档顺序混合流：<li>（切区间）与 <table>（多栏码表，不切区间，归当前区间）
        for el in note_li.descendants:
            if not hasattr(el, "name") or el.name is None:
                continue
            if el.name == "table":
                add_codes(el.get_text())
            elif el.name == "li":
                own = _own_text(el)
                letter_val = (el.get("value") or "").strip()
                lm = re.fullmatch(r"\(([a-z]+)\)", letter_val)
                letter = lm.group(1) if lm else None
                if RE_APPLIES_TO.search(own):
                    target = (RE_APPLIES_TO.search(own).group(1), "applies")
                elif letter and (note_no, letter) in excl_pairs and "Trade Representative" in own:
                    target = (excl_pairs[(note_no, letter)], "exclusion")
                elif letter and (note_no, letter) in enum_refs:
                    target = (enum_refs[(note_no, letter)], "applies")
                elif RE_RATE_LETTER.search(own):
                    target = None
                # 区间内码（own text，如 "(1) 8412.21.0075" 或粘连码表文本）
                add_codes(own)

    return (
        {k: sorted(v) for k, v in applies_map.items()},
        {k: sorted(v) for k, v in exclusion_map.items()},
    )


def main() -> None:
    items = [x for x in load_items() if (x.get("htsno") or "").startswith("9903") and x.get("htsno") != "9903.92"]
    applies_map, exclusion_map = extract_note_lists(items)

    overlays = []
    for x in items:
        code = x["htsno"]
        desc = re.sub(r"\s+", " ", x.get("description") or "")
        general = x.get("general") or ""
        rate = parse_rate(general)
        origin = "China" if "product of China" in desc else ("Mexico" if "Mexico" in desc else ("Canada" if "Canada" in desc else None))
        applies = set(applies_map.get(code, []))
        exclusions = set(exclusion_map.get(code, []))
        # 普惠型 overlay：无码清单 + 描述无 "enumerated in"（枚举=有专属码清单）
        # + "articles the product of X" 全称适用措辞。
        # note：desc 引用 "as provided for in U.S. note NN" 只是法律基础，不构成排他清单
        universal = (
            not applies and not exclusions
            and "enumerated in" not in desc
            and "following" not in desc[:180]
            and bool(re.search(r"[Aa]rticles? the product of", desc[:260]))
        )
        # 豁免条款：granted an exclusion / 明确排除措辞
        is_exemption = "granted an exclusion" in desc or "not subject to" in desc.lower()[:150]
        overlays.append({
            "overlay_code": code,
            "series": code[:8],
            "rate_pct": rate,
            "origin": origin,
            "is_exemption": is_exemption,
            "universal": universal,
            "applies_to_8d": sorted(applies),
            "exclusions": sorted(exclusions),
            "desc_snippet": desc[:220],
        })

    # 汇总报告
    with_rate = [o for o in overlays if o["rate_pct"] is not None]
    with_codes = [o for o in overlays if o["applies_to_8d"]]
    print(f"9903 overlays: {len(overlays)}, 有税率: {len(with_rate)}, 挂接码清单: {len(with_codes)}")
    by_series = defaultdict(int)
    for o in overlays:
        by_series[o["series"]] += 1
    for s, c in sorted(by_series.items()):
        sample = next(o for o in overlays if o["series"] == s)
        print(f"  {s}: {c} 条, 税率样例={sample['rate_pct']}%, origin={sample['origin']}, 清单规模={len(sample['applies_to_8d'])}")

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    out = ARTIFACTS / "ch99_overlays.json"
    out.write_text(json.dumps(overlays, ensure_ascii=False), encoding="utf-8")
    print(f"saved -> {out}")


if __name__ == "__main__":
    main()
