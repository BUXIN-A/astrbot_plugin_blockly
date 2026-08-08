/* Blocky 可视化编程 WebUI 逻辑 */
/* global Blockly */
"use strict";

const $ = (id) => document.getElementById(id);

// 运行时由 JS 创建的图标使用 data URI：
// AstrBot 插件页只重写 HTML/CSS/import 中的静态资源引用，
// JS 动态创建的 <img> 若引用图片文件将不带 asset_token 而 401（且 token 短期过期）。
const IMG_COPY =
  "data:image/png;base64,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";
const IMG_DELETE =
  "data:image/png;base64,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";
const IMG_CHECK =
  "data:image/png;base64,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";

// 「启用」开关启用后显示的图标（运行时切换 src，同样用 data URI 避免 401）。
const IMG_CHECK_OK =
  "data:image/png;base64,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";

let bridge = window.AstrBotPluginPage;
// 工具栏「启用」开关图标：运行时按启用状态切换（data URI，避免 401）。
const toolbarCheckImg = $("enabledCheck").nextElementSibling;
function syncToolbarCheckIcon() {
  toolbarCheckImg.src = $("enabledCheck").checked ? IMG_CHECK_OK : IMG_CHECK;
}
let workspace = null;
let currentId = null;
let currentMode = "blockly"; // blockly | python
let currentWorkspaceState = null; // 最近一次保存/加载的积木状态
let programs = [];
let selectedModels = []; // 当前表单中的「可用模型」白名单
let availableModels = []; // 后端可用的模型列表
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

function ctypeLabel(type) {
  return type === "python" ? "代码" : "积木";
}

/* ---------- 弹窗（沙箱 iframe 内原生 confirm/alert 不可用，使用自定义弹窗） ---------- */

function openModal(id) {
  $(id).classList.remove("hidden");
}

function closeModal(id) {
  $(id).classList.add("hidden");
}

let confirmResolve = null;

function confirmDialog(message, options) {
  const opts = options || {};
  $("confirmTitle").textContent = opts.title || "提示";
  $("confirmMessage").textContent = message;
  $("confirmOk").textContent = opts.okText || "确定";
  $("confirmOk").classList.toggle("btn-danger", !!opts.danger);
  openModal("confirmModal");
  return new Promise((resolve) => {
    confirmResolve = resolve;
  });
}

function bindConfirmModal() {
  const close = (value) => {
    closeModal("confirmModal");
    if (confirmResolve) {
      confirmResolve(value);
      confirmResolve = null;
    }
  };
  $("confirmOk").onclick = () => close(true);
  $("confirmCancel").onclick = () => close(false);
  $("confirmModal").addEventListener("click", (e) => {
    if (e.target === $("confirmModal")) close(false);
  });
}

function openCreateDialog() {
  $("createName").value = "";
  $("createNameHint").textContent = "";
  document.querySelectorAll('input[name="createType"]')[0].checked = true;
  openModal("createModal");
  setTimeout(() => $("createName").focus(), 50);
  return new Promise((resolve) => {
    createResolve = resolve;
  });
}

let createResolve = null;

