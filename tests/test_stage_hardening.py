"""
S3/S4 漏打分重试 + S5 子目 BM25 模糊修正的单测。
monkeypatch ask_json，不联网、不烧 token；S5 用真实 artifacts 验证。
运行：python -m tests.test_stage_hardening  （或 pytest tests/test_stage_hardening.py -q）
"""
import re

import src.stages.s3_l1_rank as s3
import src.stages.s4_l2_rank as s4
import src.stages.s5_subheading as s5
from src.stages.s1_extract import Attributes

CANDS = ["3919", "3920", "3921"]  # 真实品目，同属 39 章


def _attrs() -> Attributes:
    return Attributes(
        material="plastic", form="film", function="packing of goods",
        end_use="unspecified", features=[], decorations=[],
        is_part=False, is_set=False,
    )


def _codes_in_prompt(text: str) -> list[str]:
    if "=== heading" in text:
        return re.findall(r"=== heading (\d{4})", text)
    return [ln.split(":", 1)[0] for ln in text.splitlines() if len(ln) > 4 and ln[:4].isdigit() and ln[4] == ":"]


def test_s3_retry_once_only_missing() -> None:
    calls: list[str] = []

    def fake_ask(messages, schema, temperature=0):
        calls.append(messages[1]["content"])
        codes = _codes_in_prompt(messages[1]["content"])
        if len(calls) == 1:  # 第一次漏掉最后一个候选
            return s3.L1Ranking(rankings=[s3.L1Entry(heading=c, score=5) for c in codes[:-1]])
        return s3.L1Ranking(rankings=[s3.L1Entry(heading=c, score=7) for c in codes])

    orig = s3.ask_json
    s3.ask_json = fake_ask
    try:
        ranked = s3.rank_l1("plastic film", _attrs(), CANDS)
    finally:
        s3.ask_json = orig
    assert len(calls) == 2, f"expect retry, got {len(calls)} calls"
    assert _codes_in_prompt(calls[1]) == ["3921"], "重试应只发漏掉的候选"
    by = {r.heading: r.score for r in ranked}
    assert by == {"3919": 5, "3920": 5, "3921": 7}


def test_s3_missing_filled_zero() -> None:
    def fake_ask(messages, schema, temperature=0):
        codes = _codes_in_prompt(messages[1]["content"])
        return s3.L1Ranking(rankings=[s3.L1Entry(heading=c, score=5) for c in codes[:-1]])  # 永远漏最后一个

    orig = s3.ask_json
    s3.ask_json = fake_ask
    try:
        ranked = s3.rank_l1("plastic film", _attrs(), CANDS)
    finally:
        s3.ask_json = orig
    assert len(ranked) == 3
    last = ranked[-1]
    assert last.heading == "3921" and last.score == 0 and "missing" in last.reason


def test_s4_retry_once_only_missing() -> None:
    calls: list[str] = []

    def fake_ask(messages, schema, temperature=0):
        calls.append(messages[1]["content"])
        codes = _codes_in_prompt(messages[1]["content"])
        if len(calls) == 1:
            return s4.L2Result(rankings=[s4.L2Entry(heading="3920", kept=True, pros=["film"])])
        return s4.L2Result(rankings=[s4.L2Entry(heading=c, kept=True, pros=["retry"]) for c in codes])

    orig = s4.ask_json
    s4.ask_json = fake_ask
    try:
        result = s4.rank_l2("plastic film", _attrs(), CANDS)
    finally:
        s4.ask_json = orig
    assert len(calls) == 2, f"expect retry, got {len(calls)} calls"
    assert set(_codes_in_prompt(calls[1])) == {"3919", "3921"}, "重试应只发漏掉的候选"
    by = {r.heading: r for r in result.rankings}
    assert set(by) == set(CANDS)
    assert by["3919"].kept and by["3921"].kept and by["3920"].kept


def test_s5_bm25_correction_on_real_artifacts() -> None:
    store = s5.get_store()
    h = store.get_heading("6109")
    assert h, "artifacts 需包含品目 6109（T恤，针织）"
    codes6 = {n["code"].replace(".", "")[:6]
              for _, n in s5._flatten_subtree(h.get("subheadings", []))}

    # 1) 有效码原样通过，不标 ambiguous
    res = s5._validate(s5.SubheadingResolution(six_digit="610910", confidence=0.9), "6109", "x")
    assert res.six_digit == "610910" and not res.ambiguous

    # 2) 无效码 → 子目文本 BM25 修正（cotton 描述命中棉制子目），标 ambiguous
    res = s5._validate(
        s5.SubheadingResolution(six_digit="999999", confidence=0.9),
        "6109", "men's t-shirt of cotton, knitted",
    )
    assert res.six_digit in codes6, f"修正码 {res.six_digit} 不在子树"
    assert res.six_digit == "610910", f"cotton 应命中棉制子目，得到 {res.six_digit}"
    assert res.ambiguous and "BM25" in res.reasoning


def test_s5_no_lexical_hit_falls_back_to_depth0() -> None:
    code = s5.heuristic_six_digit("6109", "量子波动速读机")  # CJK bigram，英文子树零命中
    store = s5.get_store()
    h = store.get_heading("6109")
    depth0 = [n for d, n in s5._flatten_subtree(h.get("subheadings", [])) if d == 0]
    assert code == depth0[0]["code"].replace(".", "")[:6]


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as e:
                print(f"FAIL {name}: {e}")
                failures += 1
    print(f"{failures} failures")
    raise SystemExit(1 if failures else 0)
