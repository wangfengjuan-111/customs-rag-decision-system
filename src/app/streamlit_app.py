"""
Streamlit 前端：三 tab（归类 / 税率 / 合规）。

归类 tab 的核心卖点是**漏斗中间态可视化**——S1 属性 → S2 候选规模 → S3 短名单 →
S4 注释感知精排（kept / demoted_by_note）→ S5 子目解析 → S6 评分与逐字引用，
每个阶段的输入输出都摊开给用户看，对应论文的确定性工作流叙事。

运行：streamlit run src/app/streamlit_app.py
"""
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

st.set_page_config(page_title="HS Tariff Agent", page_icon="🛃", layout="wide")


# ── 共享缓存 ──
@st.cache_resource
def pipeline_modules():
    from src.stages.pipeline import classify

    return classify


@st.cache_resource
def rag():
    from src.compliance.rag import get_rag

    return get_rag()


# ══════════ Tab 1 · HTS 归类 ══════════

def render_classify() -> None:
    st.header("HTS 编码归类（六阶段确定性漏斗）")
    st.caption("控制流由代码固定，LLM 只在窄阶段调用；每个阶段的中间态都可检查、可归因。")

    # 输入框绑定 session_state：切 tab / 改税率查询不丢内容
    if "classify_desc" not in st.session_state:
        st.session_state["classify_desc"] = (
            "50 pcs HD hydrogel film for all phones, matte / anti-blue-ray / UV / privacy, TPU material"
        )

    col1, col2 = st.columns([3, 2])
    with col1:
        desc = st.text_area("商品描述（英文效果最佳）", key="classify_desc", height=90)
    with col2:
        attrs_json = st.text_area("卖家结构化属性（可选，JSON）", key="classify_attrs", height=90)

    if st.button("🚀 开始归类", type="primary"):
        classify = pipeline_modules()
        try:
            with st.status("六阶段漏斗运行中…", expanded=True) as status:
                def _report(name):
                    status.update(label=f"六阶段漏斗：{name}…")

                r = classify(desc, attrs_json, on_stage=_report)
                status.update(
                    label=f"完成，总耗时 {r.timings.get('total', '?')}s",
                    state="complete",
                    expanded=False,
                )
            # 结果缓存到 session_state：rerun 不重算，直到再次点击按钮
            st.session_state["classify_result"] = r
        except Exception as e:  # noqa: BLE001
            st.error(f"流水线失败：{e}")
            return

    # 渲染只依赖缓存结果——与按钮点击解耦
    r = st.session_state.get("classify_result")
    if r is None:
        return
    if desc != r.description:
        st.caption("📎 当前显示**上次归类结果**（缓存）——输入已修改，点击「开始归类」重新查询。")
    else:
        st.caption("📎 当前显示上次归类结果（缓存）——再次点击「开始归类」刷新。")

    # ── 最终结果（用户要的第一屏：6/8 位码 + 置信度，中文）──
    top3 = r.codes_4d
    if not top3:
        st.error("未产生候选——描述可能过于简略。")
        return
    six = (r.codes_6d or [""])[0]
    eight = r.code_8d
    conf = (r.s6_verdict.get("candidates") or [{}])[0].get("confidence")
    conf_str = f"{conf:.0%}" if isinstance(conf, (int, float)) else "—"

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("6 位海关编码（HS）", six or "未确定")
    m2.metric(
        "8 位编码（美国统计细目）",
        eight or "未确定",
        help="8 位码需要描述能无歧义定位统计细目（如材质）；未确定时用 6 位码申报前的统计细目需人工确认",
    )
    m3.metric("可靠度", conf_str)
    m4.metric("总耗时", f"{r.timings.get('total', '—')}s")
    if r.ambiguous:
        st.info("⚠️ 该商品描述存在歧义（如缺少材质/用途关键信息），建议补充描述后重跑，或以人工归类为准。")
    st.session_state["last_codes_6d"] = r.codes_6d or []

    # ── 漏斗各阶段中间态（英文原文，供审计）──
    S1_LABELS = {
        "material": "材质", "form": "形态", "function": "功能", "end_use": "最终用途",
        "features": "特征", "decorations": "修饰词", "is_part": "是否部件", "is_set": "是否成套",
    }
    with st.expander("S1 · 属性抽取（结构化商品理解）", expanded=False):
        rows = [
            {"属性": S1_LABELS.get(k, k), "值（英文原文）": v if not isinstance(v, list) else "；".join(map(str, v))}
            for k, v in r.attributes.items()
            if v not in (None, "", [])
        ]
        st.dataframe(rows, use_container_width=True, hide_index=True)

    with st.expander(f"S2 · 候选检索（top-{len(r.s2_candidates)}，双查询 BM25⊕dense + RRF + 残差注入）"):
        st.write("  ".join(r.s2_candidates))

    with st.expander("S3 · L1 粗排短名单"):
        st.write("  ".join(r.s3_shortlist))

    with st.expander("S4 · L2 注释感知精排（加载章注/类注，可仅凭排除条款降级）", expanded=True):
        for e in r.s4_rankings[:10]:
            flag = ""
            if e.get("demoted_by_note"):
                flag = " 🔖 **demoted by note**"
            elif e.get("kept"):
                flag = " ✅ kept"
            st.markdown(f"- `{e['heading']}` {e.get('reason', '')[:150]}{flag}")

    with st.expander("S5 · 子目解析（GIR 6）"):
        st.json(r.s5_resolution)

    with st.expander("S6 · 最终评分与逐字引用（groundedness 反查）", expanded=True):
        v = r.s6_verdict
        for c in v.get("candidates", [])[:3]:
            conf = c.get("confidence")
            conf_str = f"{conf:g}" if isinstance(conf, (int, float)) else "—"
            head = (
                f"**候选 {c['rank']}**：`{c['heading']}`"
                + (f" → `{c['six_digit']}`" if c.get("six_digit") else "")
                + f"　可靠度 {conf_str}"
            )
            st.markdown(head)
            if c.get("pro"):
                st.markdown(f"- ✅ {c['pro']}")
            if c.get("con"):
                st.markdown(f"- ⚠️ {c['con']}")
        if v.get("load_bearing_clause"):
            st.markdown(f"**决定性条款**：`{v['load_bearing_clause']}`")
        for c in v.get("citations_verbatim", []):
            st.markdown(f"> 📖 `[{c['clause_id']}|{c['type']}]` {c['text'][:200]}")


