"""
utils — 工具函数包
====================

提供文档加载、OWL/SHACL/SPARQL 操作等共享工具。

子模块:
    - :mod:`utils.document_loader`  — 多格式文档加载 (.txt/.md/.csv/.docx/.pdf)
    - :mod:`utils.owl_utils`        — RDF/OWL/SHACL/SPARQL 操作工具

Usage Example::

    from utils.document_loader import load_text
    from utils.owl_utils import new_ontology_graph, add_class, save_graph

    # 加载领域文档
    text = load_text("domain_spec.docx")

    # 创建 OWL 图并添加类
    g = new_ontology_graph()
    add_class(g, "Device", label_zh="设备")
    save_graph(g, "my_ontology.owl")
"""