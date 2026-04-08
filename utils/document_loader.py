"""
document_loader — 多格式文档加载器
====================================

根据文件后缀自动选择读取策略，将 ``.txt`` / ``.md`` / ``.csv`` /
``.docx`` / ``.pdf`` 等常见文档统一转为纯文本字符串，供下游 Agent 消费。

支持的格式
----------
=========  ==================  =================
后缀       依赖                说明
=========  ==================  =================
.txt .md   无                  UTF-8 直接读取
.csv       无                  UTF-8 直接读取
.json      无                  UTF-8 直接读取
.jsonl     无                  UTF-8 直接读取
.ttl       无                  Turtle RDF 直接读取
.sparql    无                  SPARQL 查询直接读取
.docx      python-docx         段落拼接
.pdf       PyMuPDF (fitz)      逐页提取文字
=========  ==================  =================

Usage Example::

    from utils.document_loader import load_text

    # 自动检测格式
    text = load_text("report.docx")
    text = load_text("notes.md")

    # 文件不存在会抛 FileNotFoundError
    # 不支持的后缀会回退到 UTF-8 纯文本读取

作者: Jiangsheng Yu
许可: MIT License
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

# 可直接以 UTF-8 读取的纯文本后缀
_PLAIN_TEXT_EXTS = frozenset((".txt", ".md", ".csv", ".json", ".jsonl", ".ttl", ".sparql"))


def load_text(path: str) -> str:
    """根据文件后缀自动选择读取方式，返回纯文本。

    Parameters
    ----------
    path : str
        文件路径（相对或绝对均可）。

    Returns
    -------
    str
        文件的纯文本内容。

    Raises
    ------
    FileNotFoundError
        文件不存在时抛出。
    """
    if not os.path.isfile(path):
        raise FileNotFoundError(f"文件不存在: {path}")

    ext = os.path.splitext(path)[1].lower()
    logger.info("加载文档: %s (类型=%s)", path, ext or "unknown")

    if ext in _PLAIN_TEXT_EXTS:
        with open(path, encoding="utf-8") as f:
            return f.read()
    if ext == ".docx":
        return _load_docx(path)
    if ext == ".pdf":
        return _load_pdf(path)

    # 兜底：按 UTF-8 尝试读取
    logger.warning("未识别的文件后缀 '%s'，尝试按 UTF-8 读取", ext)
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


# ── 私有加载函数 ──────────────────────────────────────────────

def _load_docx(path: str) -> str:
    """提取 .docx 全部段落文本（跳过空行）。"""
    from docx import Document

    doc = Document(path)
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


def _load_pdf(path: str) -> str:
    """逐页提取 .pdf 文字内容（需安装 PyMuPDF）。"""
    import fitz  # PyMuPDF

    text_parts: list[str] = []
    with fitz.open(path) as pdf:
        for page in pdf:
            text_parts.append(page.get_text())
    return "\n".join(text_parts)
