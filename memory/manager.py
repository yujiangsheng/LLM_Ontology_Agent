"""
memory.manager — 统一记忆管理器
=================================

为上层 Agent 和 Orchestrator 提供 **单一入口** 访问四层记忆:

.. code-block:: text

    ┌──────────────────────────────────────────────────────┐
    │                 MemoryManager (统一接口)               │
    │                                                      │
    │   ┌─────────────┐  ┌─────────────┐  ┌────────────┐  │
    │   │ Working Mem  │  │ Long-term   │  │ Persistent │  │
    │   │ (会话级)     │  │ (向量检索)  │  │ (经验/知识) │  │
    │   └─────────────┘  └─────────────┘  └────────────┘  │
    │                                                      │
    │   ┌─────────────────────────────────────────────────┐│
    │   │        External Memory (RAG + Web Search)       ││
    │   └─────────────────────────────────────────────────┘│
    └──────────────────────────────────────────────────────┘

核心方法:
  - ``recall(query)``    — 综合四层记忆检索相关信息
  - ``memorize(...)``    — 根据信息类型写入到对应层
  - ``get_context_for_agent(agent_name)`` — 为指定 Agent 组装记忆上下文

作者: Jiangsheng Yu
许可: MIT License
"""
from __future__ import annotations

import json
import logging
from typing import Any

from memory.working import WorkingMemory
from memory.long_term import LongTermMemory
from memory.persistent import PersistentMemory
from memory.external import RAGMemory, WebSearchMemory

logger = logging.getLogger(__name__)


