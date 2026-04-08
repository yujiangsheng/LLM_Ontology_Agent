"""
orchestrator — 多智能体协调器
==============================

编排所有专业智能体，实现两大核心流程：

**流程一 — 本体 & 知识图谱构建** (``build_ontology``):
  CQ 提取 → 术语抽取 → OWL 本体生成 → 知识图谱填充 → 三类自动验证

**流程二 — 领域推理** (``reason``):
  SPARQL 取证 → OWL 推理 → SHACL 验证 → LLM 软推理 → 自然语言解释

此外提供 ``load_from_output()`` 方法，从 ``output/`` 目录加载已有产物，
无需重跑构建流程即可进行推理。

内置四层记忆系统:
  - 工作记忆: 会话级短期上下文
  - 长期记忆: 跨会话向量检索
  - 持久记忆: 经验/知识/Ontology
  - 外部记忆: RAG 文档检索 + 网络搜索

作者: Jiangsheng Yu
许可: MIT License
"""
from __future__ import annotations

import glob
import json
import logging
import os
from typing import Any

from rdflib import Graph

from agents.cq_agent import CQAgent
from agents.term_extractor import TermExtractorAgent
from agents.ontology_builder import OntologyBuilderAgent
from agents.validator import ValidatorAgent
from agents.knowledge_populator import KnowledgePopulatorAgent
from agents.reasoning_agent import ReasoningAgent
from agents.explanation_agent import ExplanationAgent
from agents.prefrontal_lobe import PrefrontalLobe
from agents.base_agent import set_shared_memory
from memory.manager import MemoryManager
import config

logger = logging.getLogger(__name__)


