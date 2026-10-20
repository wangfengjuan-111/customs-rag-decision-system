"""
Stage 2 · 候选检索：原文 + S1 属性双查询，RRF 合并，出 ~64 个品目候选。

只求召回不求精度，后续阶段判别（论文：手动调检索权重不如改 ranker prompt）。

两项召回保障（70 条评测错例归因驱动，48% 错误是 S2 漏召回）：
1. 跨查询按真实 RRF 分数累加（而非出现次数），保留各查询内的排序信息；
2. 残差品目注入：GIR 1(b) 逻辑——商品与任何具体品目条文都不匹配时落入
   "other articles of X"。残差品目的条文文本（"其他塑料制品"）与商品描述
   语义距离远，检索永远排不上来；但只要同章的兄弟品目被召回，就应把该章
   残差品目补进候选，交给 S3/S4 判别。
"""
import re
from collections import defaultdict

from config import N_RETRIEVE
from src.knowledge.retrieval import get_retriever
from src.stages.s1_extract import Attributes, to_query_text

# 文本不是 "Other articles of X" 措辞、但同为章内残差的品目（纺织/纸/印刷品）
_EXTRA_RESIDUALS = {"6307", "6217", "6117", "4823", "4911"}
_RESIDUAL_RE = re.compile(r"^other articles of\b", re.I)

_residual_by_chapter: dict[int, list[str]] | None = None


def _residuals() -> dict[int, list[str]]:
    """章号 → 该章的残差品目（"Other articles of X" 等），从 headings.json 派生一次并缓存。"""
    global _residual_by_chapter
    if _residual_by_chapter is None:
        from src.knowledge.store import get_store

        out: dict[int, list[str]] = defaultdict(list)
        for h in get_store().iter_headings():
            code = h["heading"].replace(".", "")[:4]
            if _RESIDUAL_RE.match((h.get("description") or "").strip()) or code in _EXTRA_RESIDUALS:
                out[h["chapter"]].append(code)
        _residual_by_chapter = dict(out)
    return _residual_by_chapter


def retrieve(description: str, attrs: Attributes | None = None, top_k: int = N_RETRIEVE) -> list[str]:
    """双查询（原文 + 属性摘要）各出 top_k，RRF 分数累加合并取前 top_k，再注入残差品目。"""
    queries = [q for q in (description, to_query_text(attrs) if attrs else "") if q]
    rrf: dict[str, float] = defaultdict(float)
    retriever = get_retriever()
    for q in queries:
        for h, s in retriever.search(q, top_k=top_k):
            rrf[h] += s
    ranked = [h for h, _ in sorted(rrf.items(), key=lambda x: -x[1])]
    if len(ranked) > top_k:
        ranked = ranked[:top_k]

    # 残差注入：top-8 候选所在章的残差品目若缺席则补位（GIR 1(b) 兜底）
    seen_chapters = {h[:2] for h in ranked[:8]}
    injected = False
    for ch in sorted(seen_chapters):
        for res in _residuals().get(int(ch), []):
            if res not in ranked:
                ranked.append(res)
                injected = True
    return ranked
