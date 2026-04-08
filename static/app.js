/* ═══════════════════════════════════════════════════════════
   LLM + Ontology 多智能体系统 — Web 前端逻辑
   ═══════════════════════════════════════════════════════════ */

(function () {
  "use strict";

  // ── DOM 引用 ─────────────────────────────────────────────
  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => document.querySelectorAll(sel);

  const overlay = $("#loading-overlay");
  const loadingText = $("#loading-text");

  // ── Tab 切换 ─────────────────────────────────────────────
  $$("nav .tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      $$("nav .tab").forEach((t) => t.classList.remove("active"));
      $$(".tab-panel").forEach((p) => p.classList.remove("active"));
      tab.classList.add("active");
      const panel = $("#tab-" + tab.dataset.tab);
      if (panel) panel.classList.add("active");

      // 切换到记忆页时自动刷新
      if (tab.dataset.tab === "memory") refreshMemory();
    });
  });

  // ── 构建: 文本/文件 模式切换 ─────────────────────────────
  $$(".switch-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      $$(".switch-btn").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      $$(".build-mode").forEach((m) => m.classList.remove("active"));
      const target = $("#build-" + btn.dataset.mode + "-mode");
      if (target) target.classList.add("active");
    });
  });

  // ── 通用辅助 ─────────────────────────────────────────────
  function showLoading(text) {
    loadingText.textContent = text || "处理中，请稍候 ...";
    overlay.classList.remove("hidden");
  }

  function hideLoading() {
    overlay.classList.add("hidden");
  }

  function showOutput(el, text, isError) {
    el.classList.remove("hidden", "error", "success");
    el.classList.add(isError ? "error" : "success");
    el.textContent = text;
  }

  function showLog(el, text) {
    if (!text || !text.trim()) {
      el.classList.add("hidden");
      return;
    }
    el.classList.remove("hidden");
    el.textContent = text;
  }

  async function apiPost(url, body, isFormData) {
    const opts = { method: "POST" };
    if (isFormData) {
      opts.body = body;
    } else {
      opts.headers = { "Content-Type": "application/json" };
      opts.body = JSON.stringify(body);
    }
    const res = await fetch(url, opts);
    return await res.json();
  }

  async function apiGet(url) {
    const res = await fetch(url);
    return await res.json();
  }

  // ── 构建: 文本模式 ──────────────────────────────────────
  $("#btn-build-text").addEventListener("click", async () => {
    const text = $("#domain-text").value.trim();
    const domain = $("#domain-name").value.trim();
    if (!text) {
      alert("请输入领域文档内容");
      return;
    }

    showLoading("正在构建本体 + 知识图谱 ...");
    const out = $("#build-output");
    try {
      const data = await apiPost("/api/build", { text, domain });
      if (data.ok) {
        showOutput(out, "✅ 构建成功\n\n" + (data.log || ""), false);
      } else {
        showOutput(out, "❌ " + data.error + "\n\n" + (data.log || ""), true);
      }
    } catch (e) {
      showOutput(out, "❌ 网络错误: " + e.message, true);
    } finally {
      hideLoading();
    }
  });

  // ── 构建: 文件上传模式 ──────────────────────────────────
  $("#btn-build-file").addEventListener("click", async () => {
    const fileInput = $("#domain-file");
    if (!fileInput.files.length) {
      alert("请选择文件");
      return;
    }

    const domain = $("#domain-name").value.trim();
    const fd = new FormData();
    fd.append("file", fileInput.files[0]);
    fd.append("domain", domain);

    showLoading("正在上传并构建 ...");
    const out = $("#build-output");
    try {
      const data = await apiPost("/api/build-file", fd, true);
      if (data.ok) {
        showOutput(out, "✅ 构建成功\n\n" + (data.log || ""), false);
      } else {
        showOutput(out, "❌ " + data.error + "\n\n" + (data.log || ""), true);
      }
    } catch (e) {
      showOutput(out, "❌ 网络错误: " + e.message, true);
    } finally {
      hideLoading();
    }
  });

  // ── 加载已有产物 ────────────────────────────────────────
  $("#btn-load").addEventListener("click", async () => {
    showLoading("正在加载已有本体产物 ...");
    const out = $("#build-output");
    try {
      const data = await apiPost("/api/load", {});
      if (data.ok) {
        showOutput(out, "✅ " + data.message + "\n\n" + (data.log || ""), false);
      } else {
        showOutput(out, "⚠️ " + (data.message || data.error) + "\n\n" + (data.log || ""), true);
      }
    } catch (e) {
      showOutput(out, "❌ 网络错误: " + e.message, true);
    } finally {
      hideLoading();
    }
  });

  // ── 推理问答 ────────────────────────────────────────────
  $("#btn-reason").addEventListener("click", async () => {
    const question = $("#question-input").value.trim();
    if (!question) {
      alert("请输入问题");
      return;
    }

    showLoading("正在推理 ...");
    const answerBox = $("#reason-answer");
    const logBox = $("#reason-log");
    try {
      const data = await apiPost("/api/reason", { question });
      if (data.ok) {
        showOutput(answerBox, data.answer, false);
        showLog(logBox, data.log);
      } else {
        showOutput(answerBox, "❌ " + data.error, true);
        showLog(logBox, data.log);
      }
    } catch (e) {
      showOutput(answerBox, "❌ 网络错误: " + e.message, true);
    } finally {
      hideLoading();
    }
  });

  // ── 记忆统计 ────────────────────────────────────────────
  async function refreshMemory() {
    try {
      const data = await apiGet("/api/memory");
      if (data.ok) {
        const s = data.stats;
        $("#stat-working").textContent = s.working_entries + " 条";
        $("#stat-longterm").textContent = s.long_term_entries + " 条";
        $("#stat-experience").textContent = s.experiences + " 条";
        $("#stat-knowledge").textContent = s.knowledge_facts + " 条";
        $("#stat-ontology").textContent = s.has_ontology ? "✅ 已加载" : "❌ 未加载";
        $("#stat-rag").textContent = s.rag_chunks + " 块";
      }
    } catch (e) {
      console.error("刷新记忆失败:", e);
    }
  }

  $("#btn-refresh-memory").addEventListener("click", refreshMemory);

  // ── 添加 RAG 文档 ──────────────────────────────────────
  $("#btn-add-doc").addEventListener("click", async () => {
    const fileInput = $("#rag-file");
    if (!fileInput.files.length) {
      alert("请选择文件");
      return;
    }

    const fd = new FormData();
    fd.append("file", fileInput.files[0]);

    showLoading("正在处理文档 ...");
    const out = $("#rag-output");
    try {
      const data = await apiPost("/api/add-doc", fd, true);
      if (data.ok) {
        showOutput(out, "✅ " + data.message, false);
        refreshMemory();
      } else {
        showOutput(out, "❌ " + data.error, true);
      }
    } catch (e) {
      showOutput(out, "❌ 网络错误: " + e.message, true);
    } finally {
      hideLoading();
    }
  });

  // ── 元认知演化 ──────────────────────────────────────────
  $("#btn-evolve").addEventListener("click", async () => {
    showLoading("正在执行元认知分析 (可能需要较长时间) ...");
    const out = $("#evolve-output");
    try {
      const data = await apiPost("/api/evolve", {});
      if (data.ok) {
        const text = typeof data.result === "object"
          ? JSON.stringify(data.result, null, 2)
          : String(data.result);
        showOutput(out, "✅ 演化完成\n\n" + text + "\n\n" + (data.log || ""), false);
      } else {
        showOutput(out, "❌ " + data.error + "\n\n" + (data.log || ""), true);
      }
    } catch (e) {
      showOutput(out, "❌ 网络错误: " + e.message, true);
    } finally {
      hideLoading();
    }
  });

  // ── 退出 / 关闭服务 ─────────────────────────────────────
  const shutdownDialog = $("#shutdown-dialog");

  $("#btn-shutdown").addEventListener("click", () => {
    shutdownDialog.classList.remove("hidden");
  });

  $("#btn-shutdown-cancel").addEventListener("click", () => {
    shutdownDialog.classList.add("hidden");
  });

  $("#btn-shutdown-confirm").addEventListener("click", async () => {
    shutdownDialog.classList.add("hidden");
    showLoading("正在关闭服务 ...");
    try {
      await apiPost("/api/shutdown", {});
    } catch (e) {
      // 服务关闭后连接会断开, 这是正常的
    }
    hideLoading();
    document.body.innerHTML =
      '<div style="display:flex;align-items:center;justify-content:center;' +
      'height:100vh;flex-direction:column;font-family:sans-serif;">' +
      '<h2>服务已关闭</h2>' +
      '<p style="color:#64748b;margin-top:8px;">可以安全关闭此页面。</p>' +
      "</div>";
  });

  // ── 页面加载时初始化 ────────────────────────────────────
  refreshMemory();
})();