# ══════════ Tab 2 · 关税税率 ══════════

def render_tariff() -> None:
    st.header("多国关税税率查询")
    st.caption(
        "官方数据源：美国 hts.usitc.gov（含 99 章 301/232/IEEPA 叠加）· 欧盟 TARIC（CIRCABC，含对华反倾销）· "
        "英国 GOV.UK · 日本 Japan Customs。"
    )

    default = ""
    if "last_codes_6d" in st.session_state and st.session_state["last_codes_6d"]:
        default = st.session_state["last_codes_6d"][0]

    from src.tariff.countries import COUNTRIES

    c_sel, c_code, c_origin = st.columns([1.5, 2, 1])
    with c_sel:
        country = st.selectbox(
            "目的国",
            list(COUNTRIES.keys()),
            format_func=lambda c: COUNTRIES[c]["label"],
        )
    with c_code:
        code = st.text_input("HS 编码（4/6/8 位）", value=default)
    with c_origin:
        if country in ("US", "EU"):
            ph = "CN" if country == "US" else "CN / VN / TR / IN…"
            origin = st.text_input("原产国（两位代码）", value="CN", placeholder=ph).strip().upper()
        else:
            origin = ""

    if not code:
        return

    from src.tariff.countries import lookup

    res = lookup(country, code, origin)
    if res.get("error"):
        st.error(res["error"])
        return

    if country == "US":
        _render_tariff_us(res, origin)
    elif country == "EU":
        _render_tariff_eu(res, origin)
    else:
        _render_tariff_generic(res)


def _render_tariff_eu(res: dict, origin: str) -> None:
    """欧盟：按 TARIC 行分组展示（描述 + 基础税率 + 原产国附加措施）。"""
    multiple = len(res["lines"]) > 1
    if multiple:
        st.info(f"🔎 该编码下有 {len(res['lines'])} 个 TARIC 税号行（各行税率可能不同），请按商品特征对号入座。")
    for line in res["lines"]:
        st.markdown(f"**`{line['code']}`** {line.get('description', '')}")
        st.markdown(
            f"- **基础税率（第三国关税，ERGA OMNES）**：`{line['mfn_raw']}`"
        )
        measures = line.get("measures", [])
        if origin and not measures:
            st.markdown(f"- **{origin} 附加措施**：无命中（该编码对 {origin} 无反倾销/反补贴/额外关税）")
        for m in measures:
            tag = {
                "anti_dumping": "🔴 反倾销",
                "countervailing": "🔴 反补贴",
                "additional": "🟠 额外关税",
                "customs_union": "关税同盟税率",
            }.get(m["type"], m["type"])
            cond = "（条件性税率，按企业抽样税率执行，需人工核算）" if m["duty"].get("conditional") else ""
            st.markdown(f"- **{tag}（{m['origin']}）**：`{m['duty']['raw'][:80]}` {cond}")
            st.caption(f"  法律基础：{m['legal']}")
    st.caption(f"ℹ️ {res['source_note']}")


