#!/usr/bin/env python3
"""
LLM + Ontology 多智能体系统 — 命令行入口
==========================================

使用本地 qwen3-coder:30b (Ollama) 作为 LLM 后端，实现领域 Ontology 抽取
和基于 Ontology + 知识图谱的领域推理。内置四层记忆系统和元认知自我演化。

子命令:
  build        从领域文档构建 OWL 本体 + 知识图谱 + 自动验证
  reason       加载已有本体后推理（等价于 ask）
  interactive  先构建再进入交互推理 REPL
  ask          快速问答（加载已有产物）
  memory       查看记忆系统统计信息
  add-doc      将文档加入 RAG 外部记忆索引
  evolve       构建后执行元认知自我演化

快速上手::

  # 1. 构建本体 + 知识图谱
  python main.py build test_domain.txt --domain "设备故障诊断"

  # 2. 推理问答
  python main.py ask "哪些设备存在过热风险？"

  # 3. 交互模式 (构建 → REPL 循环)
  python main.py interactive test_domain.txt --domain "设备故障诊断"

  # 4. 添加 RAG 参考文档
  python main.py add-doc reference_manual.txt

  # 5. 查看记忆统计
  python main.py memory

  # 6. 元认知自我演化
  python main.py evolve test_domain.txt --domain "设备故障诊断"

  # 7. 启动 Web 界面
  python main.py web
  python main.py web --port 8080

  # 8. 启用调试日志
  python main.py -v build test_domain.txt

作者: Jiangsheng Yu
许可: MIT License
"""
from __future__ import annotations

import argparse
import json
import logging
import sys

from agents.orchestrator import Orchestrator
from utils.document_loader import load_text

__version__ = "0.1.0"


def setup_logging(verbose: bool = False) -> None:
    """初始化全局日志配置。"""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    # 降低第三方库日志噪音
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("rdflib").setLevel(logging.WARNING)


def cmd_build(args: argparse.Namespace) -> None:
    """子命令: build — 从领域文档构建 Ontology + 知识图谱。"""
    orch = Orchestrator()
    text = load_text(args.file)
    orch.build_ontology(text, domain_name=args.domain)
    orch.end_session()


def cmd_reason(args: argparse.Namespace) -> None:
    """子命令: reason — 加载已有产物后推理。"""
    orch = Orchestrator()
    orch.load_from_output()
    orch.reason(args.question)
    orch.end_session()


