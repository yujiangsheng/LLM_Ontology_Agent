"""
prefrontal_lobe — 元认知智能体 (Metacognitive Agent)
=====================================================

灵感来源于大脑前额叶皮层 (Prefrontal Cortex) — 负责规划、监控、
自我反省和行为调节。本智能体对系统中所有其他智能体的运行进行
**元层面的监控和优化**，通过修改智能体的技能描述文件（skill markdown）
赋予智能体自我演化能力，并通过验证闭环确保修改提升了正确率。

核心循环::

    监控 → 评估 → 诊断 → 优化 → 验证 → 应用 / 回滚

三大能力:
  1. **Performance Monitor**: 收集和分析各智能体的执行指标
  2. **Skill Optimizer**: 诊断瓶颈并生成技能改进方案
  3. **Evolution Guard**: 验证改进方案的有效性，防止退化

作者: Jiangsheng Yu
许可: MIT License
"""
from __future__ import annotations

import copy
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from agents.base_agent import BaseAgent
import config
import llm_client

logger = logging.getLogger(__name__)

# 技能文件目录（从 config 读取）
SKILLS_DIR = config.SKILLS_DIR

# 演化记录持久化路径
EVOLUTION_LOG_PATH = os.path.join(config.OUTPUT_DIR, "memory", "evolution_log.json")


# ═══════════════════════════════════════════════════════════════
#  数据结构
# ═══════════════════════════════════════════════════════════════


@dataclass
class AgentMetrics:
    """单个智能体的执行指标快照。"""

    agent_name: str
    timestamp: str = ""
    # 通用指标
    success: bool = True
    execution_time_s: float = 0.0
    llm_calls: int = 0
    error_message: str = ""
    # 特化指标（各 Agent 不同）
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "agent_name": self.agent_name,
            "timestamp": self.timestamp,
            "success": self.success,
            "execution_time_s": self.execution_time_s,
            "llm_calls": self.llm_calls,
            "error_message": self.error_message,
            "details": self.details,
        }


@dataclass
class EvolutionProposal:
    """一次技能演化提案。"""

    target_agent: str            # 目标智能体名称
    diagnosis: str               # 诊断结论
    proposal_type: str           # prompt_rewrite / strategy_add / parameter_tune
    original_section: str        # 被修改的原始内容
    proposed_section: str        # 建议的新内容
    expected_improvement: str    # 预期改进效果
    confidence: float = 0.0     # 置信度 0-1
    approved: bool = False       # 是否通过验证
    validation_result: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "target_agent": self.target_agent,
            "diagnosis": self.diagnosis,
            "proposal_type": self.proposal_type,
            "original_section": self.original_section[:500],
            "proposed_section": self.proposed_section[:500],
            "expected_improvement": self.expected_improvement,
            "confidence": self.confidence,
            "approved": self.approved,
            "validation_result": self.validation_result,
        }


# ═══════════════════════════════════════════════════════════════
#  Prefrontal Lobe 系统提示词
# ═══════════════════════════════════════════════════════════════

SYSTEM_DIAGNOSE = """\
你是一位 AI 系统元认知分析师。你的任务是分析智能体的执行指标，
诊断性能瓶颈，并提出针对性改进方案。

你会收到：
1. 智能体的技能描述（包含系统提示词、核心策略、评估指标）
2. 智能体的执行指标快照
3. 构建/推理全流程的上下文

请诊断问题根因并建议改进，以 JSON 格式返回：
{
  "diagnosed_issues": [
    {
      "issue": "问题描述",
      "severity": "critical|major|minor",
      "root_cause": "根因分析",
      "affected_metric": "受影响的评估指标"
    }
  ],
  "improvement_proposals": [
    {
      "target_section": "系统提示词|核心策略",
      "proposal_type": "prompt_rewrite|strategy_add|parameter_tune",
      "current_content": "当前内容摘要",
      "suggested_change": "建议的具体修改",
      "expected_effect": "预期效果",
      "confidence": 0.8
    }
  ]
}
只返回 JSON。"""

