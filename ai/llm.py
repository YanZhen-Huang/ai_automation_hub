"""LLM 接入层：OpenAI 兼容接口，可配置 DeepSeek 等。"""

from core.config import CONFIG
from core.logger import get_logger

log = get_logger("llm")


def _client():
    from openai import OpenAI
    return OpenAI(api_key=CONFIG["llm"]["api_key"],
                  base_url=CONFIG["llm"]["base_url"],
                  timeout=60, max_retries=1)


def available() -> bool:
    return bool(CONFIG["llm"]["api_key"])


def chat(messages, temperature=0.1, max_tokens=1500):
    """messages: list[{'role','content'}]，返回文本。"""
    cfg = CONFIG["llm"]
    client = _client()
    resp = client.chat.completions.create(
        model=cfg["model"],
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    content = resp.choices[0].message.content
    return content.strip() if content else ""