class Orchestrator:
    """多智能体协调器 — 编排 7 个专业智能体完成本体构建与推理。

    初始化时自动创建 :class:`~memory.manager.MemoryManager` 并注入到
    所有 Agent（通过 BaseAgent 的全局共享机制），使得每个 Agent
    都可以通过 ``self.memory`` / ``self.recall()`` / ``self.memorize()``
    读写记忆。

    Attributes
    ----------
    context : dict
        流程产物缓存，包含 ``ontology_graph``, ``knowledge_graph``,
        ``ontology_spec``, ``competency_questions`` 等中间/最终结果。
    memory : MemoryManager
        四层记忆管理器实例。
    """

    def __init__(self):
        # ── 初始化记忆系统 ─────────────────────────────────
        self.memory = MemoryManager()
        set_shared_memory(self.memory)

        # ── 初始化智能体 ───────────────────────────────────
        self.cq_agent = CQAgent()
        self.term_agent = TermExtractorAgent()
        self.builder_agent = OntologyBuilderAgent()
        self.validator_agent = ValidatorAgent()
        self.populator_agent = KnowledgePopulatorAgent()
        self.reasoning_agent = ReasoningAgent()
        self.explanation_agent = ExplanationAgent()
        self.metacognition = PrefrontalLobe()

        self.context: dict[str, Any] = {}

    # ═══════════════════════════════════════════════════════════
    #  流程一：构建领域 Ontology & Knowledge Graph
    # ═══════════════════════════════════════════════════════════

    def build_ontology(
        self, domain_text: str, domain_name: str = "domain"
    ) -> dict[str, Any]:
        """五步管线：CQ → 术语 → OWL 本体 → 知识图谱 → 验证。

        Parameters
        ----------
        domain_text : str
            领域文档原始文本。
        domain_name : str
            领域名称，用于文件命名，默认 ``"domain"``。

        Returns
        -------
        dict
            完整的上下文字典，包含所有中间/最终产物。
        """
        # ── 开启记忆会话 ──────────────────────────────────────
        self.memory.start_session(focus=f"构建领域本体: {domain_name}")
        # 将领域文档加入 RAG 索引
        self.memory.rag.add_text(domain_text, source_name=domain_name)

        self.context["domain_text"] = domain_text
        self.context["domain_name"] = domain_name

        # ── Step 1: 提炼 Competency Questions ────────────────
        print("\n[1/5] 🔍 提炼 Competency Questions ...")
        cq_result = self.cq_agent.run(self.context)
        cqs = cq_result.get("competency_questions", cq_result)
        self.context["competency_questions"] = cqs
        self._save_artifact("competency_questions.json", cqs)
        # 记录到工作记忆
        cq_count = len(cqs) if isinstance(cqs, list) else "?"
        self.memory.memorize(
            f"CQ 提取完成: {cq_count} 个 Competency Questions",
            layer="working", tag="cq", agent_name="CQAgent",
        )
        print(f"      ✓ 生成 {cq_count} 个 CQ")

        # ── Step 2: 术语抽取 ─────────────────────────────────
        print("\n[2/5] 📝 术语抽取与类型判定 ...")
        term_result = self.term_agent.run(self.context)
        terms = term_result.get("terms", term_result)
        self.context["terms"] = terms
        self._save_artifact("terms.json", terms)
        terms_list = terms if isinstance(terms, list) else terms.get("terms", [])
        self.memory.memorize(
            f"术语抽取完成: {len(terms_list)} 个术语",
            layer="working", tag="terms", agent_name="TermExtractorAgent",
        )
        print(f"      ✓ 抽取 {len(terms_list)} 个术语")

        # ── Step 3: 生成 OWL 本体 ────────────────────────────
        print("\n[3/5] 🏗️  生成 OWL 本体 ...")
        ont_result = self.builder_agent.run(self.context)
        self.context.update(ont_result)
        self._save_artifact("ontology_spec.json", ont_result["ontology_spec"])
        self.memory.memorize(
            f"OWL 本体构建完成: {ont_result['ontology_path']}",
            layer="working", tag="ontology", agent_name="OntologyBuilderAgent",
        )
        print(f"      ✓ 本体已保存: {ont_result['ontology_path']}")

        # ── Step 4: 知识图谱填充 ─────────────────────────────
        print("\n[4/5] 💾 知识图谱填充 ...")
        kg_result = self.populator_agent.run(self.context)
        self.context.update(kg_result)
        self._save_artifact("kg_data.json", kg_result.get("kg_data", {}))
        self.memory.memorize(
            f"KG 填充完成: {kg_result['individuals_count']} 实例, "
            f"{kg_result['relations_count']} 关系",
            layer="working", tag="kg", agent_name="KnowledgePopulatorAgent",
        )
        print(
            f"      ✓ 实例 {kg_result['individuals_count']} 个, "
            f"关系 {kg_result['relations_count']} 条"
        )

        # ── Step 5: 自动验证 ─────────────────────────────────
        print("\n[5/5] ✅ 三类自动验证 (OWL / SHACL / SPARQL CQ) ...")
        val_result = self.validator_agent.run(self.context)
        self.context.update(val_result)
        self.memory.memorize(
            val_result['validation_summary'],
            layer="working", tag="validation", agent_name="ValidatorAgent",
        )
        print(f"      {val_result['validation_summary']}")

        # ── 将构建产物加载到持久记忆 ──────────────────────────
        self.memory.load_ontology_from_context(
            ontology_graph=self.context.get("ontology_graph"),
            kg_graph=self.context.get("knowledge_graph"),
            ontology_spec=self.context.get("ontology_spec"),
        )
        # 记录构建经验
        self.memory.memorize(
            f"成功构建领域 '{domain_name}' 本体 — "
            f"{cq_count} CQ, {len(terms_list)} 术语, "
            f"{kg_result['individuals_count']} 实例",
            layer="experience",
            category="strategy",
            success=True,
            domain=domain_name,
        )
        # 记录验证结论到知识库
        self.memory.memorize(
            val_result['validation_summary'],
            layer="knowledge",
            source="owl",
            domain=domain_name,
        )

        print(f"\n{'=' * 60}")
        print(f"所有产物已保存至: {config.OUTPUT_DIR}")
        self._print_memory_stats()
        print(f"{'=' * 60}")

        return self.context

    # ═══════════════════════════════════════════════════════════
    #  元认知: 自动演化
    # ═══════════════════════════════════════════════════════════

    def evolve(self) -> dict[str, Any]:
        """触发元认知分析，诊断各智能体表现并自动优化技能。

        基于最近一次构建的结果，执行完整的元认知循环:
        监控 → 评估 → 诊断 → 优化 → 验证 → 应用/回滚

        Returns
        -------
        dict
            演化结果报告。
        """
        if not self.context:
            print("❌ 请先运行 build_ontology() 构建本体和知识图谱。")
            return {"evolution_performed": False, "reason": "无构建上下文"}

        return self.metacognition.run(self.context)

    # ═══════════════════════════════════════════════════════════
    #  流程二：领域推理
    # ═══════════════════════════════════════════════════════════

    def reason(self, question: str) -> str:
        """对用户问题执行推理并返回自然语言解释。

        Parameters
        ----------
        question : str
            用户的自然语言问题。

        Returns
        -------
        str
            Markdown 格式的推理解释报告。
        """
        if "ontology_graph" not in self.context:
            return "❌ 请先运行 build_ontology() 构建本体和知识图谱。"

        print(f"\n{'=' * 60}")
        print(f"推理问题: {question}")
        print(f"{'=' * 60}")

        # 设置工作记忆焦点
        self.memory.working.set_focus(f"推理: {question}")
        self.memory.memorize(
            f"用户提问: {question}",
            layer="working", tag="question", agent_name="Orchestrator",
        )

        ctx = dict(self.context)
        ctx["question"] = question

        # ── Step 1: 硬推理 + 软推理 ──────────────────────────
        print("\n[1/2] 🧠 执行推理 (硬推理 + 软推理) ...")
        reason_result = self.reasoning_agent.run(ctx)
        ctx.update(reason_result)

        # ── Step 2: 自然语言解释 ─────────────────────────────
        print("[2/2] 📖 生成可读解释 ...")
        expl_result = self.explanation_agent.run(ctx)

        explanation = expl_result["explanation"]
        print(f"\n{'─' * 60}")
        print(explanation)
        print(f"{'─' * 60}")

        # ── 记录推理结论到长期记忆 ────────────────────────────
        self.memory.memorize(
            f"问题: {question}\n结论: {explanation[:500]}",
            layer="long_term",
            category="reasoning",
        )

        return explanation

    # ═══════════════════════════════════════════════════════════
    #  从已有文件加载
    # ═══════════════════════════════════════════════════════════

    def load_from_output(self) -> None:
        """从 ``output/`` 目录加载已有的本体、知识图谱和 SHACL shapes。

        加载后可直接调用 ``reason()`` 进行推理，无需重跑整个构建流程。
        同时将 Ontology 加载到持久记忆。
        """
        owl_files = glob.glob(os.path.join(config.OUTPUT_DIR, "*_ontology.owl"))
        if not owl_files:
            print("未找到已有本体文件")
            return

        ont_g = Graph()
        ont_g.parse(owl_files[0])
        self.context["ontology_graph"] = ont_g

        kg_path = os.path.join(config.OUTPUT_DIR, "knowledge_graph.ttl")
        if os.path.exists(kg_path):
            kg = Graph()
            kg.parse(kg_path, format="turtle")
            self.context["knowledge_graph"] = kg

        shacl_path = os.path.join(config.OUTPUT_DIR, "shacl_shapes.ttl")
        if os.path.exists(shacl_path):
            shapes = Graph()
            shapes.parse(shacl_path, format="turtle")
            self.context["shacl_shapes"] = shapes

        spec_path = os.path.join(config.OUTPUT_DIR, "ontology_spec.json")
        if os.path.exists(spec_path):
            with open(spec_path, encoding="utf-8") as f:
                self.context["ontology_spec"] = json.load(f)

        # 加载到持久记忆
        self.memory.load_ontology_from_context(
            ontology_graph=self.context.get("ontology_graph"),
            kg_graph=self.context.get("knowledge_graph"),
            ontology_spec=self.context.get("ontology_spec"),
        )

        print(f"已从 {config.OUTPUT_DIR} 加载本体和知识图谱")
        self._print_memory_stats()

    # ═══════════════════════════════════════════════════════════
    #  RAG 文档管理
    # ═══════════════════════════════════════════════════════════

    def add_document(self, file_path: str) -> int:
        """将文档加入 RAG 索引，用于外部记忆检索。

        Parameters
        ----------
        file_path : str
            文档路径 (.txt / .md / .docx)。

        Returns
        -------
        int
            新增的分块数。
        """
        return self.memory.rag.add_document(file_path)

    # ═══════════════════════════════════════════════════════════
    #  会话管理
    # ═══════════════════════════════════════════════════════════

    def end_session(self) -> None:
        """结束当前会话并将摘要保存至长期记忆。"""
        self.memory.end_session(save_summary=True)
        print("会话已结束，工作记忆摘要已保存至长期记忆")

    # ── 内部辅助 ──────────────────────────────────────────────

    @staticmethod
    def _save_artifact(filename: str, data: Any) -> None:
        """将 JSON 可序列化的产物保存至 ``output/`` 目录。"""
        path = os.path.join(config.OUTPUT_DIR, filename)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _print_memory_stats(self) -> None:
        """打印记忆系统统计信息。"""
        stats = self.memory.stats()
        print(f"\n📊 记忆统计: "
              f"工作记忆 {stats['working_entries']} 条 | "
              f"长期记忆 {stats['long_term_entries']} 条 | "
              f"经验 {stats['experiences']} 条 | "
              f"知识 {stats['knowledge_facts']} 条 | "
              f"RAG {stats['rag_chunks']} 块 | "
              f"Ontology {'✓' if stats['has_ontology'] else '✗'}")
