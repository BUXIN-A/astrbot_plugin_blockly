/* Blockly 主题设置页面逻辑（独立插件页面）。
 *
 * 主题设置已从 Blockly 编辑页面迁移到本独立页面：
 * - 切换应用主题（内置 default/dark / 自定义主题）；
 * - 导入主题（zip）、导出指定自定义主题（zip）；
 * - 自定义主题可编辑文件树（内置主题的设置/删除按钮禁用）；
 * - 主题只影响 Blockly 编辑页面，不影响本设置页面。
 */
"use strict";

const $ = (id) => document.getElementById(id);
const bridge = window.AstrBotPluginPage;

let state = { active: "default", builtin: [], customThemes: [] };
let editTarget = null; // 正在编辑的主题 {id, name, files}
let editFile = ""; // 当前编辑的文件相对路径

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

function fmtSize(bytes) {
  if (!Number.isFinite(bytes) || bytes <= 0) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

/* ---------- 弹窗 ---------- */

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
  openModal("confirmModal");
  return new Promise((resolve) => {
    confirmResolve = resolve;
  });
}

function bindConfirm() {
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

/* ---------- 状态加载 ---------- */

async function loadState() {
  const res = await bridge.apiGet("theme");
  state = {
    active: res.active || "default",
    builtin: res.builtin || [],
    customThemes: res.custom_themes || [],
  };
  return state;
}

/* ---------- 主题列表 ---------- */

// 主题条目上的图标按钮（SVG 内联，避免图片资源 401）
function iconButton(kind, title, disabled) {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "theme-icon-btn" + (disabled ? " disabled" : "");
  btn.title = title;
  btn.disabled = !!disabled;
  if (kind === "settings") {
    btn.innerHTML =
      '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33h.09a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51h.09a1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82v.09a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>';
  } else if (kind === "export") {
    btn.innerHTML =
      '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>';
  } else {
    btn.innerHTML =
      '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/></svg>';
  }
  return btn;
}

function renderThemeList() {
  const list = $("themeList");
  list.innerHTML = "";
  const options = [
    {
      id: "default",
      label: "默认主题",
      desc: "插件默认样式",
      builtin: true,
    },
    {
      id: "dark",
      label: "深色主题",
      desc: "跟随 AstrBot 深色模式",
      builtin: true,
    },
  ];
  for (const t of state.customThemes) {
    options.push({
      id: t.id,
      label: t.name,
      desc: `自定义主题（${t.files.length} 个文件）`,
      builtin: false,
    });
  }

  for (const opt of options) {
    const row = document.createElement("div");
    row.className =
      "theme-item" + (state.active === opt.id ? " active" : "");
    row.title = "点击应用该主题";

    const nameEl = document.createElement("span");
    nameEl.className = "theme-name";
    nameEl.textContent = opt.label;

    const descEl = document.createElement("span");
    descEl.className = "theme-desc";
    descEl.textContent = opt.desc;

    const info = document.createElement("span");
    info.className = "theme-info";
    info.append(nameEl, descEl);

    const actions = document.createElement("span");
    actions.className = "theme-item-actions";

    // 设置（编辑文件）：内置主题禁用
    const setBtn = iconButton(
      "settings",
      opt.builtin ? "内置主题不可编辑" : "编辑主题文件",
      opt.builtin,
    );
    if (!opt.builtin) {
      setBtn.onclick = (e) => {
        e.stopPropagation();
        openEditor({
          id: opt.id,
          name: opt.label,
          files: state.customThemes.find((x) => x.id === opt.id)?.files || [],
        });
      };
    }
    actions.appendChild(setBtn);

    // 导出：内置主题无文件树，不提供导出
    if (!opt.builtin) {
      const expBtn = iconButton("export", "导出主题（zip）", false);
      expBtn.onclick = (e) => {
        e.stopPropagation();
        exportTheme(opt.id, opt.label);
      };
      actions.appendChild(expBtn);
    }

    // 删除：内置主题禁用
    const delBtn = iconButton(
      "trash",
      opt.builtin ? "内置主题不可删除" : "删除主题",
      opt.builtin,
    );
    if (!opt.builtin) {
      delBtn.onclick = (e) => {
        e.stopPropagation();
        deleteTheme(opt.id, opt.label);
      };
    }
    actions.appendChild(delBtn);

    row.append(info, actions);
    row.onclick = () => applyTheme(opt.id);
    list.appendChild(row);
  }
}

async function applyTheme(id) {
  if (state.active === id) return;
  try {
    await bridge.apiPost("theme", { active: id });
  } catch (err) {
    showToast(err.message || "应用主题失败", true);
    return;
  }
  state.active = id;
  renderThemeList();
  showToast("主题已切换，刷新「Blockly 可视化编程」页面后完全生效");
}

/* ---------- 导入 / 导出 / 删除 ---------- */

async function importTheme(file) {
  if (!file) return;
  try {
    const res = await bridge.upload("theme/import", file);
    state.active = res.active;
    await loadState();
    renderThemeList();
    showToast(
      `主题「${res.name || "导入的主题"}」已导入并启用，刷新 Blockly 编辑页面后完全生效`,
    );
  } catch (err) {
    showToast(err.message || "导入主题失败", true);
  }
}

function exportTheme(tid, label) {
  bridge
    .download("theme/export", { tid }, "blockly_theme.zip")
    .catch((err) => showToast(err.message || "导出主题失败", true));
}

async function deleteTheme(tid, label) {
  const ok = await confirmDialog(
    `确定删除主题「${label}」吗？删除后不可恢复。`,
    { title: "删除主题", okText: "删除" },
  );
  if (!ok) return;
  try {
    await bridge.apiPost(`theme/${tid}/delete`, {});
  } catch (err) {
    showToast(err.message || "删除主题失败", true);
    return;
  }
  // 删除的是正在编辑的主题时关闭编辑区
  if (editTarget && editTarget.id === tid) {
    closeEditor();
  }
  await loadState();
  renderThemeList();
  showToast("主题已删除");
}

/* ---------- 文件编辑 ---------- */

function openEditor(theme) {
  editTarget = theme;
  editFile = "";
  $("editorTitle").textContent = `编辑主题：${theme.name}`;
  $("editorEmpty").classList.add("hidden");
  $("editorWrap").classList.remove("hidden");
  $("fileContent").value = "";
  $("fileSave").disabled = true;
  renderFileTree();
}

function closeEditor() {
  editTarget = null;
  editFile = "";
  $("editorTitle").textContent = "文件编辑";
  $("editorEmpty").classList.remove("hidden");
  $("editorWrap").classList.add("hidden");
  $("fileContent").value = "";
  $("fileSave").disabled = true;
}

function renderFileTree() {
  const tree = $("fileTree");
  tree.innerHTML = "";
  if (!editTarget || !editTarget.files.length) {
    tree.innerHTML = '<div class="file-tree-empty">主题内没有文件</div>';
    return;
  }
  for (const f of editTarget.files) {
    const item = document.createElement("button");
    item.type = "button";
    item.className =
      "file-tree-item" + (f.path === editFile ? " active" : "");
    item.title = f.path;
    item.onclick = () => selectFile(f.path);
    const nameEl = document.createElement("span");
    nameEl.textContent = f.path;
    const sizeEl = document.createElement("span");
    sizeEl.className = "file-tree-size";
    sizeEl.textContent = fmtSize(f.size);
    item.append(nameEl, sizeEl);
    tree.appendChild(item);
  }
}

async function selectFile(path) {
  if (!editTarget) return;
  editFile = path;
  renderFileTree();
  try {
    const res = await bridge.apiGet(`theme/${editTarget.id}/file`, { path });
    $("fileContent").value = res.content || "";
  } catch (err) {
    $("fileContent").value = "";
    showToast(err.message || "读取文件失败", true);
  }
  $("fileSave").disabled = false;
}

async function saveFile() {
  if (!editTarget || !editFile) return;
  try {
    await bridge.apiPost(`theme/${editTarget.id}/file`, {
      path: editFile,
      content: $("fileContent").value,
    });
  } catch (err) {
    showToast(err.message || "保存文件失败", true);
    return;
  }
  showToast("文件已保存");
}

/* ---------- 启动 ---------- */

async function init() {
  try {
    const ctx = await bridge.ready();
    document.title = ctx.pageTitle || "Blockly 主题设置";
    bindConfirm();
    $("importBtn").onclick = () => $("importFile").click();
    $("importFile").onchange = (e) => {
      importTheme(e.target.files[0]);
      e.target.value = "";
    };
    $("fileSave").onclick = saveFile;
    await loadState();
    renderThemeList();
  } catch (err) {
    showToast("初始化失败：" + (err.message || err), true);
  }
}

init();
