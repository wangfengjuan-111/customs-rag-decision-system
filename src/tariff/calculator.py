"""
美国进口关税计算器：MFN 基础税率 + 99 章叠加税（301/IEEPA/232 等）。

公式（用户给定的建模）：
    总关税 = HTS 基础 MFN 税率 + Σ(命中的 99 章 overlay 税率，可叠加) − 豁免

数据源：
- 基础税率：artifacts/headings.json（品目树上的 general 字段，exportList 官方数据）
- 叠加税：artifacts/ch99_overlays.json（9903 系列：applies_to_8d 码清单命中 + universal 普惠）

用法：
    from src.tariff.calculator import compute_duty
    result = compute_duty("8517.62.00", origin="China", value_usd=1000)
"""
import json
import re
from dataclasses import dataclass, field

from config import ARTIFACTS

CH99_OVERLAYS = ARTIFACTS / "ch99_overlays.json"

# MFN 税率文本解析："15.9%" / "Free" / "32.5¢/kg + 5%" / "37.5¢/kg"
RE_PCT = re.compile(r"(\d+(?:\.\d+)?)\s*%")
RE_CENT_PER_KG = re.compile(r"(\d+(?:\.\d+)?)¢/kg")

# 用户输入 → 99 章 overlay 的 origin 字段
ORIGIN_MAP = {
    "CN": "China",
    "CHINA": "China",
    "MX": "Mexico",
    "MEXICO": "Mexico",
    "CA": "Canada",
    "CANADA": "Canada",
}


@dataclass
class DutyBreakdown:
    code_8d: str
    origin: str
    mfn_text: str
    mfn_pct: float          # 从价部分
    mfn_cents_per_kg: float | None = None   # 从量部分（如纺织品 ¢/kg）
    special_text: str = ""  # 协定税率原文（不做智能匹配，仅供参考）
    overlays: list[dict] = field(default_factory=list)  # 命中的 99 章叠加
    notes: list[str] = field(default_factory=list)

    @property
    def total_addon_pct(self) -> float:
        return sum(o["rate_pct"] or 0 for o in self.overlays)

    @property
    def effective_pct(self) -> float:
        """从价合计（MFN + 叠加）。从量部分需按重量另算。"""
        return self.mfn_pct + self.total_addon_pct

    def duty_on_value(self, value_usd: float, weight_kg: float = 0.0) -> float:
        d = value_usd * self.mfn_pct / 100
        if self.mfn_cents_per_kg and weight_kg:
            d += self.mfn_cents_per_kg / 100 * weight_kg  # 美分/kg → 美元
        d += value_usd * self.total_addon_pct / 100
        return d


def _load_overlays() -> list[dict]:
    return json.loads(CH99_OVERLAYS.read_text(encoding="utf-8"))


def _find_rate_node(heading_rec: dict, code_8d: str) -> dict | None:
    """在品目子树里找 8 位码对应的税率节点。"""
    digits = code_8d.replace(".", "")
    stack = [heading_rec] + list(heading_rec.get("subheadings", []))
    while stack:
        n = stack.pop()
        if not n.get("code"):
            continue
        nd = n["code"].replace(".", "")
        if nd[:8] == digits[:8] and (n.get("general") or n.get("other")):
            return n
        stack.extend(n.get("children", []))
    return None


