"""
Stage 5 · 子目解析：GIR 6，四位 → 六位（→八位）。

GIR 6 要义：只在同一品目内、同一层级的子目间比较；子目注与品目注类推适用。
输出码经过子树校验：模型吐出不存在的码时标记 ambiguous 并回退到子树内模糊匹配。
"""
import re

import numpy as np
from rank_bm25 import BM25Okapi

from pydantic import BaseModel, Field

from config import TEMP_RESOLVE
from src.knowledge.store import get_store
from src.llm.client import ask_json
from src.stages.s1_extract import Attributes

SYSTEM = (
    "You resolve the subheading of a product under an already-chosen HS heading, applying "
    "GIR 6: compare only subheadings at the same level within this heading; the terms of the "
    "subheadings and related subheading notes apply mutatis mutandis (GIR 1/3 analogues).\n"
    "Output:\n"
    "- six_digit: the 6-digit subheading, e.g. '610120' (digits only, no dots)\n"
    "- eight_digit: the US 8-digit code if the description unambiguously implies it, else null\n"
    "- ambiguous: true if the description does not determine the subheading\n"
    "Only choose codes present in the provided subheading tree."
)


class SubheadingResolution(BaseModel):
    six_digit: str = Field(description="6 digits, no dots")
    eight_digit: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    ambiguous: bool = False
    reasoning: str = ""


def _flatten_subtree(subheadings: list[dict], depth: int = 0) -> list[tuple[int, dict]]:
    out: list[tuple[int, dict]] = []
    for n in subheadings:
        out.append((depth, n))
        out.extend(_flatten_subtree(n.get("children", []), depth + 1))
    return out


def _tree_text(code: str) -> str:
    h = get_store().get_heading(code)
    lines = []
    for depth, n in _flatten_subtree(h.get("subheadings", [])):
        rates = n.get("general") or ""
        lines.append(f"{'  '*depth}{n['code']}  {n['description'][:100]}" + (f"  [duty {rates}]" if rates else ""))
    return "\n".join(lines) if lines else "(no subheadings)"


def resolve(code: str, description: str, attrs: Attributes) -> SubheadingResolution:
    user = (
        f"Product description: {description}\n"
        f"Attributes: {attrs.model_dump_json()}\n\n"
        f"Chosen heading {code}: {get_store().get_heading(code)['description']}\n"
        f"Subheading tree:\n{_tree_text(code)}\n\n"
        f"Resolve the subheading as JSON."
    )
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": user},
    ]
    res = ask_json(messages, SubheadingResolution, temperature=TEMP_RESOLVE)
    return _validate(res, code)


def _validate(res: SubheadingResolution, code: str) -> SubheadingResolution:
    """码必须真实存在于子树；否则标 ambiguous 并尝试模糊修正。"""
    store = get_store()
    h = store.get_heading(code)
    codes6, codes8 = set(), set()
    for _, n in _flatten_subtree(h.get("subheadings", [])):
        digits = n["code"].replace(".", "")
        codes8.add(n["code"])
        codes6.add(digits[:6])
    six = re.sub(r"\D", "", res.six_digit or "")[:6]
    if six not in codes6:
        # 模糊修正：前 4 位一致且 6 位前缀最接近的子目
        cands = [c for c in codes6 if c[:4] == code.replace(".", "")[:4]]
        alt = min(cands, key=lambda c: sum(a != b for a, b in zip(c, six))) if cands and six else None
        if alt:
            six = alt
            res.ambiguous = True
            res.reasoning += " [auto-corrected: model emitted a code not in the subtree]"
        else:
            six = ""
            res.ambiguous = True
    res.six_digit = six  # 无论哪条路径都写回归一化后的纯数字码
    eight = res.eight_digit
    if eight:
        eight = re.sub(r"[^0-9.]", "", eight)
        if eight not in codes8 and eight.replace(".", "") not in {c.replace(".", "") for c in codes8}:
            res.eight_digit = None  # 校验失败宁缺毋滥
    return res


def heuristic_six_digit(code: str, description: str) -> str:
    """无 LLM 的廉价六位猜测（仅用于 top-2/3 的 6 位评测口径）：
    在品目子树内用 BM25 选与描述最匹配的子目文本。"""
    from src.knowledge.retrieval import tokenize

    store = get_store()
    h = store.get_heading(code)
    flat = _flatten_subtree(h.get("subheadings", []))
    if not flat:
        return ""
    corpus = [tokenize(n["description"]) for _, n in flat]
    query = tokenize(description)
    if not any(corpus) or not query:
        depth0 = [n for d, n in flat if d == 0] or [n for _, n in flat]
        return depth0[0]["code"].replace(".", "")[:6]
    bm = BM25Okapi(corpus)
    best = int(np.argmax(bm.get_scores(query)))
    return flat[best][1]["code"].replace(".", "")[:6]
