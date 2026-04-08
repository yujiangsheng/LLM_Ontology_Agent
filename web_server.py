"""
web_server — Web 前端服务
=========================

基于 Flask 的 Web 界面，提供与 CLI 等价的功能，
包括本体构建、推理问答、记忆管理、元认知演化等。

内置 **退出** 功能：通过页面按钮或 ``POST /api/shutdown``
可随时优雅终止服务。

启动方式::

    # 通过 CLI 子命令
    python main.py web

    # 自定义端口
    python main.py web --port 8080

    # 直接运行本模块
    python web_server.py

作者: Jiangsheng Yu
许可: MIT License
"""
from __future__ import annotations

import io
import logging
import os
import signal
import sys
import threading
from contextlib import redirect_stdout

from flask import Flask, jsonify, render_template, request

from agents.orchestrator import Orchestrator
from utils.document_loader import load_text
import config

logger = logging.getLogger(__name__)

app = Flask(__name__, template_folder="templates", static_folder="static")

# ── 全局 Orchestrator 实例 ────────────────────────────────
_orch: Orchestrator | None = None
_orch_lock = threading.Lock()


def _get_orch() -> Orchestrator:
    """获取全局 Orchestrator 实例（惰性初始化）。"""
    global _orch
    if _orch is None:
        with _orch_lock:
            if _orch is None:
                _orch = Orchestrator()
    return _orch


# ═══════════════════════════════════════════════════════════════
#  页面路由
# ═══════════════════════════════════════════════════════════════

@app.route("/")
def index():
    """主页 — 单页应用。"""
    return render_template("index.html")


# ═══════════════════════════════════════════════════════════════
#  API 路由
# ═══════════════════════════════════════════════════════════════

@app.route("/api/build", methods=["POST"])
def api_build():
    """构建 Ontology + 知识图谱。

    请求体 (JSON):
        text: 领域文档文本 (与 file 二选一)
        file: 上传的文件路径
        domain: 领域名称 (默认 "domain")
    """
    data = request.get_json(silent=True) or {}
    domain_text = data.get("text", "").strip()
    domain_name = data.get("domain", "domain").strip() or "domain"

    if not domain_text:
        return jsonify({"ok": False, "error": "请提供领域文档文本"}), 400

    orch = _get_orch()

    # 捕获 print 输出作为日志
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            orch.build_ontology(domain_text, domain_name=domain_name)
    except Exception as e:
        logger.exception("build_ontology 失败")
        return jsonify({"ok": False, "error": str(e), "log": buf.getvalue()}), 500

    return jsonify({
        "ok": True,
        "log": buf.getvalue(),
        "stats": orch.memory.stats(),
    })


@app.route("/api/build-file", methods=["POST"])
def api_build_file():
    """从上传文件构建 Ontology。

    表单字段:
        file: 上传的文件
        domain: 领域名称 (默认 "domain")
    """
    if "file" not in request.files:
        return jsonify({"ok": False, "error": "请上传文件"}), 400

    uploaded = request.files["file"]
    if not uploaded.filename:
        return jsonify({"ok": False, "error": "文件名为空"}), 400

    domain_name = request.form.get("domain", "domain").strip() or "domain"

    # 保存临时文件
    tmp_path = os.path.join(config.OUTPUT_DIR, f"_upload_{uploaded.filename}")
    try:
        uploaded.save(tmp_path)
        domain_text = load_text(tmp_path)
    except Exception as e:
        return jsonify({"ok": False, "error": f"文件读取失败: {e}"}), 400
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    orch = _get_orch()
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            orch.build_ontology(domain_text, domain_name=domain_name)
    except Exception as e:
        logger.exception("build_ontology 失败")
        return jsonify({"ok": False, "error": str(e), "log": buf.getvalue()}), 500

    return jsonify({
        "ok": True,
        "log": buf.getvalue(),
        "stats": orch.memory.stats(),
    })


