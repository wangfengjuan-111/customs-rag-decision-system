"""
Stage Attribution：每条 4 位 top-1 错例标注"首个丢失阶段"（论文 §IV-C 复刻）。

判定逻辑（按流水线顺序，取最早出错阶段）：
    S2                  gold 四位不在 ~40 召回里
    S3                  在召回里但 L1 粗排掉出 ~10
    S4_kept_not_rank1   L2 保留了 gold（在 top-3）但没排第一   ← 论文 65% 主错误模式
    S4_dropped_by_note  L2 把 gold 剔除且标注是排除条款所致  ← 本架构的价值指标
    S4_dropped_other    L2 剔除但非注释原因
    S5                  四位对、六位错
产出：分布表 + 与论文对照。
"""
import json
import sys
from pathlib import Path
from collections import Counter

from config import ARTIFACTS

RESULTS = ARTIFACTS / "eval_results.jsonl"


def attribute(rec: dict) -> str:
    gold4 = rec["gold"][:4]
    pred4 = rec["codes_4d"][0] if rec["codes_4d"] else ""
    if gold4 == pred4:
        # 4 位对，看 6 位
        pred6 = (rec["codes_6d"] or [""])[0][:6]
        return "none" if rec["gold"][:6] == pred6 else "S5"
    if gold4 not in rec["s2_candidates"]:
        return "S2"
    if gold4 not in rec["s3_shortlist"]:
        return "S3"
    entry = next((e for e in rec["s4_rankings"] if e["heading"] == gold4), None)
    if entry is None:
        return "S4_missing"
    if entry.get("kept"):
        return "S4_kept_not_rank1"
    return "S4_dropped_by_note" if entry.get("demoted_by_note") else "S4_dropped_other"


def main(results_file=None) -> None:
    recs = [json.loads(l) for l in open(results_file or RESULTS, encoding="utf-8")]
    n = len(recs)
    if not n:
        print("no results")
        return
    wrong4 = [r for r in recs if r["gold"][:4] != (r["codes_4d"][0] if r["codes_4d"] else "")]
    dist = Counter(attribute(r) for r in recs)
    wrong_dist = Counter(attribute(r) for r in wrong4)
    print(f"n={n}  (4-digit top-1 errors: {len(wrong4)})")
    print("\n全部归因分布（含正确 none）：")
    for k, v in sorted(dist.items()):
        print(f"  {k:20s} {v:4d}  {v/n:.1%}")
    print("\n错例归因分布（对照论文：65% 在 L2 保留未排第一）：")
    for k, v in sorted(wrong_dist.items()):
        print(f"  {k:20s} {v:4d}  {v/len(wrong4):.1%}")
    # 输出跟输入走：分析归档文件时写 *.vN.json/png，不覆盖在用结果
    stem = Path(results_file).stem if results_file else "attribution"
    out = ARTIFACTS / f"{stem}.json"
    out.write_text(json.dumps({"n": n, "all": dict(dist), "errors": dict(wrong_dist)}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nsaved -> {out}")
    if wrong_dist:
        plot(wrong_dist, len(wrong4), ARTIFACTS / f"{stem}.png")


def plot(wrong_dist: dict[str, int], n_errors: int, out_path) -> None:
    """错例归因分布图（与论文 §IV-C 对照的条形图）。"""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False

    labels = {
        "S2": "S2 recall\n(检索未召回)",
        "S3": "S3 L1\n(粗排淘汰)",
        "S4_kept_not_rank1": "S4 kept\n(在top-3未排第一)",
        "S4_dropped_by_note": "S4 dropped\n(排除条款降级)",
        "S4_dropped_other": "S4 dropped\n(其他原因剔除)",
        "S5": "S5\n(四位对六位错)",
    }
    items = [(labels.get(k, k), v) for k, v in sorted(wrong_dist.items())]
    xs = [i for i, _ in enumerate(items)]
    ys = [v / n_errors for _, v in items]
    fig, ax = plt.subplots(figsize=(7, 4))
    bars = ax.bar(xs, [v for _, v in items], color="#4C72B0")
    for x, y, (_, cnt) in zip(xs, ys, items):
        ax.text(x, cnt + 0.1, f"{cnt}\n{y:.0%}", ha="center", va="bottom", fontsize=9)
    ax.set_xticks(xs)
    ax.set_xticklabels([l for l, _ in items], fontsize=8)
    ax.set_ylabel("error share")
    ax.set_title(f"First-failure-stage attribution (n={n_errors} 4-digit errors)")
    ax.set_ylim(0, max(v for _, v in items) * 1.35)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    print(f"plot -> {out_path}")


if __name__ == "__main__":
    # 可传入历史结果文件：python -m src.eval.attribution artifacts/eval_results.v1.jsonl
    main(sys.argv[1] if len(sys.argv) > 1 else None)