SYSTEM_OPTIMIZE = """\
你是一位 AI 提示词工程和策略优化专家。你的任务是根据诊断结论，
生成具体的、可直接应用的技能文件修改。

注意：
1. 修改必须保持与原有格式完全一致（Markdown 格式）
2. 系统提示词修改必须保持 JSON 输出格式要求不变
3. 新增的策略条目必须具体可执行，不能是空泛的建议
4. 每次只修改一个具体的部分

返回 JSON：
{
  "section_type": "system_prompt|core_strategy|evaluation_metric",
  "original_text": "被修改的确切原文",
  "new_text": "替换后的新内容",
  "rationale": "修改理由"
}
只返回 JSON。"""

SYSTEM_VALIDATE = """\
你是一位 AI 系统质量保证专家。你的任务是评审一次技能修改提案，
判断它是否能真正改善智能体的知识抽取和推理正确率。

评审维度：
1. 安全性 — 修改是否可能引入新的错误或退化
2. 有效性 — 修改是否能解决诊断出的问题
3. 一致性 — 修改后的技能是否与系统整体架构一致
4. 可逆性 — 如果效果不佳，是否容易回滚

返回 JSON：
{
  "approved": true/false,
  "safety_score": 0.0-1.0,
  "effectiveness_score": 0.0-1.0,
  "consistency_score": 0.0-1.0,
  "risks": ["可能的风险1", ...],
  "verdict": "通过/拒绝理由"
}
只返回 JSON。"""


# ═══════════════════════════════════════════════════════════════
#  Prefrontal Lobe 智能体
# ═══════════════════════════════════════════════════════════════


