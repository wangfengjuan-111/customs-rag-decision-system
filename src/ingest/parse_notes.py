"""
章注 HTML → 类型化条款 clauses.jsonl + 章注组 chapters_meta.json。

输入：data/raw/notes/chNN.html（getChapterNotes 端点，li[value] 自带编号）
输出：
    artifacts/clauses.jsonl     每行一个条款（含类型/路径/提及品目/父条款）
    artifacts/chapters_meta.json 每章标题/所属类/注释组概况

条款类型用关键词规则分类（可复现，不依赖 LLM）：
    exclusion  排除条款（"does not cover" 等，Stage4 降级的承重机制）
    inclusion  包含条款
    priority   优先级/归属裁决（"prima facie ... classifiable" 等）
    definition 定义条款（"means" / "term"）
    scope      适用范围声明（"For the purposes of heading ..."）
    other

用法：python -m src.ingest.parse_notes
"""
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from bs4 import BeautifulSoup, Tag

from config import ARTIFACTS, DATA_RAW

NOTES_DIR = DATA_RAW / "notes"

RE_HEADING_REF = re.compile(r"\b(\d{4})\b")
RE_CODE_REF = re.compile(r"\b(\d{4}\.\d{2})\b")

# 关键词规则（顺序即优先级）
RULES: list[tuple[str, str]] = [
    ("exclusion", r"does not cover|do not cover|not cover|excludes?|are excluded|is excluded"),
    ("priority", r"prima facie|classifiable (?:in|both|with)|takes? precedence|regardless of|shall be classified|are to be classified|goes? to|remain in"),
    ("inclusion", r"applies only to|apply only to|includes? only|covers? only|applies to|covers\b"),
    ("definition", r"\bmeans\b|\bterm\b|expression|refers? to|shall be treated as|deemed"),
    ("scope", r"for the purposes? of|for purposes? of"),
]


def classify(text: str) -> str:
    low = text.lower()
    for ctype, pat in RULES:
        if re.search(pat, low):
            return ctype
    return "other"


def own_text(li: Tag) -> str:
    """取 li 自身文本（不含嵌套子条款）。"""
    parts: list[str] = []
    for child in li.contents:
        if isinstance(child, Tag) and child.name in ("ul", "li"):
            break
        parts.extend(child.strings if isinstance(child, Tag) else [str(child)])
    text = "".join(parts)
    # 去掉开头的重复编号（"2. This chapter..." → "This chapter..."）
    text = re.sub(r"^\s*(?:[0-9]{1,2}\.|\([a-z]\)|-)\s*", "", text, count=1)
    return re.sub(r"\s+", " ", text).strip()


@dataclass
class Clause:
    clause_id: str
    chapter: int
    group: str          # legal | additional_us | statistical
    path: list          # [2, 'a'] 条款编号路径
    ctype: str          # exclusion | inclusion | priority | definition | scope | other
    text: str
    parent_id: str | None = None
    applies_to: list[str] = field(default_factory=list)  # 文中提及的 4 位品目


def parse_note_group(ul: Tag, chapter: int, group: str, counters: dict) -> list[Clause]:
    """递归解析一个注释组。counters 用于生成全局唯一 clause_id。

    子条款组合父前缀成自含文本（父句以冒号结尾且较短时），
    使 "Goods of heading 6212" 这类碎片保留 "This chapter does not cover:" 的排除语义。
    """
    clauses: list[Clause] = []

    def walk(ul_tag: Tag, parent_path: list, parent_id: str | None, prefix: str) -> None:
        for li in ul_tag.find_all("li", recursive=False):
            val = (li.get("value") or "").strip()
            path = parent_path + ([val.rstrip(".")] if val else ["-"])
            text = own_text(li)
            if not text:
                continue
            # 组合前缀：父句以冒号结尾且总长可控时继承
            if prefix and len(prefix) + len(text) <= 400:
                full_text = f"{prefix} {text}"
            else:
                full_text = text
            full_text = re.sub(r"\s+", " ", full_text)
            counters["n"] += 1
            cid = f"ch{chapter:02d}_{counters['n']:03d}"
            applies = sorted(set(RE_HEADING_REF.findall(full_text)) | {c.replace(".", "") for c in RE_CODE_REF.findall(full_text)})
            clauses.append(Clause(
                clause_id=cid,
                chapter=chapter,
                group=group,
                path=path,
                ctype=classify(full_text),
                text=full_text,
                parent_id=parent_id,
                applies_to=applies,
            ))
            sub = li.find("ul", recursive=False)
            if sub:
                child_prefix = full_text if text.endswith(":") and len(full_text) <= 300 else ""
                walk(sub, path, cid, child_prefix)

    walk(ul, [], None, "")
    return clauses