def _render_tariff_us(res: dict, origin: str = "") -> None:
    """美国：总关税置顶 + 三列税率明细 + 99 章叠加拆解。"""
    # ── 99 章叠加拆解（301/232/IEEPA/芬太尼），总关税置顶 ──
    duty = None
    try:
        from src.tariff.calculator import compute_duty

        duty = compute_duty(res["code"], origin=origin if origin else "CN")
    except Exception as e:  # noqa: BLE001
        st.warning(f"99 章叠加计算不可用：{e}")

    if duty is not None:
        st.success(
            f"### 🇺🇸 合计从价税率：**{duty.effective_pct:.1f}%**"
            f"（MFN {duty.mfn_pct:g}% + 99 章叠加 {duty.total_addon_pct:g}%）"
            + (f" + 从量 {duty.mfn_cents_per_kg}¢/kg" if duty.mfn_cents_per_kg else "")
        )
        st.caption("公式：总关税 = MFN 基础税率 + Σ(命中的 99 章叠加，301/232/IEEPA 各授权独立累加)；豁免条款已剔除。")
        for n in duty.notes:
            st.caption(f"⚠️ {n}")

    st.info(f"🌍 适用列判定：{res['scheme_basis']}")
    COL_LABELS = {
        "general": "General 普遍税率",
        "special": "Special 协定税率",
        "column2": "Column 2 非最惠国",
    }
    for line in res["lines"]:
        st.markdown(f"**`{line['code']}`** {line['description']}")
        cols = line["columns"]
        table = [
            {
                "税率列": COL_LABELS[key] + (" ✅ **适用**" if key == line["applicable"] else ""),
                "税率解读": cols[key]["parsed"],
                "税率原文": cols[key]["raw"],
            }
            for key in ("general", "special", "column2")
        ]
        st.table(table)
    st.caption(f"ℹ️ {res['source_note']}")

    if duty is not None and duty.overlays:
        st.subheader("Chapter 99 叠加关税明细")
        rows = [
            {
                "叠加税号": o["overlay_code"],
                "税率": f"+{o['rate_pct']:g}%",
                "措施说明": o["desc"][:90],
            }
            for o in duty.overlays
        ]
        st.table(rows)


def _render_tariff_generic(res: dict) -> None:
    """英/日/加/澳：行式展示（列随国家 schema）。"""
    lines = res.get("lines", [])
    if not lines:
        st.warning("该编码下没有匹配的税率线——请检查位数与格式。")
        return
    cty = res["country"]
    if cty == "GB":
        rows = [
            {
                "商品码": l["code"],
                "描述": l["description"][:80],
                "普遍税率 (MFN)": l.get("mfn", "—"),
                "优惠税率（FTA/GSP）": "；".join(l.get("preferences", [])) or "—",
            }
            for l in lines
        ]
    elif cty == "JP":
        rows = [
            {
                "商品码": l["code_display"],
                "描述": l["description"][:80],
                "General（国内法）": l["general"] or "—",
                "Temporary（暂定）": l["temporary"] or "—",
                "WTO（协定）": l["wto"] or "—",
            }
            for l in lines
        ]
    elif cty == "CA":
        rows = [
            {
                "商品码": l["code_display"],
                "描述": l["description"][:80],
                "普遍税率 (MFN)": l["mfn"],
                "优惠协定": l["preferential"][:150] or "—",
            }
            for l in lines
        ]
    else:  # AU
        rows = [
            {
                "商品码": l["code_display"],
                "统计码": l["stat"],
                "描述": l["description"][:80],
                "普遍税率 (General)": l["general"],
            }
            for l in lines
        ]
    st.dataframe(rows, use_container_width=True, hide_index=True)
    st.caption(f"ℹ️ {res['source_note']}")


# ══════════ Tab 3 · 合规问答 ══════════

def render_compliance() -> None:
    st.header("美欧市场合规问答（RAG）")
    st.caption(f"知识库 {len(rag().chunks)} 块 / {len({c['doc'] for c in rag().chunks})} 篇策展文档；答案只基于知识库并给出官方出处。")

    q = st.text_input(
        "问题",
        value="selling plush toys to USA, what certification do I need?",
    )
    if not st.button("🔎 检索回答", type="primary"):
        return

    with st.spinner("检索 + 生成…"):
        try:
            res = rag().answer(q)
        except Exception as e:  # noqa: BLE001
            st.error(f"失败：{e}")
            return

    st.markdown(res["answer"])
    if res.get("caveats"):
        st.info(f"⚠️ {res['caveats']}")
    if res.get("citations"):
        st.markdown("**出处**")
        for c in res["citations"]:
            review = "✅" if c["review"] == "reviewed" else "🟡 draft"
            st.markdown(
                f"- [{c['n']}] {c['title']} — {c['section']}（{c['authority']}，{c['jurisdiction']}）{review} "
                f"[原文]({c['source']})"
            )
    st.caption("🟡 = 未经人工核验的草稿条目，正式合规决策请以官方原文为准。")


tab1, tab2, tab3 = st.tabs(["🛃 HTS 归类", "💵 关税税率", "📋 合规问答"])

with tab1:
    render_classify()
with tab2:
    render_tariff()
with tab3:
    render_compliance()
