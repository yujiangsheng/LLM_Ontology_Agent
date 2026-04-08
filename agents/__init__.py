"""
agents — 多智能体模块
======================

按职责拆分为 7 个专门化 Agent + 1 个 Orchestrator 协调器 +
1 个 PrefrontalLobe 元认知智能体，实现从领域文档到 OWL 本体、
知识图谱和推理闭环的完整流水线，并具备自我演化能力。

Agent 列表:
    - CQAgent               — Competency Questions 提炼
    - TermExtractorAgent    — 领域术语抽取与类型判定
    - OntologyBuilderAgent  — OWL 2 本体构建
    - KnowledgePopulatorAgent — 知识图谱实例填充
    - ValidatorAgent        — OWL + SHACL + SPARQL 三类自动验证
    - ReasoningAgent        — 硬推理 + 软推理
    - ExplanationAgent      — 可读解释生成
    - Orchestrator          — 流程编排协调器
    - PrefrontalLobe        — 元认知智能体（技能自我演化）

Architecture::

    ┌──────────────────── Build Pipeline ────────────────────┐
    │  CQAgent → TermExtractor → OntologyBuilder            │
    │                │               → KnowledgePopulator    │
    │                │                       → Validator     │
    └───────────────────────────────────────────────────────┘
    ┌──────────────── Reasoning Pipeline ───────────────────┐
    │  ReasoningAgent (OWL+SHACL+SPARQL+LLM) → Explanation │
    └───────────────────────────────────────────────────────┘
    ┌──────────────── Metacognition Loop ───────────────────┐
    │  PrefrontalLobe: Monitor → Diagnose → Optimize → Apply│
    └───────────────────────────────────────────────────────┘

Usage Example::

    from agents.orchestrator import Orchestrator

    orch = Orchestrator()
    orch.build_ontology(domain_text, domain_name="设备故障诊断")
    explanation = orch.reason("哪些设备存在过热风险？")
"""