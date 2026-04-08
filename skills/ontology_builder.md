# OntologyBuilderAgent — OWL 本体构建技能

## 元信息

- **智能体**: OntologyBuilderAgent
- **模块**: agents/ontology_builder.py
- **版本**: 1.0.0
- **最后修改**: 2026-04-08
- **修改者**: 初始版本

## 角色定位

本体建模专家，根据术语列表和 CQ 设计 OWL 2 本体结构（类层级、属性、公理），
并使用 rdflib 构建为符合 OWL 语义的 RDF 图。

## 系统提示词

```
你是本体建模专家。你需要根据已抽取的术语列表和 Competency Questions，
设计类的层级关系（subClassOf）、对象属性（domain/range）和数据属性。
还需要生成关键的 OWL 公理（如等价类、属性限制等）。

请以 JSON 格式返回：
{
  "classes": [
    {"name": "DeviceName", "parent": null, "label_zh": "...", "comment": "..."}
  ],
  "object_properties": [
    {"name": "hasSensor", "domain": "Device", "range": "Sensor", "label_zh": "..."}
  ],
  "data_properties": [
    {"name": "hasTemperature", "domain": "Sensor", "range": "xsd:float", "label_zh": "..."}
  ],
  "axioms": [
    {"description": "...", "type": "subclass_restriction", "class": "OverheatRiskDevice",
     "equivalent_to": "Device and (emitsAlarm some OverheatAlarm)"}
  ]
}
只返回 JSON。
```

## 输入输出

### 输入
| 参数 | 类型 | 必选 | 说明 |
|------|------|------|------|
| terms | list[dict] | 是 | TermExtractorAgent 输出的术语列表 |
| competency_questions | list[dict] | 是 | CQAgent 输出的 CQ 列表 |
| domain_name | str | 否 | 领域名称，默认"domain" |

### 输出
```json
{
  "ontology_graph": "rdflib.Graph 对象",
  "ontology_path": "output/xxx_ontology.owl",
  "ontology_spec": {
    "classes": [...],
    "object_properties": [...],
    "data_properties": [...],
    "axioms": [...]
  }
}
```

## 核心策略

1. **LLM 草案 + 代码构建**: LLM 产出 JSON 规范，Python 代码保证 OWL 语法正确
2. **按模块生成**: 分别处理 classes / object_properties / data_properties / axioms
3. **等价类公理解析**: 自动解析 `"X and (P some Y)"` 模式为 `owl:equivalentClass` + `owl:Restriction`
4. **XSD 数据类型映射**: 支持 xsd:string/float/double/integer/boolean/dateTime/date
5. **双格式输出**: 同时保存 RDF/XML (.owl) 和 Turtle (.ttl)
6. **类层级**: 通过 parent 字段构建 rdfs:subClassOf 层级

## 评估指标

| 指标 | 权重 | 说明 |
|------|------|------|
| OWL 一致性 | 0.3 | OWL 推理是否无矛盾 |
| 术语覆盖率 | 0.25 | 抽取的术语被本体结构覆盖的比例 |
| 公理丰富度 | 0.2 | 生成有意义的 OWL 公理数量 |
| 结构合理性 | 0.15 | 类层级深度合理、属性 domain/range 正确 |
| SPARQL 可查询性 | 0.1 | 生成的本体结构能支持多少 CQ 转为 SPARQL |

## 已知局限

- 公理解析仅支持 `"X and (P some Y)"` 模式，复杂 DL 表达式不支持
- LLM 有时会生成不合法的类名（含空格/特殊字符）
- 对 OWL 2 高级特性（如 disjointWith, propertyChain）支持有限

## 演化历史

| 日期 | 版本 | 修改内容 | 触发原因 | 效果 |
|------|------|---------|---------|------|
| 2026-04-08 | 1.0.0 | 初始版本 | - | - |
