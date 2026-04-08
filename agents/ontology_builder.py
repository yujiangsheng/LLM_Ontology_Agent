"""
ontology_builder — OWL 本体构建智能体
=======================================

根据上游的术语列表和 Competency Questions，让 LLM 设计 OWL 本体结构
（类层级、对象属性、数据属性和公理），然后使用 rdflib 将规范转化为
符合 OWL 2 语义的 RDF 图，并保存为 ``.owl`` (RDF/XML) 和 ``.ttl``
(Turtle) 两种格式。

设计理念
--------
- **按模块生成**：拆分为 classes / object_properties / data_properties / axioms
- **LLM 草案 + 代码构建**：LLM 产出 JSON 规范，Python 代码保证 OWL 语法正确
- **等价类公理**：自动解析 ``"X and (P some Y)"`` 模式为 ``owl:equivalentClass``

作者: Jiangsheng Yu
许可: MIT License
"""
from __future__ import annotations

import logging
import re
from typing import Any

from rdflib import Literal, OWL, RDFS, RDF, BNode
from rdflib.collection import Collection
from rdflib.namespace import XSD

from agents.base_agent import BaseAgent
from utils.owl_utils import (
    new_ontology_graph,
    add_class,
    add_object_property,
    add_data_property,
    save_graph,
    ONT,
)

logger = logging.getLogger(__name__)

# LLM 系统提示词
SYSTEM = """\
你是本体建模专家。你需要根据已抽取的术语列表和 Competency Questions，
设计类的层级关系（subClassOf）、对象属性（domain/range）和数据属性。
还需要生成关键的 OWL 公理（如等价类、属性限制等）。

请以 JSON 格式返回：
{
  "classes": [
    {"name": "DeviceName", "parent": null, "label_zh": "...", "comment": "..."}
  ],
  "object_properties": [
    {"name": "hasSensor", "domain": "Device", "range": "Sensor", "label_zh": "..."}
  ],
  "data_properties": [
    {"name": "hasTemperature", "domain": "Sensor", "range": "xsd:float", "label_zh": "..."}
  ],
  "axioms": [
    {"description": "...", "type": "subclass_restriction", "class": "OverheatRiskDevice",
     "equivalent_to": "Device and (emitsAlarm some OverheatAlarm)"}
  ]
}
只返回 JSON。"""

# XSD 数据类型映射表
XSD_MAP: dict[str, Any] = {
    "xsd:string": XSD.string,
    "xsd:float": XSD.float,
    "xsd:double": XSD.double,
    "xsd:integer": XSD.integer,
    "xsd:int": XSD.integer,
    "xsd:boolean": XSD.boolean,
    "xsd:dateTime": XSD.dateTime,
    "xsd:date": XSD.date,
}


