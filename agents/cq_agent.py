"""
cq_agent — Competency Questions 提炼智能体
=============================================

从领域文档中自动提炼 **Competency Questions (CQ)**，即一份本体
应当能够回答的业务问题清单。CQ 是本体开发中的核心对象 [1]_，
决定了后续术语抽取和 OWL 建模的范围与粒度。

输出格式::

    {
      "competency_questions": [
        {
          "id": "CQ1",
          "question": "哪些设备处于过热风险？",
          "focus_concepts": ["Device", "OverheatAlarm"],
          "expected_answer_type": "list"
        },
        ...
      ]
    }

.. [1] arXiv:2409.08820 — RAG + LLM for CQ generation in ontology development.

作者: Jiangsheng Yu
许可: MIT License
"""
from __future__ import annotations

from typing import Any

from agents.base_agent import BaseAgent

# 系统提示词 —— 指导 LLM 以本体工程视角提炼 CQ
SYSTEM = """\
你是一位本体工程专家。你的任务是从用户提供的领域文档片段中提炼出高质量的
"Competency Questions (CQ)"，即一份本体应该能够回答的业务问题清单。

每个 CQ 应该：
1. 聚焦于领域核心概念和关系
2. 可以用 SPARQL 在知识图谱上回答
3. 明确、无歧义

请以 JSON 格式返回，格式为：
{
  "competency_questions": [
    {"id": "CQ1", "question": "...", "focus_concepts": ["概念A","概念B"], \
"expected_answer_type": "list|boolean|count|description"}
  ]
}
只返回 JSON，不要多余文字。"""


class CQAgent(BaseAgent):
    """Competency Questions 提炼智能体。

    从领域文档中提炼 10-20 个高质量的业务问题，用于指导后续
    术语抽取、本体建模和 SPARQL 回归测试。
    """

    name = "CQAgent"

    def __init__(self):
        super().__init__(system_prompt=SYSTEM)

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        """执行 CQ 提炼。

        Parameters
        ----------
        context : dict
            必须包含 ``domain_text`` (str)；
            可选 ``domain_name`` (str, 默认 ``"未知领域"``)。

        Returns
        -------
        dict
            ``{"competency_questions": [...]}``.
        """
        domain_text = context["domain_text"]
        domain_name = context.get("domain_name", "未知领域")

        prompt = (
            f"领域名称：{domain_name}\n\n"
            f"请根据以下领域文档内容，提炼 10-20 个 Competency Questions：\n\n"
            f"---\n{domain_text[:6000]}\n---"
        )
        return self.ask_json(prompt)
