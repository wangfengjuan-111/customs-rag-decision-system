"""
HSCodeComp 评测：批量跑流水线，落盘 JSONL，断点续跑。

用法：
    python -m src.eval.run_eval 20          # 前 20 条
    python -m src.eval.run_eval 50 --seed 7 # 抽样 50 条
    python -m src.eval.run_eval all         # 全量 632
    python -m src.eval.run_eval report      # 只汇总已有结果

产出：artifacts/eval_results.jsonl（每行一条完整 PipelineResult + gold）
"""
import json
import random
import re
import sys
import time

from config import ARTIFACTS, DATA_HSCODES

RESULTS = ARTIFACTS / "eval_results.jsonl"


def load_rows() -> list[dict]:
    return [json.loads(l) for l in open(DATA_HSCODES / "hstest.jsonl", encoding="utf-8")]


def gold_digits(hs_code) -> str:
    return str(hs_code).zfill(10).replace(".", "").replace("-", "")


def digits6(code: str) -> str:
    """六位归一化：去点线取前六位（历史结果里 S5 曾存带点码，比较前必须归一）。"""
    return re.sub(r"\D", "", code or "")[:6]


def run(n: int | str, seed: int | None = None) -> None:
    rows = load_rows()
    if seed is not None:
        rng = random.Random(seed)
        rows = rng.sample(rows, int(n))
    elif n != "all":
        rows = rows[: int(n)]

    done = set()
    if RESULTS.exists():
        for line in open(RESULTS, encoding="utf-8"):
            try:
                done.add(json.loads(line)["task_id"])
            except (json.JSONDecodeError, KeyError):
                continue

    from src.stages.pipeline import classify

    ok4 = t3_4 = ok6 = t3_6 = n_done = 0
    t0 = time.time()
    for i, row in enumerate(rows):
        if row["task_id"] in done:
            continue
        try:
            r = classify(row["product_name"], row.get("product_attributes") or "")
        except Exception as e:  # noqa: BLE001
            print(f"[{i}] FAIL {row['task_id']}: {e}")
            continue
        rec = r.to_dict()
        rec["task_id"] = row["task_id"]
        rec["gold"] = gold_digits(row["hs_code"])
        with open(RESULTS, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        # 实时指标
        g4, g6 = rec["gold"][:4], rec["gold"][:6]
        c4, c6 = rec["codes_4d"], [digits6(c) for c in rec["codes_6d"]]
        ok4 += g4 == (c4[0] if c4 else "")
        t3_4 += g4 in c4
        ok6 += g6 == (c6[0] if c6 else "")
        t3_6 += g6 in c6
        n_done += 1
        if n_done % 5 == 0:
            rate = n_done / (time.time() - t0)
            print(
                f"[{i+1}/{len(rows)}] 4d top1={ok4/n_done:.1%} top3={t3_4/n_done:.1%} | "
                f"6d top1={ok6/n_done:.1%} top3={t3_6/n_done:.1%} | {rate:.1f} it/s"
            )
    print(f"new: {n_done}, total in file: {len(done) + n_done}")


def report() -> None:
    recs = [json.loads(l) for l in open(RESULTS, encoding="utf-8")]
    n = len(recs)
    if not n:
        print("no results yet")
        return
    ok4 = sum(r["gold"][:4] == (r["codes_4d"][0] if r["codes_4d"] else "") for r in recs)
    t34 = sum(r["gold"][:4] in r["codes_4d"] for r in recs)
    c6s = [[digits6(c) for c in (r["codes_6d"] or [])] for r in recs]
    ok6 = sum(r["gold"][:6] == (c[0] if c else "") for r, c in zip(recs, c6s))
    t36 = sum(r["gold"][:6] in c for r, c in zip(recs, c6s))
    amb = sum(1 for r in recs if r.get("ambiguous"))
    print(f"n={n}")
    print(f"4-digit: top1={ok4/n:.1%}  top3={t34/n:.1%}   (paper: 75.0% / 91.5%)")
    print(f"6-digit: top1={ok6/n:.1%}  top3={t36/n:.1%}   (paper: 64.2% / 78.3%)")
    print(f"ambiguous flagged: {amb}/{n}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "report":
        report()
    else:
        n = sys.argv[1] if len(sys.argv) > 1 else "20"
        seed = int(sys.argv[sys.argv.index("--seed") + 1]) if "--seed" in sys.argv else None
        run(n, seed)