@app.route("/api/reason", methods=["POST"])
def api_reason():
    """推理问答。

    请求体 (JSON):
        question: 自然语言问题
    """
    data = request.get_json(silent=True) or {}
    question = data.get("question", "").strip()
    if not question:
        return jsonify({"ok": False, "error": "请输入问题"}), 400

    orch = _get_orch()

    if "ontology_graph" not in orch.context:
        # 尝试加载已有产物
        buf_load = io.StringIO()
        with redirect_stdout(buf_load):
            orch.load_from_output()
        if "ontology_graph" not in orch.context:
            return jsonify({
                "ok": False,
                "error": "尚未构建本体，请先在「构建」页面构建或上传领域文档。",
            }), 400

    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            explanation = orch.reason(question)
    except Exception as e:
        logger.exception("reason 失败")
        return jsonify({"ok": False, "error": str(e), "log": buf.getvalue()}), 500

    return jsonify({
        "ok": True,
        "answer": explanation,
        "log": buf.getvalue(),
    })


@app.route("/api/memory", methods=["GET"])
def api_memory():
    """获取记忆系统统计信息。"""
    orch = _get_orch()
    try:
        stats = orch.memory.stats()
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
    return jsonify({"ok": True, "stats": stats})


@app.route("/api/add-doc", methods=["POST"])
def api_add_doc():
    """将文档加入 RAG 索引。

    表单字段:
        file: 上传的文档文件
    """
    if "file" not in request.files:
        return jsonify({"ok": False, "error": "请上传文件"}), 400

    uploaded = request.files["file"]
    if not uploaded.filename:
        return jsonify({"ok": False, "error": "文件名为空"}), 400

    tmp_path = os.path.join(config.OUTPUT_DIR, f"_upload_{uploaded.filename}")
    try:
        uploaded.save(tmp_path)
        orch = _get_orch()
        count = orch.add_document(tmp_path)
    except Exception as e:
        return jsonify({"ok": False, "error": f"文档处理失败: {e}"}), 400
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    return jsonify({
        "ok": True,
        "message": f"已加入 RAG 索引 (新增 {count} 块)",
        "stats": orch.memory.stats(),
    })


@app.route("/api/evolve", methods=["POST"])
def api_evolve():
    """执行元认知自我演化。"""
    orch = _get_orch()

    if not orch.context:
        return jsonify({
            "ok": False,
            "error": "请先构建本体，然后才能执行元认知演化。",
        }), 400

    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            result = orch.evolve()
    except Exception as e:
        logger.exception("evolve 失败")
        return jsonify({"ok": False, "error": str(e), "log": buf.getvalue()}), 500

    return jsonify({
        "ok": True,
        "result": result if isinstance(result, dict) else str(result),
        "log": buf.getvalue(),
    })


@app.route("/api/load", methods=["POST"])
def api_load():
    """从 output/ 加载已有本体产物。"""
    orch = _get_orch()
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            orch.load_from_output()
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

    has_ontology = "ontology_graph" in orch.context
    return jsonify({
        "ok": has_ontology,
        "message": "本体加载成功" if has_ontology else "未找到已有本体文件",
        "log": buf.getvalue(),
        "stats": orch.memory.stats(),
    })


@app.route("/api/shutdown", methods=["POST"])
def api_shutdown():
    """优雅关闭 Web 服务。"""
    global _orch

    # 结束 Orchestrator 会话
    if _orch is not None:
        try:
            _orch.end_session()
        except Exception:
            pass
        _orch = None

    logger.info("收到关闭请求，正在终止服务 ...")

    # 延迟发送 SIGINT 以便响应先返回
    def _shutdown():
        os.kill(os.getpid(), signal.SIGINT)

    threading.Timer(0.5, _shutdown).start()
    return jsonify({"ok": True, "message": "服务正在关闭 ..."})


# ═══════════════════════════════════════════════════════════════
#  启动入口
# ═══════════════════════════════════════════════════════════════

def run_server(host: str = "127.0.0.1", port: int = 5000) -> None:
    """启动 Flask 开发服务器。"""
    print(f"\n{'=' * 60}")
    print(f"  LLM + Ontology 多智能体系统 — Web 界面")
    print(f"  地址: http://{host}:{port}")
    print(f"  按 Ctrl+C 或点击页面「退出」按钮终止服务")
    print(f"{'=' * 60}\n")
    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    run_server()
