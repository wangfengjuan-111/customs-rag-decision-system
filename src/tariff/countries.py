"""
多国关税注册表：统一 lookup(country, code) 入口。

各国数据源（全部官方；详见各 provider 模块头注释）：
    US  hts.usitc.gov exportList（离线全量，rates.py）+ 99 章叠加（calculator.py，parse_ch99.py）
    EU  TARIC 措施数据库 CIRCABC 导出（离线全量，eu.py；ingest/parse_taric.py）
    GB  GOV.UK Trade Tariff API（按需 + 磁盘缓存，uk.py）
    JP  Japan Customs 英文关税表（离线全量，jp.py；ingest/download_tariff_jp.py）
    CA  CBSA Customs Tariff HTML 章节页（离线全量，ca.py；ingest/download_tariff_ca.py）
    AU  ABF Customs Tariff Schedule 3 章节页（离线全量，au.py；ingest/download_tariff_au.py）

调研过但先不做（2026-10）：
    KR  unipass 开放 API 需韩国侧注册（外国人受限）
    SG  无机器可读官方源（税种极简：酒/烟/车/油 4 类 + GST 9%）
    TH  官网可达但未找到机器可读接口
    BR  官网可达但未确认机器可读源
    IN  icegate.gov.in 网络不可达（SSL）
    MX  sat.gob.mx 网络不可达
"""
from src.tariff import au, ca, eu, jp, uk
from src.tariff.rates import summarize as summarize_us

COUNTRIES = {
    "US": {"label": "美国（HTS + 301/232/IEEPA 叠加）", "lookup": summarize_us, "needs_country": True},
    "EU": {"label": "欧盟（TARIC 含对华反倾销）", "lookup": eu.lookup_eu, "needs_country": True},
    "GB": {"label": "英国（UK Global Tariff）", "lookup": uk.lookup_uk, "needs_country": False},
    "JP": {"label": "日本（関税率）", "lookup": jp.lookup_jp, "needs_country": False},
    "CA": {"label": "加拿大（Customs Tariff）", "lookup": ca.lookup_ca, "needs_country": False},
    "AU": {"label": "澳大利亚（Schedule 3）", "lookup": au.lookup_au, "needs_country": False},
}


def lookup(country: str, code: str, origin: str = "") -> dict:
    """统一查询入口。origin 用于 US（判定适用税率列）和 EU（反倾销措施匹配）。"""
    cfg = COUNTRIES.get(country)
    if not cfg:
        return {"error": f"不支持的国家代码 {country}，可选：{list(COUNTRIES)}"}
    if cfg["needs_country"]:
        return cfg["lookup"](code, origin)
    return cfg["lookup"](code)
