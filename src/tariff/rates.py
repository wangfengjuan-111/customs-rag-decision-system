"""
关税税率模块：HTS 税率查询 + 关税计算。

税率原文挂在子目树节点上（general/special/other），中间节点（如 6101.30）为空，
法定税率线是最深带税率的节点。查找逻辑：给定 4/6/8/10 位码，定位到该码节点，
返回它自身或其子树上所有带税率的法定线。

税率表达式解析（覆盖全表 99% 模式，实测分布）：
    "15.9%"                → 从价
    "Free"                 → 0
    "38.6¢/kg + 10%"       → 复合（从量+从价）
    "4.4¢/kg" / "$0.9/kg"  → 从量（单位折算成 USD）
    "N¢ each + N% on the case + ..."（钟表分件公式）等长尾 → calculable=False，原文返回

special 税率形如 "Free (A,AU,BH,...)"：括号内是协定/优惠计划代码（A=GSP、
AU=澳FTA、KR=韩FTA…），按 2 字母国家代码粗判会员资格（计划代码 A*/A+/A+ 细则不展开，
README 声明口径）。

用法：
    python -m src.tariff.rates 6101.20.00
    python -m src.tariff.rates 6101.20.00 --value 1000 --kg 5
"""
import re
import sys
from dataclasses import dataclass, field

from src.knowledge.store import get_store

# ── 税率表达式解析 ──

_AV = re.compile(r"^(\d+(?:\.\d+)?)%$")                                   # 15.9%
_SPEC = re.compile(r"^(\d+(?:\.\d+)?)\s*¢/(kg|liter|l|bbl|doz\.?|pr\.?|each|clean kg)$")
_SPEC_D = re.compile(r"^\$(\d+(?:\.\d+))/(kg|each|doz\.?)$")              # $0.9/kg
_COMPOUND = re.compile(
    r"^(?:\$?(\d+(?:\.\d+)?)\s*¢?\s*/\s*(kg|liter|l|doz\.?|pr\.?|each)|(\d+(?:\.\d+)?)\s*¢\s*(?:each|/kg|/pr\.|/doz\.?))\s*\+\s*(\d+(?:\.\d+)?)%$"
)

_UNIT_ALIASES = {
    # 解析侧（税率原文里的写法）
    "l": "liter", "doz": "doz", "doz.": "doz", "pr.": "pair", "clean kg": "kg",
    # 用户输入侧（UI 常见写法归一到法定单位）
    "ea": "each", "pc": "each", "pcs": "each", "pc.": "each", "pce": "each",
    "kgs": "kg", "litre": "liter", "liters": "liter",
    "dozen": "doz", "pair": "pair", "pairs": "pair", "pr": "pair",
    "barrel": "bbl", "barrels": "bbl",
}

_UNIT_ZH = {
    "kg": "千克", "each": "个", "doz": "打（12个）", "liter": "升",
    "pair": "对/双", "bbl": "桶",
}


def norm_unit(u: str | None) -> str | None:
    """用户输入/税率原文的单位 → 法定单位（each/kg/doz/liter/pair/bbl）。"""
    if not u:
        return None
    return _UNIT_ALIASES.get(u.strip().lower(), u.strip().lower())


def unit_zh(u: str) -> str:
    return f"{u}（{_UNIT_ZH.get(u, '?')}）" if u in _UNIT_ZH else u


