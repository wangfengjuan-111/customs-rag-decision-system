"""
DeepSeek LLM client：JSON mode + pydantic 校验失败自修重试 + 磁盘缓存。

设计要点（对应论文"确定性工作流"哲学）：
- 每次调用 = 一次窄任务，输入输出都有严格 schema
- json_object 模式强制合法 JSON；pydantic 校验不过则把错误信息回喂模型自修（≤3 次）
- 以 (model, messages, temperature) 哈希为 key 落盘缓存，重跑评测不重复计费
"""
import hashlib
import re
import json
import os
import time
from pathlib import Path

from openai import OpenAI
from pydantic import BaseModel, ValidationError

from config import (
    DEEPSEEK_API_KEY,
    DEEPSEEK_BASE_URL,
    DEEPSEEK_MODEL,
    JSON_MAX_RETRIES,
    ROOT,
)

CACHE_DIR = ROOT / "artifacts" / "llm_cache"
_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        if not DEEPSEEK_API_KEY:
            raise ValueError("DEEPSEEK_API_KEY 未配置，检查 hs_tariff_agent/.env")
        _client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)
    return _client


def _cache_key(messages: list[dict], model: str, temperature: float) -> str:
    blob = json.dumps({"m": messages, "model": model, "t": temperature}, ensure_ascii=False)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()


def ask_json(
    messages: list[dict],
    schema: type[BaseModel],
    temperature: float = 0.1,
    model: str = DEEPSEEK_MODEL,
    use_cache: bool = True,
) -> BaseModel:
    """发送对话并强制返回符合 schema 的对象。"""
    key = _cache_key(messages, model, temperature)
    cache_file = CACHE_DIR / f"{key}.json"

    if use_cache and cache_file.exists():
        try:
            return schema.model_validate(json.loads(cache_file.read_text(encoding="utf-8")))
        except (ValidationError, json.JSONDecodeError):
            pass  # 缓存损坏则重新请求

    client = _get_client()
    last_err = ""
    schema_json = json.dumps(schema.model_json_schema(), ensure_ascii=False)
    # DeepSeek json_object 模式要求 prompt 含 "json" 字样——client 层统一保证
    msgs_base = list(messages)
    if msgs_base and msgs_base[0].get("role") == "system":
        if "json" not in msgs_base[0]["content"].lower():
            msgs_base[0] = {**msgs_base[0], "content": msgs_base[0]["content"] + "\nRespond with a single JSON object."}
    else:
        msgs_base = [{"role": "system", "content": "Respond with a single JSON object."}] + msgs_base
    for attempt in range(JSON_MAX_RETRIES):
        msgs = list(msgs_base)
        if last_err:
            # 自修：附上 schema 定义 + 校验错误 + 上次输出
            msgs = msgs + [
                {"role": "assistant", "content": _last_raw.get(key, "")},
                {
                    "role": "user",
                    "content": (
                        f"Your previous JSON output failed validation.\n"
                        f"Errors: {last_err}\n"
                        f"Expected JSON schema:\n{schema_json}\n"
                        f"Output ONLY one corrected JSON object matching the schema, no extra keys, no markdown."
                    ),
                },
            ]
        resp = client.chat.completions.create(
            model=model,
            messages=msgs,
            temperature=temperature,
            response_format={"type": "json_object"},
        )
        raw = resp.choices[0].message.content or ""
        _last_raw[key] = raw
        try:
            cleaned = raw.strip()
            if cleaned.startswith("```"):  # 兼容围栏
                cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned)
            data = json.loads(cleaned)
            obj = schema.model_validate(data)
            if use_cache:
                CACHE_DIR.mkdir(parents=True, exist_ok=True)
                cache_file.write_text(cleaned, encoding="utf-8")
            return obj
        except json.JSONDecodeError as e:
            last_err = f"invalid JSON: {e}"
        except ValidationError as e:
            last_err = json.dumps(e.errors()[:3], ensure_ascii=False, default=str)
        time.sleep(1.5 * (attempt + 1))

    raise RuntimeError(f"JSON 校验连续 {JSON_MAX_RETRIES} 次失败: {last_err[:300]}")


_last_raw: dict[str, str] = {}