function bindCreateModal() {
  const close = (value) => {
    closeModal("createModal");
    if (createResolve) {
      createResolve(value);
      createResolve = null;
    }
  };
  const validate = () => {
    const name = $("createName").value.trim();
    const exists = programs.some(
      (p) => p.name.trim().toLowerCase() === name.toLowerCase(),
    );
    if (!name) {
      $("createNameHint").textContent = "请输入程序名称";
      $("createOk").disabled = true;
      return;
    }
    if (exists) {
      $("createNameHint").textContent = "名称已存在，请更换名称";
      $("createOk").disabled = true;
      return;
    }
    $("createNameHint").textContent = "";
    $("createOk").disabled = false;
  };
  $("createName").addEventListener("input", validate);
  $("createOk").onclick = () => {
    const name = $("createName").value.trim();
    if (!name) return;
    const typeEl = document.querySelector('input[name="createType"]:checked');
    close({ name, content_type: typeEl ? typeEl.value : "blockly" });
  };
  $("createCancel").onclick = () => close(null);
  $("createModal").addEventListener("click", (e) => {
    if (e.target === $("createModal")) close(null);
  });
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
      message0: "当接收到消息 %1",
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
      tooltip: "发送者的唯一 ID。",
    },
    {
      type: "blocky_get_group_id",
      message0: "群号",
      output: "String",
      colour: 160,
      tooltip: "消息所在群聊的 ID（私聊为空）。",
    },
    {
      type: "blocky_get_session",
      message0: "会话标识",
      output: "String",
      colour: 160,
      tooltip: "当前会话的 unified_msg_origin 标识。",
    },
    {
      type: "blocky_get_platform",
      message0: "平台名称",
      output: "String",
      colour: 160,
      tooltip: "消息来源平台（如 aiocqhttp / telegram）。",
    },
    {
      type: "blocky_is_admin",
      message0: "发送者是否为管理员",
      output: "Boolean",
      colour: 160,
      tooltip: "发送者是否是机器人管理员。",
    },
    {
      type: "blocky_is_private",
      message0: "是否为私聊",
      output: "Boolean",
      colour: 160,
      tooltip: "消息是否来自私聊。",
    },
    {
      type: "blocky_reply",
      message0: "回复 %1",
      args0: [{ type: "input_value", name: "TEXT", check: "String" }],
      previousStatement: null,
      nextStatement: null,
      colour: 210,
      tooltip:
        "回复一条消息但不劫持事件（其他匹配程序仍会执行；AstrBot 将不再回复）。",
    },
    {
      type: "blocky_return_msg",
      message0: "返回消息 %1",
      args0: [{ type: "input_value", name: "TEXT", check: "String" }],
      previousStatement: null,
      nextStatement: null,
      colour: 210,
      tooltip:
        "回复消息并劫持事件（返回消息模式）：阻止 AstrBot 继续处理本次消息。",
    },
    {
      type: "blocky_forward",
      message0: "传出消息（交给 AstrBot 继续处理）",
      previousStatement: null,
      nextStatement: null,
      colour: 210,
      tooltip: "放行消息（传出消息模式），交给 AstrBot 继续处理并回复。",
    },
    {
      type: "blocky_stop",
      message0: "停止事件传播",
      previousStatement: null,
      nextStatement: null,
      colour: 210,
      tooltip: "立即停止事件传播，AstrBot 不再处理。",
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
      tooltip:
        "调用当前会话的 AI 模型，返回回答文本；受程序「可用模型」白名单约束。",
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
      controls: false,
      wheel: true,
      startScale: 0.9,
      maxScale: 3,
      minScale: 0.3,
      scaleSpeed: 1.1,
    },
    trashcan: false,
    scrollbars: true,
    sounds: false,
  });
  workspace.addChangeListener((e) => {
    if (loading) return;
    // UI 类事件（主题切换 THEME_CHANGE、选中、视图变化等）不代表内容被修改，
    // 否则刚进入页面时 setTheme 就会把 dirty 置位，导致切换程序误弹"未保存"提示。
    if (e && e.isUiEvent) return;
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
      '<div class="empty-state">暂无程序<br/>点击「新建」创建第一个程序</div>';
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
    meta.textContent = `${ctypeLabel(p.content_type)} · 优先级 ${
      p.priority
    } · ${fmtTime(p.last_run_at)}${
      p.last_error ? " · " + p.last_error : ""
    }`;
    info.appendChild(name);
    info.appendChild(meta);

    const actions = document.createElement("div");
    actions.className = "p-actions";
    const dupBtn = document.createElement("button");
    dupBtn.className = "icon-btn";
    dupBtn.title = "复制";
    dupBtn.innerHTML = `<img class="icon" src="${IMG_COPY}" alt="复制" />`;
    dupBtn.onclick = (e) => {
      e.stopPropagation();
      duplicateProgram(p.id);
    };
    const delBtn = document.createElement("button");
    delBtn.className = "icon-btn danger";
    delBtn.title = "删除";
    delBtn.innerHTML = `<img class="icon" src="${IMG_DELETE}" alt="删除" />`;
    delBtn.onclick = (e) => {
      e.stopPropagation();
      deleteProgram(p.id);
    };
    actions.appendChild(dupBtn);
    actions.appendChild(delBtn);

    const toggle = document.createElement("label");
    toggle.className = "icon-toggle";
    toggle.title = "启用/关闭";
    toggle.onclick = (e) => e.stopPropagation();
    const toggleInput = document.createElement("input");
    toggleInput.type = "checkbox";
    toggleInput.checked = !!p.enabled;
    const toggleImg = document.createElement("img");
    toggleImg.className = "toggle-check";
    toggleImg.src = toggleInput.checked ? IMG_CHECK_OK : IMG_CHECK;
    toggleImg.alt = "启用";
    toggleInput.onclick = (e) => {
      e.stopPropagation();
      toggleImg.src = toggleInput.checked ? IMG_CHECK_OK : IMG_CHECK;
      toggleProgram(p.id, toggleInput.checked);
    };
    toggle.appendChild(toggleInput);
    toggle.appendChild(toggleImg);

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
  if (dirty) {
    const ok = await confirmDialog(
      "当前程序有未保存的修改，是否放弃？",
      { title: "切换程序", okText: "放弃修改" },
    );
    if (!ok) return;
  }
  try {
    const res = await apiGet("programs/" + id);
    loadProgram(res.program);
  } catch (err) {
    showToast(err.message || "加载程序失败", true);
  }
}

function enableEditor() {
  [
    "nameInput",
    "descriptionInput",
    "enabledCheck",
    "priorityInput",
    "timeoutInput",
    "triggerType",
    "triggerValue",
    "modelInput",
    "addModelBtn",
    "loadModelsBtn",
    "saveBtn",
    "testBtn",
    "resetBtn",
  ].forEach((id) => {
    $(id).disabled = false;
  });
}

function loadProgram(p) {
  currentId = p.id;
  loading = true;
  dirty = false;
  enableEditor();

  $("nameInput").value = p.name || "";
  $("descriptionInput").value = p.description || "";
  $("ctypeBadge").textContent = ctypeLabel(p.content_type);
  $("enabledCheck").checked = !!p.enabled;
  syncToolbarCheckIcon();
  $("priorityInput").value = p.priority || 0;
  $("timeoutInput").value = p.timeout || 30;
  const trigType = p.trigger && p.trigger.type ? p.trigger.type : "all";
  $("triggerType").value = trigType;
  $("triggerValue").value =
    (trigType === "contains" || trigType === "prefix" || trigType === "regex") &&
    p.trigger
      ? p.trigger.value || ""
      : "";
  updateTriggerValueState();
  $("idBadge").textContent = p.id;
  $("testResult").textContent = "";
  $("testResult").classList.remove("err");
  selectedModels = Array.isArray(p.models) ? p.models.slice() : [];
  renderModels();

  currentWorkspaceState = null;
  try {
    const raw = p.workspace;
    if (raw) currentWorkspaceState = JSON.parse(raw);
  } catch (err) {
    currentWorkspaceState = null;
  }

  $("codeEditor").value = p.code || "";
  applyEditorMode(p.content_type === "python" ? "python" : "blockly");
  renderSidebar();
  loading = false;
  window.dispatchEvent(new Event("resize"));
}

function applyEditorMode(mode) {
  // 积木模式与代码模式相互隔离，程序一经创建便固定编辑方式，不可切换。
  currentMode = mode === "python" ? "python" : "blockly";
  $("blocklyDiv").classList.toggle("hidden", currentMode !== "blockly");
  $("codeEditor").classList.toggle("hidden", currentMode !== "python");
  $("ctypeBadge").textContent = currentMode === "python" ? "代码" : "积木";
  if (currentMode === "blockly") {
    if (currentWorkspaceState) {
      Blockly.serialization.workspaces.load(currentWorkspaceState, workspace);
    } else {
      workspace.clear();
      Blockly.serialization.workspaces.load(defaultWorkspaceState(), workspace);
    }
  }
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
    content_type: currentMode === "blockly" ? "blockly" : "python",
    workspace: workspaceState ? JSON.stringify(workspaceState) : "",
    code: code,
    trigger: { type: triggerType, value: triggerValue },
    models: selectedModels.slice(),
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
  const choice = await openCreateDialog();
  if (!choice) return;
  try {
    const res = await apiPost("programs", {
      name: choice.name,
      content_type: choice.content_type,
    });
    programs.push(res.program);
    renderSidebar();
    await loadProgram(res.program);
    dirty = true;
    $("nameInput").focus();
    $("nameInput").select();
  } catch (err) {
    showToast(err.message || "新建失败", true);
  }
}

function clearEditor() {
  currentId = null;
  currentWorkspaceState = null;
  currentMode = "blockly";
  selectedModels = [];
  renderModels();
  workspace.clear();
  $("codeEditor").value = "";
  $("nameInput").value = "";
  $("descriptionInput").value = "";
  $("enabledCheck").checked = false;
  syncToolbarCheckIcon();
  $("priorityInput").value = 0;
  $("timeoutInput").value = 30;
  $("triggerType").value = "all";
  $("triggerValue").value = "";
  updateTriggerValueState();
  $("idBadge").textContent = "";
  $("ctypeBadge").textContent = "积木";
  $("testResult").textContent = "";
  $("testResult").classList.remove("err");
  [
    "nameInput",
    "descriptionInput",
    "enabledCheck",
    "priorityInput",
    "timeoutInput",
    "triggerType",
    "triggerValue",
    "modelInput",
    "addModelBtn",
    "loadModelsBtn",
    "saveBtn",
    "testBtn",
    "resetBtn",
  ].forEach((id) => {
    $(id).disabled = true;
  });
}

async function deleteProgram(id) {
  const ok = await confirmDialog("确定删除该程序？此操作不可恢复。", {
    title: "删除程序",
    okText: "删除",
    danger: true,
  });
  if (!ok) return;
  try {
    await apiPost("programs/" + id + "/delete", {});
    if (currentId === id) {
      clearEditor();
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
    if (currentId === id) {
      $("enabledCheck").checked = !!res.enabled;
      syncToolbarCheckIcon();
    }
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
    if (res.stopped) {
      lines.push("[事件] 已停止（返回消息：AstrBot 将不再处理）");
    } else {
      lines.push("[事件] 未停止（传出消息：将继续交给 AstrBot 处理）");
    }
    lines.push(`[耗时] ${res.cost}s`);
    if (!lines.length) lines.push("（程序无任何输出）");
    const el = $("testResult");
    el.innerHTML = "";
    el.classList.toggle("err", !!res.error);
    for (const line of lines) {
      const row = document.createElement("div");
      if (line.startsWith("[错误]")) row.className = "err-line";
      row.textContent = line;
      el.appendChild(row);
    }
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

/* ---------- 可用模型白名单（提供商 ID + 模型 ID） ---------- */

function modelDisplay(id) {
  const parts = String(id || "").split(":");
  if (parts.length > 1) {
    return `${parts[0]} / ${parts.slice(1).join(":")}`;
  }
  return id;
}

async function loadAvailableModels() {
  try {
    const res = await apiGet("models");
    availableModels = res.models || [];
    const list = $("modelList");
    list.innerHTML = "";
    for (const m of availableModels) {
      const opt = document.createElement("option");
      opt.value = m.id;
      opt.textContent = `${m.provider} · ${m.model}`;
      list.appendChild(opt);
    }
  } catch (err) {
    showToast(err.message || "加载模型列表失败", true);
  }
}

function renderModels() {
  const chips = $("modelChips");
  chips.innerHTML = "";
  if (!selectedModels.length) {
    const hint = document.createElement("span");
    hint.className = "chips-empty";
    hint.textContent = "不限制";
    chips.appendChild(hint);
    return;
  }
  for (const m of selectedModels) {
    const chip = document.createElement("span");
    chip.className = "chip";
    const label = document.createElement("span");
    label.textContent = modelDisplay(m);
    label.title = m;
    const rm = document.createElement("button");
    rm.type = "button";
    rm.className = "chip-remove";
    rm.innerHTML = `<img class="icon icon-sm" src="${IMG_DELETE}" alt="移除" />`;
    rm.onclick = () => {
      selectedModels = selectedModels.filter((x) => x !== m);
      renderModels();
      markDirty();
    };
    chip.appendChild(label);
    chip.appendChild(rm);
    chips.appendChild(chip);
  }
}

function addModel(name) {
  name = (name || "").trim();
  if (!name) return;
  if (selectedModels.includes(name)) {
    showToast(`模型 ${modelDisplay(name)} 已在列表中`);
    return;
  }
  selectedModels.push(name);
  renderModels();
  markDirty();
}

function markDirty() {
  if (!loading) dirty = true;
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
  $("resetBtn").onclick = () => {
    if (!currentId) return;
    confirmDialog(
      "放弃未保存的修改，重新加载当前程序？",
      { title: "重置", okText: "重置" },
    ).then(async (ok) => {
      if (!ok) return;
      try {
        const res = await apiGet("programs/" + currentId);
        loadProgram(res.program);
        showToast("已重置为上次保存的内容");
      } catch (err) {
        showToast(err.message || "重置失败", true);
      }
    });
  };
  $("exportAllBtn").onclick = exportAll;
  $("collapseBtn").onclick = () => {
    $("sidebar").classList.toggle("collapsed");
  };

  const importBtn = $("importBtn");
  const importFile = $("importFile");
  importBtn.onclick = () => importFile.click();
  importFile.onchange = (e) => {
    importFromFile(e.target.files[0]);
    e.target.value = "";
  };

  $("triggerType").onchange = updateTriggerValueState;

  $("enabledCheck").addEventListener("change", syncToolbarCheckIcon);
  syncToolbarCheckIcon();

  const bindDirty = (id) => {
    const el = $(id);
    el.addEventListener("input", markDirty);
    el.addEventListener("change", markDirty);
  };
  [
    "nameInput",
    "descriptionInput",
    "enabledCheck",
    "priorityInput",
    "timeoutInput",
    "triggerType",
    "triggerValue",
    "codeEditor",
  ].forEach(bindDirty);

  $("testChat").addEventListener("input", markDirty);

  $("addModelBtn").onclick = () => {
    addModel($("modelInput").value);
    $("modelInput").value = "";
  };
  $("modelInput").addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      addModel($("modelInput").value);
      $("modelInput").value = "";
    }
  });
  $("loadModelsBtn").onclick = loadAvailableModels;

  window.addEventListener("beforeunload", (e) => {
    if (dirty) {
      e.preventDefault();
      e.returnValue = "";
    }
  });

  bindConfirmModal();
  bindCreateModal();
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
    loadAvailableModels();
    await refreshPrograms();
    if (programs.length) {
      await selectProgram(programs[0].id);
    }
  } catch (err) {
    showToast("初始化失败：" + (err.message || err), true);
  }
})();
