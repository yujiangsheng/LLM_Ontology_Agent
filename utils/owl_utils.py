"""
owl_utils — OWL / RDF / SHACL / SPARQL 工具函数集
===================================================

为上层 Agent 提供语义 Web 技术的基础能力：

- **图构建辅助** — ``new_ontology_graph()``, ``add_class()``, ``add_object_property()`` 等
- **SHACL 验证** — ``validate_shacl()``
- **SPARQL 查询** — ``run_sparql()``
- **OWL 推理**   — ``run_owl_reasoning()``（基于 owlrl 的 OWL 2 RL 闭包）

核心命名空间
------------
``ONT``  → 本体 TBox（由 ``config.ONTOLOGY_BASE_IRI`` 决定）
``KB``   → 知识图谱 ABox（由 ``config.KNOWLEDGE_BASE_IRI`` 决定）

Usage Example::

    from utils.owl_utils import (
        new_ontology_graph, add_class, add_object_property,
        add_data_property, add_individual, save_graph,
        validate_shacl, run_sparql, run_owl_reasoning,
    )

    # 创建空本体
    g = new_ontology_graph()

    # 添加类层级
    add_class(g, "Device", label="设备", comment="工厂设备")
    add_class(g, "Sensor", parent="Device", label="传感器")

    # 添加属性
    add_object_property(g, "hasSensor", domain="Device", range_="Sensor")
    add_data_property(g, "temperature", domain="Sensor", range_uri=XSD.float)

    # SPARQL 查询
    results = run_sparql(g, "SELECT ?cls WHERE { ?cls a owl:Class }")

    # 保存
    save_graph(g, "output.owl")

作者: Jiangsheng Yu
许可: MIT License
"""
from __future__ import annotations

import logging
import os

from rdflib import Graph, Namespace, RDF, RDFS, OWL, Literal, URIRef, BNode
from rdflib.namespace import XSD

import config

logger = logging.getLogger(__name__)

# 全局命名空间对象，供各 Agent 引用
ONT = Namespace(config.ONTOLOGY_BASE_IRI)
KB = Namespace(config.KNOWLEDGE_BASE_IRI)


# ═══════════════════════════════════════════════════════════════
#  OWL 图构建辅助
# ═══════════════════════════════════════════════════════════════

def new_ontology_graph() -> Graph:
    """创建一个绑定了常用命名空间前缀的空 RDF 图。

    绑定的前缀包括 ``ont:``, ``kb:``, ``owl:``, ``rdfs:``, ``xsd:``。
    """
    g = Graph()
    g.bind("ont", ONT)
    g.bind("kb", KB)
    g.bind("owl", OWL)
    g.bind("rdfs", RDFS)
    g.bind("xsd", XSD)
    return g


def add_class(
    g: Graph,
    name: str,
    parent: str | None = None,
    label: str = "",
    comment: str = "",
) -> URIRef:
    """向图中添加一个 OWL 类。

    Parameters
    ----------
    g : Graph
        目标 RDF 图。
    name : str
        类的本地名（将拼到 ``ONT`` 命名空间下）。
    parent : str, optional
        父类本地名，非空则添加 ``rdfs:subClassOf``。
    label : str, optional
        中文标签（``rdfs:label``）。
    comment : str, optional
        中文注释（``rdfs:comment``）。

    Returns
    -------
    URIRef
        新建或已有类的 URI。
    """
    cls = ONT[name]
    g.add((cls, RDF.type, OWL.Class))
    if parent:
        g.add((cls, RDFS.subClassOf, ONT[parent]))
    if label:
        g.add((cls, RDFS.label, Literal(label, lang="zh")))
    if comment:
        g.add((cls, RDFS.comment, Literal(comment, lang="zh")))
    return cls


def add_object_property(
    g: Graph,
    name: str,
    domain: str | None = None,
    range_: str | None = None,
    label: str = "",
) -> URIRef:
    """向图中添加一个 OWL 对象属性（关联两个实例的关系）。"""
    prop = ONT[name]
    g.add((prop, RDF.type, OWL.ObjectProperty))
    if domain:
        g.add((prop, RDFS.domain, ONT[domain]))
    if range_:
        g.add((prop, RDFS.range, ONT[range_]))
    if label:
        g.add((prop, RDFS.label, Literal(label, lang="zh")))
    return prop


