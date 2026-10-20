"""
下载 HSCodeComp 评测集（HuggingFace ATH-MaaS/HSCodeComp，632 条）
转存为 data/hscodes/hstest.jsonl。

用法：python -m src.ingest.download_hscodes
"""
import json

from datasets import load_dataset

from config import DATA_HSCODES


def main() -> None:
    DATA_HSCODES.mkdir(parents=True, exist_ok=True)
    ds = load_dataset("ATH-MaaS/HSCodeComp", split="test")
    print("columns:", ds.column_names, "rows:", len(ds))

    out = DATA_HSCODES / "hstest.jsonl"
    with open(out, "w", encoding="utf-8") as f:
        for row in ds:
            f.write(json.dumps(dict(row), ensure_ascii=False) + "\n")
    print(f"saved -> {out}")

    # 打印首条样例看字段
    print(json.dumps(dict(ds[0]), ensure_ascii=False)[:600])


if __name__ == "__main__":
    main()
