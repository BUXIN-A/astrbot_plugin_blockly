/* Blocky 可视化编程 WebUI 逻辑 */
/* global Blockly */
"use strict";

const $ = (id) => document.getElementById(id);

let bridge = window.AstrBotPluginPage;
let workspace = null;
let currentId = null;
let currentMode = "blockly"; // blockly | python
let currentWorkspaceState = null; // 最近一次保存/加载的积木状态
let programs = [];
let dirty = false;
let loading = false;

/* ---------- 通用 ---------- */

function showToast(message, isError = false) {
  const el = document.createElement("div");
  el.className = "toast" + (isError ? " toast-error" : "");
  el.textContent = message;
  document.body.appendChild(el);
  setTimeout(() => el.classList.add("show"), 10);
  setTimeout(() => {
    el.classList.remove("show");
    setTimeout(() => el.remove(), 250);
  }, 2600);
}

function fmtTime(ts) {
  if (!ts) return "从未运行";
  const d = new Date(ts * 1000);
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(
    d.getHours(),
  )}:${pad(d.getMinutes())}`;
}

function modeLabel(mode) {
  return mode === "return" ? "返回" : "传出";
}

/* ---------- 桥接 API ---------- */

async function apiGet(endpoint, params) {
  return await bridge.apiGet(endpoint, params || {});
}

async function apiPost(endpoint, body) {
  return await bridge.apiPost(endpoint, body || {});
}

/* ---------- Blockly 自定义积木 ---------- */

function defineBlocks() {
  Blockly.common.defineBlocksWithJsonArray([
    {
      type: "blocky_event",
      message0: "当接收到消息",
      args0: [{ type: "input_statement", name: "DO" }],
      colour: 210,
      nextStatement: null,
      tooltip: "程序入口：在此放置收到消息时需要执行的积木。",
    },
    {
      type: "blocky_get_message",
      message0: "消息文本",
      output: "String",
      colour: 160,
      tooltip: "本次收到的消息内容。",
    },
    {
      type: "blocky_get_sender_name",
      message0: "发送者名称",
      output: "String",
      colour: 160,
      tooltip: "发送者的昵称。",
    },
    {
      type: "blocky_get_sender_id",
      message0: "发送者ID",
      output: "String",
      colour: 160,
    },
    {
      type: "blocky_get_group_id",
      message0: "群号",
      output: "String",
      colour: 160,
    },
    {
      type: "blocky_get_session",
      message0: "会话标识",
      output: "String",
      colour: 160,
    },
    {
      type: "blocky_get_platform",
      message0: "平台名称",
      output: "String",
      colour: 160,
    },
    {
      type: "blocky_is_admin",
      message0: "发送者是否为管理员",
      output: "Boolean",
      colour: 160,
    },
    {
      type: "blocky_is_private",
      message0: "是否为私聊",
      output: "Boolean",
      colour: 160,
    },
    {
      type: "blocky_reply",
      message0: "回复 %1",
      args0: [{ type: "input_value", name: "TEXT", check: "String" }],
      previousStatement: null,
      nextStatement: null,
      colour: 210,
      tooltip: "回复一条消息，并继续让 AstrBot 处理。",
    },
    {
      type: "blocky_return_msg",
      message0: "返回消息 %1",
      args0: [{ type: "input_value", name: "TEXT", check: "String" }],
      previousStatement: null,
      nextStatement: null,
      colour: 210,
      tooltip: "回复消息并劫持事件，阻止 AstrBot 继续处理。",
    },
    {
      type: "blocky_forward",
      message0: "传出消息（交给 AstrBot 继续处理）",
      previousStatement: null,
      nextStatement: null,
      colour: 210,
    },
    {
      type: "blocky_stop",
      message0: "停止事件传播",
      previousStatement: null,
      nextStatement: null,
      colour: 210,
    },
    {
      type: "blocky_send",
      message0: "向会话 %1 发送 %2",
      args0: [
        { type: "input_value", name: "SESSION", check: "String" },
        { type: "input_value", name: "TEXT", check: "String" },
      ],
      previousStatement: null,
      nextStatement: null,
      colour: 210,
      tooltip: "主动发送消息到指定会话（unified_msg_origin）。",
    },
    {
      type: "blocky_sleep",
      message0: "延时 %1 毫秒",
      args0: [{ type: "field_number", name: "MS", value: 1000, min: 0 }],
      previousStatement: null,
      nextStatement: null,
      colour: 210,
    },
    {
      type: "blocky_log",
      message0: "输出日志 %1",
      args0: [{ type: "input_value", name: "TEXT" }],
      previousStatement: null,
      nextStatement: null,
      colour: 210,
    },
    {
      type: "blocky_chat",
      message0: "AI 回答 %1",
      args0: [{ type: "input_value", name: "PROMPT", check: "String" }],
      output: "String",
      colour: 90,
      tooltip: "调用当前会话的 AI 模型，返回回答文本。",
    },
    {
      type: "blocky_http_get",
      message0: "HTTP GET %1 请求头 %2",
      args0: [
        { type: "input_value", name: "URL", check: "String" },
        { type: "field_input", name: "HEADERS", text: "{}" },
      ],
      output: null,
      colour: 330,
      tooltip: "发起 GET 请求，返回 {status, body}。",
    },
    {
      type: "blocky_http_get_json",
      message0: "HTTP GET JSON %1 请求头 %2",
      args0: [
        { type: "input_value", name: "URL", check: "String" },
        { type: "field_input", name: "HEADERS", text: "{}" },
      ],
      output: null,
      colour: 330,
      tooltip: "发起 GET 请求并解析 JSON 响应。",
    },
    {
      type: "blocky_http_post",
      message0: "HTTP POST %1 数据 %2 请求头 %3",
      args0: [
        { type: "input_value", name: "URL", check: "String" },
        { type: "field_input", name: "DATA", text: "{}" },
        { type: "field_input", name: "HEADERS", text: "{}" },
      ],
      output: null,
      colour: 330,
    },
    {
      type: "blocky_http_post_json",
      message0: "HTTP POST JSON %1 数据 %2 请求头 %3",
      args0: [
        { type: "input_value", name: "URL", check: "String" },
        { type: "field_input", name: "DATA", text: "{}" },
        { type: "field_input", name: "HEADERS", text: "{}" },
      ],
      output: null,
      colour: 330,
    },
    {
      type: "blocky_dict_get",
      message0: "取 %1 的键 %2",
      args0: [
        { type: "input_value", name: "DICT" },
        { type: "input_value", name: "KEY", check: "String" },
      ],
      output: null,
      colour: 330,
    },
  ]);
}

function registerPythonGenerator() {
  const py = Blockly.Python;

  py.forBlock["blocky_event"] = function (block) {
    const code = py.statementToCode(block, "DO");
    return [code, py.ORDER_NONE];
  };

  const simpleValueBlocks = {
    blocky_get_message: "_blk.get_message()",
    blocky_get_sender_name: "_blk.get_sender_name()",
    blocky_get_sender_id: "_blk.get_sender_id()",
    blocky_get_group_id: "_blk.get_group_id()",
    blocky_get_session: "_blk.get_session()",
    blocky_get_platform: "_blk.get_platform()",
    blocky_is_admin: "_blk.is_admin()",
    blocky_is_private: "_blk.is_private()",
  };
  for (const [type, expr] of Object.entries(simpleValueBlocks)) {
    py.forBlock[type] = () => [expr, py.ORDER_FUNCTION_CALL];
  }

  py.forBlock["blocky_reply"] = function (block) {
    const text = py.valueToCode(block, "TEXT", py.ORDER_NONE) || "''";
    return [`await _blk.reply(${text})\n`, py.ORDER_NONE];
  };

  py.forBlock["blocky_return_msg"] = function (block) {
    const text = py.valueToCode(block, "TEXT", py.ORDER_NONE) || "''";
    return [`await _blk.return_msg(${text})\n`, py.ORDER_NONE];
  };

  py.forBlock["blocky_forward"] = () => ["_blk.forward()\n", py.ORDER_NONE];
  py.forBlock["blocky_stop"] = () => ["_blk.stop()\n", py.ORDER_NONE];

  py.forBlock["blocky_send"] = function (block) {
    const session = py.valueToCode(block, "SESSION", py.ORDER_NONE) || "''";
    const text = py.valueToCode(block, "TEXT", py.ORDER_NONE) || "''";
    return [`await _blk.send(${session}, ${text})\n`, py.ORDER_NONE];
  };

  py.forBlock["blocky_sleep"] = function (block) {
    const ms = block.getFieldValue("MS") || "0";
    return [`await _blk.sleep(${ms})\n`, py.ORDER_NONE];
  };

  py.forBlock["blocky_log"] = function (block) {
    const text = py.valueToCode(block, "TEXT", py.ORDER_NONE) || "''";
    return [`_blk.log(${text})\n`, py.ORDER_NONE];
  };

  py.forBlock["blocky_chat"] = function (block) {
    const prompt = py.valueToCode(block, "PROMPT", py.ORDER_NONE) || "''";
    return [`await _blk.chat(${prompt})`, py.ORDER_FUNCTION_CALL];
  };

  py.forBlock["blocky_http_get"] = function (block) {
    const url = py.valueToCode(block, "URL", py.ORDER_NONE) || "''";
    const headers = block.getFieldValue("HEADERS") || "{}";
    return [`await _blk.http_get(${url}, ${headers})`, py.ORDER_FUNCTION_CALL];
  };

  py.forBlock["blocky_http_get_json"] = function (block) {
    const url = py.valueToCode(block, "URL", py.ORDER_NONE) || "''";
    const headers = block.getFieldValue("HEADERS") || "{}";
    return [
      `await _blk.http_get_json(${url}, ${headers})`,
      py.ORDER_FUNCTION_CALL,
    ];
  };

  py.forBlock["blocky_http_post"] = function (block) {
    const url = py.valueToCode(block, "URL", py.ORDER_NONE) || "''";
    const data = block.getFieldValue("DATA") || "{}";
    const headers = block.getFieldValue("HEADERS") || "{}";
    return [
      `await _blk.http_post(${url}, ${data}, ${headers})`,
      py.ORDER_FUNCTION_CALL,
    ];
  };

  py.forBlock["blocky_http_post_json"] = function (block) {
    const url = py.valueToCode(block, "URL", py.ORDER_NONE) || "''";
    const data = block.getFieldValue("DATA") || "{}";
    const headers = block.getFieldValue("HEADERS") || "{}";
    return [
      `await _blk.http_post_json(${url}, ${data}, ${headers})`,
      py.ORDER_FUNCTION_CALL,
    ];
  };

  py.forBlock["blocky_dict_get"] = function (block) {
    const dictExpr = py.valueToCode(block, "DICT", py.ORDER_NONE) || "{}";
    const key = py.valueToCode(block, "KEY", py.ORDER_NONE) || "''";
    return [`_blk.dict_get(${dictExpr}, ${key})`, py.ORDER_FUNCTION_CALL];
  };
}

function initWorkspace(isDark) {
  workspace = Blockly.inject("blocklyDiv", {
    toolbox: $("toolbox"),
    media: "vendor/media/",
    theme: isDark ? Blockly.Themes.Dark : Blockly.Themes.Classic,
    grid: { spacing: 20, length: 3, colour: "#cccccc", snap: true },
    zoom: {
      controls: true,
      wheel: true,
      startScale: 0.9,
      maxScale: 3,
      minScale: 0.3,
      scaleSpeed: 1.1,
    },
    trashcan: true,
    scrollbars: true,
    sounds: true,
  });
  workspace.addChangeListener(() => {
    if (loading) return;
    dirty = true;
  });
}

function defaultWorkspaceState() {
  return {
    blocks: { languageVersion: 0, blocks: [{ type: "blocky_event" }] },
  };
}

/* ---------- 程序列表 ---------- */

async function refreshPrograms() {
  try {
    const res = await apiGet("programs");
    programs = res.programs || [];
    renderSidebar();
  } catch (err) {
    showToast(err.message || "获取程序列表失败", true);
  }
}

function renderSidebar() {
  const list = $("programList");
  list.innerHTML = "";
  if (!programs.length) {
    list.innerHTML =
      '<div class="empty-state">暂无程序<br/>点击「+ 新建」创建第一个程序</div>';
    return;
  }
  for (const p of programs) {
    const item = document.createElement("div");
    item.className = "program-item" + (p.id === currentId ? " active" : "");

    const info = document.createElement("div");
    info.className = "p-info";
    const name = document.createElement("div");
    name.className = "p-name";
    name.textContent = p.name || "未命名程序";
    const meta = document.createElement("div");
    meta.className = "p-meta" + (p.last_error ? " p-error" : "");
    meta.textContent = `${modeLabel(p.mode)} · 优先级 ${p.priority} · ${fmtTime(
      p.last_run_at,
    )}${p.last_error ? " · " + p.last_error : ""}`;
    info.appendChild(name);
    info.appendChild(meta);

    const actions = document.createElement("div");
    actions.className = "p-actions";
    const dupBtn = document.createElement("button");
    dupBtn.className = "icon-btn";
    dupBtn.textContent = "⧉";
    dupBtn.title = "复制";
    dupBtn.onclick = (e) => {
      e.stopPropagation();
      duplicateProgram(p.id);
    };
    const delBtn = document.createElement("button");
    delBtn.className = "icon-btn danger";
    delBtn.textContent = "✕";
    delBtn.title = "删除";
    delBtn.onclick = (e) => {
      e.stopPropagation();
      deleteProgram(p.id);
    };
    actions.appendChild(dupBtn);
    actions.appendChild(delBtn);

    const toggle = document.createElement("input");
    toggle.type = "checkbox";
    toggle.className = "switch";
    toggle.checked = !!p.enabled;
    toggle.title = "启用/关闭";
    toggle.onclick = (e) => {
      e.stopPropagation();
      toggleProgram(p.id, toggle.checked);
    };

    item.appendChild(info);
    item.appendChild(actions);
    item.appendChild(toggle);
    item.onclick = () => selectProgram(p.id);
    list.appendChild(item);
  }
}

/* ---------- 程序载入与保存 ---------- */

async function selectProgram(id) {
  if (id === currentId) return;
  if (dirty && !confirm("当前程序有未保存的修改，是否放弃？")) return;
  try {
    const res = await apiGet("programs/" + id);
    loadProgram(res.program);
  } catch (err) {
    showToast(err.message || "加载程序失败", true);
  }
}

function loadProgram(p) {
  currentId = p.id;
  loading = true;
  dirty = false;

  $("nameInput").value = p.name || "";
  $("descriptionInput").value = p.description || "";
  $("modeSelect").value = p.mode === "return" ? "return" : "forward";
  $("enabledCheck").checked = !!p.enabled;
  $("priorityInput").value = p.priority || 0;
  $("timeoutInput").value = p.timeout || 30;
  $("triggerType").value =
    p.trigger && p.trigger.type ? p.trigger.type : "all";
  $("triggerValue").value = (p.trigger && p.trigger.value) || "";
  updateTriggerValueState();
  $("idBadge").textContent = p.id;
  $("testResult").textContent = "";

  currentWorkspaceState = null;
  try {
    const raw = p.workspace;
    if (raw) currentWorkspaceState = JSON.parse(raw);
  } catch (err) {
    currentWorkspaceState = null;
  }

  if (p.content_type === "python") {
    setEditorMode("python");
    $("codeEditor").value = p.code || "";
  } else {
    $("codeEditor").value = p.code || "";
    setEditorMode("blockly");
    if (currentWorkspaceState) {
      Blockly.serialization.workspaces.load(currentWorkspaceState, workspace);
    } else {
      workspace.clear();
    }
  }
  renderSidebar();
  loading = false;
}

function setEditorMode(mode) {
  currentMode = mode;
  $("tabBlockly").classList.toggle("active", mode === "blockly");
  $("tabPython").classList.toggle("active", mode === "python");
  $("blocklyDiv").classList.toggle("hidden", mode !== "blockly");
  $("codeEditor").classList.toggle("hidden", mode !== "python");
  if (mode === "python") {
    $("codeEditor").value = generateCode();
  }
  window.dispatchEvent(new Event("resize"));
}

function generateCode() {
  try {
    return Blockly.Python.workspaceToCode(workspace);
  } catch (err) {
    return $("codeEditor").value || "";
  }
}

function collectForm() {
  const triggerType = $("triggerType").value;
  const triggerValue =
    triggerType === "contains" ||
    triggerType === "prefix" ||
    triggerType === "regex"
      ? $("triggerValue").value
      : "";
  let code = "";
  let workspaceState = null;
  if (currentMode === "blockly") {
    workspaceState = Blockly.serialization.workspaces.save(workspace);
    code = generateCode();
  } else {
    workspaceState = currentWorkspaceState;
    code = $("codeEditor").value;
  }
  return {
    name: $("nameInput").value.trim() || "未命名程序",
    description: $("descriptionInput").value.trim(),
    mode: $("modeSelect").value,
    content_type: currentMode === "blockly" ? "blockly" : "python",
    workspace: workspaceState ? JSON.stringify(workspaceState) : "",
    code: code,
    trigger: { type: triggerType, value: triggerValue },
    priority: Number($("priorityInput").value) || 0,
    timeout: Math.max(1, Number($("timeoutInput").value) || 30),
    enabled: $("enabledCheck").checked,
  };
}

async function saveProgram(silent = false) {
  if (!currentId) return;
  const payload = collectForm();
  try {
    const res = await apiPost("programs/" + currentId, payload);
    currentWorkspaceState = payload.workspace
      ? JSON.parse(payload.workspace)
      : null;
    dirty = false;
    const idx = programs.findIndex((p) => p.id === currentId);
    if (idx >= 0) programs[idx] = res.program || programs[idx];
    renderSidebar();
    if (!silent) showToast("已保存");
  } catch (err) {
    showToast(err.message || "保存失败", true);
  }
}

/* ---------- 增删改查操作 ---------- */

async function newProgram() {
  try {
    const res = await apiPost("programs", {
      name: "未命名程序",
      mode: "forward",
      content_type: "blockly",
    });
    programs.push(res.program);
    renderSidebar();
    await loadProgram(res.program);
    loading = true;
    Blockly.serialization.workspaces.load(defaultWorkspaceState(), workspace);
    loading = false;
    dirty = true;
    $("nameInput").focus();
    $("nameInput").select();
  } catch (err) {
    showToast(err.message || "新建失败", true);
  }
}

async function deleteProgram(id) {
  if (!confirm("确定删除该程序？此操作不可恢复。")) return;
  try {
    await apiPost("programs/" + id + "/delete", {});
    if (currentId === id) {
      currentId = null;
      currentWorkspaceState = null;
      workspace.clear();
      $("codeEditor").value = "";
    }
    await refreshPrograms();
    showToast("已删除");
    if (currentId === null && programs.length) await selectProgram(programs[0].id);
  } catch (err) {
    showToast(err.message || "删除失败", true);
  }
}

async function duplicateProgram(id) {
  try {
    const res = await apiPost("programs/" + id + "/duplicate", {});
    programs.push(res.program);
    renderSidebar();
    await loadProgram(res.program);
    showToast("已复制");
  } catch (err) {
    showToast(err.message || "复制失败", true);
  }
}

async function toggleProgram(id, enabled) {
  try {
    const res = await apiPost("programs/" + id + "/toggle", { enabled });
    const idx = programs.findIndex((p) => p.id === id);
    if (idx >= 0) programs[idx].enabled = res.enabled;
    if (currentId === id) $("enabledCheck").checked = !!res.enabled;
    renderSidebar();
  } catch (err) {
    showToast(err.message || "开关切换失败", true);
  }
}

/* ---------- 测试运行 ---------- */

async function runTest() {
  if (!currentId) return;
  let chatResponses = {};
  try {
    const raw = $("testChat").value.trim();
    if (raw) chatResponses = JSON.parse(raw);
  } catch (err) {
    showToast("模拟 AI 回答的 JSON 格式不正确", true);
    return;
  }
  $("testResult").textContent = "正在运行…";
  try {
    await saveProgram(true);
    const res = await apiPost("programs/" + currentId + "/test", {
      message: $("testMessage").value,
      is_admin: $("testAdmin").checked,
      is_private: $("testPrivate").checked,
      chat_responses: chatResponses,
    });
    const lines = [];
    if (res.error) {
      lines.push(`[错误] ${res.error}`);
    }
    if (res.replies && res.replies.length) {
      lines.push(`[回复] ${res.replies.join(" | ")}`);
    }
    if (res.sends && res.sends.length) {
      for (const s of res.sends) {
        lines.push(`[主动发送] ${s[1] || ""}`);
      }
    }
    if (res.stopped) lines.push("[事件] 已停止传播（AstrBot 将不再处理）");
    else lines.push("[事件] 未停止（将继续交给 AstrBot 处理）");
    lines.push(`[耗时] ${res.cost}s`);
    if (!lines.length) lines.push("（程序无任何输出）");
    const el = $("testResult");
    el.textContent = lines.join("\n");
    if (res.error) el.classList.add("err");
    else el.classList.remove("err");
  } catch (err) {
    $("testResult").textContent = "运行出错：" + err.message;
    $("testResult").classList.add("err");
  }
}

/* ---------- 导入导出 ---------- */

function exportAll() {
  if (!programs.length) {
    showToast("暂无程序可导出");
    return;
  }
  bridge.download("export", {}, "blocky_programs.json").catch((err) => {
    showToast(err.message || "导出失败", true);
  });
}

function exportCurrent() {
  if (!currentId) return;
  bridge
    .download("export/" + currentId, {}, "blocky_program.json")
    .catch((err) => showToast(err.message || "导出失败", true));
}

async function importFromFile(file) {
  if (!file) return;
  try {
    const res = await bridge.upload("import/file", file);
    showToast(`已导入 ${res.imported} 个程序`);
    await refreshPrograms();
  } catch (err) {
    showToast(err.message || "导入失败", true);
  }
}

/* ---------- 事件绑定 ---------- */

function updateTriggerValueState() {
  const t = $("triggerType").value;
  $("triggerValue").disabled =
    !(t === "contains" || t === "prefix" || t === "regex");
}

function bindEvents() {
  $("newBtn").onclick = newProgram;
  $("saveBtn").onclick = () => saveProgram(false);
  $("testBtn").onclick = runTest;
  $("refreshBtn").onclick = refreshPrograms;
  $("exportAllBtn").onclick = exportAll;
  $("tabBlockly").onclick = () => setEditorMode("blockly");
  $("tabPython").onclick = () => setEditorMode("python");

  const importBtn = $("importBtn");
  const importFile = $("importFile");
  importBtn.onclick = () => importFile.click();
  importFile.onchange = (e) => {
    importFromFile(e.target.files[0]);
    e.target.value = "";
  };

  $("triggerType").onchange = updateTriggerValueState;

  const markDirty = () => {
    if (!loading) dirty = true;
  };
  [
    "nameInput",
    "descriptionInput",
    "modeSelect",
    "enabledCheck",
    "priorityInput",
    "timeoutInput",
    "triggerType",
    "triggerValue",
    "codeEditor",
  ].forEach((id) => {
    $(id).addEventListener("input", markDirty);
    $(id).addEventListener("change", markDirty);
  });

  $("testChat").addEventListener("input", markDirty);

  window.addEventListener("beforeunload", (e) => {
    if (dirty) {
      e.preventDefault();
      e.returnValue = "";
    }
  });
}

/* ---------- 启动 ---------- */

(async function init() {
  try {
    const ctx = await bridge.ready();
    document.title = ctx.pageTitle || "Blocky 可视化编程";
    defineBlocks();
    registerPythonGenerator();
    initWorkspace(ctx.isDark);
    bridge.onContext((c) => {
      if (workspace) {
        workspace.setTheme(
          c && c.isDark ? Blockly.Themes.Dark : Blockly.Themes.Classic,
        );
      }
    });
    bindEvents();
    await refreshPrograms();
    if (programs.length) {
      await selectProgram(programs[0].id);
    }
  } catch (err) {
    showToast("初始化失败：" + (err.message || err), true);
  }
})();
