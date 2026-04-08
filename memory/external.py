"""
memory.external — 外部记忆（RAG 文档检索 + 网络搜索）
=====================================================

外部记忆为智能体提供超出自身训练数据和本地知识库的信息获取能力:

1. **RAG 文档检索**
   - 加载本地文档（.txt / .md / .docx）
   - 文档分块 → 向量化 → 存储
   - 查询时按向量相似度检索 Top-K 相关段落

2. **网络搜索**（可选）
   - 通过可配置的搜索 API 获取外部信息
   - 目前支持简单 HTTP 搜索接口
   - 搜索结果自动摘要后注入 Agent 上下文

设计原则:
  - 外部记忆是 **补充** 而非替代 — 优先使用 Ontology 和长期记忆
  - 搜索结果需经 Agent 审核后才纳入推理
  - RAG 检索结果自动标注来源文件和位置

作者: Jiangsheng Yu
许可: MIT License
"""
from __future__ import annotations

import json
import logging
import math
import os
import time
from dataclasses import dataclass, field
from typing import Any

import config

logger = logging.getLogger(__name__)

# RAG 索引存储路径
_RAG_DIR = os.path.join(config.OUTPUT_DIR, "memory", "rag")
os.makedirs(_RAG_DIR, exist_ok=True)


# ═══════════════════════════════════════════════════════════════
#  数据结构
# ═══════════════════════════════════════════════════════════════

@dataclass
class DocumentChunk:
    """文档分块 — RAG 检索的基本单元。"""

    chunk_id: str
    content: str
    source_file: str              # 来源文件路径
    chunk_index: int              # 在源文件中的块编号
    embedding: list[float] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SearchResult:
    """网络搜索单条结果。"""

    title: str
    snippet: str
    url: str = ""
    timestamp: float = field(default_factory=time.time)


# ═══════════════════════════════════════════════════════════════
#  RAG 文档检索
# ═══════════════════════════════════════════════════════════════

class RAGMemory:
    """RAG 文档检索 — 本地文档的分块向量化与语义检索。

    Parameters
    ----------
    store_dir : str, optional
        RAG 索引存储目录。
    chunk_size : int
        分块大小（字符数），默认 500 字。
    chunk_overlap : int
        块间重叠字符数，默认 100 字。
    """

    def __init__(
        self,
        store_dir: str | None = None,
        chunk_size: int = 500,
        chunk_overlap: int = 100,
    ):
        self._dir = store_dir or _RAG_DIR
        os.makedirs(self._dir, exist_ok=True)
        self._index_path = os.path.join(self._dir, "rag_index.json")
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap
        self._chunks: list[DocumentChunk] = []
        self._load_index()

    # ── 文档加载 ────────────────────────────────────────────

    def add_document(self, file_path: str) -> int:
        """加载一份文档: 分块 → 向量化 → 存储。

        Parameters
        ----------
        file_path : str
            文档路径 (.txt / .md / .docx)。

        Returns
        -------
        int
            新增的分块数。
        """
        from utils.document_loader import load_text

        abs_path = os.path.abspath(file_path)
        text = load_text(abs_path)
        chunks_text = self._split_text(text)

        new_count = 0
        for i, chunk_text in enumerate(chunks_text):
            chunk_id = f"rag_{os.path.basename(abs_path)}_{i}"
            # 跳过已存在的块
            if any(c.chunk_id == chunk_id for c in self._chunks):
                continue
            embedding = self._embed(chunk_text)
            chunk = DocumentChunk(
                chunk_id=chunk_id,
                content=chunk_text,
                source_file=abs_path,
                chunk_index=i,
                embedding=embedding,
            )
            self._chunks.append(chunk)
            new_count += 1

        if new_count > 0:
            self._save_index()
            logger.info("RAG 新增 %d 块 (来自 %s)", new_count, file_path)
        return new_count

    def add_text(self, text: str, source_name: str = "inline") -> int:
        """将纯文本分块并加入 RAG 索引。"""
        chunks_text = self._split_text(text)
        new_count = 0
        for i, chunk_text in enumerate(chunks_text):
            chunk_id = f"rag_{source_name}_{i}_{int(time.time())}"
            embedding = self._embed(chunk_text)
            chunk = DocumentChunk(
                chunk_id=chunk_id,
                content=chunk_text,
                source_file=source_name,
                chunk_index=i,
                embedding=embedding,
            )
            self._chunks.append(chunk)
            new_count += 1

        if new_count > 0:
            self._save_index()
        return new_count

    # ── 语义检索 ────────────────────────────────────────────

    def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        threshold: float = 0.3,
    ) -> list[dict[str, Any]]:
        """基于向量相似度检索最相关的文档块。

        Parameters
        ----------
        query : str
            查询文本。
        top_k : int
            返回最多 *top_k* 条结果，默认 5。
        threshold : float
            最低相似度阈值，默认 0.3。

        Returns
        -------
        list[dict]
            每项包含 ``content``, ``source_file``, ``score``, ``chunk_index``。
        """
        query_vec = self._embed(query)
        if not query_vec:
            return []

        scored: list[tuple[float, DocumentChunk]] = []
        for chunk in self._chunks:
            if not chunk.embedding:
                continue
            score = _cosine_similarity(query_vec, chunk.embedding)
            if score >= threshold:
                scored.append((score, chunk))

        scored.sort(key=lambda x: x[0], reverse=True)

        return [
            {
                "content": chunk.content,
                "source_file": chunk.source_file,
                "chunk_index": chunk.chunk_index,
                "score": round(score, 4),
            }
            for score, chunk in scored[:top_k]
        ]

    @property
    def chunk_count(self) -> int:
        return len(self._chunks)

    @property
    def source_files(self) -> list[str]:
        """返回已索引的所有源文件列表。"""
        return list({c.source_file for c in self._chunks})

    # ── 文本分块 ────────────────────────────────────────────

    def _split_text(self, text: str) -> list[str]:
        """将文本按固定窗口分块，块间有重叠。"""
        if not text:
            return []

        chunks: list[str] = []
        step = self._chunk_size - self._chunk_overlap
        if step <= 0:
            step = self._chunk_size

        start = 0
        while start < len(text):
            end = start + self._chunk_size
            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            start += step
        return chunks

    # ── 持久化 ──────────────────────────────────────────────

    def _save_index(self) -> None:
        data = []
        for c in self._chunks:
            data.append({
                "chunk_id": c.chunk_id,
                "content": c.content,
                "source_file": c.source_file,
                "chunk_index": c.chunk_index,
                "embedding": c.embedding,
                "metadata": c.metadata,
            })
        with open(self._index_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)

    def _load_index(self) -> None:
        if not os.path.exists(self._index_path):
            return
        try:
            with open(self._index_path, encoding="utf-8") as f:
                data = json.load(f)
            self._chunks = [DocumentChunk(**item) for item in data]
            logger.info("RAG 索引已加载: %d 块", len(self._chunks))
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning("RAG 索引加载失败: %s", e)
            self._chunks = []

    @staticmethod
    def _embed(text: str) -> list[float]:
        try:
            import llm_client
            vectors = llm_client.embed([text])
            return vectors[0] if vectors else []
        except Exception as e:
            logger.warning("Embedding 生成失败: %s", e)
            return []


