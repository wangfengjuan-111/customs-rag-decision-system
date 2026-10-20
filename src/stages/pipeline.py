"""
六阶段流水线总装：确定性控制流，LLM 只在窄阶段调用。

classify(description, attributes_json, on_stage) -> PipelineResult
所有中间态都留在结果对象里——评测的 stage attribution 和前端"漏斗可视化"都靠它。

时延结构：S1→S3→S4→S6 必须串行（后级吃前级输出），S5 的 top-3 解析互相独立
走线程池并行（墙钟 ≈ 单次调用）。on_stage 回调把阶段进度透出去（CLI 打印 /
前端 st.status），顺带记录各阶段耗时。
"""
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from src.stages import s1_extract, s2_retrieve, s3_l1_rank, s4_l2_rank, s5_subheading, s6_score


@dataclass
class PipelineResult:
    description: str
    attributes: dict = field(default_factory=dict)
    s2_candidates: list[str] = field(default_factory=list)   # ~40
    s3_ranked: list[dict] = field(default_factory=list)      # 全量打分
    s3_shortlist: list[str] = field(default_factory=list)    # ~10
    s4_rankings: list[dict] = field(default_factory=list)    # 全量含 kept/demoted
    s4_top3: list[dict] = field(default_factory=list)
    s5_resolution: dict = field(default_factory=dict)
    s6_verdict: dict = field(default_factory=dict)
    # 评测口径
    codes_4d: list[str] = field(default_factory=list)        # top-3 四位
    codes_6d: list[str] = field(default_factory=list)        # top-3 六位
    code_8d: str | None = None
    ambiguous: bool = False
    timings: dict[str, float] = field(default_factory=dict)  # 各阶段秒数


def classify(
    description: str,
    attributes_json: str = "",
    on_stage: "callable | None" = None,
) -> PipelineResult:
    """跑通六阶段。attributes_json: 卖家结构化属性（可为空）；on_stage(stage_name) 报进度。"""
    t_total = time.time()
    res = PipelineResult(description=description)

    def stage(name: str, fn, *a, **kw):
        t0 = time.time()
        if on_stage:
            on_stage(name)
        out = fn(*a, **kw)
        res.timings[name] = round(time.time() - t0, 2)
        return out

    # S1 属性抽取
    attrs = stage("S1 属性抽取", s1_extract.extract, description, attributes_json)
    res.attributes = attrs.model_dump()

    # S2 候选检索（~64）
    res.s2_candidates = stage("S2 候选检索", s2_retrieve.retrieve, description, attrs)

    # S3 L1 粗排（~10）
    l1_ranked = stage("S3 L1 粗排", s3_l1_rank.rank_l1, description, attrs, res.s2_candidates)
    res.s3_ranked = [r.model_dump() for r in l1_ranked]
    res.s3_shortlist = s3_l1_rank.shortlist(l1_ranked)

    # S4 L2 精排（top-3 承诺）
    l2 = stage("S4 L2 精排（章注+子目）", s4_l2_rank.rank_l2, description, attrs, res.s3_shortlist)
    res.s4_rankings = [r.model_dump() for r in l2.rankings]
    top3 = s4_l2_rank.top3(l2)
    res.s4_top3 = [r.model_dump() for r in top3]
    res.codes_4d = [e.heading for e in top3]

    # S5 子目解析：top-3 互相独立，线程池并行（GIR 6），失败/空码回退子树内 BM25 启发式
    all_clause_cited = [cid for e in top3 for cid in e.cited_clauses]
    resolution = None
    if top3:
        if on_stage:
            on_stage("S5 子目解析（并行）")

        def _safe_resolve(heading: str):
            try:
                return s5_subheading.resolve(heading, description, attrs)
            except Exception:  # noqa: BLE001 评测跑批不因单条解析失败中断
                return None

        t0 = time.time()
        with ThreadPoolExecutor(max_workers=3) as pool:
            resolved = list(pool.map(_safe_resolve, [e.heading for e in top3]))
        res.timings["S5 子目解析"] = round(time.time() - t0, 2)

        if resolved[0] is None:  # top-1 解析失败：与旧版一致，整体失败交给上层重试
            raise RuntimeError("S5 resolution failed for top-1 heading")
        resolution = resolved[0]
        res.s5_resolution = resolution.model_dump()
        res.codes_6d = [resolution.six_digit] if resolution.six_digit else []
        for r_i, e in zip(resolved[1:], top3[1:]):
            h6 = r_i.six_digit if r_i else ""
            if not h6:
                h6 = s5_subheading.heuristic_six_digit(e.heading, description)
            if h6:
                res.codes_6d.append(h6)
        res.code_8d = resolution.eight_digit

    # S6 最终评分+引用
    verdict = stage("S6 评分与引用", s6_score.score, description, attrs, top3, resolution)
    res.s6_verdict = verdict.model_dump()
    res.ambiguous = verdict.ambiguous or (resolution.ambiguous if resolution else True)
    # 逐字引用（groundedness 反查）
    res.s6_verdict["citations_verbatim"] = s6_score.citations_verbatim(all_clause_cited)
    res.timings["total"] = round(time.time() - t_total, 2)
    return res


if __name__ == "__main__":
    import sys

    desc = sys.argv[1] if len(sys.argv) > 1 else (
        "50 pcs HD hydrogel film for all phones, matte / anti-blue-ray / UV / privacy, TPU material"
    )

    def _p(name):
        print(f"… {name}", flush=True)

    r = classify(desc, on_stage=_p)
    print("各阶段耗时:", r.timings)
    print("S2 candidates:", r.s2_candidates[:10], "...")
    print("S3 shortlist:", r.s3_shortlist)
    print("S4 top3:", [(e["heading"], e["demoted_by_note"]) for e in r.s4_top3])
    print("S5:", r.s5_resolution)
    print("codes_4d:", r.codes_4d, "codes_6d:", r.codes_6d, "8d:", r.code_8d)
    print("ambiguous:", r.ambiguous)
    for c in r.s6_verdict.get("citations_verbatim", [])[:3]:
        print(f"  cite [{c['clause_id']}|{c['type']}] {c['text'][:90]}")
