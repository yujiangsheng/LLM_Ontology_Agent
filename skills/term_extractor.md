# TermExtractorAgent — 领域术语抽取与类型判定技能

## 元信息

- **智能体**: TermExtractorAgent
- **模块**: agents/term_extractor.py
- **版本**: 1.0.0
- **最后修改**: 2026-04-08
- **修改者**: 初始版本

## 角色定位

领域本体术语抽取专家，识别文本中的关键术语并判定其在 OWL 本体中的角色
（Class / ObjectProperty / DataProperty / Individual）。

## 系统提示词

```
你是一位领域本体术语抽取专家。你的任务是从给定的领域文本中抽取本体术语，
并判定每个术语在本体中最可能扮演的角色。

对每个术语，输出以下字段：
- term: 术语名称（英文或中文均可，推荐以英文 CamelCase 作为 OWL 标识符）
- label_zh: 中文标签
- candidate_type: Class | ObjectProperty | DataProperty | Individual
- definition: 简短定义
- confidence: high | medium | low

请以 JSON 格式返回，格式为：
{
  "terms": [
    {"term": "...", "label_zh": "...", "candidate_type": "Class",
    "definition": "...", "confidence": "high"}
  ]
}
只返回 JSON，不要多余文字。
```

## 输入输出

### 输入
| 参数 | 类型 | 必选 | 说明 |
|------|------|------|------|
| domain_text | str | 是 | 领域文档原始文本（截取前6000字符） |
| competency_questions | list[dict] | 否 | CQAgent 的输出，用于指导抽取 |

### 输出
```json
{
  "terms": [
    {
      "term": "Device",
      "label_zh": "设备",
      "candidate_type": "Class",
      "definition": "工厂中需要被监控的物理实体",
      "confidence": "high"
    }
  ]
}
```

## 核心策略

1. **CamelCase 标识符**: 术语推荐用英文 CamelCase，兼容 OWL IRI
2. **四种类型判定**: Class（概念类）/ ObjectProperty（实体间关系）/ DataProperty（数据属性）/ Individual（实例）
3. **CQ 引导**: 若有 CQ，将其作为参考信息附加在 prompt 中，提高术语覆盖率
4. **置信度标注**: high / medium / low，供下游决策参考
5. **双语标签**: 同时输出英文 term 和中文 label_zh

## 评估指标

| 指标 | 权重 | 说明 |
|------|------|------|
| 术语覆盖率 | 0.3 | 文档中关键领域术语被抽取的比例 |
| 类型判定准确率 | 0.3 | 术语被正确分类为 Class/Property/Individual 的比例 |
| CQ 匹配率 | 0.2 | CQ 中 focus_concepts 在抽取术语中的命中率 |
| 冗余度 | 0.2 | 越少重复/近义术语越好 |

## 已知局限

- 文本截取前 6000 字符
- ObjectProperty 和 DataProperty 的区分容易混淆
- 个体实例 (Individual) 检测不稳定，取决于文本描述粒度

## 演化历史

| 日期 | 版本 | 修改内容 | 触发原因 | 效果 |
|------|------|---------|---------|------|
| 2026-04-08 | 1.0.0 | 初始版本 | - | - |
