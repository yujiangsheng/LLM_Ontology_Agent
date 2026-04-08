"""
memory.persistent — 持久记忆（经验 / 知识 / Ontology）
======================================================

持久记忆存储系统长期积累的 **结构化知识与经验**:

1. **经验库 (Experience)**
   - Agent 执行成功/失败的模式
   - 效果好的 prompt 模板
   - 常见错误与修复策略
   - LLM 输出质量评估记录

2. **知识库 (Knowledge)**
   - 已验证的领域事实
   - 推理结论与置信度
   - 跨领域的通用规则

3. **Ontology 记忆**
   - 已构建的 OWL 本体图 (rdflib Graph)
   - 本体结构规范 (ontology_spec JSON)
   - 知识图谱 (KG Turtle)
   - SHACL 约束图
   - 支持 SPARQL 结构化查询

持久化:
  - 经验 / 知识以 JSON 文件存储
  - Ontology 以 RDF 文件 (.owl / .ttl) 存储
  - 支持增量更新和版本追踪

作者: Jiangsheng Yu
许可: MIT License
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field, asdict
from typing import Any

from rdflib import Graph

import config
from utils.owl_utils import run_sparql, ONT

logger = logging.getLogger(__name__)

# 持久记忆存储路径
_PERSISTENT_DIR = os.path.join(config.OUTPUT_DIR, "memory", "persistent")
os.makedirs(_PERSISTENT_DIR, exist_ok=True)


# ═══════════════════════════════════════════════════════════════
#  数据结构
# ═══════════════════════════════════════════════════════════════

@dataclass
class ExperienceEntry:
    """经验记录 — Agent 执行过程中积累的模式。"""

    id: str
    pattern: str                     # 经验描述
    category: str = "general"        # prompt / error_fix / strategy / evaluation
    success: bool = True
    agent_name: str = ""
    domain: str = ""
    confidence: float = 1.0          # 0.0 ~ 1.0
    use_count: int = 0               # 被引用次数
    timestamp: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class KnowledgeFact:
    """知识事实 — 已验证的领域结论。"""

    id: str
    statement: str                   # 事实陈述
    source: str = "reasoning"        # reasoning / user / owl / sparql
    domain: str = ""
    confidence: float = 1.0
    evidence: list[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)


# ═══════════════════════════════════════════════════════════════
#  持久记忆管理器
# ═══════════════════════════════════════════════════════════════

class PersistentMemory:
    """持久记忆 — 经验、知识、Ontology 的统一管理。

    Parameters
    ----------
    store_dir : str, optional
        存储目录，默认 ``output/memory/persistent``。
    """

    def __init__(self, store_dir: str | None = None):
        self._dir = store_dir or _PERSISTENT_DIR
        os.makedirs(self._dir, exist_ok=True)

        self._exp_path = os.path.join(self._dir, "experiences.json")
        self._know_path = os.path.join(self._dir, "knowledge.json")

        self._experiences: list[ExperienceEntry] = []
        self._knowledge: list[KnowledgeFact] = []

        # Ontology 缓存 (rdflib Graph)
        self._ontology_graph: Graph | None = None
        self._kg_graph: Graph | None = None
        self._ontology_spec: dict | None = None

        self._load()

    # ═══════════════════════════════════════════════════════════
    #  经验库
    # ═══════════════════════════════════════════════════════════

    def add_experience(
        self,
        pattern: str,
        *,
        category: str = "general",
        success: bool = True,
        agent_name: str = "",
        domain: str = "",
        confidence: float = 1.0,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """记录一条执行经验。"""
        eid = f"exp_{int(time.time() * 1000)}_{len(self._experiences)}"
        entry = ExperienceEntry(
            id=eid,
            pattern=pattern,
            category=category,
            success=success,
            agent_name=agent_name,
            domain=domain,
            confidence=confidence,
            metadata=metadata or {},
        )
        self._experiences.append(entry)
        self._save_experiences()
        return eid

    def get_experiences(
        self,
        *,
        category: str | None = None,
        agent_name: str | None = None,
        success_only: bool = False,
        domain: str | None = None,
        top_k: int = 10,
    ) -> list[ExperienceEntry]:
        """检索经验记录。"""
        results = self._experiences
        if category:
            results = [e for e in results if e.category == category]
        if agent_name:
            results = [e for e in results if e.agent_name == agent_name]
        if success_only:
            results = [e for e in results if e.success]
        if domain:
            results = [e for e in results if e.domain == domain]
        # 按置信度和引用次数排序
        results.sort(key=lambda e: (e.confidence, e.use_count), reverse=True)
        return results[:top_k]

    def increment_use(self, experience_id: str) -> None:
        """标记某条经验被引用。"""
        for e in self._experiences:
            if e.id == experience_id:
                e.use_count += 1
                self._save_experiences()
                return

    # ═══════════════════════════════════════════════════════════
    #  知识库
    # ═══════════════════════════════════════════════════════════

    def add_knowledge(
        self,
        statement: str,
        *,
        source: str = "reasoning",
        domain: str = "",
        confidence: float = 1.0,
        evidence: list[str] | None = None,
    ) -> str:
        """添加一条已验证的知识事实。"""
        kid = f"know_{int(time.time() * 1000)}_{len(self._knowledge)}"
        fact = KnowledgeFact(
            id=kid,
            statement=statement,
            source=source,
            domain=domain,
            confidence=confidence,
            evidence=evidence or [],
        )
        self._knowledge.append(fact)
        self._save_knowledge()
        return kid

    def search_knowledge(
        self,
        query: str,
        *,
        domain: str | None = None,
        top_k: int = 5,
    ) -> list[KnowledgeFact]:
        """基于关键词的知识检索。"""
        results = self._knowledge
        if domain:
            results = [k for k in results if k.domain == domain]
        # 简单关键词匹配 + 置信度排序
        query_lower = query.lower()
        matched = [k for k in results if query_lower in k.statement.lower()]
        if not matched:
            # 退化为全部，按置信度排序
            matched = results
        matched.sort(key=lambda k: k.confidence, reverse=True)
        return matched[:top_k]

    # ═══════════════════════════════════════════════════════════
    #  Ontology 记忆
    # ═══════════════════════════════════════════════════════════

    def load_ontology(
        self,
        ontology_graph: Graph | None = None,
        kg_graph: Graph | None = None,
        ontology_spec: dict | None = None,
    ) -> None:
        """加载/更新 Ontology 到记忆中。"""
        if ontology_graph is not None:
            self._ontology_graph = ontology_graph
        if kg_graph is not None:
            self._kg_graph = kg_graph
        if ontology_spec is not None:
            self._ontology_spec = ontology_spec

    def load_ontology_from_files(self) -> bool:
        """从 output/ 目录的文件自动加载 Ontology。"""
        import glob

        # OWL 本体
        owl_files = glob.glob(os.path.join(config.OUTPUT_DIR, "*_ontology.owl"))
        if owl_files:
            self._ontology_graph = Graph()
            self._ontology_graph.parse(owl_files[0])

        # 知识图谱
        kg_path = os.path.join(config.OUTPUT_DIR, "knowledge_graph.ttl")
        if os.path.exists(kg_path):
            self._kg_graph = Graph()
            self._kg_graph.parse(kg_path, format="turtle")

        # 本体规范
        spec_path = os.path.join(config.OUTPUT_DIR, "ontology_spec.json")
        if os.path.exists(spec_path):
            with open(spec_path, encoding="utf-8") as f:
                self._ontology_spec = json.load(f)

        loaded = self._ontology_graph is not None
        if loaded:
            logger.info("Ontology 已加载至持久记忆")
        return loaded

    def query_ontology(self, sparql: str) -> list[dict]:
        """在 Ontology + KG 上执行 SPARQL 查询。

        Parameters
        ----------
        sparql : str
            SPARQL SELECT 查询。

        Returns
        -------
        list[dict]
            查询结果行。
        """
        g = self._get_merged_graph()
        if g is None:
            return []
        return run_sparql(g, sparql)

    def get_ontology_summary(self) -> str:
        """返回当前 Ontology 的结构摘要。"""
        if not self._ontology_spec:
            return "（无 Ontology）"
        spec = self._ontology_spec
        classes = [c["name"] for c in spec.get("classes", [])]
        obj_props = [p["name"] for p in spec.get("object_properties", [])]
        data_props = [p["name"] for p in spec.get("data_properties", [])]
        lines = [
            f"类 ({len(classes)}): {', '.join(classes[:10])}",
            f"对象属性 ({len(obj_props)}): {', '.join(obj_props[:10])}",
            f"数据属性 ({len(data_props)}): {', '.join(data_props[:10])}",
        ]
        if self._ontology_graph:
            lines.append(f"本体三元组数: {len(self._ontology_graph)}")
        if self._kg_graph:
            lines.append(f"知识图谱三元组数: {len(self._kg_graph)}")
        return "\n".join(lines)

    @property
    def has_ontology(self) -> bool:
        return self._ontology_graph is not None

    @property
    def ontology_graph(self) -> Graph | None:
        return self._ontology_graph

    @property
    def kg_graph(self) -> Graph | None:
        return self._kg_graph

    @property
    def ontology_spec(self) -> dict | None:
        return self._ontology_spec

    # ── 内部辅助 ────────────────────────────────────────────

    def _get_merged_graph(self) -> Graph | None:
        """合并本体图和知识图谱。"""
        if self._ontology_graph is None:
            return None
        merged = Graph()
        for t in self._ontology_graph:
            merged.add(t)
        if self._kg_graph:
            for t in self._kg_graph:
                merged.add(t)
        return merged

    def _save_experiences(self) -> None:
        data = [asdict(e) for e in self._experiences]
        with open(self._exp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _save_knowledge(self) -> None:
        data = [asdict(k) for k in self._knowledge]
        with open(self._know_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _load(self) -> None:
        # 经验
        if os.path.exists(self._exp_path):
            try:
                with open(self._exp_path, encoding="utf-8") as f:
                    data = json.load(f)
                self._experiences = [ExperienceEntry(**item) for item in data]
                logger.info("经验库已加载: %d 条", len(self._experiences))
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning("经验库加载失败: %s", e)

        # 知识
        if os.path.exists(self._know_path):
            try:
                with open(self._know_path, encoding="utf-8") as f:
                    data = json.load(f)
                self._knowledge = [KnowledgeFact(**item) for item in data]
                logger.info("知识库已加载: %d 条", len(self._knowledge))
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning("知识库加载失败: %s", e)