def add_data_property(
    g: Graph,
    name: str,
    domain: str | None = None,
    range_: URIRef | None = None,
    label: str = "",
) -> URIRef:
    """向图中添加一个 OWL 数据属性（关联实例与字面值的关系）。"""
    prop = ONT[name]
    g.add((prop, RDF.type, OWL.DatatypeProperty))
    if domain:
        g.add((prop, RDFS.domain, ONT[domain]))
    if range_:
        g.add((prop, RDFS.range, range_))
    if label:
        g.add((prop, RDFS.label, Literal(label, lang="zh")))
    return prop


def add_individual(g: Graph, name: str, cls: str, ns: Namespace = KB) -> URIRef:
    """向图中添加一个命名个体（ABox 实例）。"""
    ind = ns[name]
    g.add((ind, RDF.type, ONT[cls]))
    return ind


def save_graph(g: Graph, filename: str, fmt: str = "xml") -> str:
    """将图序列化后保存到 ``config.OUTPUT_DIR`` 下。

    Parameters
    ----------
    g : Graph
        待保存的 RDF 图。
    filename : str
        输出文件名（不含目录）。
    fmt : str
        序列化格式，默认 ``"xml"``；可选 ``"turtle"``, ``"n3"`` 等。

    Returns
    -------
    str
        保存后的完整路径。
    """
    path = os.path.join(config.OUTPUT_DIR, filename)
    g.serialize(destination=path, format=fmt)
    logger.debug("图已保存: %s (%d 三元组)", path, len(g))
    return path


# ═══════════════════════════════════════════════════════════════
#  SHACL 验证
# ═══════════════════════════════════════════════════════════════

def validate_shacl(data_graph: Graph, shapes_graph: Graph) -> tuple[bool, str]:
    """运行 SHACL 验证。

    Parameters
    ----------
    data_graph : Graph
        待验证的数据图（ABox + TBox 均可）。
    shapes_graph : Graph
        SHACL Shapes 图。

    Returns
    -------
    tuple[bool, str]
        ``(conforms, report_text)``。``conforms`` 为 ``True``
        表示数据完全符合约束。
    """
    import pyshacl

    conforms, _results_graph, results_text = pyshacl.validate(
        data_graph,
        shacl_graph=shapes_graph,
        inference="none",
        abort_on_first=False,
    )
    return conforms, results_text


# ═══════════════════════════════════════════════════════════════
#  SPARQL 查询
# ═══════════════════════════════════════════════════════════════

def run_sparql(g: Graph, query: str) -> list[dict]:
    """在 rdflib Graph 上执行 SPARQL SELECT 查询。

    返回结果中，键使用 SPARQL 变量名（如 ``"x"``, ``"name"``），
    而非位置序号，方便下游代码按语义访问。

    Usage Example::

        results = run_sparql(g, "SELECT ?dev ?temp WHERE { ?dev ont:hasTemp ?temp }")
        for row in results:
            print(row["dev"], row["temp"])

    Returns
    -------
    list[dict]
        每行一个字典，键为 SPARQL 变量名，值为绑定结果的字符串。
    """
    result = g.query(query)
    var_names = [str(v) for v in result.vars] if result.vars else []
    rows: list[dict] = []
    for row in result:
        if var_names:
            rows.append({name: str(row[i]) for i, name in enumerate(var_names)})
        else:
            rows.append({str(i): str(row[i]) for i in range(len(row))})
    return rows


# ═══════════════════════════════════════════════════════════════
#  OWL 推理（基于 owlrl）
# ═══════════════════════════════════════════════════════════════

def run_owl_reasoning(g: Graph, profile: str = "rdfs+owl") -> Graph:
    """基于 owlrl 在给定图上执行 OWL 2 RL / RDFS 演绎闭包。

    推理结果直接追加到 *g* 中并返回。

    Parameters
    ----------
    g : Graph
        目标图（会被原地修改）。
    profile : str
        推理策略：``"rdfs"`` 仅做 RDFS 推理；
        ``"rdfs+owl"``（默认）做 OWL 2 RL 完整推理。

    Returns
    -------
    Graph
        与输入同一个 Graph 对象（追加了推理三元组）。
    """
    import owlrl

    if profile == "rdfs":
        owlrl.DeductiveClosure(owlrl.RDFS_Semantics).expand(g)
    else:
        owlrl.DeductiveClosure(owlrl.OWLRL_Semantics).expand(g)
    return g