def cmd_interactive(args: argparse.Namespace) -> None:
    """子命令: interactive — 构建后进入交互推理 REPL。"""
    orch = Orchestrator()
    text = load_text(args.file)
    orch.build_ontology(text, domain_name=args.domain)

    print("\n进入交互推理模式 (quit 退出 | memory 记忆统计 | evolve 自我演化)\n")
    while True:
        try:
            question = input("❓ 请输入问题: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not question or question.lower() in ("quit", "exit", "q"):
            break
        if question.lower() == "memory":
            _show_memory_stats(orch)
            continue
        if question.lower() == "evolve":
            orch.evolve()
            continue
        orch.reason(question)

    orch.end_session()


def cmd_ask(args: argparse.Namespace) -> None:
    """子命令: ask — 快速问答（等同于 reason）。"""
    orch = Orchestrator()
    orch.load_from_output()
    orch.reason(args.question)
    orch.end_session()


def cmd_memory(args: argparse.Namespace) -> None:
    """子命令: memory — 查看记忆系统统计信息。"""
    orch = Orchestrator()
    orch.memory.load_ontology_from_files()
    _show_memory_stats(orch)


def cmd_add_doc(args: argparse.Namespace) -> None:
    """子命令: add-doc — 将文档加入 RAG 外部记忆索引。"""
    orch = Orchestrator()
    count = orch.add_document(args.file)
    print(f"✓ 已将 {args.file} 加入 RAG 索引 (新增 {count} 块)")


def cmd_evolve(args: argparse.Namespace) -> None:
    """子命令: evolve — 构建后执行元认知自我演化。"""
    orch = Orchestrator()
    text = load_text(args.file)
    orch.build_ontology(text, domain_name=args.domain)
    orch.evolve()
    orch.end_session()


def cmd_web(args: argparse.Namespace) -> None:
    """子命令: web — 启动 Web 界面。"""
    from web_server import run_server
    run_server(host=args.host, port=args.port)


def _show_memory_stats(orch: Orchestrator) -> None:
    """打印详细的记忆统计信息。"""
    stats = orch.memory.stats()
    print(f"\n{'=' * 50}")
    print("📊 记忆系统统计")
    print(f"{'=' * 50}")
    print(f"  工作记忆:   {stats['working_entries']} 条")
    if stats['working_focus']:
        print(f"    焦点:     {stats['working_focus']}")
    print(f"  长期记忆:   {stats['long_term_entries']} 条")
    print(f"  经验库:     {stats['experiences']} 条")
    print(f"  知识库:     {stats['knowledge_facts']} 条")
    print(f"  Ontology:   {'已加载' if stats['has_ontology'] else '未加载'}")
    print(f"  RAG 索引:   {stats['rag_chunks']} 块")
    if stats['rag_sources']:
        print(f"    来源:     {', '.join(stats['rag_sources'][:5])}")
    print(f"{'=' * 50}")


def main() -> None:
    """解析命令行参数并分发至对应子命令。"""
    parser = argparse.ArgumentParser(
        prog="ontology-agent",
        description="LLM + Ontology 多智能体系统 — 领域本体抽取与知识推理（带四层记忆 & 元认知演化）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "快速上手:\n"
            "  %(prog)s build domain.txt --domain '设备故障诊断'   构建本体+KG\n"
            "  %(prog)s ask '哪些设备过热？'                       推理问答\n"
            "  %(prog)s interactive domain.txt --domain '设备故障'  交互模式\n"
            "  %(prog)s evolve domain.txt --domain '设备故障'       元认知演化\n"
            "  %(prog)s web                                       启动 Web 界面\n"
            "\n"
            "详细文档: README.md | 配置: config.py | 许可: MIT"
        ),
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="显示调试日志 (DEBUG 级别)")
    parser.add_argument("-V", "--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", title="子命令")

    # build
    p_build = sub.add_parser("build", help="从领域文档构建 OWL 本体 + 知识图谱 + 自动验证")
    p_build.add_argument("file", help="领域文档路径 (.txt/.md/.docx/.pdf)")
    p_build.add_argument("--domain", default="domain", help="领域名称 (默认: domain)")

    # reason
    p_reason = sub.add_parser("reason", help="基于已有本体进行推理问答")
    p_reason.add_argument("question", help="推理问题 (自然语言)")

    # interactive
    p_inter = sub.add_parser("interactive", help="构建后进入交互推理 REPL 模式")
    p_inter.add_argument("file", help="领域文档路径")
    p_inter.add_argument("--domain", default="domain", help="领域名称 (默认: domain)")

    # ask
    p_ask = sub.add_parser("ask", help="快速问答 (加载 output/ 中的已有产物)")
    p_ask.add_argument("question", help="推理问题 (自然语言)")

    # memory
    sub.add_parser("memory", help="查看四层记忆系统统计信息")

    # add-doc
    p_doc = sub.add_parser("add-doc", help="将文档加入 RAG 外部记忆索引 (支持 .txt/.md/.docx)")
    p_doc.add_argument("file", help="文档路径")

    # evolve
    p_evolve = sub.add_parser("evolve", help="构建后执行 PrefrontalLobe 元认知自我演化")
    p_evolve.add_argument("file", help="领域文档路径")
    p_evolve.add_argument("--domain", default="domain", help="领域名称 (默认: domain)")

    # web
    p_web = sub.add_parser("web", help="启动 Web 界面 (浏览器操作，带退出按钮)")
    p_web.add_argument("--host", default="127.0.0.1", help="绑定地址 (默认: 127.0.0.1)")
    p_web.add_argument("--port", type=int, default=5000, help="端口号 (默认: 5000)")

    args = parser.parse_args()
    setup_logging(args.verbose)

    handlers = {
        "build": cmd_build,
        "reason": cmd_reason,
        "interactive": cmd_interactive,
        "ask": cmd_ask,
        "memory": cmd_memory,
        "add-doc": cmd_add_doc,
        "evolve": cmd_evolve,
        "web": cmd_web,
    }
    handler = handlers.get(args.command)
    if handler:
        handler(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
