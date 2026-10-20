"""
Stage 6 · 最终评分 + 结构化引用：产出可审计的最终输出。

输出 schema 对应论文的 correctness/groundedness 两轴：
- 每个候选码带置信度、pro、con、GIR 条款
- 引用是 clause_id（经工件库校验后反查逐字原文），并标注承重子句
- final_code 经过子树校验；对不上时输出 four_digit 并标 ambiguous
"""
from pydantic import BaseModel, Field

from config import TEMP_SCORE
from src.knowledge.store import get_store
from src.llm.client import ask_json
from src.stages.s1_extract import Attributes
from src.stages.s4_l2_rank import L2Entry
from src.stages.s5_subheading import SubheadingResolution

SYSTEM = (
    "You produce the FINAL auditable classification verdict. You receive the L2 shortlist "
    "(with pros/cons/citations) and the subheading resolution. Emit the top-3 candidate codes "
    "in rank order. For rank 1 give the definitive verdict; ranks 2-3 are alternatives.\n"
    "For each candidate: confidence (0-1), the single strongest pro and con, the GIR rules "
    "applied, and the load-bearing clause ids you actually relied on (only from the provided "
    "ids). Also state which quoted clause was decisive (load_bearing_clause for rank 1)."
)


class FinalCandidate(BaseModel):
    rank: int = Field(ge=1, le=3)
    heading: str
    six_digit: str = Field(default="", description="digits only; empty for alternatives beyond rank 1")
    eight_digit: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    pro: str
    con: str
    gir_rules: list[str] = Field(default_factory=list)
    cited_clauses: list[str] = Field(default_factory=list)


class FinalVerdict(BaseModel):
    candidates: list[FinalCandidate]
    load_bearing_clause: str | None = Field(default=None, description="clause id of the decisive rule for rank 1")
    ambiguous: bool = False
    summary: str = ""


def score(description: str, attrs: Attributes, shortlist: list[L2Entry], resolution: SubheadingResolution | None) -> FinalVerdict:
    sl_text = "\n".join(
        f"#{i+1} {e.heading} kept={e.kept} demoted_by_note={e.demoted_by_note}\n"
        f"   pros: {e.pros}\n   cons: {e.cons}\n   GIR: {e.gir_rules}\n   clauses: {e.cited_clauses}"
        for i, e in enumerate(shortlist)
    )
    res_text = (
        f"Subheading resolution: six={resolution.six_digit} eight={resolution.eight_digit} "
        f"ambiguous={resolution.ambiguous}\n  reasoning: {resolution.reasoning}"
        if resolution
        else "Subheading resolution unavailable."
    )
    user = (
        f"Product description: {description}\n"
        f"Attributes: {attrs.model_dump_json()}\n\n"
        f"L2 shortlist:\n{sl_text}\n\n{res_text}\n\n"
        f"Produce the final verdict as JSON."
    )
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": user},
    ]
    verdict = ask_json(messages, FinalVerdict, temperature=TEMP_SCORE)
    return sanitize(verdict, shortlist, resolution)


def sanitize(verdict: FinalVerdict, shortlist: list[L2Entry], resolution: SubheadingResolution | None) -> FinalVerdict:
    store = get_store()
    valid_headings = {e.heading for e in shortlist}
    all_clause_ids = {cid for e in shortlist for cid in e.cited_clauses}
    kept: list[FinalCandidate] = []
    for c in verdict.candidates:
        if c.heading not in valid_headings:
            continue
        c.cited_clauses = [cid for cid in c.cited_clauses if cid in all_clause_ids]
        if c.rank == 1 and resolution and not resolution.ambiguous:
            c.six_digit = resolution.six_digit or c.six_digit
            c.eight_digit = resolution.eight_digit or c.eight_digit
        kept.append(c)
    kept.sort(key=lambda c: c.rank)
    # 承重条款必须真实存在
    if verdict.load_bearing_clause and verdict.load_bearing_clause not in all_clause_ids:
        verdict.load_bearing_clause = None
    verdict.candidates = kept[:3]
    if resolution and resolution.ambiguous:
        verdict.ambiguous = True
    return verdict


def citations_verbatim(cited: list[str]) -> list[dict]:
    """clause_id → 逐字原文（groundedness 由工件库保证）。"""
    store = get_store()
    out = []
    for cid in cited:
        c = store.clauses.get(cid)
        if c:
            out.append({"clause_id": cid, "type": c["ctype"], "text": c["text"]})
    return out
