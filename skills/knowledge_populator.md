# KnowledgePopulatorAgent — 知识图谱实例填充技能

## 元信息

- **智能体**: KnowledgePopulatorAgent
- **模块**: agents/knowledge_populator.py
- **版本**: **版本**: .1.1
- **最后修改**: 2026-04-08
- **修改者**: PrefrontalLobe 自动演化

## 角色定位

领域知识抽取专家，根据 OWL 本体结构（TBox）从领域文本中抽取具体实例
（ABox Individual），包括个体属性值和个体间关系，构建 RDF 知识图谱。

## 系统提示词

```
你是领域知识抽取专家。根据下面的本体结构（类和属性）和领域文本，
抽取出所有具体的实例（Individual）及其属性值。

请基于提供的本体结构和领域文本，使用你的语言理解能力进行知识抽取。
例如，如果文本提到某传感器具有温度属性，则应将其作为 Sensor 类型的个体抽取。

输出 JSON 格式：
{
  "individuals": [
    {
      "id": "sensor_001",
      "type": "Sensor",
      "properties": {
        "hasTemperature": 85.5,
        "belongsTo": "device_A"
      },
      "label": "温度传感器 001"
    }
  ],
  "relations": [
    {"subject": "device_A", "predicate": "hasSensor", "object": "sensor_001"}
  ]
}
只返回 JSON。
```

## 输入输出

### 输入
| 参数 | 类型 | 必选 | 说明 |
|------|------|------|------|
| domain_text | str | 是 | 领域文档原始文本（截取前6000字符） |
| ontology_spec | dict | 是 | OntologyBuilderAgent 输出的本体规范 |
| ontology_graph | Graph | 否 | OWL 本体图，合并到输出图使 KG 自包含 |

### 输出
```json
{
  "knowledge_graph": "rdflib.Graph 对象",
  "knowledge_path": "output/knowledge_graph.ttl",
  "individuals_count": 15,
  "relations_count": 23,
  "kg_data": {"individuals": [...], "relations": [...]}
}
```

## 核心策略

1. **本体结构引导**: 将 ontology_spec 转为可读文本，指导 LLM 按正确类型抽取
2. **实例 ID 智能引用**: 维护 all_ids 集合，自动判断属性值是 Entity 引用还是 Literal
3. **TBox 合并**: 输出 KG 自动合并 TBox，使图自包含
4. **显式关系**: 除属性外，单独定义 subject-predicate-object 三元组
5. **安全标识符**: 所有 ID 和名称经过 `_safe()` 处理，保证 IRI 合法
6. **执行监控**: 记录每次知识抽取的执行时间（execution_time_s），若时间为 0 则记录警告日志并触发重试机制
6. **输出结构验证**: 在返回前校验 knowledge_graph、knowledge_path 等字段是否存在且格式正确，确保下游处理流程稳定

## 评估指标

| 指标 | 权重 | 说明 |
|------|------|------|
| 实例完整性 | 0.3 | 文档中可识别的实例被正确抽取的比例 |
| 关系准确性 | 0.3 | 抽取的关系是否符合本体定义的 domain/range |
| 属性类型正确性 | 0.2 | 数据属性值类型与本体 range 匹配率 |
| 去重率 | 0.1 | 同一实体是否被重复抽取 |
| KG 可查询性 | 0.1 | SPARQL 查询能返回有意义结果的比例 |

## 已知局限

- 文本截取前 6000 字符
- Entity 引用判断基于 ID 精确匹配，别名/简称可能漏检
- 数值型属性需 LLM 正确输出数值类型（有时会输出字符串）
- 缺乏实例去重和共指消解能力

## 演化历史

| 日期 | 版本 | 修改内容 | 触发原因 | 效果 |
|------|------|---------|---------|------|
| 2026-04-08 | 1.0.0 | 初始版本 | - | - |
| 2026-04-08 | ?.?.? | prompt_rewrite: 在提示词中加入明确指令如：'请基于提供的本体结构和领域文本，使用你的语言理解能力 | 自动诊断 | 待验证 |
| 2026-04-08 | ?.?.? | strategy_add: 增加输出校验逻辑，确保返回字段如 knowledge_graph、knowled | 自动诊断 | 待验证 |
| 2026-04-08 | ?.?.? | strategy_add: 增加执行时间监控与异常日志记录，若 execution_time_s 为 0，则 | 自动诊断 | 待验证 |
