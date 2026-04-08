"""
llm_client — Ollama REST API 客户端
=====================================

封装 Ollama ``/api/chat`` 与 ``/api/embed`` 端点，为上层 Agent 提供
统一的 LLM 调用接口。仅依赖 Python 标准库 ``urllib``，无需额外 HTTP 库。

主要函数
--------
- :func:`chat`      — 单轮对话，返回纯文本
- :func:`chat_json` — 单轮对话，强制 JSON 输出并自动解析
- :func:`embed`     — 文本向量化

Usage Example::

    import llm_client

    # 纯文本问答
    answer = llm_client.chat("什么是 OWL 本体？", system="你是知识工程专家")

    # JSON 模式 — 自动解析
    data = llm_client.chat_json("列出三种 OWL 公理", system="返回 JSON")
    # => {"axioms": [...]}

    # 文本向量化（用于语义检索）
    vectors = llm_client.embed(["设备故障", "传感器过热"])
    # => [[0.12, -0.03, ...], [0.08, 0.15, ...]]

作者: Jiangsheng Yu
许可: MIT License
"""
from __future__ import annotations

import json
import logging
import re
import time
import urllib.request
import urllib.error
from typing import Any

import config

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
#  对话
# ═══════════════════════════════════════════════════════════════

def chat(
    prompt: str,
    *,
    system: str = "",
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    json_mode: bool = False,
) -> str:
    """向 Ollama ``/api/chat`` 发送单轮对话，返回 assistant 文本。

    Parameters
    ----------
    prompt : str
        用户消息正文。
    system : str, optional
        系统提示词（角色设定）。
    model : str, optional
        模型名称，默认取 ``config.DEFAULT_MODEL``。
    temperature : float, optional
        采样温度，默认取 ``config.LLM_TEMPERATURE``。
    max_tokens : int, optional
        最大生成 token 数，默认取 ``config.LLM_MAX_TOKENS``。
    json_mode : bool, optional
        是否强制模型输出 JSON 格式。

    Returns
    -------
    str
        模型返回的文本内容。
    """
    model = model or config.DEFAULT_MODEL
    temperature = temperature if temperature is not None else config.LLM_TEMPERATURE
    max_tokens = max_tokens or config.LLM_MAX_TOKENS

    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    body: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
        },
    }
    if json_mode:
        body["format"] = "json"

    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{config.OLLAMA_BASE_URL}/api/chat",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    # 带重试的请求发送（应对网络抖动和服务重启）
    last_exc: Exception | None = None
    for attempt in range(1, config.LLM_RETRY_COUNT + 2):  # +2: 首次 +重试次数
        try:
            with urllib.request.urlopen(req, timeout=config.LLM_TIMEOUT) as resp:
                result = json.loads(resp.read().decode())
            return result["message"]["content"]
        except urllib.error.URLError as exc:
            last_exc = exc
            if attempt <= config.LLM_RETRY_COUNT:
                wait = 2 ** attempt  # 指数退避: 2s, 4s, ...
                logger.warning(
                    "Ollama 请求失败 (第 %d 次), %ds 后重试: %s",
                    attempt, wait, exc,
                )
                time.sleep(wait)

    logger.error("Ollama 请求最终失败 (%s): %s", config.OLLAMA_BASE_URL, last_exc)
    raise RuntimeError(
        f"无法连接 Ollama ({config.OLLAMA_BASE_URL})，请确认服务已启动"
    ) from last_exc


# ═══════════════════════════════════════════════════════════════
#  JSON 对话
# ═══════════════════════════════════════════════════════════════

def chat_json(prompt: str, *, system: str = "", **kwargs) -> dict | list:
    """调用 :func:`chat` 并将返回文本解析为 JSON 对象。

    自动剥离模型偶尔包裹的 Markdown 代码块标记（````json ... ```）。

    Returns
    -------
    dict | list
        解析后的 JSON 数据。

    Raises
    ------
    json.JSONDecodeError
        当模型返回非法 JSON 时抛出。
    """
    raw = chat(prompt, system=system, json_mode=True, **kwargs)

    # 剥离 markdown 代码块包裹
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?", "", raw)
        raw = re.sub(r"```$", "", raw)
        raw = raw.strip()

    return json.loads(raw)


# ═══════════════════════════════════════════════════════════════
#  文本嵌入
# ═══════════════════════════════════════════════════════════════

def embed(texts: list[str], *, model: str | None = None) -> list[list[float]]:
    """调用 Ollama ``/api/embed`` 将文本列表转为向量。

    Parameters
    ----------
    texts : list[str]
        待向量化的文本列表。
    model : str, optional
        嵌入模型名称，默认取 ``config.EMBED_MODEL``。

    Returns
    -------
    list[list[float]]
        与 *texts* 等长的向量列表。
    """
    model = model or config.EMBED_MODEL
    body = json.dumps({"model": model, "input": texts}).encode()
    req = urllib.request.Request(
        f"{config.OLLAMA_BASE_URL}/api/embed",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        result = json.loads(resp.read().decode())
    return result["embeddings"]