@dataclass
class RateExpr:
    """一条法定税率线。calculable=False 表示长尾公式，只保留原文。"""
    raw: str
    advalorem: float = 0.0                       # 从价部分（0.159 = 15.9%）
    specific_per_unit: float | None = None       # 从量部分（USD/单位）
    specific_unit: str = ""                      # kg / liter / bbl / doz / pair / each
    free: bool = False
    calculable: bool = True

    def duty(self, value_usd: float, quantity: float | None = None, qty_unit: str = "kg") -> float | None:
        """从价+从量合计。从量需要数量，单位不匹配或缺失返回 None。"""
        if not self.calculable:
            return None
        d = self.advalorem * value_usd
        if self.specific_per_unit is not None:
            if quantity is None or _UNIT_ALIASES.get(qty_unit, qty_unit) != self.specific_unit:
                return None
            d += self.specific_per_unit * quantity
        return d

    def duty_items(
        self, value_usd: float, quantity: float | None = None, qty_unit: str = "kg"
    ) -> list[dict] | None:
        """税种分解：每项 {tax_type, rate_str, formula, amount}；从量在前从价在后。

        不可计算（长尾公式 / 从量缺数量 / 单位不符）返回 None，由调用方提示。
        单位经 norm_unit 归一（pcs/ea/pc → each 等），与税率原文单位对齐。
        """
        if not self.calculable:
            return None
        items: list[dict] = []
        if self.specific_per_unit is not None:
            unit = norm_unit(qty_unit)
            if quantity is None or unit != self.specific_unit:
                return None
            items.append(
                {
                    "tax_type": "从量税",
                    "rate_str": f"${self.specific_per_unit:g}/{self.specific_unit}",
                    "formula": f"${self.specific_per_unit:g} × {quantity:g} {self.specific_unit}",
                    "amount": round(self.specific_per_unit * quantity, 2),
                }
            )
        if self.advalorem > 0:
            items.append(
                {
                    "tax_type": "从价税",
                    "rate_str": f"{self.advalorem:.1%}",
                    "formula": f"{self.advalorem:.1%} × ${value_usd:,.2f}",
                    "amount": round(self.advalorem * value_usd, 2),
                }
            )
        if not items:  # Free：既无从量也从价
            items.append({"tax_type": "免税", "rate_str": "Free", "formula": "—", "amount": 0.0})
        return items


def parse_rate(raw: str) -> RateExpr:
    s = (raw or "").strip()
    if not s:
        return RateExpr(raw=raw, calculable=False)
    # 归一化无斜杠的从量写法："0.9¢ each" → "0.9¢/each"，"$1.75 each" → "$1.75/each"
    s = re.sub(r"¢\s*each\b", "¢/each", s)
    s = re.sub(r"\$([0-9.]+)\s*each\b", r"$\1/each", s)
    if s.lower() == "free":
        return RateExpr(raw=raw, free=True)
    if m := _AV.match(s):
        return RateExpr(raw=raw, advalorem=float(m.group(1)) / 100)
    if m := _SPEC.match(s):
        unit = _UNIT_ALIASES.get(m.group(2), m.group(2))
        return RateExpr(raw=raw, specific_per_unit=float(m.group(1)) / 100, specific_unit=unit)
    if m := _SPEC_D.match(s):
        unit = _UNIT_ALIASES.get(m.group(2), m.group(2))
        return RateExpr(raw=raw, specific_per_unit=float(m.group(1)), specific_unit=unit)
    # 复合：先分离从价尾巴
    if "+" in s and s.rstrip().endswith("%"):
        head, _, tail = s.rpartition("+")
        av = float(_AV.match(tail.strip()).group(1)) / 100 if _AV.match(tail.strip()) else None
        head = head.strip()
        if av is not None:
            for pat in (_SPEC, _SPEC_D):
                if m := pat.match(head):
                    unit = _UNIT_ALIASES.get(m.group(2), m.group(2))
                    amt = float(m.group(1)) / (100 if pat is _SPEC else 1)
                    return RateExpr(raw=raw, advalorem=av, specific_per_unit=amt, specific_unit=unit)
    return RateExpr(raw=raw, calculable=False)  # 长尾公式（钟表分件/果汁梯度等）


# ── special 税率的国家资格 ──

_SPECIAL_CODES = re.compile(r"([A-Z]{2})[+*]?")

# Column 2（非最惠国）适用国家：HTS General Notes 3(d) 定义（公开知识整理，draft 待核验）
_COLUMN2_COUNTRIES = {"KP", "CU", "RU", "BY"}


def special_free_for(special_raw: str, country: str) -> bool:
    """special 原文（"Free (A,AU,BH,...)"）里是否有该国的协定代码。"""
    return country.upper() in _SPECIAL_CODES.findall(special_raw or "")


def determine_scheme(country: str) -> tuple[str, str]:
    """原产国 → 优先适用的税率列。

    Column 2 是管制国家名单（整列适用，与具体编码无关）；Special 是逐编码的
    协定清单（调用方再按 special_free_for 细判）；其余走 General。
    返回 (scheme, 判定依据说明)。
    """
    c = (country or "").strip().upper()
    if not c:
        return "general", "未提供原产国，默认按 General 普遍税率参考"
    if c in _COLUMN2_COUNTRIES:
        return "column2", f"原产国 {c} 在 Column 2（非最惠国）名单内（General Notes 3(d)）"
    return "general", f"原产国 {c} 不在 Column 2 名单——Special 是否适用看各编码的协定清单，其余走 General"


# ── 码 → 节点索引 ──

