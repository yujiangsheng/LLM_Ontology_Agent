"""
memory.long_term — 长期记忆（跨会话向量检索）
==============================================

长期记忆在多次会话之间持久化，并通过 **向量相似度** 实现语义检索。

存储内容:
  - 历史对话摘要
  - 过去的推理结论
  - 用户反馈与纠正
  - Agent 运行日志中的关键事件

底层机制:
  - 使用 Ollama embedding API (``llm_client.embed``) 生成向量
  - 以 JSON 文件持久化（向量 + 元数据）
  - 检索时计算余弦相似度，返回 Top-K 条目

作者: Jiangsheng Yu
许可: MIT License
"""
from __future__ import annotations

import json
import logging
import math
import os
import time
from dataclasses import dataclass, field, asdict
from typing import Any

import config

logger = logging.getLogger(__name__)

# 长期记忆存储路径
_LONG_TERM_DIR = os.path.join(config.OUTPUT_DIR, "memory", "long_term")
os.makedirs(_LONG_TERM_DIR, exist_ok=True)

_INDEX_PATH = os.path.join(_LONG_TERM_DIR, "index.json")


@dataclass
class LongTermEntry:
    """长期记忆单条记录。"""

    id: str
    content: str
    category: str = "general"        # reasoning / feedback / event / summary
    source_agent: str = ""
    timestamp: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)
    embedding: list[float] = field(default_factory=list)


class LongTermMemory:
    """跨会话长期记忆 — 基于向量相似度的语义检索。

    Parameters
    ----------
    store_dir : str, optional
        存储目录，默认 ``output/memory/long_term``。
    """

    def __init__(self, store_dir: str | None = None):
        self._dir = store_dir or _LONG_TERM_DIR
        os.makedirs(self._dir, exist_ok=True)
        self._index_path = os.path.join(self._dir, "index.json")
        self._entries: list[LongTermEntry] = []
        self._load()

    # ── 写入 ────────────────────────────────────────────────

    def add(
        self,
        content: str,
        *,
        category: str = "general",
        source_agent: str = "",
        metadata: dict[str, Any] | None = None,
        embedding: list[float] | None = None,
    ) -> str:
        """添加一条长期记忆并持久化。

        Parameters
        ----------
        content : str
            记忆内容文本。
        category : str
            分类: ``reasoning`` / ``feedback`` / ``event`` / ``summary``。
        embedding : list[float], optional
            预计算的向量。如果为 None，调用 ``_embed`` 自动生成。

        Returns
        -------
        str
            新条目的 ID。
        """
        entry_id = f"ltm_{int(time.time() * 1000)}_{len(self._entries)}"
        if embedding is None:
            embedding = self._embed(content)
        entry = LongTermEntry(
            id=entry_id,
            content=content,
            category=category,
            source_agent=source_agent,
            metadata=metadata or {},
            embedding=embedding,
        )
        self._entries.append(entry)
        self._save()
        logger.debug("长期记忆新增: %s (category=%s)", entry_id, category)
        return entry_id

    # ── 语义检索 ────────────────────────────────────────────

    def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        category: str | None = None,
        threshold: float = 0.3,
    ) -> list[dict[str, Any]]:
        """基于向量相似度检索最相关的记忆条目。

        Parameters
        ----------
        query : str
            查询文本。
        top_k : int
            返回最多 *top_k* 条结果，默认 5。
        category : str, optional
            仅在指定分类中检索。
        threshold : float
            最低相似度阈值，默认 0.3。

        Returns
        -------
        list[dict]
            每项包含 ``content``, ``category``, ``score``, ``metadata``。
        """
        query_vec = self._embed(query)
        if not query_vec:
            return []

        candidates = self._entries
        if category:
            candidates = [e for e in candidates if e.category == category]

        scored: list[tuple[float, LongTermEntry]] = []
        for entry in candidates:
            if not entry.embedding:
                continue
            score = _cosine_similarity(query_vec, entry.embedding)
            if score >= threshold:
                scored.append((score, entry))

        scored.sort(key=lambda x: x[0], reverse=True)

        return [
            {
                "id": entry.id,
                "content": entry.content,
                "category": entry.category,
                "score": round(score, 4),
                "source_agent": entry.source_agent,
                "metadata": entry.metadata,
            }
            for score, entry in scored[:top_k]
        ]

    # ── 按分类/全部检索 ─────────────────────────────────────

    def by_category(self, category: str) -> list[LongTermEntry]:
        """返回指定分类的所有条目。"""
        return [e for e in self._entries if e.category == category]

    def all_entries(self) -> list[LongTermEntry]:
        """返回所有长期记忆条目。"""
        return list(self._entries)

    @property
    def size(self) -> int:
        return len(self._entries)

    # ── 持久化 ──────────────────────────────────────────────

    def _save(self) -> None:
        """将所有条目序列化为 JSON 文件。"""
        data = [asdict(e) for e in self._entries]
        with open(self._index_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _load(self) -> None:
        """从 JSON 文件恢复所有条目。"""
        if not os.path.exists(self._index_path):
            return
        try:
            with open(self._index_path, encoding="utf-8") as f:
                data = json.load(f)
            self._entries = [LongTermEntry(**item) for item in data]
            logger.info("长期记忆已加载: %d 条", len(self._entries))
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning("长期记忆加载失败: %s", e)
            self._entries = []

    # ── 向量生成 ────────────────────────────────────────────

    @staticmethod
    def _embed(text: str) -> list[float]:
        """调用 Ollama embedding API 生成文本向量。

        嵌入失败时返回空列表，不阻塞主流程。
        """
        try:
            import llm_client
            vectors = llm_client.embed([text])
            return vectors[0] if vectors else []
        except Exception as e:
            logger.warning("Embedding 生成失败: %s", e)
            return []


# ═══════════════════════════════════════════════════════════════
#  辅助函数
# ═══════════════════════════════════════════════════════════════

def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """计算两个向量的余弦相似度。"""
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
