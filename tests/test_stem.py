"""
_stem 保护性用例：白名单挡误伤，同时锁定既有正确行为不回归。
运行：python -m tests.test_stem  （或 pytest tests/test_stem.py -q）
"""
from src.knowledge.retrieval import _stem, tokenize

# (输入, 期望词干)
CASES = [
    # ies→y 主干行为（不得回归）
    ("batteries", "battery"),
    ("accessories", "accessory"),
    ("facilities", "facility"),
    ("duties", "duty"),
    ("commodities", "commodity"),
    # 白名单①：-ie 词干/不变格，剥一个 s 收敛单复数
    ("movies", "movie"),
    ("cookies", "cookie"),
    ("series", "serie"),
    ("species", "specie"),
    # 双辅音收缩既有行为
    ("knitted", "knit"),
    ("stopped", "stop"),
    ("planed", "plan"),
    ("called", "call"),
    ("crossed", "cross"),
    # ① 元音排除修复：-eed/-eeing 不再被收缩
    ("needed", "need"),
    ("needing", "need"),
    ("speeding", "speed"),
    ("freeing", "free"),
    # ⑤ v→ve 还原（ing/ed 后缀）
    ("moving", "move"),
    ("moved", "move"),
    ("derived", "derive"),
    ("serving", "serve"),
    ("drivers", "driv"),  # 既有行为：ers 后缀不做 v 还原
    ("coated", "coat"),  # 非 v 结尾、无双辅音：原样去后缀
    # es 分支：默认剥 es
    ("boxes", "box"),
    ("buses", "bus"),
    ("lenses", "lens"),
    ("watches", "watch"),
    ("glasses", "glass"),
    ("addresses", "address"),
    # 白名单②：-se 词干 +es
    ("houses", "house"),
    ("cases", "case"),
    ("warehouses", "warehouse"),
    ("purposes", "purpose"),
    ("licenses", "license"),
    ("expenses", "expense"),
    # es 分支：普通 -e 词
    ("articles", "article"),
    ("notes", "note"),
    ("sales", "sale"),
    # s 分支既有行为
    ("goods", "good"),
    ("toys", "toy"),
    ("ties", "tie"),
    ("pies", "pie"),
    ("biscuits", "biscuit"),
    # ④ -sis/自身以 s 结尾的单数保护
    ("analysis", "analysis"),
    ("basis", "basis"),
    ("chassis", "chassis"),
    ("diagnosis", "diagnosis"),
    ("business", "business"),
    ("lens", "lens"),
    # 已知遗留损失（本轮不修，锁定现状防止意外变化）
    ("news", "new"),  # news/new 碰撞：查询与语料同函数处理，自洽
    ("used", "used"),  # len(base)<3 守卫原样返回
]


def test_stem_cases() -> None:
    for w, expected in CASES:
        got = _stem(w)
        assert got == expected, f"_stem({w!r}) = {got!r}, want {expected!r}"


def test_tokenize_cjk_bigram() -> None:
    assert tokenize("锂电池") == ["锂电", "电池"]
    assert "phone" in tokenize("TPU hydrogel film for all phones")


if __name__ == "__main__":
    failures = 0
    for w, expected in CASES:
        got = _stem(w)
        if got != expected:
            print(f"FAIL _stem({w!r}) = {got!r}, want {expected!r}")
            failures += 1
    for text, expect in [("锂电池", ["锂电", "电池"]),
                         ("TPU hydrogel film for all phones", None)]:
        toks = tokenize(text)
        if expect is not None and toks != expect:
            print(f"FAIL tokenize({text!r}) = {toks!r}")
            failures += 1
    print(f"{len(CASES) + 2} checks, {failures} failures")
    raise SystemExit(1 if failures else 0)
