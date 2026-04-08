"""
config — 全局配置中心
======================

所有配置项均可通过同名环境变量覆盖，方便在不同环境（开发 / CI / 生产）
之间切换而无需修改代码。

配置分区:
  - **LLM**:       Ollama 服务地址、模型名称、生成参数
  - **Ontology**:  OWL / KG 命名空间 IRI
  - **Memory**:    四层记忆系统参数
  - **Skills**:    技能描述文件目录
  - **Evolution**: 元认知自我演化阈值
  - **Paths**:     项目根目录、输出目录

Usage Example::

    import config

    # 读取当前 LLM 模型名
    print(config.DEFAULT_MODEL)          # "qwen3-coder:30b"

    # 通过环境变量覆盖
    #   export LLM_MODEL="llama3:70b"
    #   export LLM_TEMPERATURE="0.5"

作者: Jiangsheng Yu
许可: MIT License
"""
from __future__ import annotations

import os

# ═══════════════════════════════════════════════════════════════
#  Ollama / LLM 配置
# ═══════════════════════════════════════════════════════════════

# Ollama 服务地址（默认本地 11434 端口）
OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

# 默认对话模型（推荐 qwen3-coder:30b）
DEFAULT_MODEL: str = os.getenv("LLM_MODEL", "qwen3-coder:30b")

# 文本嵌入模型（用于长期记忆和 RAG 的语义检索）
EMBED_MODEL: str = os.getenv("EMBED_MODEL", "nomic-embed-text:latest")

# LLM 生成参数
LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0.3"))
LLM_MAX_TOKENS: int = int(os.getenv("LLM_MAX_TOKENS", "4096"))

# 单次请求超时（秒）——大模型推理可能较慢，默认 10 分钟
LLM_TIMEOUT: int = int(os.getenv("LLM_TIMEOUT", "600"))

# 重试次数（网络抖动或服务暂停时自动重试）
LLM_RETRY_COUNT: int = int(os.getenv("LLM_RETRY_COUNT", "2"))

# ═══════════════════════════════════════════════════════════════
#  Ontology 命名空间
# ═══════════════════════════════════════════════════════════════

# 本体 TBox 命名空间
ONTOLOGY_BASE_IRI: str = os.getenv(
    "ONTOLOGY_BASE_IRI", "http://example.org/ontology/"
)

# 知识图谱 ABox（实例）命名空间
KNOWLEDGE_BASE_IRI: str = os.getenv(
    "KNOWLEDGE_BASE_IRI", "http://example.org/kb/"
)

# ═══════════════════════════════════════════════════════════════
#  记忆系统配置
# ═══════════════════════════════════════════════════════════════

# 工作记忆滑动窗口大小（条目数）
WORKING_MEMORY_MAX_ENTRIES: int = int(os.getenv("WORKING_MEMORY_MAX_ENTRIES", "50"))

# 工作记忆 token 上限估算（1 字符 ≈ 1.5 token）
WORKING_MEMORY_MAX_TOKENS: int = int(os.getenv("WORKING_MEMORY_MAX_TOKENS", "8000"))

# 长期记忆 / RAG 语义检索默认相似度阈值
SIMILARITY_THRESHOLD: float = float(os.getenv("SIMILARITY_THRESHOLD", "0.3"))

# RAG 分块大小（字符数）和块间重叠
RAG_CHUNK_SIZE: int = int(os.getenv("RAG_CHUNK_SIZE", "500"))
RAG_CHUNK_OVERLAP: int = int(os.getenv("RAG_CHUNK_OVERLAP", "100"))

# ═══════════════════════════════════════════════════════════════
#  元认知 / 演化配置
# ═══════════════════════════════════════════════════════════════

# 演化验证通过的最低分数阈值（safety / effectiveness / consistency 三项）
EVOLUTION_MIN_SCORE: float = float(os.getenv("EVOLUTION_MIN_SCORE", "0.6"))

# ═══════════════════════════════════════════════════════════════
#  项目路径
# ═══════════════════════════════════════════════════════════════

# 项目根目录（与本文件同级）
PROJECT_ROOT: str = os.path.dirname(os.path.abspath(__file__))

# 所有生成产物的输出目录
OUTPUT_DIR: str = os.path.join(PROJECT_ROOT, "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 智能体技能描述文件目录
SKILLS_DIR: str = os.path.join(PROJECT_ROOT, "skills")