@dataclass
class RateLine:
    code: str
    description: str
    general: RateExpr
    special_raw: str = ""
    other_raw: str = ""
    units: list[str] = field(default_factory=list)
    path: list[str] = field(default_factory=list)   # 品目→…→本行 的描述链


_index: dict[str, list[tuple[dict, RateLine]]] | None = None  # 归一化码(去点) → [(heading, line)]


def _norm(code: str) -> str:
    return re.sub(r"\D", "", code or "")


def _walk(nodes: list[dict], trail: list[str], heading: dict, out: dict) -> None:
    for n in nodes:
        path = trail + [n["description"]]
        if n.get("general") or n.get("special") or n.get("other"):
            line = RateLine(
                code=n["code"],
                description=n["description"],
                general=parse_rate(n.get("general") or ""),
                special_raw=n.get("special") or "",
                other_raw=n.get("other") or "",
                units=list(n.get("units") or []),
                path=path,
            )
            key = _norm(n["code"])
            # 10 位行挂 8 位键下；同时登记自身与截断前缀，支持 4/6/8 位查询
            for k in {key, key[:8], key[:6], key[:4]}:
                out.setdefault(k, []).append((heading, line))
        _walk(n.get("children") or [], path, heading, out)


def _get_index() -> dict[str, list[tuple[dict, RateLine]]]:
    global _index
    if _index is None:
        out: dict[str, list[tuple[dict, RateLine]]] = {}
        for h in get_store().iter_headings():
            _walk(h.get("subheadings") or [], [h["description"]], h, out)
        _index = out
    return _index


def lookup(code: str) -> list[RateLine]:
    """查码下所有法定税率线。6 位码通常展开成多条 8/10 位线；空=码不存在。"""
    return [line for _, line in _get_index().get(_norm(code), [])]


def explain(code: str) -> str:
    lines = lookup(code)
    if not lines:
        return f"{code}: not found"
    out = [f"{code} → {len(lines)} statutory line(s):"]
    for l in lines[:8]:
        av = f"{l.general.advalorem:.1%} ad valorem" if l.general.advalorem else ""
        sp = f", specific ${l.general.specific_per_unit}/{l.general.specific_unit}" if l.general.specific_per_unit is not None else ""
        calc = "" if l.general.calculable else "  [formula not auto-calculable]"
        out.append(f"  {l.code:<15} {l.description[:60]:<60} {l.general.raw:<28} ({av}{sp}){calc}")
    return "\n".join(out)


def _applicable_for(auto_scheme: str, country: str, l: RateLine) -> str:
    """单条法定线的适用列：Column 2 名单优先 → Special 逐线协定清单 → General。"""
    if auto_scheme == "column2":
        return "column2"
    if country and special_free_for(l.special_raw, country):
        return "special"
    return "general"


def _rate_desc(e: RateExpr) -> str:
    """税率人话解读（不算税额）：从价/从量/复合/免税/公式。"""
    if not e.calculable:
        return "分件公式税率，需人工核算"
    if e.free and not e.advalorem and e.specific_per_unit is None:
        return "免税（Free）"
    parts = []
    if e.specific_per_unit is not None:
        parts.append(f"${e.specific_per_unit:g}/{e.specific_unit}（从量，按{unit_zh(e.specific_unit).split('（')[0]}计）")
    if e.advalorem > 0:
        parts.append(f"{round(e.advalorem * 100, 1):g}%（从价）")
    return " + ".join(parts) if parts else e.raw


def summarize(code: str, country: str = "") -> dict:
    """纯税率速查（不算税额）：三列并示 + 按原产国判定适用列。"""
    auto_scheme, scheme_basis = determine_scheme(country)
    rows = []
    for l in lookup(code):
        applicable = _applicable_for(auto_scheme, country, l)
        columns = {
            "general": {"raw": l.general.raw or "—", "parsed": _rate_desc(l.general)},
            "special": {
                "raw": l.special_raw or "—",
                "parsed": "协定免税（该国在清单内）" if applicable == "special" else "未命中协定清单，同 General",
            },
            "column2": {"raw": l.other_raw or "—", "parsed": "非最惠国税率，按原文适用" if applicable == "column2" else ""},
        }
        rows.append(
            {"code": l.code, "description": l.description, "columns": columns, "applicable": applicable}
        )
    return {
        "code": code,
        "country": (country or "").upper(),
        "scheme_basis": scheme_basis,
        "lines": rows,
        "source_note": "税率数据来源：hts.usitc.gov（美国 HTS）；申报以美国海关与边境保护局（CBP）裁定为准",
    }


