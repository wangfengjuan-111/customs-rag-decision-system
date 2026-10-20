"""
双路检索：BM25（词法，接罕见具体名词）+ BGE 稠密（接功能改述），RRF 无权重融合。

- build_indices(): 离线构建（BM25 pickle + dense npy），~1220 条品目文档
- search(): 在线查询，返回 RRF 融合后的品目候选

检索文档粒度 = 四位品目：heading 描述 + 子目描述（retrieval_text 已拼接）。
dense 查询侧加 BGE 指令前缀（model card 要求）。

用法：
    python -m src.knowledge.retrieval build   # 构建索引
    python -m src.knowledge.retrieval query "TPU hydrogel film screen protector"
"""
import json
import pickle
import re
import sys

import numpy as np
from rank_bm25 import BM25Okapi

from config import (
    ARTIFACTS,
    BM25_INDEX,
    DENSE_META_JSON,
    DENSE_NPY,
    EMBED_MODEL,
    EMBED_QUERY_PREFIX,
    N_RETRIEVE,
)

RE_TOKEN = re.compile(r"[a-z0-9]+")
RE_CJK = re.compile(r"[一-鿿]")

# 轻量词干化：ies→y（batteries→battery）、s 剥离（Porter 式 es 规则）、双辅音收缩（knitted→knit）
_SXZCHSH = ("s", "x", "z", "ch", "sh")
_SUF = ("ing", "ers", "ed")


def _stem(w: str) -> str:
    if len(w) <= 3:
        return w
    if w.endswith("ies") and len(w) > 4:
        return w[:-3] + "y"
    for suf in _SUF:
        if w.endswith(suf):
            base = w[: -len(suf)]
            if len(base) >= 3:
                if len(base) >= 4 and base[-1] == base[-2] and base[-1] not in "lsf":
                    base = base[:-1]
                return base
            return w
    if w.endswith("es"):
        stem2 = w[:-2]
        if stem2.endswith(_SXZCHSH) and len(stem2) >= 3:
            return stem2
        return w[:-1]  # articles→article
    if w.endswith("s") and not w.endswith("ss") and len(w) > 3:
        return w[:-1]
    return w


def tokenize(text: str) -> list[str]:
    """英文走词干化；CJK 字符切 bigram（合规库有中文内容，bge-en 对中文无效，靠 BM25 接住）。"""
    t = text.lower()
    toks = [_stem(w) for w in RE_TOKEN.findall(t)]
    cjk = RE_CJK.findall(t)
    toks += [cjk[i] + cjk[i + 1] for i in range(len(cjk) - 1)]
    return toks


