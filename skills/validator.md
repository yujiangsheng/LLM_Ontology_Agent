# ValidatorAgent — 三类自动验证技能

## 元信息

- **智能体**: ValidatorAgent
- **模块**: agents/validator.py
- **版本**: 1.0.0
- **最后修改**: 2026-04-08
- **修改者**: 初始版本

## 角色定位

本体质量保证专家，执行三类形式化验证：OWL 推理一致性检查、SHACL 约束验证、
SPARQL Competency Question 回归测试。

## 系统提示词

```
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
只返回 JSON。
```

## 输入输出

### 输入
| 参数 | 类型 | 必选 | 说明 |
|------|------|------|------|
| ontology_graph | Graph | 是 | OWL 本体图 |
| competency_questions | list[dict] | 否 | CQ 列表，用于 SPARQL 回归 |
| ontology_spec | dict | 否 | 本体结构规范，用于生成 SHACL/SPARQL |
| knowledge_graph | Graph | 否 | 知识图谱，SHACL 验证目标 |

### 输出
```json
{
  "owl_reasoning_ok": true,
  "shacl_conforms": true,
  "shacl_report": "...",
  "sparql_results": [
    {"cq_id": "CQ1", "question": "...", "sparql": "...", "result_count": 5, "sample": [...]}
  ],
  "validation_summary": "=== 验证摘要 ===\nOWL: 通过\nSHACL: 通过\nSPARQL: 8/10 成功"
}
```

## 核心策略

1. **三管线并行**: OWL 推理 → SHACL 验证 → SPARQL CQ 回归
2. **OWL 2 RL 推理**: 使用 owlrl 做推理闭包，检测逻辑不一致
3. **LLM 生成 SHACL**: LLM 根据本体结构生成 SHACL NodeShape（minCount/maxCount）
4. **LLM 生成 SPARQL**: 将每个 CQ 翻译为 SPARQL SELECT 查询
5. **推理图查询**: SPARQL 优先在 OWL 推理后的合并图上执行
6. **产物保存**: SHACL Shapes 保存为 shacl_shapes.ttl

## 三类验证详解

### 1. OWL 推理一致性
- 合并 TBox + ABox → owlrl 推理闭包
- 检测是否有逻辑矛盾（owl:Nothing 非空等）

### 2. SHACL 约束验证
- LLM 根据本体结构生成 SHACL shapes
- 用 pyshacl 验证知识图谱数据质量
- 检查: 必填属性、基数约束、值类型

### 3. SPARQL CQ 回归
- LLM 将 CQ 翻译为 SPARQL 查询
- 在推理后的图上执行，验证本体可回答性
- 记录成功/失败数量和样例结果

## 评估指标

| 指标 | 权重 | 说明 |
|------|------|------|
| OWL 一致性通过率 | 0.25 | 推理无异常的比例 |
| SHACL 质量 | 0.25 | 生成的 SHACL shapes 有效且有意义 |
| SPARQL 执行成功率 | 0.3 | CQ 翻译为 SPARQL 后成功执行的比例 |
| SPARQL 非空结果率 | 0.2 | 成功执行的 SPARQL 返回非空结果的比例 |

## 已知局限

- SHACL shapes 质量完全依赖 LLM，可能过松或过严
- SPARQL 语法错误率较高（LLM 生成的 SPARQL 不总是合法的）
- OWL 推理在大图上可能较慢
- 缺乏对 SHACL 高级特性的支持（如 sh:pattern, sh:qualifiedValueShape）

## 演化历史

| 日期 | 版本 | 修改内容 | 触发原因 | 效果 |
|------|------|---------|---------|------|
| 2026-04-08 | 1.0.0 | 初始版本 | - | - |