def calculate(
    code: str,
    value_usd: float,
    quantity: float | None = None,
    qty_unit: str = "kg",
    country: str = "",
) -> dict:
    """
    关税计算（三列并示 + 按原产国自动判定适用列）。

    每条法定线返回 {code, description, columns, applicable, items, total, note}：
    - columns: {general, special, column2} 三列各自的 {items, total}（Special 只在
      原产国命中协定清单时给协定免税，否则与 General 同值并注明回落）
    - applicable: 按原产国判定的适用列名 + 依据
    - items/total: 适用列的税种明细与合计（columns[applicable] 的快捷方式）
    同一 6 位码下的多条法定线是不同统计细目的择一适用，不是叠加。
    """
    auto_scheme, scheme_basis = determine_scheme(country)
    rows = []
    for l in lookup(code):
        gen_items = l.general.duty_items(value_usd, quantity, qty_unit)
        applicable = _applicable_for(auto_scheme, country, l)

        columns = {}
        # General（基准列）
        columns["general"] = {
            "items": gen_items,
            "total": round(sum(i["amount"] for i in gen_items), 2) if gen_items else None,
            "raw": l.general.raw,
        }
        # Special（协定列）：命中给协定免税；未命中与 General 同值（回落）
        if applicable == "special":
            sp_items = [
                {
                    "tax_type": "协定免税",
                    "rate_str": "Free (special)",
                    "formula": f"{country.upper()} 在协定清单内",
                    "amount": 0.0,
                }
            ]
            sp_total = 0.0
            sp_raw = l.special_raw
        else:
            sp_items, sp_total, sp_raw = gen_items, columns["general"]["total"], l.special_raw
        columns["special"] = {"items": sp_items, "total": sp_total, "raw": sp_raw}
        # Column 2（非最惠国）：税率原文独立成串未经解析，只展示原文
        columns["column2"] = {"items": None, "total": None, "raw": l.other_raw or ""}

        items = columns[applicable]["items"]
        total = columns[applicable]["total"]

        # 依据说明
        if applicable == "special":
            note = f"依据：{l.code} Special 列——原产国 {country.upper()} 在协定代码清单内（适用 ✅）"
        elif applicable == "column2":
            note = f"依据：{l.code} Column 2 列——{scheme_basis}；税率原文「{l.other_raw or 'n/a'}」，需人工核算"
        else:
            note = f"依据：{l.code} General 列「{l.general.raw}」"
            if country and l.special_raw and not special_free_for(l.special_raw, country):
                note += f"；{country.upper()} 不在 Special 协定清单，General 适用"
            if items is None:
                if not l.general.calculable:
                    note += "——分件公式税率，需人工核算"
                elif quantity is None:
                    note += (
                        f"——含从量税，请提供数量（按 {unit_zh(l.general.specific_unit)} 计）"
                    )
                else:
                    note += (
                        f"——从量税按 {unit_zh(l.general.specific_unit)} 计，"
                        f"与所选数量单位（{qty_unit}）不符，请换算后重填"
                    )
        rows.append(
            {
                "code": l.code,
                "description": l.description,
                "columns": columns,
                "applicable": applicable,
                "items": items,
                "total": total,
                "note": note,
            }
        )
    return {
        "code": code,
        "country": (country or "").upper(),
        "applicable": auto_scheme,
        "scheme_basis": scheme_basis,
        "lines": rows,
        "source_note": "税率数据来源：hts.usitc.gov（美国 HTS）；本计算为指示性，申报以美国海关与边境保护局（CBP）裁定为准",
    }


if __name__ == "__main__":
    if len(sys.argv) > 1:
        code = sys.argv[1]
        print(explain(code))
        if "--value" in sys.argv:
            v = float(sys.argv[sys.argv.index("--value") + 1])
            kg = float(sys.argv[sys.argv.index("--kg") + 1]) if "--kg" in sys.argv else None
            country = sys.argv[sys.argv.index("--country") + 1] if "--country" in sys.argv else ""
            res = calculate(code, v, kg, country=country)
            print("\n" + "=" * 40)
            print("适用列判定:", res["scheme_basis"])
            for r in res["lines"]:
                parts = " + ".join(
                    f"{i['tax_type']} {i['formula']}=${i['amount']:,.2f}" for i in (r["items"] or [])
                ) or "（不可自动计算）"
                total = f"${r['total']:,.2f}" if r["total"] is not None else "—"
                print(f"  {r['code']:<15} [{r['applicable']}] {parts}  => 合计 {total}")
                print(f"  {'':<15} {r['note']}")