class MemoryManager:
    """统一记忆管理器 — 四层记忆的单一访问入口。

    Attributes
    ----------
    working : WorkingMemory
        工作记忆（会话级），会话结束自动清空。
    long_term : LongTermMemory
        长期记忆（跨会话），基于向量语义检索。
    persistent : PersistentMemory
        持久记忆（经验/知识/Ontology）。
    rag : RAGMemory
        RAG 文档检索。
    web : WebSearchMemory
        网络搜索（可选，需配置 API）。
    """

    def __init__(self):
        self.working = WorkingMemory()
        self.long_term = LongTermMemory()
        self.persistent = PersistentMemory()
        self.rag = RAGMemory()
        self.web = WebSearchMemory()

    # ═══════════════════════════════════════════════════════════
    #  综合检索
    # ═══════════════════════════════════════════════════════════

    def recall(
        self,
        query: str,
        *,
        layers: list[str] | None = None,
        top_k: int = 5,
        include_web: bool = False,
    ) -> dict[str, list[dict[str, Any]]]:
        """综合多层记忆检索与 query 相关的信息。

        Parameters
        ----------
        query : str
            查询文本。
        layers : list[str], optional
            指定检索的记忆层，可选值:
            ``"working"``, ``"long_term"``, ``"persistent"``,
            ``"rag"``, ``"web"``。
            默认 None 表示除 web 外全部。
        top_k : int
            每层返回的最大结果数。
        include_web : bool
            是否包含网络搜索（默认 False，需显式开启）。

        Returns
        -------
        dict[str, list[dict]]
            按记忆层分组的检索结果。键为层名，值为检索条目列表。
        """
        if layers is None:
            layers = ["working", "long_term", "persistent", "rag"]
            if include_web:
                layers.append("web")

        results: dict[str, list[dict[str, Any]]] = {}

        if "working" in layers:
            results["working"] = self._recall_working(query, top_k)

        if "long_term" in layers:
            results["long_term"] = self.long_term.search(query, top_k=top_k)

        if "persistent" in layers:
            results["persistent"] = self._recall_persistent(query, top_k)

        if "rag" in layers:
            results["rag"] = self.rag.search(query, top_k=top_k)

        if "web" in layers:
            web_results = self.web.search(query, max_results=top_k)
            results["web"] = [
                {"title": r.title, "snippet": r.snippet, "url": r.url}
                for r in web_results
            ]

        return results

    # ═══════════════════════════════════════════════════════════
    #  统一写入
    # ═══════════════════════════════════════════════════════════

    def memorize(
        self,
        content: str,
        *,
        layer: str = "working",
        **kwargs,
    ) -> str | None:
        """根据指定的记忆层类型写入记忆。

        Parameters
        ----------
        content : str
            记忆内容。
        layer : str
            目标记忆层: ``"working"`` / ``"long_term"`` /
            ``"experience"`` / ``"knowledge"``。
        **kwargs
            传递给具体记忆层的额外参数。

        Returns
        -------
        str | None
            新记录的 ID（对于 long_term / experience / knowledge），
            working 层返回 None。
        """
        if layer == "working":
            self.working.add(content, **kwargs)
            return None
        elif layer == "long_term":
            return self.long_term.add(content, **kwargs)
        elif layer == "experience":
            return self.persistent.add_experience(content, **kwargs)
        elif layer == "knowledge":
            return self.persistent.add_knowledge(content, **kwargs)
        else:
            logger.warning("未知记忆层: %s", layer)
            return None

    # ═══════════════════════════════════════════════════════════
    #  Agent 上下文组装
    # ═══════════════════════════════════════════════════════════

    def get_context_for_agent(
        self,
        agent_name: str,
        query: str = "",
        *,
        include_ontology: bool = True,
        include_experience: bool = True,
    ) -> str:
        """为指定 Agent 组装记忆上下文字符串。

        将多层记忆的相关信息拼装为一段文本，可直接注入 Agent 的 prompt 中。

        Parameters
        ----------
        agent_name : str
            Agent 名称。
        query : str
            当前任务描述（用于语义检索）。
        include_ontology : bool
            是否包含 Ontology 摘要。
        include_experience : bool
            是否包含相关经验。

        Returns
        -------
        str
            格式化的记忆上下文文本。
        """
        sections: list[str] = []

        # 1) 工作记忆摘要
        wm_summary = self.working.summarize()
        if wm_summary:
            sections.append(f"[工作记忆]\n{wm_summary}")

        # 2) 相关经验
        if include_experience:
            exps = self.persistent.get_experiences(
                agent_name=agent_name, success_only=True, top_k=3
            )
            if exps:
                exp_lines = [f"- {e.pattern}" for e in exps]
                sections.append(f"[相关经验]\n" + "\n".join(exp_lines))

        # 3) Ontology 摘要
        if include_ontology and self.persistent.has_ontology:
            ont_summary = self.persistent.get_ontology_summary()
            sections.append(f"[Ontology]\n{ont_summary}")

        # 4) 长期记忆检索（如果有查询）
        if query:
            lt_results = self.long_term.search(query, top_k=3)
            if lt_results:
                lt_lines = [f"- {r['content'][:200]}" for r in lt_results]
                sections.append(f"[相关长期记忆]\n" + "\n".join(lt_lines))

        # 5) RAG 检索
        if query and self.rag.chunk_count > 0:
            rag_results = self.rag.search(query, top_k=3)
            if rag_results:
                rag_lines = [
                    f"- [{r['source_file']}] {r['content'][:200]}"
                    for r in rag_results
                ]
                sections.append(f"[相关文档]\n" + "\n".join(rag_lines))

        return "\n\n".join(sections)

    # ═══════════════════════════════════════════════════════════
    #  生命周期
    # ═══════════════════════════════════════════════════════════

    def start_session(self, focus: str = "") -> None:
        """会话开始 — 初始化工作记忆。"""
        self.working.clear()
        if focus:
            self.working.set_focus(focus)
        logger.info("记忆会话已开始 (焦点: %s)", focus or "无")

    def end_session(self, *, save_summary: bool = True) -> None:
        """会话结束 — 可选将工作记忆摘要保存到长期记忆。"""
        if save_summary and len(self.working) > 0:
            summary = self.working.summarize()
            self.long_term.add(
                summary,
                category="summary",
                source_agent="MemoryManager",
            )
            logger.info("会话摘要已保存至长期记忆")
        self.working.clear()

    def load_ontology_from_context(
        self,
        ontology_graph=None,
        kg_graph=None,
        ontology_spec=None,
    ) -> None:
        """将 Orchestrator 的构建产物加载到持久记忆。"""
        self.persistent.load_ontology(
            ontology_graph=ontology_graph,
            kg_graph=kg_graph,
            ontology_spec=ontology_spec,
        )

    def load_ontology_from_files(self) -> bool:
        """从 output/ 目录自动加载 Ontology 到持久记忆。"""
        return self.persistent.load_ontology_from_files()

    # ── 统计 ────────────────────────────────────────────────

    def stats(self) -> dict[str, Any]:
        """返回各层记忆的统计信息。"""
        return {
            "working_entries": len(self.working),
            "working_focus": self.working.focus,
            "long_term_entries": self.long_term.size,
            "experiences": len(self.persistent._experiences),
            "knowledge_facts": len(self.persistent._knowledge),
            "has_ontology": self.persistent.has_ontology,
            "rag_chunks": self.rag.chunk_count,
            "rag_sources": self.rag.source_files,
        }

    # ── 内部辅助 ────────────────────────────────────────────

    def _recall_working(self, query: str, top_k: int) -> list[dict]:
        """从工作记忆中检索相关条目（关键词匹配）。"""
        query_lower = query.lower()
        results = []
        for e in reversed(self.working.entries):
            if query_lower in e.content.lower():
                results.append({
                    "content": e.content[:300],
                    "agent_name": e.agent_name,
                    "tag": e.tag,
                })
                if len(results) >= top_k:
                    break
        return results

    def _recall_persistent(self, query: str, top_k: int) -> list[dict]:
        """从持久记忆中检索知识和经验。"""
        knowledge = self.persistent.search_knowledge(query, top_k=top_k)
        return [
            {
                "type": "knowledge",
                "statement": k.statement,
                "source": k.source,
                "confidence": k.confidence,
            }
            for k in knowledge
        ]
