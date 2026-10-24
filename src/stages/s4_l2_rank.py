"""
Stage 4 · L2 精排（全流水线核心）：加载类注/章注 + 子目文本深度重排。

论文机制复刻：
- 排除条款降级：明确授权仅凭一条 exclusion 条款否掉表面强候选
- note-triggered confirmation：强制前三位承诺，结构化 pros/cons/GIR/引用
- 引用只能来自给定 clause_id 清单（groundedness：引用由工件库反查逐字原文，不是 LLM 自由发挥）

v3 改动（评测驱动：65% 错误是 kept_not_rank1，两大族群——珠宝 71 章内材质互混、
电子设备"功能 vs 类名"混淆）：
1. Context 按章分组：同章候选共享一份章注（原来 9× 重复烧预算），省出的预算
   给每品目加子目文本——材质/形态判据（7113 "Of silver"、7116 "natural, synthetic
   or reconstructed"）大多在子目层。
2. Prompt 注入 GIR 原则化的"客观特征优先"判据：材质组合决定珠宝归属、主功能
   决定机器设备归属（Section XVI Note 3）、8543 残差优先于牵强类比。
"""
from pydantic import BaseModel, Field

from config import N_L2_KEEP, TEMP_RANK
from src.knowledge.store import get_store
from src.llm.client import ask_json
from src.stages.s1_extract import Attributes

# 上下文预算
MAX_CH_CLAUSES = 14       # 每章展示的共享条款数
MAX_CH_CHARS = 2600       # 每章共享条款字符预算
MAX_SUBS = 8              # 每品目展示的子目行数
MAX_EXTRA = 4             # 每品目跨章引用条数

SYSTEM = (
    "You are the L2 ranker in an HS tariff classification pipeline. Unlike L1, you now see "
    "the legal context: for each candidate heading its text and subheadings, plus the "
    "section/chapter note clauses that constrain it (with clause ids and clause types).\n"
    "Rules of engagement:\n"
    "1. GIR 1 first: classification is determined by heading terms AND the relative section/"
    "chapter notes. A note exclusion is decisive.\n"
    "2. You are explicitly permitted — and expected — to demote or reject a candidate solely "
    "on the strength of one exclusion clause whose text covers the product, even when the "
    "heading text itself matches well.\n"
    "3. GIR 3(a): a heading that specifically names the product (or its form/material/function) "
    "beats a residual 'other' basket heading. GIR 3(b): composite goods go by essential character.\n"
    "4. Classify by OBJECTIVE CHARACTERISTICS — composition and function — never by product "
    "name or superficial analogy:\n"
    "   - Composition decides jewelry: body of precious metal or metal clad with precious "
    "metal → 7113; articles whose essential material is pearls or precious/semiprecious "
    "stones (natural, SYNTHETIC or reconstructed — synthetic zircon/CZ included) → 7116; "
    "base metal with imitation stones or no stones → 7117 'imitation jewelry'.\n"
    "   - Principal function decides machines and electronic devices (section XVI note 3, "
    "multifunction machines classify by principal function): a wrist-worn device that makes "
    "wireless calls is a telephone apparatus of 8517 (its text explicitly covers smartphones "
    "and other telephones for wireless networks), not a watch of 9102; a head unit whose "
    "principal role is navigation is 8526, not 8527. When no heading names the device's "
    "actual function, the electrical-machines residual 8543 beats a strained analogy to a "
    "specific apparatus heading.\n"
    "   - The marketed name ('smartwatch', 'car radio', 'fashion bracelet') is NOT evidence "
    "of classification; the heading and subheading terms are.\n"
    "5. Note-triggered confirmation: commit to the top 3 headings. For each kept heading record "
    "pros, cons, the GIR rules applied, and the load-bearing clause ids you relied on.\n"
    "6. Be TERSE: at most 2 items each of pros/cons, reason under 30 words. For candidates you "
    "reject as clearly irrelevant, emit only heading, kept=false and a one-line reason.\n"
    "Citations: only use clause ids from the provided context. Never invent clause ids."
)


class L2Entry(BaseModel):
    heading: str
    kept: bool = Field(description="true for the committed top-3, false if demoted/rejected")
    demoted_by_note: bool = Field(default=False, description="true if an exclusion clause was the decisive reason")
    pros: list[str] = Field(default_factory=list)
    cons: list[str] = Field(default_factory=list)
    gir_rules: list[str] = Field(default_factory=list, description="e.g. ['GIR1','GIR3a']")
    cited_clauses: list[str] = Field(default_factory=list, description="clause ids from the provided context")
    reason: str = ""


class L2Result(BaseModel):
    rankings: list[L2Entry]


