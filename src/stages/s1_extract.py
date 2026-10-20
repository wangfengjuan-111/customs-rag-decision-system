"""
Stage 1 · 属性抽取：自由文本商品描述 → 固定 schema 的结构化属性。

对应论文：把人类归类员"翻税则前的预读"外部化；营销词标记为非归类装饰。
S2 检索将同时用原始描述与本阶段属性（原文+属性双查询）。
"""
import json

from pydantic import BaseModel, Field

from config import TEMP_EXTRACT
from src.llm.client import ask_json

SYSTEM = (
    "You are a customs classification assistant. Extract structured product attributes "
    "from a free-form e-commerce product description for HS tariff classification. "
    "Only use information present in the description. Marketing terms that do not affect "
    "classification must be listed in decorations, never in the substantive fields."
)


class Attributes(BaseModel):
    material: str = Field(description="Primary material/substance, e.g. 'thermoplastic polyurethane (TPU)'. 'unspecified' if unknown.")
    form: str = Field(description="Physical form/processing state: primary form (granule/powder/liquid), intermediate form (sheet/film/monofilament/profile), finished article, or part.")
    function: str = Field(description="Principal function or what the product does.")
    end_use: str = Field(description="Intended end use / what machine or scenario it serves. 'unspecified' if unknown.")
    features: list[str] = Field(description="Salient distinguishing features relevant to classification (max 5).")
    decorations: list[str] = Field(description="Marketing/fashion words with no classification weight (max 8).")
    is_part: bool = Field(description="True if the product is a part/component of a machine or article rather than a finished article of its own.")
    is_set: bool = Field(description="True if the product is a composite good or retail set of different materials/components.")


def extract(product_description: str, product_attributes: str = "") -> Attributes:
    """product_attributes: 卖家结构化属性 JSON 字符串（HSCodeComp 提供，真实场景可为空）。"""
    user = "Product description:\n" + product_description
    if product_attributes:
        user += "\n\nSeller attributes (may contain noise):\n" + product_attributes
    user += "\n\nExtract attributes as JSON per the schema."
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": user},
    ]
    return ask_json(messages, Attributes, temperature=TEMP_EXTRACT)


def to_query_text(attrs: Attributes) -> str:
    """S2 增强查询串：材质+形态+功能关键词。"""
    parts = [attrs.material, attrs.form, attrs.function, attrs.end_use, *attrs.features]
    return " ".join(p for p in parts if p and p.lower() != "unspecified")


if __name__ == "__main__":
    desc = "50 pcs HD hydrogel film for all phones, matte / anti-blue-ray / UV / privacy, TPU material"
    a = extract(desc)
    print(json.dumps(a.model_dump(), ensure_ascii=False, indent=1))
    print("\nS2 augmented query:", to_query_text(a))
