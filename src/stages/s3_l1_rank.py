"""
Stage 3 · L1 粗排：LLM 只看品目条文（不加载注释），对属性打分，留 ~10 个候选。

设计意图（论文）：先廉价判别，再加载昂贵的章注上下文。
"""
from pydantic import BaseModel, Field

from config import N_L1_KEEP, TEMP_RANK
from src.knowledge.store import get_store
from src.llm.client import ask_json
from src.stages.s1_extract import Attributes

SYSTEM = (
    "You are the L1 ranker in an HS tariff classification pipeline. "
    "You see ONLY the heading texts of candidate headings — chapter/section notes are NOT "
    "available at this stage. Given the product description and extracted attributes, score "
    "each heading from 0 to 10 on how well its text describes the product: 10 = the heading "
    "text clearly covers this product; 0 = unrelated. This is semantic matching only; do not "
    "try to apply legal rules. You must score every heading in the list."
)


class L1Entry(BaseModel):
    heading: str = Field(description="4-digit heading code, copied from the input list")
    score: int = Field(ge=0, le=10)
    reason: str = Field(default="", description="one short phrase")


class L1Ranking(BaseModel):
    rankings: list[L1Entry]


def _heading_lines(codes: list[str]) -> str:
    store = get_store()
    lines = []
    for c in codes:
        h = store.get_heading(c)
        desc = (h["description"] if h else "unknown")[:140]
        lines.append(f"{c}: {desc}")
    return "\n".join(lines)


def rank_l1(description: str, attrs: Attributes, candidates: list[str]) -> list[L1Entry]:
    """返回按分数降序的完整打分列表（调用方取前 N_L1_KEEP）。"""
    user = (
        f"Product description: {description}\n"
        f"Attributes: {attrs.model_dump_json()}\n\n"
        f"Candidate headings:\n{_heading_lines(candidates)}\n\n"
        f"Score all {len(candidates)} headings as JSON."
    )
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": user},
    ]
    result = ask_json(messages, L1Ranking, temperature=TEMP_RANK)
    # 防幻觉：只保留候选集内的打分，缺失的候选拼在末尾给最低分
    by_code = {r.heading: r for r in result.rankings if r.heading in candidates}
    filled = [by_code.get(c, L1Entry(heading=c, score=0, reason="missing from model output")) for c in candidates]
    filled.sort(key=lambda r: -r.score)
    return filled


def shortlist(ranked: list[L1Entry], keep: int = N_L1_KEEP) -> list[str]:
    return [r.heading for r in ranked[:keep]]
