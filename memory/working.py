"""
memory.working — 工作记忆（会话级短期上下文）
==============================================

工作记忆类似于人类的短期记忆 / "心理白板"，用于在一次会话
（build 或 reason 流程）内维护:

- **对话历史** — 最近 N 轮 LLM 交互记录（自动滑动窗口）
- **中间产物摘要** — 每步 Agent 产出的关键信息摘要
- **当前焦点** — 当前任务描述、活跃实体 / 概念

特性:
  - 容量有限，自动淘汰最早条目（滑动窗口）
  - 会话结束后自动清空
  - 支持按 tag 筛选（如 ``"reasoning"``, ``"validation"``）

作者: Jiangsheng Yu
许可: MIT License
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class MemoryEntry:
    """工作记忆中的单条记录。"""

    content: str
    role: str = "system"          # system / user / assistant / agent
    tag: str = ""                 # 自定义标签，用于分类筛选
    agent_name: str = ""          # 产生此条目的 Agent
    timestamp: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)


class WorkingMemory:
    """会话级工作记忆 — 滑动窗口管理。

    Parameters
    ----------
    max_entries : int
        最大条目数，超出后淘汰最早的条目。
    max_tokens_estimate : int
        Token 粗估上限（按 1 字 ≈ 1.5 token 估算），超出后淘汰最早条目。
    """

    def __init__(
        self,
        max_entries: int = 50,
        max_tokens_estimate: int = 8000,
    ):
        self._entries: list[MemoryEntry] = []
        self.max_entries = max_entries
        self.max_tokens_estimate = max_tokens_estimate
        self._focus: str = ""

    # ── 写入 ────────────────────────────────────────────────

    def add(
        self,
        content: str,
        *,
        role: str = "system",
        tag: str = "",
        agent_name: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """添加一条记忆并自动执行容量控制。"""
        entry = MemoryEntry(
            content=content,
            role=role,
            tag=tag,
            agent_name=agent_name,
            metadata=metadata or {},
        )
        self._entries.append(entry)
        self._evict()

    def set_focus(self, focus: str) -> None:
        """设置当前任务焦点描述。"""
        self._focus = focus

    # ── 读取 ────────────────────────────────────────────────

    @property
    def focus(self) -> str:
        return self._focus

    @property
    def entries(self) -> list[MemoryEntry]:
        return list(self._entries)

    def recent(self, n: int = 10) -> list[MemoryEntry]:
        """返回最近 *n* 条记录。"""
        return self._entries[-n:]

    def by_tag(self, tag: str) -> list[MemoryEntry]:
        """返回指定标签的所有条目。"""
        return [e for e in self._entries if e.tag == tag]

    def by_agent(self, agent_name: str) -> list[MemoryEntry]:
        """返回指定 Agent 产生的所有条目。"""
        return [e for e in self._entries if e.agent_name == agent_name]

    def to_messages(self, n: int | None = None) -> list[dict[str, str]]:
        """将最近 *n* 条记录转为 LLM messages 格式。"""
        subset = self._entries[-n:] if n else self._entries
        return [{"role": e.role, "content": e.content} for e in subset]

    def summarize(self) -> str:
        """生成工作记忆摘要文本（用于注入 prompt）。"""
        lines: list[str] = []
        if self._focus:
            lines.append(f"当前焦点: {self._focus}")
        for e in self._entries[-10:]:
            prefix = f"[{e.agent_name}]" if e.agent_name else f"[{e.role}]"
            # 截取前 200 字符避免过长
            text = e.content[:200] + ("..." if len(e.content) > 200 else "")
            lines.append(f"{prefix} {text}")
        return "\n".join(lines)

    # ── 生命周期 ────────────────────────────────────────────

    def clear(self) -> None:
        """清空工作记忆（会话结束时调用）。"""
        self._entries.clear()
        self._focus = ""

    def __len__(self) -> int:
        return len(self._entries)

    # ── 内部 ────────────────────────────────────────────────

    def _evict(self) -> None:
        """容量控制: 超出条目数或 token 估算上限时淘汰最早条目。"""
        # 条目数控制
        while len(self._entries) > self.max_entries:
            self._entries.pop(0)

        # Token 粗估控制
        while self._estimate_tokens() > self.max_tokens_estimate and len(self._entries) > 1:
            self._entries.pop(0)

    def _estimate_tokens(self) -> int:
        """按 1 字 ≈ 1.5 token 粗略估算总 token 数。"""
        total_chars = sum(len(e.content) for e in self._entries)
        return int(total_chars * 1.5)
