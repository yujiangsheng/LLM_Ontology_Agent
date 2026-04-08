"""
validator — 三类自动验证智能体
================================

在本体和知识图谱构建完成后，执行三类自动检查：

1. **OWL 推理一致性** — 使用 owlrl (OWL 2 RL) 检查逻辑一致性
2. **SHACL 约束验证** — 让 LLM 生成 SHACL Shapes，然后用 pyshacl 验证数据质量
3. **SPARQL CQ 回归** — 将 Competency Questions 翻译为 SPARQL 查询并执行

核心原则: *SHACL 把关，SPARQL 取证* [W3C SHACL / SPARQL 1.1]

输出产物:
  - ``shacl_shapes.ttl`` — SHACL Shapes 图（Turtle 格式）
  - 验证摘要文本

作者: Jiangsheng Yu
许可: MIT License
"""
from __future__ import annotations

import logging
from typing import Any

from rdflib import Graph, Namespace, RDF, RDFS, OWL, Literal, BNode
from rdflib.namespace import XSD

from agents.base_agent import BaseAgent
from utils.owl_utils import (
    run_owl_reasoning,
    validate_shacl,
    run_sparql,
    ONT,
    KB,
    save_graph,
)

logger = logging.getLogger(__name__)

# SHACL 命名空间
SH = Namespace("http://www.w3.org/ns/shacl#")

# LLM 系统提示词
SYSTEM = """\
你是本体质量保证专家。你需要为给定的 OWL 本体生成：
1. SHACL Shapes：检查实例数据的必填字段、值类型、基数约束
2. SPARQL 查询：将 Competency Questions 转化为可执行的 SPARQL SELECT 查询

请以 JSON 格式返回：
{
  "shacl_shapes": [
    {"target_class": "Device", "properties": [
      {"path": "hasSensor", "min_count": 1, "description": "设备至少有一个传感器"}
    ]}
  ],
  "sparql_queries": [
    {"cq_id": "CQ1", "question": "...", "sparql": "SELECT ?x WHERE {...}"}
  ]
}
只返回 JSON。"""


