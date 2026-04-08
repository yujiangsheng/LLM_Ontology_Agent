"""
knowledge_populator — 知识图谱实例填充智能体
==============================================

根据已有的 OWL 本体结构（TBox）和领域文本，让 LLM 抽取具体
的实例（ABox Individual），包括个体属性值和个体间关系，然后
构建为 RDF 知识图谱。

输出产物:
  - ``knowledge_graph.ttl``  — Turtle 格式的知识图谱
  - ``kg_data.json``         — JSON 中间数据（便于审计）

作者: Jiangsheng Yu
许可: MIT License
"""
from __future__ import annotations

import logging
import re
from typing import Any

from rdflib import Graph, Literal, RDF, RDFS
from rdflib.namespace import XSD

from agents.base_agent import BaseAgent
from utils.owl_utils import new_ontology_graph, ONT, KB, save_graph

logger = logging.getLogger(__name__)

# LLM 系统提示词
SYSTEM = """\
你是领域知识抽取专家。根据下面的本体结构（类和属性）和领域文本，
抽取出所有具体的实例（Individual）及其属性值。

输出 JSON 格式：
{
  "individuals": [
    {
      "id": "sensor_001",
      "type": "Sensor",
      "properties": {
        "hasTemperature": 85.5,
        "belongsTo": "device_A"
      },
      "label": "温度传感器 001"
    }
  ],
  "relations": [
    {"subject": "device_A", "predicate": "hasSensor", "object": "sensor_001"}
  ]
}
只返回 JSON。"""


class KnowledgePopulatorAgent(BaseAgent):
    """知识图谱实例填充智能体。

    从领域文本中抽取具体实例，按本体结构映射为 RDF 三元组。
    """

    name = "KnowledgePopulatorAgent"

    def __init__(self):
        super().__init__(system_prompt=SYSTEM)

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        """执行知识抽取与图谱填充。

        Parameters
        ----------
        context : dict
            必须包含 ``domain_text`` (str)、``ontology_spec`` (dict)；
            可选 ``ontology_graph`` (Graph, 会被合并到输出图中)。

        Returns
        -------
        dict
            包含 ``knowledge_graph`` (Graph)、``knowledge_path`` (str)、
            ``individuals_count`` (int)、``relations_count`` (int)、
            ``kg_data`` (dict)。
        """
        domain_text = context["domain_text"]
        spec = context.get("ontology_spec", {})

        spec_str = self._spec_to_str(spec)
        prompt = (
            f"本体结构：\n{spec_str}\n\n"
            f"请从以下领域文本中抽取所有实例和关系：\n\n"
            f"---\n{domain_text[:6000]}\n---"
        )
        kg_data = self.ask_json(prompt)
        g = self._build_kg(kg_data, context.get("ontology_graph"))
        path = save_graph(g, "knowledge_graph.ttl", fmt="turtle")

        individuals = kg_data.get("individuals", [])
        relations = kg_data.get("relations", [])
        logger.info("知识图谱: %d 个实例, %d 条关系", len(individuals), len(relations))

        return {
            "knowledge_graph": g,
            "knowledge_path": path,
            "individuals_count": len(individuals),
            "relations_count": len(relations),
            "kg_data": kg_data,
        }

    # ── 辅助方法 ──────────────────────────────────────────────

    def _spec_to_str(self, spec: dict) -> str:
        """将本体规范转为 LLM 可读的文本摘要。"""
        lines: list[str] = []
        for c in spec.get("classes", []):
            parent = c.get("parent", "")
            lines.append(f"Class: {c['name']}" + (f" ⊑ {parent}" if parent else ""))
        for op in spec.get("object_properties", []):
            lines.append(
                f"ObjectProperty: {op['name']} "
                f"({op.get('domain', '')} → {op.get('range', '')})"
            )
        for dp in spec.get("data_properties", []):
            lines.append(
                f"DataProperty: {dp['name']} "
                f"({dp.get('domain', '')} → {dp.get('range', '')})"
            )
        return "\n".join(lines)

    def _build_kg(self, kg_data: dict, ont_g: Graph | None) -> Graph:
        """将 LLM 输出的 JSON 实例数据转为 rdflib Graph。"""
        g = new_ontology_graph()

        # 合并本体 TBox（使知识图谱自包含）
        if ont_g:
            for t in ont_g:
                g.add(t)

        # 所有个体 id 集合（用于判断属性值是引用还是字面量）
        all_ids = {ind["id"] for ind in kg_data.get("individuals", [])}
        all_safe_ids = {_safe(id_) for id_ in all_ids}

        # 添加个体
        for ind in kg_data.get("individuals", []):
            ind_id = _safe(ind["id"])
            ind_uri = KB[ind_id]
            g.add((ind_uri, RDF.type, ONT[ind["type"]]))

            if "label" in ind:
                g.add((ind_uri, RDFS.label, Literal(ind["label"], lang="zh")))

            for prop_name, value in ind.get("properties", {}).items():
                if isinstance(value, (int, float)):
                    g.add((ind_uri, ONT[prop_name], Literal(value)))
                elif isinstance(value, str) and _safe(value) in all_safe_ids:
                    # 值匹配另一个实例 → 作为对象属性引用
                    g.add((ind_uri, ONT[prop_name], KB[_safe(value)]))
                else:
                    g.add((ind_uri, ONT[prop_name], Literal(str(value))))

        # 添加显式关系三元组
        for rel in kg_data.get("relations", []):
            subj = KB[_safe(rel["subject"])]
            pred = ONT[rel["predicate"]]
            obj = KB[_safe(rel["object"])]
            g.add((subj, pred, obj))

        return g


def _safe(name: str) -> str:
    """将名称转为安全标识符（保留 Unicode 字母与数字）。"""
    return re.sub(r"[^\w]", "_", name, flags=re.UNICODE).strip("_") or "default"
