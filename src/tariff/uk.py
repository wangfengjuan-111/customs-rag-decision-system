"""
英国关税：GOV.UK Trade Tariff 官方 API（无需 key）。

- /api/v2/headings/{4位} → 品目下的商品码清单（~50KB，缓存）
- /api/v2/commodities/{10位} → 单个商品码的全部进口措施（Third country duty
  = MFN 普遍税率 + Tariff preference = 各 FTA/GSP 优惠），缓存
- 所有响应落盘 artifacts/uk_cache/，同一码只拉一次

API 关系结构（JSON:API）：measure → duty_expression(base "12.00 %") +
measure_type(103=Third country duty / 105=Tariff preference) +
geographical_area(ERGA OMNES / 各贸易集团)。
"""
import json
from pathlib import Path

import requests

from config import ARTIFACTS

BASE = "https://www.trade-tariff.service.gov.uk/api/v2"
CACHE = ARTIFACTS / "uk_cache"
H = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}


def _get_json(kind: str, code: str) -> dict:
    """API GET + 磁盘缓存（kind: heading / commodity）。"""
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / f"{kind}_{code}.json"
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    r = requests.get(f"{BASE}/{'headings' if kind == 'heading' else 'commodities'}/{code}", timeout=30, headers=H)
    r.raise_for_status()
    data = r.json()
    f.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


def _index(d: dict) -> dict:
    return {i["type"] + ":" + str(i["id"]): i for i in d.get("included", [])}


def _deref(included: dict, rel: dict, t: str) -> dict:
    ref = (rel.get(t) or {}).get("data") or {}
    return included.get(t + ":" + str(ref.get("id", "")))


def _measures(d: dict) -> list[dict]:
    """included 里的 import measure → {type_id, type, duty, geo}。"""
    included = _index(d)
    out = []
    for i in d.get("included", []):
        if i["type"] != "measure":
            continue
        a = i["attributes"]
        if not a.get("import"):
            continue
        rel = i.get("relationships", {})
        de = _deref(included, rel, "duty_expression")
        mt = _deref(included, rel, "measure_type")
        geo = _deref(included, rel, "geographical_area")
        out.append(
            {
                "type_id": str((rel.get("measure_type") or {}).get("data", {}).get("id", "")),
                "type": (mt or {}).get("attributes", {}).get("description", "?"),
                "duty": (de or {}).get("attributes", {}).get("base") or "",
                "geo": (geo or {}).get("attributes", {}).get("description", "") if geo else "",
            }
        )
    return out


def child_codes(h4: str) -> list[dict]:
    """品目下全部商品码 [{code, description}]。"""
    d = _get_json("heading", h4)
    return [
        {
            "code": c["attributes"].get("goods_nomenclature_item_id", ""),
            "description": (c["attributes"].get("description") or "").strip(),
        }
        for c in d.get("included", [])
        if c["type"] == "commodity"
    ]


def lookup_uk(code: str) -> dict:
    """英国税率查询：4/6/8/10 位码 → 商品线列表（MFN + 优惠概览）。

    4 位 = 列出全部子码；6 位以上 = 过滤前缀。每条线带 Third country duty
    （MFN）与 Tariff preference 摘要（按贸易集团）。"""
    digits = "".join(ch for ch in code if ch.isdigit())
    if len(digits) < 4:
        return {"error": "至少 4 位"}
    h4 = digits[:4]
    children = [c for c in child_codes(h4) if c["code"].startswith(digits)]
    lines = []
    for c in children:
        try:
            d = _get_json("commodity", c["code"])
        except Exception as e:  # noqa: BLE001
            lines.append({"code": c["code"], "description": c["description"], "error": str(e)[:80]})
            continue
        com = d["data"]["attributes"]
        ms = _measures(d)
        mfn = next((m["duty"] for m in ms if m["type_id"] == "103"), "")
        seen_geo = set()
        prefs = []
        for m in ms:
            if m["type_id"] != "142" or not m["duty"] or m["geo"] in seen_geo:
                continue
            seen_geo.add(m["geo"])
            prefs.append(f"{m['geo']} {m['duty']}")
        if not mfn and not prefs:
            continue  # 6 位父码层无措施（如 6101200000），子码才带税率
        prefs = prefs[:6]
        lines.append(
            {
                "code": c["code"],
                "description": (com.get("formatted_description") or c["description"] or "").strip(),
                "mfn": mfn,                    # Third country duty（最惠国普遍税率）
                "preferences": prefs,          # FTA/GSP 优惠（集团 + 税率）
                "note": f"依据：UK Global Tariff {c['code']}，Third country duty（MFN）；优惠税率按贸易集团适用",
            }
        )
    # 有带税率的子码时，过滤掉无 MFN 的父码占位行（如 6101200000）
    real = [l for l in lines if l.get("mfn")] or lines
    return {
        "country": "GB",
        "code": digits,
        "lines": real,
        "source_note": "数据来源：GOV.UK Trade Tariff API（api.trade-tariff.service.gov.uk，英国官方）；申报以 HMRC 裁定为准",
    }


if __name__ == "__main__":
    import sys

    res = lookup_uk(sys.argv[1] if len(sys.argv) > 1 else "610120")
    for l in res["lines"]:
        print(f"{l['code']}  {l.get('mfn', ''):10s} {l['description'][:60]}")
        for p in l.get("preferences", [])[:3]:
            print(f"          优惠: {p}")