class ValidatorAgent(BaseAgent):
    """三类自动验证智能体 (OWL / SHACL / SPARQL CQ)。

    执行流程:
      1. 将本体+知识图谱合并后做 OWL 2 RL 推理，检测不一致
      2. 让 LLM 根据本体结构生成 SHACL Shapes → pyshacl 验证
      3. 让 LLM 将 CQ 转为 SPARQL → 在推理后的图上执行回归测试
    """

    name = "ValidatorAgent"

    def __init__(self):
        super().__init__(system_prompt=SYSTEM)

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        """执行三类自动验证。

        Parameters
        ----------
        context : dict
            必须包含 ``ontology_graph`` (Graph)；
            可选 ``competency_questions``, ``ontology_spec``, ``knowledge_graph``。

        Returns
        -------
        dict
            包含 ``owl_reasoning_ok``, ``shacl_conforms``, ``shacl_report``,
            ``sparql_results``, ``validation_summary``。
        """
        ont_g: Graph = context["ontology_graph"]
        cqs = context.get("competency_questions", [])
        if isinstance(cqs, dict):
            cqs = cqs.get("competency_questions", [])
        kg: Graph | None = context.get("knowledge_graph")
        spec = context.get("ontology_spec", {})

        results: dict[str, Any] = {}

        # ── 1) OWL 推理一致性检查 ────────────────────────────
        inferred = Graph()
        for t in ont_g:
            inferred.add(t)
        if kg:
            for t in kg:
                inferred.add(t)

        try:
            run_owl_reasoning(inferred)
            results["owl_reasoning_ok"] = True
            logger.info("OWL 推理完成 — 未检测到不一致")
        except Exception as e:
            results["owl_reasoning_ok"] = False
            logger.warning("OWL 推理异常: %s", e)

        # ── 2) LLM 生成 SHACL + SPARQL ─────────────────────
        spec_str = self._spec_to_prompt(spec)
        cq_str = "\n".join(
            f"- {q.get('id', '')}: {q.get('question', q)}" for q in cqs
        )
        prompt = (
            f"本体结构：\n{spec_str}\n\n"
            f"Competency Questions：\n{cq_str}\n\n"
            f"请生成 SHACL shapes 和对应的 SPARQL 查询。"
        )
        validation_spec = self.ask_json(prompt)

        # ── 3) SHACL 验证 ───────────────────────────────────
        shapes_g = self._build_shacl(validation_spec.get("shacl_shapes", []))
        target_g = kg if kg else ont_g
        try:
            conforms, report = validate_shacl(target_g, shapes_g)
            results["shacl_conforms"] = conforms
            results["shacl_report"] = report
        except Exception as e:
            results["shacl_conforms"] = None
            results["shacl_report"] = f"SHACL 验证异常: {e}"
            logger.warning("SHACL 验证异常: %s", e)

        # ── 4) SPARQL CQ 回归 ───────────────────────────────
        sparql_results: list[dict] = []
        # 优先在推理后的图上查询
        query_g = inferred if results.get("owl_reasoning_ok") else target_g
        for sq in validation_spec.get("sparql_queries", []):
            try:
                rows = run_sparql(query_g, sq["sparql"])
                sparql_results.append({
                    "cq_id": sq.get("cq_id", ""),
                    "question": sq.get("question", ""),
                    "sparql": sq["sparql"],
                    "result_count": len(rows),
                    "sample": rows[:5],
                })
            except Exception as e:
                sparql_results.append({
                    "cq_id": sq.get("cq_id", ""),
                    "error": str(e),
                })
        results["sparql_results"] = sparql_results

        # 保存 SHACL shapes 产物
        save_graph(shapes_g, "shacl_shapes.ttl", fmt="turtle")

        results["validation_summary"] = self._summarize(results)
        return results

    # ── 内部辅助 ──────────────────────────────────────────────

    @staticmethod
    def _spec_to_prompt(spec: dict) -> str:
        """将本体规范转为适合 LLM 阅读的文本。"""
        lines: list[str] = []
        for c in spec.get("classes", []):
            lines.append(f"Class: {c['name']}")
        for op in spec.get("object_properties", []):
            lines.append(
                f"ObjectProperty: {op['name']} "
                f"(domain={op.get('domain')}, range={op.get('range')})"
            )
        for dp in spec.get("data_properties", []):
            lines.append(
                f"DataProperty: {dp['name']} "
                f"(domain={dp.get('domain')}, range={dp.get('range')})"
            )
        return "\n".join(lines)

    def _build_shacl(self, shapes_spec: list[dict]) -> Graph:
        """根据 LLM 输出的 shapes 规范构建 SHACL RDF 图。"""
        g = Graph()
        g.bind("sh", SH)
        g.bind("ont", ONT)
        g.bind("xsd", XSD)

        for s in shapes_spec:
            target_cls = s.get("target_class", "Thing")
            shape_node = ONT[f"{target_cls}Shape"]
            g.add((shape_node, RDF.type, SH.NodeShape))
            g.add((shape_node, SH.targetClass, ONT[target_cls]))

            for p in s.get("properties", []):
                prop_node = BNode()
                g.add((shape_node, SH.property, prop_node))
                g.add((prop_node, SH.path, ONT[p["path"]]))
                if "min_count" in p:
                    g.add((prop_node, SH.minCount, Literal(p["min_count"])))
                if "max_count" in p:
                    g.add((prop_node, SH.maxCount, Literal(p["max_count"])))
                if "description" in p:
                    g.add((prop_node, SH.description, Literal(p["description"], lang="zh")))

        return g

    @staticmethod
    def _summarize(results: dict) -> str:
        """生成简洁的验证摘要文本。"""
        lines = ["=== 验证摘要 ==="]
        lines.append(
            f"OWL 推理一致性: {'通过' if results.get('owl_reasoning_ok') else '失败'}"
        )
        if results.get("shacl_conforms") is not None:
            lines.append(
                f"SHACL 验证: {'通过' if results['shacl_conforms'] else '存在违规'}"
            )
        sq = results.get("sparql_results", [])
        ok = sum(1 for s in sq if "error" not in s)
        lines.append(f"SPARQL CQ 回归: {ok}/{len(sq)} 查询成功执行")
        return "\n".join(lines)
