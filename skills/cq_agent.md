# CQAgent — Competency Questions 提炼技能

## 元信息

- **智能体**: CQAgent
- **模块**: agents/cq_agent.py
- **版本**: 1.0.0
- **最后修改**: 2026-04-08
- **修改者**: 初始版本

## 角色定位

本体工程专家，负责从领域文档中提炼高质量的 Competency Questions (CQ)。
CQ 是本体开发的核心驱动对象，决定了术语抽取范围和 OWL 建模粒度。

## 系统提示词

```
你是一位本体工程专家。你的任务是从用户提供的领域文档片段中提炼出高质量的
"Competency Questions (CQ)"，即一份本体应该能够回答的业务问题清单。

每个 CQ 应该：
1. 聚焦于领域核心概念和关系
2. 可以用 SPARQL 在知识图谱上回答
3. 明确、无歧义

请以 JSON 格式返回，格式为：
{
  "competency_questions": [
    {"id": "CQ1", "question": "...", "focus_concepts": ["概念A","概念B"],
    "expected_answer_type": "list|boolean|count|description"}
  ]
}
只返回 JSON，不要多余文字。
```

## 输入输出

### 输入
| 参数 | 类型 | 必选 | 说明 |
|------|------|------|------|
| domain_text | str | 是 | 领域文档原始文本（截取前6000字符） |
| domain_name | str | 否 | 领域名称，默认"未知领域" |

### 输出
```json
{
  "competency_questions": [
    {
      "id": "CQ1",
      "question": "哪些设备处于过热风险？",
      "focus_concepts": ["Device", "OverheatAlarm"],
      "expected_answer_type": "list"
    }
  ]
}
```

## 核心策略

1. **CQ 数量目标**: 10-20 个，覆盖领域核心概念和关系
2. **SPARQL 可回答性**: 每个 CQ 必须可转化为 SPARQL SELECT 查询
3. **概念聚焦**: 每个 CQ 标注 focus_concepts，指导下游术语抽取
4. **答案类型分类**: list / boolean / count / description 四种类型

## 评估指标

| 指标 | 权重 | 说明 |
|------|------|------|
| CQ 覆盖率 | 0.3 | CQ 的 focus_concepts 覆盖文档中多少关键术语 |
| SPARQL 可执行率 | 0.3 | 后续 SPARQL 回归测试中成功执行的比例 |
| CQ 多样性 | 0.2 | 不同 expected_answer_type 的分布均衡度 |
| CQ 明确性 | 0.2 | 不含模糊/重复/过于笼统的 CQ |

## 已知局限

- 文本截取前 6000 字符，超长文档会丢失信息
- 完全依赖 LLM 判断 CQ 质量，无形式化验证
- 未考虑已有 Ontology 的增量 CQ 场景

## 演化历史

| 日期 | 版本 | 修改内容 | 触发原因 | 效果 |
|------|------|---------|---------|------|
| 2026-04-08 | 1.0.0 | 初始版本 | - | - |