def group_name(ul: Tag) -> str:
    """按 ul 前最近的标题 div 判定注释组。"""
    p = ul
    while p is not None:
        prev = p.find_previous_sibling()
        if prev is None:
            break
        cls = prev.get("class") or [""]
        text = prev.get_text(strip=True).upper()
        if "NOTE" in text and "title" in cls[0]:
            if "STATISTICAL" in text:
                return "statistical"
            if "U.S." in text:
                return "us_notes"
            return "legal"
        if text == "NOTES" and "title" not in cls[0]:
            # 裸 "Notes" 段落标题（misc_paragraph 类，无 NOTE 字样的 title 类）：
            # ch20/43/99 等章页面结构，此前整组误判为 annex，排除条款对 S4 不可见
            return "legal"
        p = prev
    return "annex"


def parse_chapter_file(path: Path) -> tuple[list[Clause], dict]:
    chapter = int(path.stem[2:])
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")

    title = soup.find("div", class_="misc_title")
    desc = soup.find("div", class_="misc_title_desc")
    section = soup.find("div", class_="misc_numbering")

    clauses: list[Clause] = []
    counters = {"n": 0}
    top_uls = soup.find_all("ul", recursive=True)
    # 只取顶层 ul（前面 div 可能嵌套 ul，过滤掉有 ul/li 祖先的）
    top_uls = [ul for ul in top_uls if not ul.find_parent(["ul", "li"])]
    for ul in top_uls:
        clauses.extend(parse_note_group(ul, chapter, group_name(ul), counters))

    meta = {
        "chapter": chapter,
        "title": title.get_text(strip=True) if title else "",
        "description": re.sub(r"\s+", " ", desc.get_text(strip=True)) if desc else "",
        "section": section.get_text(strip=True) if section else "",
        "n_clauses": len(clauses),
    }
    return clauses, meta


def main() -> None:
    files = sorted(NOTES_DIR.glob("ch*.html"))
    all_clauses: list[Clause] = []
    metas: list[dict] = []
    for f in files:
        try:
            clauses, meta = parse_chapter_file(f)
            all_clauses.extend(clauses)
            metas.append(meta)
        except Exception as e:  # noqa: BLE001
            print(f"  {f.name}: ERROR {e}")

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    with open(ARTIFACTS / "clauses.jsonl", "w", encoding="utf-8") as f:
        for c in all_clauses:
            f.write(json.dumps(asdict(c), ensure_ascii=False) + "\n")
    with open(ARTIFACTS / "chapters_meta.json", "w", encoding="utf-8") as f:
        json.dump(metas, f, ensure_ascii=False, indent=1)

    # 统计报告
    from collections import Counter

    types = Counter(c.ctype for c in all_clauses)
    groups = Counter(c.group for c in all_clauses)
    print(f"chapters parsed: {len(metas)}, clauses: {len(all_clauses)}")
    print("by type:", dict(types))
    print("by group:", dict(groups))
    noteless = [m["chapter"] for m in metas if m["n_clauses"] == 0]
    if noteless:
        print(f"WARN 无任何条款的章节: {noteless}（USITC 页面无注释列表，如 ch50 实测端点即空；需人工核对是否截断）")
    annex_chs = sorted({c.chapter for c in all_clauses if c.group == "annex"})
    if annex_chs:
        print(f"WARN annex 组残留 {groups.get('annex', 0)} 条，S4 不可见，章节: {annex_chs}")


if __name__ == "__main__":
    main()
