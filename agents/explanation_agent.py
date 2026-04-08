"""
explanation_agent — 推理结果自然语言翻译智能体
==============================================

将 ReasoningAgent 产出的结构化推理报告（JSON）翻译为业务人员和
工程师能直接理解并采取行动的 Markdown 文档。

翻译原则:
  1. **结论先行** — 先给结果，再给证据
  2. **确定性标注** — 区分 "确定结论"（形式推理）与 "推测性结论"（LLM 软推理）
  3. **数据质量** — 如有 SHACL 违规等数据质量问题，明确指出
  4. **可操作建议** — 给出下一步行动建议

输入: ``reasoning_result`` (dict) + ``question`` (str)
输出: ``explanation`` (str, Markdown 格式)

作者: Jiangsheng Yu
许可: MIT License
"""
from __future__ import annotations

import json
from typing import Any

from agents.base_agent import BaseAgent

# LLM 系统提示词
SYSTEM = """\
你是领域知识解释专家。你的任务是将形式推理和分析结果翻译成
业务人员和工程师能直接理解并采取行动的自然语言解释。

要求：
1. 结论先行，再给证据
2. 区分"确定结论"和"推测性结论"
3. 如果有数据质量问题，明确指出
4. 给出可操作的建议

输出格式（纯文本，使用 Markdown）。"""


class ExplanationAgent(BaseAgent):
    """推理结果自然语言翻译智能体。

    将 JSON 格式的推理报告转化为结构清晰、可操作的 Markdown 文档，
    面向业务人员和领域工程师。
    """

    name = "ExplanationAgent"

    def __init__(self):
        super().__init__(system_prompt=SYSTEM)

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        """将推理报告翻译为 Markdown 解释。

        Parameters
        ----------
        context : dict
            必须包含 ``reasoning_result`` (dict) 和 ``question`` (str)。

        Returns
        -------
        dict
            ``{"explanation": "..."}`` — Markdown 格式的自然语言解释。
        """
        reasoning = context.get("reasoning_result", {})
        question = context.get("question", "")

        prompt = (
            f"用户问题：{question}\n\n"
            f"推理分析结果：\n{json.dumps(reasoning, ensure_ascii=False, indent=2)}\n\n"
            f"请将上述推理结果翻译为业务人员能理解的 Markdown 报告。"
        )
        explanation = self.ask(prompt)
        return {"explanation": explanation}