class DualRetriever:
    def __init__(self) -> None:
        self.docs: list[dict] = []      # [{heading, description, retrieval_text}]
        self.bm25: BM25Okapi | None = None
        self.dense: np.ndarray | None = None
        self._embedder = None           # 惰性加载

    # ── 构建 ──
    def build(self) -> None:
        from src.knowledge.store import get_store

        store = get_store()
        # 章描述拼入检索文档：给残差品目（3926 等）补材质命中面
        meta = {}
        meta_file = ARTIFACTS / "chapters_meta.json"
        if meta_file.exists():
            for m in json.loads(meta_file.read_text(encoding="utf-8")):
                meta[m["chapter"]] = f'{m["title"]} {m["description"]}'
        self.docs = [
            {
                "heading": h["heading"],
                "description": h["description"],
                "retrieval_text": (meta.get(h["chapter"], "") + " " + (h["retrieval_text"] or h["description"])).strip(),
            }
            for h in store.iter_headings()
        ]
        corpus = [tokenize(d["retrieval_text"]) for d in self.docs]
        self.bm25 = BM25Okapi(corpus)
        with open(BM25_INDEX, "wb") as f:
            pickle.dump(self.docs, f)
        print(f"BM25 built: {len(self.docs)} docs")

        self.dense = self._encode([d["retrieval_text"] for d in self.docs], prefix="")
        np.save(DENSE_NPY, self.dense)
        DENSE_META_JSON.write_text(
            json.dumps([d["heading"] for d in self.docs]), encoding="utf-8"
        )
        print(f"dense built: shape={self.dense.shape}")

    # ── 加载 ──
    def load(self) -> "DualRetriever":
        with open(BM25_INDEX, "rb") as f:
            self.docs = pickle.load(f)
        # BM25Okapi 不落盘，从文档秒级重建
        corpus = [tokenize(d["retrieval_text"]) for d in self.docs]
        self.bm25 = BM25Okapi(corpus)
        self.dense = np.load(DENSE_NPY)
        self._warmup()
        return self

    def _warmup(self) -> None:
        """首次 encode 在部分 Windows/torch 组合上有 ~40s 固定开销，加载时预热掉。"""
        import time

        t0 = time.time()
        self._encode(["warmup"], prefix=EMBED_QUERY_PREFIX)
        if time.time() - t0 > 3:
            print(f"[retriever] 模型预热完成 ({time.time()-t0:.1f}s，仅启动时一次)")

    # ── embedding ──
    def _embedder_model(self):
        if self._embedder is None:
            from sentence_transformers import SentenceTransformer

            self._embedder = SentenceTransformer(EMBED_MODEL, device="cpu")
        return self._embedder

    def _encode(self, texts: list[str], prefix: str) -> np.ndarray:
        model = self._embedder_model()
        if prefix:
            texts = [prefix + t for t in texts]
        return np.asarray(model.encode(texts, batch_size=64, show_progress_bar=len(texts) > 100, normalize_embeddings=True))

    # ── 查询 ──
    def _bm25_top(self, query: str, k: int) -> list[tuple[str, float]]:
        scores = self.bm25.get_scores(tokenize(query))
        idx = np.argsort(scores)[::-1][:k]
        return [(self.docs[i]["heading"], float(scores[i])) for i in idx if scores[i] > 0]

    def _dense_top(self, query: str, k: int) -> list[tuple[str, float]]:
        q = self._encode([query], prefix=EMBED_QUERY_PREFIX)[0]
        sims = self.dense @ q
        idx = np.argsort(sims)[::-1][:k]
        return [(self.docs[i]["heading"], float(sims[i])) for i in idx]

    def search(self, query: str, top_k: int = N_RETRIEVE, return_scores: bool = False):
        """RRF 融合两路检索。返回 [(heading, rrf_score)] 或带分路得分的明细。"""
        bm = self._bm25_top(query, 50)
        dn = self._dense_top(query, 50)
        rrf: dict[str, float] = {}
        detail: dict[str, dict] = {}
        K = 60  # RRF 常数
        for rank, (h, s) in enumerate(bm):
            rrf[h] = rrf.get(h, 0.0) + 1.0 / (K + rank + 1)
            detail.setdefault(h, {})["bm25"] = s
            detail[h]["bm25_rank"] = rank + 1
        for rank, (h, s) in enumerate(dn):
            rrf[h] = rrf.get(h, 0.0) + 1.0 / (K + rank + 1)
            detail.setdefault(h, {})["dense"] = s
            detail[h]["dense_rank"] = rank + 1
        fused = sorted(rrf.items(), key=lambda x: -x[1])[:top_k]
        if return_scores:
            return [(h, detail[h]) for h, _ in fused]
        return fused


_retriever: DualRetriever | None = None


def get_retriever() -> DualRetriever:
    global _retriever
    if _retriever is None:
        _retriever = DualRetriever().load()
    return _retriever


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "build":
        DualRetriever().build()
    else:
        q = sys.argv[1] if len(sys.argv) > 1 else "TPU hydrogel film screen protector for all phones"
        r = get_retriever()
        from src.knowledge.store import get_store

        store = get_store()
        for h, det in r.search(q, return_scores=True)[:10]:
            print(f"{h}  {store.get_heading(h)['description'][:70]}  {det}")