def _prio() -> dict[str, int]:
    return {"exclusion": 0, "priority": 1, "inclusion": 2, "scope": 3, "definition": 4, "other": 5}


def _subheads(code: str) -> str:
    """直接子目文本（材质/形态判据大多在这一层）。"""
    h = get_store().get_heading(code)
    lines = [f"  {n['code']}  {n['description'][:90]}" for n in h.get("subheadings", [])[:MAX_SUBS]]
    return "\n".join(lines) if lines else "(none)"


def _context(codes: list[str]) -> str:
    """章注按章分组去重 + 每品目（条文/子目/跨章引用）。"""
    store = get_store()
    by_ch: dict[int, list[str]] = {}
    for c in codes:
        by_ch.setdefault(store.get_heading(c)["chapter"], []).append(c)

    parts: list[str] = []
    printed: set[str] = set()
    prio = _prio()
    for ch, group in by_ch.items():
        # 该组候选涉及的条款池（章级去重）
        pool: dict[str, dict] = {}
        for h in group:
            for c in store.clauses_for_heading(h):
                pool.setdefault(c["clause_id"], c)
        own = [c for cid, c in pool.items() if cid.startswith(f"ch{ch:02d}_")]
        own.sort(key=lambda c: prio.get(c["ctype"], 9))
        lines, budget = [], MAX_CH_CHARS
        for c in own[:MAX_CH_CLAUSES]:
            line = f'[{c["clause_id"]}|{c["ctype"]}] {c["text"]}'
            if len(line) > budget:
                break
            budget -= len(line) + 1
            lines.append(line)
            printed.add(c["clause_id"])
        if lines:
            parts.append(
                f"=== Chapter {ch} notes (shared by candidates {', '.join(group)}) ===\n" + "\n".join(lines)
            )
        # 品目块：条文 + 子目 + 提到本品目的跨章条款
        for h in group:
            extra = []
            for cid, c in pool.items():
                if cid in printed or cid.startswith(f"ch{ch:02d}_"):
                    continue
                if h in c["text"]:  # 他章排除/优先条款里点名本品目 → 章间判据
                    extra.append(f'[{cid}|{c["ctype"]}] {c["text"]}')
                    if len(extra) >= MAX_EXTRA:
                        break
            hd = store.get_heading(h)
            block = (
                f"=== heading {h} (chapter {ch}) ===\n"
                f"text: {hd['description']}\n"
                f"subheadings:\n{_subheads(h)}"
            )
            if extra:
                block += "\ncross-references:\n" + "\n".join(extra)
            parts.append(block)
    return "\n\n".join(parts)


def _ask_l2(description: str, attrs: Attributes, codes: list[str]) -> L2Result:
    user = (
        f"Product description: {description}\n"
        f"Attributes: {attrs.model_dump_json()}\n\n"
        f"Candidates with legal context:\n{_context(codes)}\n\n"
        f"Rank all {len(codes)} candidates; commit to exactly the top {N_L2_KEEP} as kept=true."
    )
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": user},
    ]
    return ask_json(messages, L2Result, temperature=TEMP_RANK)


def rank_l2(description: str, attrs: Attributes, candidates: list[str]) -> L2Result:
    """精排。漏打分候选重试一次（只发漏掉的）；仍缺由 _sanitize 补零分条目。"""
    result = _ask_l2(description, attrs, candidates)
    seen = {r.heading for r in result.rankings}
    missing = [c for c in candidates if c not in seen]
    if missing:
        retry = _ask_l2(description, attrs, missing)
        result.rankings.extend(r for r in retry.rankings if r.heading in missing and r.heading not in seen)
    return _sanitize(result, candidates)


def _sanitize(result: L2Result, candidates: list[str]) -> L2Result:
    """防幻觉：heading 必须在候选集、clause_id 必须真实存在（跨章引用直接丢弃）。"""
    store = get_store()
    valid = set(candidates)
    kept_entries = [r for r in result.rankings if r.heading in valid]
    # 缺失候补零分条目，保证归因完整性
    seen = {r.heading for r in kept_entries}
    for c in candidates:
        if c not in seen:
            kept_entries.append(L2Entry(heading=c, kept=False, reason="missing from model output"))
    for r in kept_entries:
        r.cited_clauses = [cid for cid in r.cited_clauses if cid in store.clauses]
    kept_entries.sort(key=lambda r: (not r.kept, -len(r.pros)))
    return L2Result(rankings=kept_entries)


def top3(result: L2Result) -> list[L2Entry]:
    kept = [r for r in result.rankings if r.kept][:N_L2_KEEP]
    if not kept:  # 模型没守约：取前 N 个
        kept = result.rankings[:N_L2_KEEP]
    return kept
