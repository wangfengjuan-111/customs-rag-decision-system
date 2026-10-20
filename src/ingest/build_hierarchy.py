"""
品目条文+税率 JSON → headings.json + hierarchy.json。

- 四位品目为根（indent 0），子目按 indent 压栈成树
- 空 htsno 的描述续行并入父节点文本
- 每个品目挂 clause_ids：本章 legal/us_notes 全部条款 + applies_to 命中该品目的条款
  （论文的 O(1) 约束查找）

用法：python -m src.ingest.build_hierarchy
"""
import json
from pathlib import Path

from config import ARTIFACTS, DATA_RAW

ITEMS_DIR = DATA_RAW / "items"


def safe_indent(v) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def load_records() -> list[dict]:
    recs: list[dict] = []
    for f in sorted(ITEMS_DIR.glob("items_*.json")):
        recs.extend(json.loads(f.read_text(encoding="utf-8")))
    return recs


def build_tree(records: list[dict]) -> list[dict]:
    """indent 压栈，返回顶层节点（各章四位品目）。"""
    roots: list[dict] = []
    stack: list[tuple[int, dict]] = []  # (indent, node)
    for rec in records:
        htsno = (rec.get("htsno") or "").strip()
        indent = safe_indent(rec.get("indent"))
        desc = (rec.get("description") or "").strip()
        if not htsno:
            # 描述续行：并入最近的父节点文本
            if stack and desc:
                stack[-1][1]["_extra_desc"].append(desc)
            continue
        node = {
            "code": htsno,
            "indent": indent,
            "description": desc,
            "_extra_desc": [],
            "units": rec.get("units") or [],
            "general": (rec.get("general") or "").strip(),
            "special": (rec.get("special") or "").strip(),
            "other": (rec.get("other") or "").strip(),
            "children": [],
        }
        while stack and stack[-1][0] >= indent:
            stack.pop()
        if stack:
            stack[-1][1]["children"].append(node)
        else:
            roots.append(node)
        stack.append((indent, node))
    return roots


def collect_texts(node: dict) -> list[str]:
    texts = [node["description"]] + [f"-- {d}" for d in node["_extra_desc"]]
    for ch in node["children"]:
        texts.extend(collect_texts(ch))
    return [t for t in texts if t]


def has_rate(n: dict) -> bool:
    return bool(n["general"] or n["special"] or n["other"])


def slim_subtree(node: dict) -> dict:
    return {
        "code": node["code"],
        "description": node["description"],
        "indent": node["indent"],
        "general": node["general"],
        "special": node["special"],
        "other": node["other"],
        "units": node["units"],
        "children": [slim_subtree(c) for c in node["children"]],
    }


def main() -> None:
    # 载入条款，构建 品目→条款 映射
    clauses = []
    clauses_file = ARTIFACTS / "clauses.jsonl"
    if clauses_file.exists():
        clauses = [json.loads(l) for l in open(clauses_file, encoding="utf-8")]
    chapter_legal: dict[int, list[str]] = {}   # 章 → 全章适用条款
    clause_by_heading: dict[str, list[str]] = {}  # 4位品目 → 精确命中条款
    for c in clauses:
        if c["group"] in ("legal", "us_notes"):
            chapter_legal.setdefault(c["chapter"], []).append(c["clause_id"])
        for h in c["applies_to"]:
            clause_by_heading.setdefault(h, []).append(c["clause_id"])

    roots = build_tree(load_records())
    headings = []
    seen_h4 = set()
    for root in roots:
        chapter = int(root["code"][:2])
        h4 = root["code"].replace(".", "")[:4]
        if h4 in seen_h4:
            continue  # 同四位已存在（章 97/98 的多根情形），保留首个
        seen_h4.add(h4)
        clause_ids = list(chapter_legal.get(chapter, [])) + list(clause_by_heading.get(h4, []))
        rates = [
            {"code": n["code"], "general": n["general"], "special": n["special"], "other": n["other"]}
            for n in [root] + root["children"]
            if has_rate(n)
        ]
        headings.append({
            "heading": h4,                    # 归一四位键（检索/评测统一用）
            "code_display": root["code"],     # HTS 原始码（如 9503.00.00）
            "chapter": chapter,
            "description": root["description"],
            "retrieval_text": " ".join(collect_texts(root)),
            "clause_ids": sorted(set(clause_ids)),
            "n_clauses": len(set(clause_ids)),
            "rates": rates,
            "subheadings": [slim_subtree(c) for c in root["children"]],
        })

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    with open(ARTIFACTS / "headings.json", "w", encoding="utf-8") as f:
        json.dump(headings, f, ensure_ascii=False)

    by_chapter: dict[int, list[str]] = {}
    for h in headings:
        by_chapter.setdefault(h["chapter"], []).append(h["heading"])
    hierarchy = {
        "n_headings": len(headings),
        "by_chapter": {k: v for k, v in sorted(by_chapter.items())},
    }
    with open(ARTIFACTS / "hierarchy.json", "w", encoding="utf-8") as f:
        json.dump(hierarchy, f, ensure_ascii=False, indent=1)

    print(f"headings: {len(headings)}, chapters: {len(by_chapter)}")
    print("sample:", headings[0]["heading"], "| clauses:", headings[0]["n_clauses"],
          "| desc:", headings[0]["description"][:60])


if __name__ == "__main__":
    main()