class PrefrontalLobe(BaseAgent):
    """元认知智能体 — 监控、诊断、优化其他智能体的技能。

    核心循环:
      1. **collect_metrics** — 从构建/推理结果收集各 Agent 的表现指标
      2. **diagnose**        — 分析指标，定位瓶颈和问题
      3. **propose**         — 针对问题生成技能修改提案
      4. **validate**        — 评审提案的安全性和有效性
      5. **apply**           — 将通过验证的修改写入技能文件
      6. **log_evolution**   — 记录演化历史

    Attributes
    ----------
    metrics_history : list[AgentMetrics]
        所有收集到的智能体执行指标。
    evolution_log : list[dict]
        技能演化历史记录。
    """

    name = "PrefrontalLobe"

    def __init__(self):
        super().__init__(system_prompt="")
        self.metrics_history: list[AgentMetrics] = []
        self.evolution_log: list[dict] = []
        self._load_evolution_log()

    # ═══════════════════════════════════════════════════════════
    #  1. 指标收集
    # ═══════════════════════════════════════════════════════════

    def collect_metrics_from_build(self, context: dict[str, Any]) -> list[AgentMetrics]:
        """从构建流程的上下文中提取各 Agent 的执行指标。"""
        now = datetime.now().isoformat()
        metrics: list[AgentMetrics] = []

        # CQAgent
        cqs = context.get("competency_questions", [])
        if isinstance(cqs, dict):
            cqs = cqs.get("competency_questions", [])
        cq_types = {}
        for cq in cqs:
            at = cq.get("expected_answer_type", "unknown")
            cq_types[at] = cq_types.get(at, 0) + 1
        metrics.append(AgentMetrics(
            agent_name="CQAgent", timestamp=now,
            details={
                "cq_count": len(cqs),
                "answer_type_distribution": cq_types,
                "has_focus_concepts": sum(
                    1 for cq in cqs if cq.get("focus_concepts")
                ),
            },
        ))

        # TermExtractorAgent
        terms = context.get("terms", [])
        if isinstance(terms, dict):
            terms = terms.get("terms", [])
        type_dist = {}
        conf_dist = {}
        for t in terms:
            ct = t.get("candidate_type", "unknown")
            type_dist[ct] = type_dist.get(ct, 0) + 1
            cf = t.get("confidence", "unknown")
            conf_dist[cf] = conf_dist.get(cf, 0) + 1
        metrics.append(AgentMetrics(
            agent_name="TermExtractorAgent", timestamp=now,
            details={
                "term_count": len(terms),
                "type_distribution": type_dist,
                "confidence_distribution": conf_dist,
            },
        ))

        # OntologyBuilderAgent
        spec = context.get("ontology_spec", {})
        metrics.append(AgentMetrics(
            agent_name="OntologyBuilderAgent", timestamp=now,
            details={
                "class_count": len(spec.get("classes", [])),
                "object_property_count": len(spec.get("object_properties", [])),
                "data_property_count": len(spec.get("data_properties", [])),
                "axiom_count": len(spec.get("axioms", [])),
                "ontology_path": context.get("ontology_path", ""),
            },
        ))

        # KnowledgePopulatorAgent
        metrics.append(AgentMetrics(
            agent_name="KnowledgePopulatorAgent", timestamp=now,
            details={
                "individuals_count": context.get("individuals_count", 0),
                "relations_count": context.get("relations_count", 0),
            },
        ))

        # ValidatorAgent
        sparql_results = context.get("sparql_results", [])
        sparql_ok = sum(1 for s in sparql_results if "error" not in s)
        sparql_nonempty = sum(
            1 for s in sparql_results
            if "error" not in s and s.get("result_count", 0) > 0
        )
        metrics.append(AgentMetrics(
            agent_name="ValidatorAgent", timestamp=now,
            details={
                "owl_reasoning_ok": context.get("owl_reasoning_ok", False),
                "shacl_conforms": context.get("shacl_conforms"),
                "sparql_total": len(sparql_results),
                "sparql_success": sparql_ok,
                "sparql_nonempty": sparql_nonempty,
                "validation_summary": context.get("validation_summary", ""),
            },
        ))

        self.metrics_history.extend(metrics)
        return metrics

    def collect_metrics_from_reasoning(
        self, question: str, reasoning_result: dict, explanation: str
    ) -> list[AgentMetrics]:
        """从推理流程中提取 ReasoningAgent 和 ExplanationAgent 的指标。"""
        now = datetime.now().isoformat()
        metrics: list[AgentMetrics] = []

        hard = reasoning_result.get("hard_reasoning", {})
        soft = reasoning_result.get("soft_reasoning", {})
        sparql_ev = hard.get("sparql_evidence", [])
        sparql_ok = sum(1 for e in sparql_ev if "error" not in e)

        metrics.append(AgentMetrics(
            agent_name="ReasoningAgent", timestamp=now,
            details={
                "question": question,
                "sparql_generated": len(sparql_ev),
                "sparql_success": sparql_ok,
                "owl_inferences": hard.get("owl_inferences", []),
                "shacl_issues": hard.get("shacl_issues", []),
                "confidence": soft.get("confidence", "unknown"),
                "hypothesis_count": len(soft.get("hypotheses", [])),
                "has_final_answer": bool(reasoning_result.get("final_answer")),
            },
        ))

        metrics.append(AgentMetrics(
            agent_name="ExplanationAgent", timestamp=now,
            details={
                "explanation_length": len(explanation),
                "has_markdown_headers": "##" in explanation,
            },
        ))

        self.metrics_history.extend(metrics)
        return metrics

    # ═══════════════════════════════════════════════════════════
    #  2. 诊断
    # ═══════════════════════════════════════════════════════════

    def diagnose(self, agent_name: str | None = None) -> list[dict]:
        """分析指标，诊断目标智能体（或全部）的性能问题。

        Parameters
        ----------
        agent_name : str | None
            指定智能体名称，None 表示诊断所有。

        Returns
        -------
        list[dict]
            诊断结果列表，包含 diagnosed_issues 和 improvement_proposals。
        """
        # 筛选相关指标
        target_metrics = [
            m for m in self.metrics_history
            if agent_name is None or m.agent_name == agent_name
        ]
        if not target_metrics:
            logger.info("没有找到 %s 的指标数据", agent_name or "任何智能体")
            return []

        # 按智能体分组
        by_agent: dict[str, list[AgentMetrics]] = {}
        for m in target_metrics:
            by_agent.setdefault(m.agent_name, []).append(m)

        all_diagnoses: list[dict] = []
        for name, agent_metrics in by_agent.items():
            skill_content = self._read_skill_file(name)
            if not skill_content:
                continue

            metrics_summary = json.dumps(
                [m.to_dict() for m in agent_metrics],
                ensure_ascii=False, indent=2,
            )

            prompt = (
                f"## 目标智能体: {name}\n\n"
                f"### 技能描述\n{skill_content}\n\n"
                f"### 执行指标\n{metrics_summary}\n\n"
                f"请诊断该智能体的性能问题并提出改进建议。"
            )
            try:
                self.system_prompt = SYSTEM_DIAGNOSE
                result = self.ask_json(prompt)
                result["agent_name"] = name
                all_diagnoses.append(result)
            except Exception as e:
                logger.warning("诊断 %s 失败: %s", name, e)

        return all_diagnoses

    # ═══════════════════════════════════════════════════════════
    #  3. 优化提案生成
    # ═══════════════════════════════════════════════════════════

    def propose(self, diagnosis: dict) -> list[EvolutionProposal]:
        """根据诊断结果生成具体的技能修改提案。"""
        agent_name = diagnosis.get("agent_name", "")
        skill_content = self._read_skill_file(agent_name)
        if not skill_content:
            return []

        proposals: list[EvolutionProposal] = []
        for imp in diagnosis.get("improvement_proposals", []):
            prompt = (
                f"## 目标智能体: {agent_name}\n\n"
                f"### 当前技能文件完整内容\n{skill_content}\n\n"
                f"### 需要执行的修改\n"
                f"- 类型: {imp.get('proposal_type', 'prompt_rewrite')}\n"
                f"- 当前内容: {imp.get('current_content', '')}\n"
                f"- 建议修改: {imp.get('suggested_change', '')}\n"
                f"- 预期效果: {imp.get('expected_effect', '')}\n\n"
                f"请生成具体的文件修改内容。"
                f"original_text 必须是技能文件中真实存在的一段原文。"
            )
            try:
                self.system_prompt = SYSTEM_OPTIMIZE
                result = self.ask_json(prompt)
                proposal = EvolutionProposal(
                    target_agent=agent_name,
                    diagnosis=imp.get("suggested_change", ""),
                    proposal_type=imp.get("proposal_type", "prompt_rewrite"),
                    original_section=result.get("original_text", ""),
                    proposed_section=result.get("new_text", ""),
                    expected_improvement=result.get("rationale", ""),
                    confidence=imp.get("confidence", 0.5),
                )
                proposals.append(proposal)
            except Exception as e:
                logger.warning("生成优化提案失败: %s", e)

        return proposals

    # ═══════════════════════════════════════════════════════════
    #  4. 验证
    # ═══════════════════════════════════════════════════════════

    def validate_proposal(self, proposal: EvolutionProposal) -> bool:
        """评审提案的安全性和有效性。

        Returns
        -------
        bool
            是否批准该提案。
        """
        skill_content = self._read_skill_file(proposal.target_agent)

        prompt = (
            f"## 技能修改评审\n\n"
            f"### 目标智能体: {proposal.target_agent}\n"
            f"### 修改类型: {proposal.proposal_type}\n\n"
            f"### 当前技能文件\n{skill_content}\n\n"
            f"### 原始内容\n```\n{proposal.original_section}\n```\n\n"
            f"### 提议修改为\n```\n{proposal.proposed_section}\n```\n\n"
            f"### 修改理由\n{proposal.expected_improvement}\n\n"
            f"请评审此修改提案。"
        )
        try:
            self.system_prompt = SYSTEM_VALIDATE
            result = self.ask_json(prompt)
            proposal.validation_result = result
            proposal.approved = bool(result.get("approved", False))

            # 额外安全检查: 三项分数均需 >= EVOLUTION_MIN_SCORE
            safety = result.get("safety_score", 0)
            effectiveness = result.get("effectiveness_score", 0)
            consistency = result.get("consistency_score", 0)
            if min(safety, effectiveness, consistency) < config.EVOLUTION_MIN_SCORE:
                proposal.approved = False
                logger.info(
                    "提案被安全阈值拒绝 (safety=%.2f, eff=%.2f, cons=%.2f, min=%.2f)",
                    safety, effectiveness, consistency, config.EVOLUTION_MIN_SCORE,
                )

            return proposal.approved
        except Exception as e:
            logger.warning("验证提案失败: %s", e)
            proposal.approved = False
            return False

    # ═══════════════════════════════════════════════════════════
    #  5. 应用修改
    # ═══════════════════════════════════════════════════════════

    def apply_proposal(self, proposal: EvolutionProposal) -> bool:
        """将通过验证的提案应用到技能文件。

        只有 ``proposal.approved == True`` 的提案才会被应用。

        Returns
        -------
        bool
            是否成功应用。
        """
        if not proposal.approved:
            logger.warning("提案未通过验证，拒绝应用")
            return False

        skill_path = self._skill_file_path(proposal.target_agent)
        if not skill_path or not os.path.exists(skill_path):
            return False

        with open(skill_path, "r", encoding="utf-8") as f:
            content = f.read()

        # 验证原始文本确实存在
        if proposal.original_section and proposal.original_section in content:
            new_content = content.replace(
                proposal.original_section,
                proposal.proposed_section,
                1,  # 只替换第一处
            )
        else:
            logger.warning(
                "原始文本在技能文件中未找到（可能已被修改），跳过应用"
            )
            return False

        # 更新版本号和修改日期
        new_content = self._bump_version(new_content)

        # 追加演化历史记录
        new_content = self._append_evolution_record(
            new_content, proposal
        )

        with open(skill_path, "w", encoding="utf-8") as f:
            f.write(new_content)

        # 记录到演化日志
        self._log_evolution(proposal)

        logger.info(
            "✓ 技能演化已应用: %s [%s]",
            proposal.target_agent, proposal.proposal_type,
        )
        return True

    # ═══════════════════════════════════════════════════════════
    #  6. 主入口: run
    # ═══════════════════════════════════════════════════════════

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        """执行完整的元认知循环。

        Parameters
        ----------
        context : dict
            包含构建/推理产物的上下文（从 Orchestrator 传入）。

        Returns
        -------
        dict
            演化结果报告。
        """
        print("\n🧠 Prefrontal Lobe: 元认知分析开始...")

        # Step 1: 收集指标
        print("  [1/5] 📊 收集执行指标...")
        build_metrics = self.collect_metrics_from_build(context)
        metrics_summary = {m.agent_name: m.details for m in build_metrics}
        print(f"        收集了 {len(build_metrics)} 个智能体的指标")

        # Step 2: 诊断
        print("  [2/5] 🔍 诊断性能瓶颈...")
        diagnoses = self.diagnose()
        total_issues = sum(
            len(d.get("diagnosed_issues", [])) for d in diagnoses
        )
        print(f"        发现 {total_issues} 个问题")

        if total_issues == 0:
            print("  ✓ 所有智能体表现正常，无需演化")
            return {
                "evolution_performed": False,
                "metrics": metrics_summary,
                "diagnoses": diagnoses,
                "proposals": [],
                "applied": [],
            }

        # Step 3: 生成优化提案
        print("  [3/5] 💡 生成优化提案...")
        all_proposals: list[EvolutionProposal] = []
        for diag in diagnoses:
            proposals = self.propose(diag)
            all_proposals.extend(proposals)
        print(f"        生成了 {len(all_proposals)} 个提案")

        # Step 4: 验证提案
        print("  [4/5] ✅ 验证提案安全性...")
        approved: list[EvolutionProposal] = []
        for p in all_proposals:
            if self.validate_proposal(p):
                approved.append(p)
        print(f"        {len(approved)}/{len(all_proposals)} 个提案通过验证")

        # Step 5: 应用修改
        print("  [5/5] 🔧 应用技能修改...")
        applied: list[EvolutionProposal] = []
        for p in approved:
            if self.apply_proposal(p):
                applied.append(p)
        print(f"        成功应用 {len(applied)} 个修改")

        result = {
            "evolution_performed": len(applied) > 0,
            "metrics": metrics_summary,
            "diagnoses": diagnoses,
            "proposals_total": len(all_proposals),
            "proposals_approved": len(approved),
            "proposals_applied": len(applied),
            "applied": [p.to_dict() for p in applied],
        }

        self._print_evolution_report(result)
        return result

    # ═══════════════════════════════════════════════════════════
    #  辅助方法
    # ═══════════════════════════════════════════════════════════

    def _read_skill_file(self, agent_name: str) -> str:
        """读取指定智能体的技能文件内容。"""
        path = self._skill_file_path(agent_name)
        if not path or not os.path.exists(path):
            return ""
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    @staticmethod
    def _skill_file_path(agent_name: str) -> str | None:
        """根据智能体名称推断技能文件路径。"""
        # 支持的映射
        mapping = {
            "CQAgent": "cq_agent.md",
            "TermExtractorAgent": "term_extractor.md",
            "OntologyBuilderAgent": "ontology_builder.md",
            "KnowledgePopulatorAgent": "knowledge_populator.md",
            "ValidatorAgent": "validator.md",
            "ReasoningAgent": "reasoning_agent.md",
            "ExplanationAgent": "explanation_agent.md",
            "Orchestrator": "orchestrator.md",
            "PrefrontalLobe": "prefrontal_lobe.md",
        }
        filename = mapping.get(agent_name)
        if not filename:
            return None
        return os.path.join(SKILLS_DIR, filename)

    @staticmethod
    def _bump_version(content: str) -> str:
        """递增技能文件中的版本号和修改日期。"""
        today = datetime.now().strftime("%Y-%m-%d")

        # 更新日期
        content = re.sub(
            r"(\*\*最后修改\*\*:\s*)\S+",
            rf"\g<1>{today}",
            content,
            count=1,
        )
        # 更新修改者
        content = re.sub(
            r"(\*\*修改者\*\*:\s*).*",
            r"\g<1>PrefrontalLobe 自动演化",
            content,
            count=1,
        )
        # 递增版本号  X.Y.Z → X.Y.(Z+1)
        def _inc_patch(m):
            major, minor, patch = m.group(1), m.group(2), m.group(3)
            return f"{major}.{minor}.{int(patch) + 1}"

        content = re.sub(
            r"(\*\*版本\*\*:\s*)(\d+)\.(\d+)\.(\d+)",
            lambda m: f"{m.group(1)}{_inc_patch(m)}",
            content,
            count=1,
        )
        return content

    @staticmethod
    def _append_evolution_record(
        content: str, proposal: EvolutionProposal
    ) -> str:
        """在技能文件的演化历史表格中追加一行记录。"""
        today = datetime.now().strftime("%Y-%m-%d")
        # 获取当前版本
        ver_match = re.search(r"\*\*版本\*\*:\s*(\d+\.\d+\.\d+)", content)
        version = ver_match.group(1) if ver_match else "?.?.?"

        new_row = (
            f"| {today} | {version} | "
            f"{proposal.proposal_type}: {proposal.diagnosis[:40]} | "
            f"自动诊断 | 待验证 |"
        )
        # 在演化历史表格末尾追加
        if "## 演化历史" in content:
            # 找到最后一行表格行并追加
            lines = content.split("\n")
            insert_idx = len(lines)
            for i in range(len(lines) - 1, -1, -1):
                if lines[i].startswith("|") and "---" not in lines[i]:
                    insert_idx = i + 1
                    break
            lines.insert(insert_idx, new_row)
            content = "\n".join(lines)

        return content

    def _log_evolution(self, proposal: EvolutionProposal) -> None:
        """记录演化事件到持久化日志。"""
        record = {
            "timestamp": datetime.now().isoformat(),
            **proposal.to_dict(),
        }
        self.evolution_log.append(record)
        self._save_evolution_log()

        # 同时写入持久记忆
        if self.memory:
            self.memory.memorize(
                f"技能演化: {proposal.target_agent} — "
                f"{proposal.proposal_type}: {proposal.diagnosis[:100]}",
                layer="experience",
                category="skill_evolution",
                success=True,
                agent_name=self.name,
            )

    def _load_evolution_log(self) -> None:
        """从文件加载演化历史。"""
        if os.path.exists(EVOLUTION_LOG_PATH):
            try:
                with open(EVOLUTION_LOG_PATH, "r", encoding="utf-8") as f:
                    self.evolution_log = json.load(f)
            except (json.JSONDecodeError, OSError):
                self.evolution_log = []

    def _save_evolution_log(self) -> None:
        """保存演化历史到文件。"""
        os.makedirs(os.path.dirname(EVOLUTION_LOG_PATH), exist_ok=True)
        with open(EVOLUTION_LOG_PATH, "w", encoding="utf-8") as f:
            json.dump(self.evolution_log, ensure_ascii=False, indent=2, fp=f)

    @staticmethod
    def _print_evolution_report(result: dict) -> None:
        """打印元认知分析报告。"""
        print(f"\n{'=' * 60}")
        print("🧠 Prefrontal Lobe — 元认知分析报告")
        print(f"{'=' * 60}")

        if not result["evolution_performed"]:
            print("  状态: 所有智能体表现正常，无需演化")
        else:
            print(f"  提案总数: {result['proposals_total']}")
            print(f"  通过验证: {result['proposals_approved']}")
            print(f"  成功应用: {result['proposals_applied']}")
            print(f"\n  已应用的修改:")
            for p in result.get("applied", []):
                print(f"    • [{p['target_agent']}] {p['proposal_type']}")
                print(f"      诊断: {p['diagnosis'][:60]}")

        # 打印指标概览
        metrics = result.get("metrics", {})
        if metrics:
            print(f"\n  📊 指标概览:")
            for agent_name, details in metrics.items():
                summary_parts = []
                for k, v in details.items():
                    if isinstance(v, (int, float, bool)):
                        summary_parts.append(f"{k}={v}")
                if summary_parts:
                    print(f"    {agent_name}: {', '.join(summary_parts[:4])}")

        print(f"{'=' * 60}")

    # ═══════════════════════════════════════════════════════════
    #  便捷方法
    # ═══════════════════════════════════════════════════════════

    def get_evolution_summary(self) -> dict:
        """获取演化历史摘要。"""
        if not self.evolution_log:
            return {"total_evolutions": 0, "agents_evolved": [], "log": []}

        agents_evolved = list({e["target_agent"] for e in self.evolution_log})
        return {
            "total_evolutions": len(self.evolution_log),
            "agents_evolved": agents_evolved,
            "log": self.evolution_log[-10:],  # 最近 10 条
        }

    def get_agent_status(self) -> dict[str, dict]:
        """获取所有智能体的最新指标状态。"""
        latest: dict[str, AgentMetrics] = {}
        for m in self.metrics_history:
            latest[m.agent_name] = m
        return {name: m.to_dict() for name, m in latest.items()}
