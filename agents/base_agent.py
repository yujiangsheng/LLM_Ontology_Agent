"""
base_agent — 所有 Agent 的公共基类
====================================

定义了 Agent 的通用接口和 LLM 交互快捷方法。每个具体 Agent
继承 :class:`BaseAgent`，设置自己的 ``name`` 和 ``system_prompt``，
然后实现 :meth:`run` 方法即可。

所有 Agent 共享同一个 :class:`~memory.manager.MemoryManager` 实例
（通过 ``memory`` 属性访问），可以在执行过程中读写记忆。

典型用法::

    class MyAgent(BaseAgent):
        name = "MyAgent"

        def __init__(self):
            super().__init__(system_prompt="你是...")

        def run(self, context):
            # 从记忆中获取相关上下文
            mem_ctx = self.recall("当前任务关键词")
            result = self.ask_json(f"记忆上下文:\n{mem_ctx}\n\n请做...")
            # 将关键结论写入记忆
            self.memorize("发现了重要模式 X", layer="long_term", category="reasoning")
            return result

作者: Jiangsheng Yu
许可: MIT License
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import llm_client

if TYPE_CHECKING:
    from memory.manager import MemoryManager

logger = logging.getLogger(__name__)

# 全局共享的 MemoryManager 实例（由 Orchestrator 初始化后注入）
_shared_memory: MemoryManager | None = None


def set_shared_memory(manager: MemoryManager) -> None:
    """设置全局共享的 MemoryManager（由 Orchestrator 调用）。"""
    global _shared_memory
    _shared_memory = manager


def get_shared_memory() -> MemoryManager | None:
    """获取全局共享的 MemoryManager。"""
    return _shared_memory


class BaseAgent:
    """所有 Agent 的公共基类。

    Attributes
    ----------
    name : str
        Agent 名称，用于日志标识。
    system_prompt : str
        发送给 LLM 的 system 角色提示词。
    memory : MemoryManager | None
        全局共享的记忆管理器实例。
    """

    name: str = "BaseAgent"

    def __init__(self, system_prompt: str = ""):
        self.system_prompt = system_prompt

    @property
    def memory(self) -> MemoryManager | None:
        """访问全局共享的记忆管理器。"""
        return _shared_memory

    # ── 记忆快捷方法 ──────────────────────────────────────────

    def recall(self, query: str, **kwargs) -> str:
        """从记忆系统检索与 query 相关的上下文（快捷方法）。

        返回格式化文本，可直接拼入 prompt。
        """
        if not self.memory:
            return ""
        return self.memory.get_context_for_agent(self.name, query, **kwargs)

    def memorize(self, content: str, *, layer: str = "working", **kwargs) -> None:
        """将信息写入指定记忆层（快捷方法）。"""
        if not self.memory:
            return
        if layer == "working":
            kwargs.setdefault("agent_name", self.name)
        elif layer in ("long_term",):
            kwargs.setdefault("source_agent", self.name)
        elif layer == "experience":
            kwargs.setdefault("agent_name", self.name)
        self.memory.memorize(content, layer=layer, **kwargs)

    # ── LLM 快捷方法 ──────────────────────────────────────────

    def ask(self, prompt: str, *, use_memory: bool = False, **kwargs) -> str:
        """向 LLM 发送纯文本问答请求，返回回复文本。

        Parameters
        ----------
        use_memory : bool
            若 True，自动将记忆上下文注入 prompt 前缀。
        """
        if use_memory:
            prompt = self._inject_memory(prompt)
        logger.info("[%s] ask  (len=%d)", self.name, len(prompt))
        resp = llm_client.chat(prompt, system=self.system_prompt, **kwargs)
        logger.info("[%s] resp (len=%d)", self.name, len(resp))
        # 记录到工作记忆
        self.memorize(f"Q: {prompt[:200]}...\nA: {resp[:200]}...", tag="llm_call")
        return resp

    def ask_json(self, prompt: str, *, use_memory: bool = False, **kwargs) -> dict | list:
        """向 LLM 发送请求并自动解析 JSON 返回值。

        Parameters
        ----------
        use_memory : bool
            若 True，自动将记忆上下文注入 prompt 前缀。
        """
        if use_memory:
            prompt = self._inject_memory(prompt)
        logger.info("[%s] ask_json (len=%d)", self.name, len(prompt))
        resp = llm_client.chat_json(prompt, system=self.system_prompt, **kwargs)
        logger.info(
            "[%s] resp_json keys=%s",
            self.name,
            list(resp.keys()) if isinstance(resp, dict) else f"list[{len(resp)}]",
        )
        return resp

    # ── 子类实现的入口 ────────────────────────────────────────

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        """Agent 执行入口（子类必须实现）。

        Parameters
        ----------
        context : dict[str, Any]
            上游传递的共享上下文。

        Returns
        -------
        dict[str, Any]
            本 Agent 的执行产出，会被合并回共享上下文。
        """
        raise NotImplementedError(f"{self.name}.run() 未实现")

    # ── 内部辅助 ──────────────────────────────────────────────

    def _inject_memory(self, prompt: str) -> str:
        """将记忆上下文注入 prompt 前缀。"""
        mem_ctx = self.recall(prompt[:200])  # 用 prompt 前 200 字作为检索 query
        if mem_ctx:
            return f"<memory_context>\n{mem_ctx}\n</memory_context>\n\n{prompt}"
        return prompt