def compute_duty(code: str, origin: str = "China", mfn_column: str = "general") -> DutyBreakdown:
    """计算 8 位码的完整关税拆解。

    code: 4/6/8 位码。origin: China/Mexico/Canada/ERGA OMNES(默认其他)。
    mfn_column: general（MFN）/ other（Column 2，适用于无最惠国待遇国）。
    """
    from src.knowledge.store import get_store

    origin = ORIGIN_MAP.get(origin.strip().upper(), origin.strip())
    digits = re.sub(r"\D", "", code)
    code8 = f"{digits[:4]}.{digits[4:6]}.{digits[6:8]}" if len(digits) >= 8 else code

    store = get_store()
    h = store.get_heading(digits[:4])
    if not h:
        raise ValueError(f"未知品目 {digits[:4]}")

    node = _find_rate_node(h, code8) if len(digits) >= 8 else None
    rate_text = (node or {}).get(mfn_column) or ""
    if not rate_text:  # 8 位节点无税率则用品目级
        rate_text = next((r[mfn_column] for r in h.get("rates", []) if r["code"].replace(".", "").startswith(digits[:6]) and r[mfn_column]), "")

    mfn_pct = 0.0
    m = RE_PCT.search(rate_text)
    if m:
        mfn_pct = float(m.group(1))
    cents = RE_CENT_PER_KG.search(rate_text)

    # 99 章叠加：码清单命中 或 普惠型（origin 匹配）
    breakdown = DutyBreakdown(
        code_8d=code8,
        origin=origin,
        mfn_text=rate_text or "(no rate found)",
        mfn_pct=mfn_pct,
        mfn_cents_per_kg=float(cents.group(1)) if cents else None,
        special_text=(node or {}).get("special") or "",
    )

    norm8 = re.sub(r"\D", "", code8)

    # 普惠型（IEEPA 基线等）：同系列（前 8 位）互斥去重，取最高税率；
    # 在途/转运等条件性条款不默认叠加
    universal_by_series: dict[str, dict] = {}
    for o in _load_overlays():
        if o.get("rate_pct") is None or not o.get("universal"):
            continue
        if o.get("origin") != origin:
            continue
        if "transit" in o["desc_snippet"].lower():
            continue
        series = o["overlay_code"][:8]
        if series not in universal_by_series or (o["rate_pct"] or 0) > (universal_by_series[series]["rate_pct"] or 0):
            universal_by_series[series] = o

    for o in _load_overlays():
        if o.get("rate_pct") is None:
            continue
        if o.get("origin") not in (None, origin):
            continue
        hit = False
        if o.get("universal") and o.get("origin") == origin:
            hit = o in universal_by_series.values()  # 同系去重后的代表
        else:
            for c in o.get("applies_to_8d", []):
                if re.sub(r"\D", "", c) == norm8:
                    hit = True
                    break
        if hit:
            # 豁免检查：该码在 overlay 的豁免清单里则跳过
            if any(re.sub(r"\D", "", e) == norm8 for e in o.get("exclusions", [])):
                breakdown.notes.append(f"{o['overlay_code']} exclusion applies — skipped")
                continue
            breakdown.overlays.append({
                "overlay_code": o["overlay_code"],
                "rate_pct": o["rate_pct"],
                "desc": o["desc_snippet"][:120],
            })
    return breakdown


def format_report(b: DutyBreakdown, value_usd: float = 1000.0, weight_kg: float = 0.0) -> str:
    lines = [
        f"HTS {b.code_8d}  (origin: {b.origin})",
        f"  MFN: {b.mfn_text}  → {b.mfn_pct}%" + (f" + {b.mfn_cents_per_kg}¢/kg" if b.mfn_cents_per_kg else ""),
    ]
    if b.special_text:
        lines.append(f"  Special (FTA, 仅供参考): {b.special_text[:80]}")
    if b.overlays:
        lines.append(f"  Chapter 99 叠加 ({len(b.overlays)} 项):")
        for o in b.overlays:
            lines.append(f"    + {o['rate_pct']:5.1f}%  {o['overlay_code']}  {o['desc'][:70]}")
    else:
        lines.append("  Chapter 99 叠加: 无命中")
    lines.append(f"  合计从价: {b.effective_pct:.1f}%")
    if value_usd:
        lines.append(f"  参考税额 (货值 ${value_usd}, 重量 {weight_kg}kg): ${b.duty_on_value(value_usd, weight_kg):.2f}")
    for n in b.notes:
        lines.append(f"  note: {n}")
    return "\n".join(lines)


if __name__ == "__main__":
    import sys

    code = sys.argv[1] if len(sys.argv) > 1 else "8517.62.00"
    origin = sys.argv[2] if len(sys.argv) > 2 else "China"
    b = compute_duty(code, origin)
    print(format_report(b, value_usd=1000))
