"""
term_extractor — 领域术语抽取与类型判定智能体
===============================================

从领域文本中抽取关键术语，并判定每个术语在 OWL 本体中最可能
扮演的角色（Class / ObjectProperty / DataProperty / Individual）。

输出格式::

    {
      "terms": [
        {
          "term": "Device",
          "label_zh": "设备",
          "candidate_type": "Class",
          "definition": "工厂中需要被监控的物理实体",
          "confidence": "high"
        },
        ...
      ]
    }

作者: Jiangsheng Yu
许可: MIT License
"""
from __future__ import annotations

from typing import Any

from agents.base_agent import BaseAgent

SYSTEM = """\
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
    {"term": "...", "label_zh": "...", "candidate_type": "Class", \
"definition": "...", "confidence": "high"}
  ]
}
只返回 JSON，不要多余文字。"""


class TermExtractorAgent(BaseAgent):
    """领域术语抽取与类型判定智能体。

    从领域文本中识别所有与本体相关的概念、关系和实例术语，
    并附带中文标签、类型判定和置信度。
    """

    name = "TermExtractorAgent"

    def __init__(self):
        super().__init__(system_prompt=SYSTEM)

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        """执行术语抽取。

        Parameters
        ----------
        context : dict
            必须包含 ``domain_text`` (str)；
            可选 ``competency_questions`` (list[dict], 来自 CQAgent)。

        Returns
        -------
        dict
            ``{"terms": [...]}``.
        """
        domain_text = context["domain_text"]
        cqs = context.get("competency_questions", [])

        # 如果有 CQ，附带作为参考信息
        cq_str = ""
        if cqs:
            cq_items = cqs if isinstance(cqs, list) else cqs.get("competency_questions", [])
            cq_str = "\n".join(f"- {q.get('question', q)}" for q in cq_items)
            cq_str = f"\n\n参考 Competency Questions：\n{cq_str}"

        prompt = (
            f"请从以下领域文档中抽取所有关键术语，并判定其本体类型。\n"
            f"注意也要抽取关系型术语（作为 ObjectProperty / DataProperty）。\n"
            f"{cq_str}\n\n"
            f"---\n{domain_text[:6000]}\n---"
        )
        return self.ask_json(prompt)