# ═══════════════════════════════════════════════════════════════
#  网络搜索
# ═══════════════════════════════════════════════════════════════

class WebSearchMemory:
    """网络搜索记忆 — 通过搜索 API 获取外部信息。

    目前实现为一个 **缓存层**：搜索结果会被缓存，避免重复查询。
    实际搜索需要配置搜索 API。

    Parameters
    ----------
    cache_dir : str, optional
        搜索缓存目录。
    api_url : str, optional
        搜索 API 端点 URL。
    """

    def __init__(
        self,
        cache_dir: str | None = None,
        api_url: str | None = None,
    ):
        self._dir = cache_dir or os.path.join(config.OUTPUT_DIR, "memory", "web_cache")
        os.makedirs(self._dir, exist_ok=True)
        self._cache_path = os.path.join(self._dir, "search_cache.json")
        self._api_url = api_url or os.getenv("WEB_SEARCH_API_URL", "")
        self._cache: dict[str, list[dict]] = {}
        self._load_cache()

    def search(self, query: str, *, max_results: int = 5) -> list[SearchResult]:
        """执行网络搜索，优先使用缓存。

        Parameters
        ----------
        query : str
            搜索查询文本。
        max_results : int
            最大返回结果数。

        Returns
        -------
        list[SearchResult]
            搜索结果列表。如果 API 未配置或请求失败，返回空列表。
        """
        # 检查缓存
        if query in self._cache:
            logger.debug("网络搜索命中缓存: %s", query)
            return [SearchResult(**r) for r in self._cache[query][:max_results]]

        # 检查 API 是否已配置
        if not self._api_url:
            logger.debug("网络搜索 API 未配置 (WEB_SEARCH_API_URL)，跳过")
            return []

        # 执行搜索
        results = self._do_search(query, max_results)
        if results:
            self._cache[query] = [
                {"title": r.title, "snippet": r.snippet, "url": r.url, "timestamp": r.timestamp}
                for r in results
            ]
            self._save_cache()
        return results

    def _do_search(self, query: str, max_results: int) -> list[SearchResult]:
        """执行实际的 HTTP 搜索请求。"""
        import urllib.request
        import urllib.parse
        import urllib.error

        try:
            params = urllib.parse.urlencode({"q": query, "limit": max_results})
            url = f"{self._api_url}?{params}"
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode())

            results: list[SearchResult] = []
            for item in data.get("results", data.get("items", []))[:max_results]:
                results.append(SearchResult(
                    title=item.get("title", ""),
                    snippet=item.get("snippet", item.get("description", "")),
                    url=item.get("url", item.get("link", "")),
                ))
            return results
        except Exception as e:
            logger.warning("网络搜索失败: %s", e)
            return []

    def _save_cache(self) -> None:
        with open(self._cache_path, "w", encoding="utf-8") as f:
            json.dump(self._cache, f, ensure_ascii=False, indent=2)

    def _load_cache(self) -> None:
        if not os.path.exists(self._cache_path):
            return
        try:
            with open(self._cache_path, encoding="utf-8") as f:
                self._cache = json.load(f)
        except (json.JSONDecodeError, TypeError):
            self._cache = {}


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
