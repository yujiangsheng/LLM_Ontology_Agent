"""
memory — 多层记忆系统
======================

为智能体提供四层记忆能力:

- :mod:`memory.working`     — 工作记忆（会话级短期上下文，滑动窗口）
- :mod:`memory.long_term`   — 长期记忆（跨会话，向量余弦相似度检索）
- :mod:`memory.persistent`  — 持久记忆（经验库 / 知识库 / Ontology SPARQL）
- :mod:`memory.external`    — 外部记忆（RAG 文档分块检索 + 网络搜索缓存）
- :mod:`memory.manager`     — 统一记忆管理器（recall / memorize / get_context_for_agent）

Architecture::

    ┌──────────────────────────────────────────────────────┐
    │                 MemoryManager (统一接口)               │
    ├─────────────┬──────────────┬────────────┬────────────┤
    │ Working Mem │ Long-term    │ Persistent │ External   │
    │  (会话级)   │  (向量检索)  │ (经验/知识) │ (RAG+Web) │
    └─────────────┴──────────────┴────────────┴────────────┘

Usage Example::

    from memory.manager import MemoryManager

    mm = MemoryManager()
    mm.start_session(focus="设备故障推理")
    mm.memorize("传感器 A 温度 > 90°C", layer="working", tag="observation")
    results = mm.recall("哪些传感器温度异常")
    mm.end_session()

作者: Jiangsheng Yu
许可: MIT License
"""
