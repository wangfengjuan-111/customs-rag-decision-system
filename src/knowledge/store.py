"""
ArtifactStore：运行时加载离线工件，提供论文式 O(1) 约束查找。

- get_heading(code) -> 品目完整记录
- clauses_for_heading(code) -> 约束该品目的全部条款（章注全章 + 精确命中）
- iter_headings() -> 全部品目
"""
import json
from functools import lru_cache

from config import ARTIFACTS, CLAUSES_JSONL, HEADINGS_JSON, HIERARCHY_JSON


class ArtifactStore:
    def __init__(self) -> None:
        self.headings: dict[str, dict] = {}
        self.clauses: dict[str, dict] = {}
        self.hierarchy: dict = {}

    def load(self) -> "ArtifactStore":
        for h in json.loads(HEADINGS_JSON.read_text(encoding="utf-8")):
            self.headings[h["heading"]] = h
        with open(CLAUSES_JSONL, encoding="utf-8") as f:
            for line in f:
                c = json.loads(line)
                self.clauses[c["clause_id"]] = c
        self.hierarchy = json.loads(HIERARCHY_JSON.read_text(encoding="utf-8"))
        return self

    def get_heading(self, code: str) -> dict | None:
        return self.headings.get(code)

    def iter_headings(self) -> list[dict]:
        return list(self.headings.values())

    def clauses_for_heading(self, code: str, groups: tuple[str, ...] = ("legal", "us_notes")) -> list[dict]:
        """约束某品目的条款：品目记录里挂的 clause_ids（建库时已合并章内全章条款+精确命中）。"""
        h = self.headings.get(code)
        if not h:
            return []
        return [self.clauses[cid] for cid in h.get("clause_ids", []) if cid in self.clauses]

    def clauses_by_type(self, code: str, ctype: str) -> list[dict]:
        return [c for c in self.clauses_for_heading(code) if c["ctype"] == ctype]

    def chapter_of(self, code: str) -> int:
        return int(code.replace(".", "")[:2])


@lru_cache(maxsize=1)
def get_store() -> ArtifactStore:
    return ArtifactStore().load()
