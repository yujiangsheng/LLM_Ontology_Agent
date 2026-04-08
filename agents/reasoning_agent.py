"""
reasoning_agent — 硬推理 + 软推理混合智能体
=============================================

实现 *"LLM 提议，Reasoner 裁决，SHACL 把关，SPARQL 取证"* 的核心推理流程。

四步管线:
  1. **OWL 推理** — 在合并图上执行 OWL 2 RL 推理闭包，补全隐含三元组
  2. **SHACL 验证** — 检查推理后图的数据质量
  3. **SPARQL 取证** — LLM 根据用户问题生成 1-3 条 SPARQL，在推理图上执行
  4. **LLM 软推理** — 将形式推理证据交给 LLM 完成假设生成、消歧和不确定性标注

输出产物:
  ``reasoning_result`` — 包含 hard_reasoning、soft_reasoning、final_answer、
  uncertainty_notes 的 JSON 对象

作者: Jiangsheng Yu
许可: MIT License
"""
from __future__ import annotations

import json
import logging
from typing import Any

from rdflib import Graph

from agents.base_agent import BaseAgent
from utils.owl_utils import run_owl_reasoning, validate_shacl, run_sparql, ONT

logger = logging.getLogger(__name__)

# LLM 系统提示词
SYSTEM = """\
你是领域推理专家。你的任务是结合本体知识和知识图谱的形式推理结果，
对用户问题进行推理分析。

推理规则：
- "LLM 提议，reasoner 裁决，SHACL 把关，SPARQL 取证"
- 对于形式推理能回答的问题，优先采信 SPARQL 查询结果和 OWL 推理结论
- 对于需要解释、假设或消歧的部分，由你来完成软推理
- 明确标注哪些结论来自形式推理（确定），哪些来自你的推断（有不确定性）

输出格式：
{
  "question": "用户的问题",
  "hard_reasoning": {
    "sparql_evidence": [...],
    "owl_inferences": [...],
    "shacl_issues": [...]
  },
  "soft_reasoning": {
    "hypotheses": [...],
    "confidence": "high|medium|low",
    "explanation": "..."
  },
  "final_answer": "综合结论",
  "uncertainty_notes": "不确定性说明"
}
"""


class ReasoningAgent(BaseAgent):
    """硬推理 + 软推理混合智能体。

    硬推理（确定性高）:
      - OWL 2 RL 推理闭包
      - SHACL 数据质量校验
      - SPARQL 查询取证

    软推理（有不确定性）:
      - LLM 假设生成与消歧
      - 不确定性标注
    """

    name = "ReasoningAgent"

    def __init__(self):
        super().__init__(system_prompt=SYSTEM)

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        """执行四步推理管线。

        Parameters
        ----------
        context : dict
            必须包含 ``question`` (str) 和 ``ontology_graph`` (Graph)；
            可选 ``knowledge_graph``, ``shacl_shapes``, ``ontology_spec``,
            ``competency_questions``。

        Returns
        -------
        dict
            ``{"reasoning_result": {...}}`` — 包含完整推理报告。
        """
        question: str = context["question"]
        ont_g: Graph = context["ontology_graph"]
        kg: Graph | None = context.get("knowledge_graph")
        shapes_g: Graph | None = context.get("shacl_shapes")

        # 合并本体图 + 知识图谱
        merged = Graph()
        for t in ont_g:
            merged.add(t)
        if kg:
            for t in kg:
                merged.add(t)

        # ── Step 1: OWL 推理 ────────────────────────────────
        owl_inferences: list[str] = []
        try:
            before_count = len(merged)
            run_owl_reasoning(merged)
            new_triples = len(merged) - before_count
            owl_inferences.append(f"OWL 推理新增 {new_triples} 条三元组")
            logger.info("OWL 推理新增 %d 条三元组", new_triples)
        except Exception as e:
            owl_inferences.append(f"OWL 推理异常: {e}")
            logger.warning("OWL 推理异常: %s", e)

        # ── Step 2: SHACL 验证 ──────────────────────────────
        shacl_issues: list[str] = []
        if shapes_g:
            try:
                conforms, report = validate_shacl(merged, shapes_g)
                if not conforms:
                    shacl_issues.append(report)
                else:
                    shacl_issues.append("SHACL 验证通过，数据符合所有约束")
            except Exception as e:
                shacl_issues.append(f"SHACL 验证异常: {e}")

        # ── Step 3: SPARQL 取证 ─────────────────────────────
        sparql_evidence = self._sparql_for_question(question, context, merged)

        # ── Step 4: LLM 软推理 ─────────────────────────────
        hard_info = {
            "sparql_evidence": sparql_evidence,
            "owl_inferences": owl_inferences,
            "shacl_issues": shacl_issues,
        }
        soft_result = self._soft_reasoning(question, hard_info)

        return {"reasoning_result": soft_result}

    # ── 内部辅助 ──────────────────────────────────────────────

    def _sparql_for_question(
        self, question: str, context: dict, g: Graph
    ) -> list[dict]:
        """让 LLM 根据用户问题和本体结构生成 SPARQL 并在图上执行。

        Returns
        -------
        list[dict]
            每项包含 ``sparql`` 和 ``results`` 或 ``error``。
        """
        spec = context.get("ontology_spec", {})
        lines: list[str] = []
        for c in spec.get("classes", []):
            lines.append(f"Class: ont:{c['name']}")
        for op in spec.get("object_properties", []):
            lines.append(f"ObjectProperty: ont:{op['name']}")
        for dp in spec.get("data_properties", []):
            lines.append(f"DataProperty: ont:{dp['name']}")

        prompt = (
            f"本体结构（前缀 ont: = <{ONT}>）：\n"
            + "\n".join(lines)
            + f"\n\n问题：{question}\n\n"
            f"请生成 1-3 条 SPARQL SELECT 查询来回答该问题。\n"
            f'返回 JSON: {{"queries": ["SELECT ...", ...]}}\n只返回 JSON。'
        )
        try:
            result = self.ask_json(prompt)
            queries = result.get("queries", [])
        except Exception:
            queries = []

        evidence: list[dict] = []
        for q in queries:
            try:
                rows = run_sparql(g, q)
                evidence.append({"sparql": q, "results": rows[:10]})
            except Exception as e:
                evidence.append({"sparql": q, "error": str(e)})
        return evidence

    def _soft_reasoning(self, question: str, hard_info: dict) -> dict:
        """LLM 综合硬推理证据执行软推理，返回完整推理报告。"""
        hard_str = json.dumps(hard_info, ensure_ascii=False, indent=2)
        prompt = (
            f"用户问题：{question}\n\n"
            f"形式推理结果：\n{hard_str}\n\n"
            f"请综合以上证据进行推理分析，按如下 JSON 格式输出：\n"
            f'{{"question":"...","hard_reasoning":...,"soft_reasoning":'
            f'{{"hypotheses":[...],"confidence":"...","explanation":"..."}},'
            f'"final_answer":"...","uncertainty_notes":"..."}}'
        )
        try:
            return self.ask_json(prompt)
        except Exception:
            return {
                "question": question,
                "hard_reasoning": hard_info,
                "soft_reasoning": {
                    "hypotheses": [],
                    "confidence": "low",
                    "explanation": "LLM 软推理解析失败",
                },
                "final_answer": "无法生成结论",
                "uncertainty_notes": "软推理阶段异常",
            }
