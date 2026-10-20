"""
合规知识库 RAG：美欧市场准入/认证要求问答。

知识库 = data/compliance/*.md（frontmatter: title/jurisdiction/authority/source/
fetched/category/review_status）。策展流程：半自动抓取官方页面 → LLM 结构化 →
人工审核（review_status: draft/reviewed）。

检索：复用主线的 BM25 词干化 + BGE 稠密 + RRF 融合，粒度 = markdown 二级标题
分块（块内保留 frontmatter 元数据，引用时给出来处与官方链接）。

为什么归类走确定性流水线而合规 RAG 就够（面试叙事）：
归类是一个封闭集合上的排序决策（~1250 个品目），错一个码就是错，需要可归因的
漏斗；合规模块是开放域的事实问答（"玩具进美国要什么认证"），答案由知识库
覆盖面决定，RAG 的检索+生成就是标准解法。

用法：
    python -m src.compliance.rag build    # 扫 data/compliance 建索引
    python -m src.compliance.rag query "selling plush toys to USA requirements"
"""
import json
import pickle
import re
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from rank_bm25 import BM25Okapi

from config import ARTIFACTS, DATA_COMPLIANCE, EMBED_QUERY_PREFIX
from src.knowledge.retrieval import tokenize

CHUNK_INDEX = ARTIFACTS / "compliance_chunks.pkl"
DENSE_NPY = ARTIFACTS / "compliance_dense.npy"

_FM = re.compile(r"^---\n(.*?)\n---\n", re.S)
_H2 = re.compile(r"^## ", re.M)


def load_chunks(min_chars: int = 120) -> list[dict]:
    """切分策展文档：frontmatter 元数据 + ## 二级标题分块。"""
    chunks: list[dict] = []
    for f in sorted(DATA_COMPLIANCE.glob("*.md")):
        text = f.read_text(encoding="utf-8")
        m = _FM.match(text)
        meta = {}
        if m:
            for line in m.group(1).splitlines():
                if ":" in line:
                    k, _, v = line.partition(":")
                    meta[k.strip()] = v.strip()
            body = text[m.end():]
        else:
            body = text
        sections = _H2.split(body)
        # sections[0] = 引言（无标题），其后成对 [title, content]
        pieces = [("(intro)", sections[0])] + list(zip(sections[1::2], sections[2::2]))
        for title, content in pieces:
            content = content.strip()
            if len(content) < min_chars:
                continue
            chunks.append(
                {
                    "doc": f.stem,
                    "section": title.strip(),
                    "text": content,
                    "title": meta.get("title", f.stem),
                    "jurisdiction": meta.get("jurisdiction", ""),
                    "authority": meta.get("authority", ""),
                    "source": meta.get("source", ""),
                    "category": meta.get("category", ""),
                    "review": meta.get("review_status", "draft"),
                }
            )
    return chunks


class ComplianceRAG:
    def __init__(self) -> None:
        self.chunks: list[dict] = []
        self.bm25: BM25Okapi | None = None
        self.dense: np.ndarray | None = None
        self._embedder = None

    def build(self) -> None:
        self.chunks = load_chunks()
        if not self.chunks:
            print("no compliance docs in", DATA_COMPLIANCE)
            return
        self.bm25 = BM25Okapi([tokenize(c["text"]) for c in self.chunks])
        with open(CHUNK_INDEX, "wb") as f:
            pickle.dump(self.chunks, f)
        self.dense = self._encode([c["text"] for c in self.chunks])
        np.save(DENSE_NPY, self.dense)
        print(f"compliance index built: {len(self.chunks)} chunks from {len({c['doc'] for c in self.chunks})} docs")

    def load(self) -> "ComplianceRAG":
        if not CHUNK_INDEX.exists():
            self.build()
            return self
        with open(CHUNK_INDEX, "rb") as f:
            self.chunks = pickle.load(f)
        self.bm25 = BM25Okapi([tokenize(c["text"]) for c in self.chunks])
        self.dense = np.load(DENSE_NPY)
        self._encode(["warmup"])  # 预热：同主检索器，避免首次查询卡固定开销
        return self

    def _encode(self, texts: list[str]) -> np.ndarray:
        if self._embedder is None:
            from sentence_transformers import SentenceTransformer

            from config import EMBED_MODEL

            self._embedder = SentenceTransformer(EMBED_MODEL, device="cpu")
        return np.asarray(self._embedder.encode(texts, normalize_embeddings=True))

    def search(self, query: str, top_k: int = 6) -> list[dict]:
        """RRF 融合两路，返回带出处的块。"""
        bm = self.bm25.get_scores(tokenize(query))
        bm_idx = np.argsort(bm)[::-1][: 3 * top_k]
        q = self._encode([EMBED_QUERY_PREFIX + query])[0]
        sims = self.dense @ q
        dn_idx = np.argsort(sims)[::-1][: 3 * top_k]
        rrf: dict[int, float] = defaultdict(float)
        for rank, i in enumerate(bm_idx):
            if bm[i] > 0:
                rrf[int(i)] += 1.0 / (60 + rank + 1)
        for rank, i in enumerate(dn_idx):
            rrf[int(i)] += 1.0 / (60 + rank + 1)
        top = sorted(rrf.items(), key=lambda x: -x[1])[:top_k]
        out = []
        for i, score in top:
            c = dict(self.chunks[i])
            c["rrf"] = round(score, 4)
            out.append(c)
        return out

    def answer(self, query: str, top_k: int = 6) -> dict:
        """检索 + DeepSeek 生成带引用的答案（合规问答入口）。"""
        hits = self.search(query, top_k)
        if not hits:
            return {"answer": "知识库暂未覆盖该问题。", "citations": []}
        ctx = "\n\n".join(
            f"[{i+1}] {h['title']} — {h['section']}\n{h['text']}" for i, h in enumerate(hits)
        )
        system = (
            "You answer market-access and product-compliance questions for cross-border "
            "e-commerce sellers, based ONLY on the provided knowledge base excerpts. "
            "Cite excerpt numbers [n] after each claim. If the excerpts don't cover the "
            "question, say so. Answer in the language of the question."
        )
        from src.llm.client import ask_json
        from pydantic import BaseModel

        class Answer(BaseModel):
            answer: str
            caveats: str = ""

        res = ask_json(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": f"Question: {query}\n\nKnowledge base:\n{ctx}"},
            ],
            Answer,
            temperature=0.1,
        )
        return {
            "answer": res.answer,
            "caveats": res.caveats,
            "citations": [
                {
                    "n": i + 1,
                    "title": h["title"],
                    "section": h["section"],
                    "authority": h["authority"],
                    "source": h["source"],
                    "review": h["review"],
                }
                for i, h in enumerate(hits)
            ],
        }


_rag: ComplianceRAG | None = None


def get_rag() -> ComplianceRAG:
    global _rag
    if _rag is None:
        _rag = ComplianceRAG().load()
    return _rag


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "build":
        ComplianceRAG().build()
    else:
        q = " ".join(sys.argv[1:]) or "what certification do plush toys need in the USA"
        rag = get_rag()
        for h in rag.search(q):
            print(f"[{h['rrf']}] {h['title']} / {h['section']}  ({h['authority']}, {h['jurisdiction']})")
