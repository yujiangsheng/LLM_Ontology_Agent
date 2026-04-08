# ReasoningAgent — 硬推理 + 软推理混合技能

## 元信息

- **智能体**: ReasoningAgent
- **模块**: agents/reasoning_agent.py
- **版本**: 1.0.0
- **最后修改**: 2026-04-08
- **修改者**: 初始版本

## 角色定位

领域推理专家，结合形式推理（OWL/SHACL/SPARQL）和 LLM 软推理，
实现 *"LLM 提议，Reasoner 裁决，SHACL 把关，SPARQL 取证"* 的推理范式。

## 系统提示词

```
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
```

## 输入输出

### 输入
| 参数 | 类型 | 必选 | 说明 |
|------|------|------|------|
| question | str | 是 | 用户的自然语言问题 |
| ontology_graph | Graph | 是 | OWL 本体图 |
| knowledge_graph | Graph | 否 | 知识图谱 |
| shacl_shapes | Graph | 否 | SHACL 约束图 |
| ontology_spec | dict | 否 | 本体结构规范 |
| competency_questions | list | 否 | CQ 列表 |

### 输出
```json
{
  "reasoning_result": {
    "question": "用户的问题",
    "hard_reasoning": {
      "sparql_evidence": [{"sparql": "SELECT ...", "results": [...]}],
      "owl_inferences": ["OWL 推理新增 42 条三元组"],
      "shacl_issues": ["SHACL 验证通过"]
    },
    "soft_reasoning": {
      "hypotheses": ["假设1: ...", "假设2: ..."],
      "confidence": "high",
      "explanation": "基于 SPARQL 证据和 OWL 推理的综合分析..."
    },
    "final_answer": "综合结论",
    "uncertainty_notes": "不确定性说明"
  }
}
```

## 核心策略

### 四步推理管线
1. **OWL 推理闭包**: 在合并图上执行 OWL 2 RL 推理，补全隐含三元组
2. **SHACL 验证**: 检查推理后数据质量，发现约束违规
3. **SPARQL 取证**: LLM 根据问题和本体结构生成 1-3 条 SPARQL 查询，在推理图上执行
4. **LLM 软推理**: 将全部硬推理证据交给 LLM，完成假设生成、消歧和不确定性标注

### 推理原则
- 形式推理（硬推理）结果优先于 LLM 判断
- LLM 只处理形式推理无法覆盖的部分（假设、解释、消歧）
- 明确标注确定性和不确定性来源
- confidence 分级: high / medium / low

## 评估指标

| 指标 | 权重 | 说明 |
|------|------|------|
| SPARQL 生成质量 | 0.25 | 生成的 SPARQL 能成功执行并返回相关结果 |
| 硬推理利用率 | 0.25 | 最终答案引用了多少硬推理证据 |
| 结论准确性 | 0.3 | final_answer 与领域事实的一致性 |
| 不确定性标注质量 | 0.2 | 确定/推测结论的区分是否恰当 |

## 已知局限

- SPARQL 生成依赖 LLM，语法错误率不低
- OWL 2 RL 推理能力有限（非完全 OWL DL 推理）
- 软推理质量取决于 LLM 能力和上下文长度
- 缺乏对推理结果的自动验证机制

## 演化历史

| 日期 | 版本 | 修改内容 | 触发原因 | 效果 |
|------|------|---------|---------|------|
| 2026-04-08 | 1.0.0 | 初始版本 | - | - |
