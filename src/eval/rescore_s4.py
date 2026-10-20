"""
S4 离线重打分：复用评测结果里已存的 S3 shortlist 与 S1 属性，只重跑 S4。

用途：S4 prompt 改动的快速 before/after 验证，不用全流水线重跑（S1-S3 免计费）。
"before" = 结果文件里已存的 codes_4d（上次完整评测的 S4 输出），"after" = 本次重跑。

用法：
    python -m src.eval.rescore_s4                       # 对 eval_results.jsonl
    python -m src.eval.rescore_s4 artifacts/foo.jsonl   # 指定文件
"""
import json
import sys

from config import ARTIFACTS
from src.stages.s1_extract import Attributes
from src.stages import s4_l2_rank


def rescore(path) -> None:
    recs = [json.loads(l) for l in open(path, encoding="utf-8")]
    ok_before = t3_before = ok_after = t3_after = 0
    fixed, broken = [], []
    for i, r in enumerate(recs):
        shortlist = r.get("s3_shortlist") or []
        if not shortlist:
            continue
        attrs = Attributes(**r["attributes"]) if r.get("attributes") else None
        l2 = s4_l2_rank.rank_l2(r["description"], attrs, shortlist)
        new4 = [e.heading for e in s4_l2_rank.top3(l2)]
        gold4 = r["gold"][:4]
        old4 = r.get("codes_4d") or []
        ok_before += gold4 == (old4[0] if old4 else "")
        t3_before += gold4 in old4
        ok_after += gold4 == (new4[0] if new4 else "")
        t3_after += gold4 in new4
        if gold4 not in old4 and gold4 in new4:
            fixed.append((r["gold"][:4], new4[0], r["description"][:50]))
        if gold4 in old4 and gold4 not in new4:
            broken.append((r["gold"][:4], new4[0], r["description"][:50]))
        print(f"[{i+1}/{len(recs)}] gold {gold4} old {old4[:2]} new {new4[:2]}")

    n = len(recs)
    print(f"\nS4 top1: {ok_before}/{n} = {ok_before/n:.1%}  →  {ok_after}/{n} = {ok_after/n:.1%}")
    print(f"S4 top3: {t3_before}/{n} = {t3_before/n:.1%}  →  {t3_after}/{n} = {t3_after/n:.1%}")
    print(f"\nfixed ({len(fixed)}):")
    for g, p, d in fixed:
        print(f"  +{g} (was {p}) | {d}")
    print(f"broken ({len(broken)}):")
    for g, p, d in broken:
        print(f"  -{g} (now {p}) | {d}")


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else ARTIFACTS / "eval_results.jsonl"
    rescore(path)
