# skills/ — 智能体技能描述文件

本目录包含系统中每个智能体的技能描述文件（Markdown 格式）。
这些文件既是人类可阅读的文档，也是 **Prefrontal_Lobe 元认知智能体**
在执行技能演化时读取和修改的目标。

## 文件结构

每个技能文件遵循统一的结构：

| 章节 | 说明 |
|------|------|
| 元信息 | 版本号、最后修改日期、修改者 |
| 角色定位 | 智能体的核心职责描述 |
| 系统提示词 | 发送给 LLM 的 system prompt（代码块格式） |
| 输入输出 | 接口规范（含参数类型和示例 JSON） |
| 核心策略 | 关键技术策略和设计决策 |
| 评估指标 | 量化评估标准（带权重，权重之和 = 1.0） |
| 已知局限 | 当前版本的局限性 |
| 演化历史 | 修改记录（日期、版本、内容、原因、效果） |

## 文件列表

| 文件 | 智能体 | 说明 |
|------|--------|------|
| cq_agent.md | CQAgent | Competency Questions 提炼 |
| term_extractor.md | TermExtractorAgent | 术语抽取与类型判定 |
| ontology_builder.md | OntologyBuilderAgent | OWL 本体构建 |
| knowledge_populator.md | KnowledgePopulatorAgent | 知识图谱填充 |
| validator.md | ValidatorAgent | 三类自动验证 |
| reasoning_agent.md | ReasoningAgent | 硬推理 + 软推理 |
| explanation_agent.md | ExplanationAgent | 推理结果翻译 |
| orchestrator.md | Orchestrator | 多智能体协调 |
| prefrontal_lobe.md | PrefrontalLobe | 元认知自我演化 |

## 使用方式

Prefrontal_Lobe 元认知智能体通过以下方式使用这些文件：

1. **读取**: 了解目标智能体的当前技能配置
2. **评估**: 根据评估指标量化智能体表现
3. **优化**: 修改系统提示词或核心策略
4. **回写**: 将修改后的内容写回技能文件
5. **记录**: 在演化历史中追加修改记录

## 手动编辑指南

如需手动编辑技能文件：

1. 保持 Markdown 格式不变（Prefrontal_Lobe 依赖格式进行解析）
2. 修改后递增版本号（遵循语义化版本 X.Y.Z）
3. 在演化历史表格末尾追加修改记录
4. 系统提示词节的代码块必须保持（LLM 需要这个作为参考）
5. 评估指标权重之和应保持为 1.0

## 新增智能体

若要为新智能体添加技能文件：

1. 按上述结构创建 `your_agent.md`
2. 在 `agents/prefrontal_lobe.py` 的 `_skill_file_path()` 中添加映射
3. 元认知智能体即可自动纳管新智能体
