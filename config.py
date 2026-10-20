"""
配置管理：路径、模型、漏斗参数。所有路径基于项目根目录。
"""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

# BGE 模型已缓存在本地时强制 HF 离线模式，跳过在线版本检查（镜像 HEAD 超时会卡 345s）。
# 本地无缓存（如 Streamlit Cloud 首次启动）则放行在线下载。
_hf_home = Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface"))
if (_hf_home / "hub" / "models--BAAI--bge-base-en-v1.5").exists():
    os.environ.setdefault("HF_HUB_OFFLINE", "1")

# ── LLM ──
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

# 漏斗各阶段温度（论文设定：抽取/子目解析低温，排序阶段略高）
TEMP_EXTRACT = 0.1   # S1 属性抽取
TEMP_RANK = 0.3      # S3/S4 排序
TEMP_RESOLVE = 0.1   # S5 子目解析
TEMP_SCORE = 0.1     # S6 最终评分

JSON_MAX_RETRIES = 3  # JSON 校验失败自修重试上限

# ── Embedding ──
EMBED_MODEL = os.getenv("EMBED_MODEL", "BAAI/bge-base-en-v1.5")
EMBED_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

# ── 漏斗参数（论文：~40 → ~10 → 3）──
N_RETRIEVE = 64   # S2 双路检索候选品目数（70 条评测：40 时 gold 召回 82.9%，64 修复融合后 94%+）
N_L1_KEEP = 10    # S3 粗排留存
N_L1_KEEP = 10    # S3 粗排留存
N_L2_KEEP = 3     # S4 精排留存（top-3 输出）

# ── 路径 ──
DATA_RAW = ROOT / "data" / "raw"
DATA_HSCODES = ROOT / "data" / "hscodes"
DATA_COMPLIANCE = ROOT / "data" / "compliance"
ARTIFACTS = ROOT / "artifacts"

HEADINGS_JSON = ARTIFACTS / "headings.json"
CLAUSES_JSONL = ARTIFACTS / "clauses.jsonl"
HIERARCHY_JSON = ARTIFACTS / "hierarchy.json"
BM25_INDEX = ARTIFACTS / "bm25.pkl"
DENSE_NPY = ARTIFACTS / "dense.npy"
DENSE_META_JSON = ARTIFACTS / "dense_meta.json"

# ── USITC 数据源 ──
USITC_EXPORT_URL = "https://hts.usitc.gov/reststop/exportList"
USITC_DOWNLOAD_URL = "https://hts.usitc.gov/download"

# 按章区间分批下载（每批 10 章）。from/to 必须是四位码边界（'81'~'90' 会漏掉 90 章整章）
CHAPTER_BATCHES = [
    (f"{a:02d}01", f"{min(a + 9, 99):02d}99") for a in range(1, 100, 10)
]
