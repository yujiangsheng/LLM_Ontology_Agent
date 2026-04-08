# LLM + Ontology 多智能体系统

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-green.svg)](https://python.org)
[![Ollama](https://img.shields.io/badge/LLM-Ollama-orange.svg)](https://ollama.com)

基于本地 **qwen3-coder:30b** (Ollama) 的领域 Ontology 自动抽取与智能推理系统。

> **核心原则**: *LLM 提议，Reasoner 裁决，SHACL 把关，SPARQL 取证*

## 架构概览

```
┌─────────────────────── 流程一: 构建 ───────────────────────┐
│                                                            │
│  领域文档 → CQ Agent → Term Extractor → Ontology Builder   │
│                                              │             │
│                                              ▼             │
│                                    Knowledge Populator     │
│                                              │             │
│                                              ▼             │
│                                      Validator Agent       │
│                                   (OWL + SHACL + SPARQL)   │
│                                                            │
└────────────────────────────────────────────────────────────┘

┌─────────────────────── 流程二: 推理 ───────────────────────┐
│                                                            │
│  用户问题 → Reasoning Agent → Explanation Agent → 报告      │
│              (硬推理 + 软推理)    (Markdown 解释)            │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

### 智能体一览

| Agent | 职责 | 输入 → 输出 |
|-------|------|-------------|
| **CQ Agent** | 从领域文档提炼 Competency Questions | 文本 → JSON (CQ 列表) |
| **Term Extractor** | 术语抽取与本体类型判定 | 文本 + CQ → JSON (术语列表) |
| **Ontology Builder** | 生成 OWL 2 本体 (类层级、属性、公理) | 术语 + CQ → OWL Graph |
| **Knowledge Populator** | 从文本抽取实例, 填充 RDF 知识图谱 | 文本 + 本体 → KG (Turtle) |
| **Validator** | OWL 推理一致性 / SHACL 验证 / SPARQL CQ 回归 | 本体 + KG → 验证报告 |
| **Reasoning Agent** | 硬推理 (OWL/SHACL/SPARQL) + 软推理 (LLM) | 问题 + 本体 + KG → JSON 推理结果 |
| **Explanation Agent** | 将推理结果翻译为人类可读报告 | 推理 JSON → Markdown |
| **Orchestrator** | 编排所有 Agent 的多智能体协调器 | 全局上下文管理 |
| **Prefrontal Lobe** | 元认知智能体，监控并优化其他 Agent 技能 | 指标 → 诊断 → 演化 |

## 技术栈

| 组件 | 技术 | 用途 |
|------|------|------|
| LLM | Ollama + qwen3-coder:30b | 自然语言理解、代码/结构生成 |
| 知识表示 | RDF / OWL 2 (rdflib) | 本体和知识图谱建模 |
| 推理引擎 | owlrl (OWL 2 RL) | 演绎推理闭包 |
| 约束验证 | pyshacl (SHACL) | 数据质量保障 |
| 查询语言 | SPARQL 1.1 (rdflib) | 结构化查询取证 |
| 文档解析 | python-docx | .docx 格式支持 |

## 快速开始

### 1. 环境准备

```bash
# 确保 Ollama 正在运行且模型已拉取
ollama list | grep qwen3-coder

# 安装 Python 依赖
pip install -r requirements.txt

# 或使用 pyproject.toml 安装
pip install -e .
```

### 2. 构建 Ontology + 知识图谱

```bash
# 从文本文档构建
python main.py build test_domain.txt --domain "设备故障诊断"

# 支持多种文档格式
python main.py build report.docx --domain "医疗诊断"
python main.py build spec.md --domain "软件架构"
```

构建五步管线会依次执行:
1. **CQ 提炼** — 从文档生成 Competency Questions
2. **术语抽取** — 识别领域术语并判定类型 (Class / Property / Individual)
3. **OWL 本体生成** — 构建类层级、属性约束、公理
4. **知识图谱填充** — 抽取实例和关系
5. **三类自动验证** — OWL 一致性 / SHACL 约束 / SPARQL CQ 回归

### 3. 推理问答

```bash
# 交互模式: 先构建，然后连续提问
python main.py interactive test_domain.txt --domain "设备故障诊断"

# 基于已有产物直接提问
python main.py ask "哪些设备处于过热风险？为什么？"

# 等效命令
python main.py reason "设备C_100的传感器读数异常的原因是什么？"
```

### 4. 调试模式

```bash
# -v 启用详细日志 (DEBUG 级别)
python main.py -v build test_domain.txt --domain "设备故障诊断"
```

## 产物说明

所有产物保存在 `output/` 目录:

| 文件 | 格式 | 说明 |
|------|------|------|
| `*_ontology.owl` | RDF/XML | OWL 本体 (机器可读) |
| `*_ontology.ttl` | Turtle | OWL 本体 (人工可读) |
| `knowledge_graph.ttl` | Turtle | 实例知识图谱 |
| `shacl_shapes.ttl` | Turtle | SHACL 约束图 |
| `competency_questions.json` | JSON | 能力问题清单 |
| `terms.json` | JSON | 抽取的领域术语 |
| `ontology_spec.json` | JSON | 本体结构规范 |
| `kg_data.json` | JSON | 知识图谱数据 (JSON 形式) |

## 配置

通过环境变量自定义:

```bash
# ── LLM 配置 ────────────────────────────────────────
export LLM_MODEL="qwen3-coder:30b"              # LLM 模型名
export OLLAMA_BASE_URL="http://localhost:11434"   # Ollama 地址
export LLM_TEMPERATURE="0.3"                      # 温度 (0.0-1.0)
export LLM_MAX_TOKENS="4096"                      # 最大生成 token 数
export LLM_TIMEOUT="600"                          # 请求超时 (秒)
export LLM_RETRY_COUNT="2"                        # 失败重试次数

# ── Ontology 命名空间 ────────────────────────────────
export ONTOLOGY_BASE_IRI="http://example.org/ontology/"  # 本体基 IRI
export KNOWLEDGE_BASE_IRI="http://example.org/kb/"       # 知识图谱基 IRI

# ── 记忆系统 ────────────────────────────────────────
export WORKING_MEMORY_MAX_ENTRIES="50"            # 工作记忆滑动窗口大小
export SIMILARITY_THRESHOLD="0.3"                 # 语义检索相似度阈值
export RAG_CHUNK_SIZE="500"                       # RAG 分块大小 (字符数)
export RAG_CHUNK_OVERLAP="100"                    # RAG 块间重叠 (字符数)

# ── 元认知演化 ──────────────────────────────────────
export EVOLUTION_MIN_SCORE="0.6"                  # 演化提案最低通过分数

# ── 外部记忆 (可选) ─────────────────────────────────
export WEB_SEARCH_API_URL="https://your-api/search?q="  # Web 搜索 API
```

参见 [config.py](config.py) 查看所有可配置项及默认值。

## 元认知自我演化 (Prefrontal Lobe)

灵感来源于大脑前额叶皮层 (Prefrontal Cortex) — 负责规划、监控、自我反省和行为调节。

```
元认知循环: 监控 → 评估 → 诊断 → 优化 → 验证 → 应用/回滚
                  ↑                          │
                  └──────────────────────────┘
```

### 工作原理

1. **指标收集**: 从构建/推理结果中提取各 Agent 的执行指标（CQ 数量、术语类型分布、SPARQL 成功率等）
2. **智能诊断**: LLM 分析指标和技能描述，定位性能瓶颈
3. **优化提案**: 生成具体的技能文件修改方案（提示词改写、策略新增、参数调优）
4. **安全验证**: 独立 LLM 评审提案的安全性、有效性、一致性（三项分数均需 ≥ 0.6）
5. **可控应用**: 只修改技能描述文件 (Markdown)，自动递增版本号并记录演化历史

### 使用方式

```bash
# 构建 + 自动演化
python main.py evolve test_domain.txt --domain "设备故障诊断"

# 交互模式中输入 evolve
python main.py interactive test_domain.txt --domain "设备故障诊断"
# > evolve
```

### 技能描述文件

每个智能体的技能通过 `skills/` 目录下的 Markdown 文件描述，包含：
- 角色定位和系统提示词
- 输入输出规范
- 核心策略和设计决策
- 量化评估指标（带权重）
- 已知局限和演化历史

Prefrontal Lobe 通过读取、评估和修改这些文件实现智能体的自我演化。

## 四层记忆系统

系统内置四层记忆架构，赋予智能体跨步骤、跨会话的记忆能力:

```
┌─────────────────────────────────────────────────────────────┐
│                     MemoryManager                           │
│                  (统一记忆接口: recall / memorize)            │
├───────────┬──────────────┬──────────────┬───────────────────┤
│ 🧠 工作记忆 │  📚 长期记忆   │  💎 持久记忆   │  🌐 外部记忆     │
│ (Working)  │ (Long-term)  │ (Persistent) │ (External)       │
│            │              │              │                  │
│ 当前会话   │ 跨会话向量   │ 经验库       │ RAG 文档检索     │
│ 滑动窗口   │ 语义检索     │ 知识库       │ Web 搜索缓存     │
│ 焦点追踪   │ 余弦相似度   │ Ontology     │ 向量化分块       │
└───────────┴──────────────┴──────────────┴───────────────────┘
```

### 记忆层详解

| 层级 | 生命周期 | 存储方式 | 检索方式 | 用途 |
|------|----------|----------|----------|------|
| **工作记忆** | 当前会话 | 内存 (滑动窗口) | 标签/Agent/时间 | 保持任务上下文连贯 |
| **长期记忆** | 跨会话持久化 | JSON + 向量 | 语义相似度 | 积累推理经验 |
| **持久记忆** | 永久 | JSON + RDF Graph | 关键词/SPARQL | 领域知识与本体 |
| **外部记忆** | 按需加载 | JSON 索引 + 缓存 | 向量检索/API | 扩展知识边界 |

### 记忆 CLI 命令

```bash
# 查看记忆统计
python main.py memory

# 将参考文档加入 RAG 索引
python main.py add-doc reference_manual.txt
python main.py add-doc technical_spec.docx

# 交互模式中输入 "memory" 查看统计
python main.py interactive test_domain.txt --domain "设备故障诊断"
# > memory
```

### 记忆工作流

1. **构建阶段**: 领域文档自动加入 RAG 索引; 构建过程记录到工作记忆; 最终本体载入持久记忆
2. **推理阶段**: 工作记忆提供上下文; 长期记忆提供历史参考; 持久记忆提供领域知识; RAG 提供文档证据
3. **会话结束**: 工作记忆摘要归档到长期记忆; 经验和知识持久化保存

### 外部记忆 — Web 搜索

通过设置环境变量启用 Web 搜索能力:

```bash
export WEB_SEARCH_API_URL="https://your-search-api/search?q="
```

记忆数据存储在 `output/memory/` 目录下，包括:
- `long_term/index.json` — 长期记忆向量索引
- `persistent/experiences.json` — 经验库
- `persistent/knowledge.json` — 知识库
- `rag/rag_index.json` — RAG 文档索引
- `web_cache/search_cache.json` — Web 搜索缓存

## 设计原则

1. **LLM 提议，Reasoner 裁决** — LLM 生成候选知识，形式推理验证正确性
2. **硬推理与软推理分离** — 可判定部分交给 OWL/SHACL/SPARQL，不确定部分交给 LLM
3. **结构化中间产物** — 每个 Agent 输出 JSON / OWL / SHACL / Turtle，便于审计和版本管理
4. **模块化管线** — 分阶段构建 (CQ → 术语 → OWL → KG → 验证)，支持增量迭代
5. **本地运行** — 所有计算在本地完成 (Ollama)，无需外部 API

## Web 界面

系统提供基于 Flask 的 Web 前端，可在浏览器中完成所有操作。

### 启动

```bash
# 默认地址 http://127.0.0.1:5000
python main.py web

# 自定义端口
python main.py web --port 8080

# 对外暴露（局域网访问）
python main.py web --host 0.0.0.0 --port 8080
```

### 功能页面

| 页面 | 功能 |
|------|------|
| **🏗️ 构建** | 文本输入或文件上传构建本体 + KG；加载已有产物 |
| **🧠 推理** | 自然语言问答，返回 Markdown 格式推理报告 |
| **📊 记忆** | 查看四层记忆统计；添加 RAG 文档 |
| **🔄 演化** | 执行 Prefrontal Lobe 元认知自我演化 |

### 退出服务

- 点击页面右上角 **⏻ 退出** 按钮（会弹出确认对话框）
- 或在终端按 `Ctrl+C`

## 项目结构

```
LLM_Ontology_Agent/
├── main.py                 # CLI 入口
├── config.py               # 全局配置
├── llm_client.py           # Ollama HTTP 客户端
├── web_server.py           # Web 前端 Flask 服务
├── templates/
│   └── index.html          # Web 单页应用
├── static/
│   ├── style.css           # 前端样式
│   └── app.js              # 前端逻辑
├── agents/
│   ├── __init__.py
│   ├── base_agent.py       # Agent 基类 (含记忆集成)
│   ├── cq_agent.py         # Competency Questions 提取
│   ├── term_extractor.py   # 术语抽取
│   ├── ontology_builder.py # OWL 本体生成
│   ├── knowledge_populator.py  # 知识图谱填充
│   ├── validator.py        # 三类自动验证
│   ├── reasoning_agent.py  # 硬推理 + 软推理
│   ├── explanation_agent.py    # 自然语言解释
│   ├── prefrontal_lobe.py  # 元认知智能体 (技能自我演化)
│   └── orchestrator.py     # 多智能体协调器 (记忆生命周期)
├── skills/                 # 智能体技能描述文件 (Markdown)
│   ├── README.md           # 技能文件结构说明
│   ├── cq_agent.md
│   ├── term_extractor.md
│   ├── ontology_builder.md
│   ├── knowledge_populator.md
│   ├── validator.md
│   ├── reasoning_agent.md
│   ├── explanation_agent.md
│   └── orchestrator.md
├── memory/
│   ├── __init__.py         # 记忆子系统包
│   ├── working.py          # 工作记忆 (滑动窗口)
│   ├── long_term.py        # 长期记忆 (向量语义检索)
│   ├── persistent.py       # 持久记忆 (经验/知识/Ontology)
│   ├── external.py         # 外部记忆 (RAG + Web 搜索)
│   └── manager.py          # 统一记忆管理器
├── utils/
│   ├── __init__.py
│   ├── owl_utils.py        # RDF/OWL/SHACL/SPARQL 工具
│   └── document_loader.py  # 多格式文档加载
├── output/                 # 构建产物 (自动生成)
│   └── memory/             # 记忆持久化数据
├── requirements.txt
├── pyproject.toml
├── LICENSE                 # MIT License
└── README.md
```

## Python API 使用示例

除命令行外，也可以在 Python 代码中直接调用:

```python
from agents.orchestrator import Orchestrator
from utils.document_loader import load_text

# ── 构建流程 ──────────────────────────────────────
orch = Orchestrator()
text = load_text("domain_spec.txt")
context = orch.build_ontology(text, domain_name="设备故障诊断")

# 查看构建产物
print(context["ontology_path"])          # output/设备故障诊断_ontology.owl
print(context["individuals_count"])      # 15
print(context["validation_summary"])     # 验证摘要

# ── 推理流程 ──────────────────────────────────────
explanation = orch.reason("哪些设备存在过热风险？")
print(explanation)                       # Markdown 格式报告

# ── 记忆操作 ──────────────────────────────────────
# 查看记忆统计
print(orch.memory.stats())

# 手动写入长期记忆
orch.memory.memorize("传感器 A 存在周期性漂移", layer="long_term", category="reasoning")

# 综合检索
results = orch.memory.recall("传感器异常", layers=["working", "long_term", "rag"])

# ── 元认知演化 ────────────────────────────────────
evolution_result = orch.evolve()
print(evolution_result["proposals_applied"])  # 成功应用的修改数

# ── 会话结束 ──────────────────────────────────────
orch.end_session()                       # 摘要归档到长期记忆
```

## 常见问题排查

### Ollama 连接失败

```
RuntimeError: 无法连接 Ollama (http://localhost:11434)，请确认服务已启动
```

**解决**: 确认 Ollama 正在运行：

```bash
ollama list                                # 检查服务是否可用
ollama pull qwen3-coder:30b                # 拉取模型（首次使用）
ollama pull nomic-embed-text:latest        # 拉取嵌入模型
```

### JSON 解析错误

LLM 偶尔返回非法 JSON（如包含注释或截断），系统已内置 Markdown 代码块剥离逻辑。
如果持续出错，可尝试：
- 降低 `LLM_TEMPERATURE` 到 `0.1`
- 增大 `LLM_MAX_TOKENS` 到 `8192`

### OWL 推理耗时长

大规模本体（> 10000 三元组）上的 OWL 2 RL 推理可能较慢。可以：
- 减少领域文本长度
- 精简 CQ 数量

### 记忆数据损坏

记忆数据存储在 `output/memory/` 目录。如遇加载错误，可安全删除对应 JSON 文件：

```bash
rm output/memory/long_term/index.json      # 重置长期记忆
rm output/memory/persistent/experiences.json  # 重置经验库
```

## 许可

[MIT License](LICENSE) — Copyright (c) 2026 Jiangsheng Yu

## 作者

**Jiangsheng Yu** — 设计、开发与维护