class OntologyBuilderAgent(BaseAgent):
    """OWL 2 本体构建智能体。

    流程: LLM 生成 JSON 规范 → 代码转为 rdflib Graph → 保存 OWL + TTL
    """

    name = "OntologyBuilderAgent"

    def __init__(self):
        super().__init__(system_prompt=SYSTEM)

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        """执行本体构建。

        Parameters
        ----------
        context : dict
            必须包含 ``terms`` (list[dict])、``competency_questions`` (list|dict)；
            可选 ``domain_name`` (str)。

        Returns
        -------
        dict
            包含 ``ontology_graph`` (Graph)、``ontology_path`` (str)、
            ``ontology_spec`` (dict)。
        """
        terms = context.get("terms", [])
        if isinstance(terms, dict):
            terms = terms.get("terms", [])
        cqs = context.get("competency_questions", [])
        if isinstance(cqs, dict):
            cqs = cqs.get("competency_questions", [])
        domain_name = context.get("domain_name", "domain")

        # 组装 prompt
        terms_str = "\n".join(
            f"- {t['term']} ({t.get('candidate_type', '?')}): {t.get('definition', '')}"
            for t in terms
        )
        cq_str = "\n".join(f"- {q.get('question', q)}" for q in cqs)

        prompt = (
            f"领域：{domain_name}\n\n"
            f"术语列表：\n{terms_str}\n\n"
            f"Competency Questions：\n{cq_str}\n\n"
            f"请设计 OWL 本体的类、属性和公理。"
        )
        spec = self.ask_json(prompt)

        # 从 JSON 规范构建 rdflib Graph
        g = self._build_graph(spec, domain_name)

        # 保存两种格式
        safe_name = _safe(domain_name)
        path = save_graph(g, f"{safe_name}_ontology.owl")
        save_graph(g, f"{safe_name}_ontology.ttl", fmt="turtle")

        return {
            "ontology_graph": g,
            "ontology_path": path,
            "ontology_spec": spec,
        }

    # ── 内部: JSON → Graph ───────────────────────────────────

    def _build_graph(self, spec: dict, domain_name: str):
        """将 LLM 输出的 JSON 规范转换为 OWL rdflib Graph。"""
        g = new_ontology_graph()

        # 声明本体 IRI
        ont_uri = ONT[_safe(domain_name) + "Ontology"]
        g.add((ont_uri, RDF.type, OWL.Ontology))
        g.add((ont_uri, RDFS.label, Literal(domain_name, lang="zh")))

        # 类
        for c in spec.get("classes", []):
            add_class(
                g, c["name"],
                c.get("parent"),
                c.get("label_zh", ""),
                c.get("comment", ""),
            )

        # 对象属性
        for op in spec.get("object_properties", []):
            add_object_property(
                g, op["name"],
                op.get("domain"),
                op.get("range"),
                op.get("label_zh", ""),
            )

        # 数据属性
        for dp in spec.get("data_properties", []):
            range_uri = XSD_MAP.get(dp.get("range"), XSD.string)
            add_data_property(
                g, dp["name"],
                dp.get("domain"),
                range_uri,
                dp.get("label_zh", ""),
            )

        # 公理（等价类等）
        for ax in spec.get("axioms", []):
            self._add_axiom(g, ax)

        logger.info("本体构建完成: %d 三元组", len(g))
        return g

    def _add_axiom(self, g, ax: dict):
        """尽力把 LLM 的公理描述转为 OWL 三元组。

        目前支持的模式:
        - ``"X and (P some Y)"`` → ``owl:equivalentClass`` + ``owl:Restriction``
        """
        cls_name = ax.get("class", "")
        if not cls_name:
            return
        cls_uri = ONT[cls_name]
        g.add((cls_uri, RDF.type, OWL.Class))

        eq = ax.get("equivalent_to", "")
        if eq and "some" in eq.lower():
            # 解析 "ClassName and (propName some FillerClass)"
            m = re.match(
                r"(\w+)\s+and\s+\((\w+)\s+some\s+(\w+)\)",
                eq,
                re.IGNORECASE,
            )
            if m:
                base_cls = ONT[m.group(1)]
                prop = ONT[m.group(2)]
                filler = ONT[m.group(3)]

                restriction = BNode()
                g.add((restriction, RDF.type, OWL.Restriction))
                g.add((restriction, OWL.onProperty, prop))
                g.add((restriction, OWL.someValuesFrom, filler))

                intersect = BNode()
                g.add((intersect, RDF.type, OWL.Class))
                list_head = BNode()
                g.add((intersect, OWL.intersectionOf, list_head))
                Collection(g, list_head, [base_cls, restriction])
                g.add((cls_uri, OWL.equivalentClass, intersect))

        # 将公理描述存为 rdfs:comment
        desc = ax.get("description", "")
        if desc:
            g.add((cls_uri, RDFS.comment, Literal(desc, lang="zh")))


def _safe(name: str) -> str:
    """将名称转为安全标识符（保留 Unicode 字母与数字）。"""
    return re.sub(r"[^\w]", "_", name, flags=re.UNICODE).strip("_") or "default"
