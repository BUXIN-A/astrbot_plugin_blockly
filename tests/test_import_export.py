"""导入导出逻辑的单元测试。

覆盖 export 剔除内部字段、import 随机 id / 默认不启用 / 不会覆盖已有程序等行为。
"""

import asyncio
import base64
import io
import sys
import tempfile
import types
import zipfile
from pathlib import Path

# main.py 依赖 astrbot 环境，这里用轻量 stub 让模块可导入测试。
if "astrbot" not in sys.modules:
    astrbot_mod = types.ModuleType("astrbot")
    api_mod = types.ModuleType("astrbot.api")
    event_mod = types.ModuleType("astrbot.api.event")
    filter_mod = types.ModuleType("astrbot.api.event.filter")
    star_mod = types.ModuleType("astrbot.api.star")
    web_mod = types.ModuleType("astrbot.api.web")
    core_mod = types.ModuleType("astrbot.core")
    star_f_mod = types.ModuleType("astrbot.core.star")
    filter_cmd_mod = types.ModuleType("astrbot.core.star.filter.command")
    star_handler_mod = types.ModuleType("astrbot.core.star.star_handler")
    utils_mod = types.ModuleType("astrbot.core.utils")
    path_mod = types.ModuleType("astrbot.core.utils.astrbot_path")

    class _AstrMessageEvent:
        pass

    class _Star:
        def __init__(self, context):
            self.context = context

    class _Context:
        pass

    def _noop_decorator(*args, **kwargs):
        def deco(fn):
            return fn

        return deco

    filter_mod.PlatformAdapterType = object
    filter_mod.EventMessageType = type("EventMessageType", (), {"ALL": object()})
    filter_mod.PermissionType = type("PermissionType", (), {"ADMIN": object()})
    filter_mod.command = _noop_decorator
    filter_mod.event_message_type = _noop_decorator
    filter_mod.permission_type = _noop_decorator
    event_mod.AstrMessageEvent = _AstrMessageEvent
    event_mod.filter = filter_mod
    star_mod.Context = _Context
    star_mod.Star = _Star
    web_mod.error_response = lambda *a, **k: None
    web_mod.file_response = lambda *a, **k: None
    web_mod.json_response = lambda data, *a, **k: data

    # request 的 json/files/query 可配置，便于测试需要请求体的 API
    REQUEST_STATE = {"json": None, "files": {}, "query": {}}

    async def _req_json(default=None):
        return REQUEST_STATE["json"] if REQUEST_STATE["json"] is not None else default

    async def _req_files():
        return REQUEST_STATE["files"]

    def _req_query_get(key, default=None):
        return REQUEST_STATE["query"].get(key, default)

    web_mod.request = types.SimpleNamespace(
        json=staticmethod(_req_json),
        files=staticmethod(_req_files),
        query=types.SimpleNamespace(get=staticmethod(_req_query_get)),
    )
    path_mod.get_astrbot_plugin_data_path = lambda: str(
        Path(tempfile.gettempdir()) / "blockly_test_data"
    )
    star_handler_mod.star_handlers_registry = types.SimpleNamespace(
        get_handlers_by_module_name=lambda m: [],
        _handlers=[],
    )
    filter_cmd_mod.GreedyStr = object

    api_mod.event = event_mod
    api_mod.star = star_mod
    api_mod.web = web_mod
    core_mod.star = star_f_mod
    star_f_mod.filter = filter_cmd_mod
    star_f_mod.star_handler = star_handler_mod
    core_mod.utils = utils_mod
    utils_mod.astrbot_path = path_mod
    astrbot_mod.api = api_mod
    astrbot_mod.core = core_mod
    sys.modules["astrbot"] = astrbot_mod
    sys.modules["astrbot.api"] = api_mod
    sys.modules["astrbot.api.event"] = event_mod
    sys.modules["astrbot.api.event.filter"] = filter_mod
    sys.modules["astrbot.api.star"] = star_mod
    sys.modules["astrbot.api.web"] = web_mod
    sys.modules["astrbot.core"] = core_mod
    sys.modules["astrbot.core.star"] = star_f_mod
    sys.modules["astrbot.core.star.filter"] = types.ModuleType(
        "astrbot.core.star.filter"
    )
    sys.modules["astrbot.core.star.filter.command"] = filter_cmd_mod
    sys.modules["astrbot.core.star.star_handler"] = star_handler_mod
    sys.modules["astrbot.core.utils"] = utils_mod
    sys.modules["astrbot.core.utils.astrbot_path"] = path_mod

from blockly.manager import BlocklyManager
from blockly.program import BlocklyProgram
from main import BlocklyPlugin


def _make_plugin(tmp_path: Path) -> BlocklyPlugin:
    """构造一个可用的 BlocklyPlugin（仅依赖 manager，不触发网络/API）。"""
    plugin = BlocklyPlugin.__new__(BlocklyPlugin)
    plugin.manager = BlocklyManager(tmp_path)
    return plugin


def test_export_strips_internal_fields(tmp_path):
    plugin = _make_plugin(tmp_path)
    program = BlocklyProgram(
        name="测试程序",
        enabled=True,
        workspace='{"blocks": {}}',
        code="await _blk.reply('hi')",
    )
    data = plugin._export_data([program])
    exported = data["programs"][0]
    assert exported["workspace"] is not None
    # name 不应导出（导入时自行设置）
    assert "name" not in exported
    # 内部字段不应导出
    assert "id" not in exported
    assert "enabled" not in exported
    assert "created_at" not in exported
    assert "updated_at" not in exported
    assert "last_run_at" not in exported
    assert "run_count" not in exported
    assert "last_error" not in exported


def test_import_requires_name(tmp_path):
    plugin = _make_plugin(tmp_path)
    body = {
        "programs": [
            {
                "content_type": "blockly",
                "workspace": '{"blocks": {}}',
                "code": "",
            }
        ]
    }
    res = asyncio.run(plugin._import_data(body))
    # 缺少 import_name 应被拒绝（error_response stub 返回 None），不导入任何条目
    assert res is None
    assert plugin.manager.list_programs() == []


def test_import_assigns_new_id_and_disables(tmp_path):
    plugin = _make_plugin(tmp_path)
    # 先创建一个已有程序，验证导入不会覆盖它
    existing = asyncio.run(plugin.manager.create(name="已有程序"))
    existing.enabled = True
    asyncio.run(plugin.manager.update(existing))
    existing_id = existing.id

    body = {
        "programs": [
            {
                "id": "some-old-id",
                "name": "原导入名",
                "import_name": "导入程序",
                "enabled": True,
                "content_type": "blockly",
                "workspace": '{"blocks": {}}',
                "code": "",
                "trigger": {"type": "all", "value": ""},
                "event_type": "message",
                "event_attr": "any",
                "models": [],
                "priority": 0,
                "timeout": 30,
            }
        ],
    }
    res = asyncio.run(plugin._import_data(body))

    imported = plugin.manager.list_programs()
    new_program = next(p for p in imported if p.id != existing_id)
    assert res["ok"] is True
    assert res["imported"] == 1
    # 新 id，且不等于原 id
    assert new_program.id != "some-old-id"
    # 使用 import_name 命名，而非导出文件中的原名
    assert new_program.name == "导入程序"
    # 默认不启用
    assert new_program.enabled is False
    # 已有程序未被覆盖
    assert plugin.manager.get(existing_id) is not None
    assert plugin.manager.get(existing_id).name == "已有程序"


def test_import_rejects_name_conflict(tmp_path):
    plugin = _make_plugin(tmp_path)
    asyncio.run(plugin.manager.create(name="同名"))
    body = {
        "programs": [
            {"import_name": "同名", "content_type": "blockly"},
        ]
    }
    res = asyncio.run(plugin._import_data(body))
    # 与已有程序同名应拒绝（error_response stub 返回 None），不导入任何条目
    assert res is None
    assert len(plugin.manager.list_programs()) == 1


def test_import_multiple_programs_separate_names(tmp_path):
    plugin = _make_plugin(tmp_path)
    body = {
        "programs": [
            {"import_name": "程序甲", "content_type": "blockly"},
            {"import_name": "程序乙", "content_type": "blockly"},
        ]
    }
    res = asyncio.run(plugin._import_data(body))
    assert res["ok"] is True
    assert res["imported"] == 2
    names = {p.name for p in plugin.manager.list_programs()}
    assert names == {"程序甲", "程序乙"}


def test_import_rejects_duplicate_names(tmp_path):
    plugin = _make_plugin(tmp_path)
    body = {
        "programs": [
            {"import_name": "重名", "content_type": "blockly"},
            {"import_name": "重名", "content_type": "blockly"},
        ]
    }
    res = asyncio.run(plugin._import_data(body))
    # 导入条目之间重名应拒绝
    assert res is None
    assert plugin.manager.list_programs() == []


# ---------- 主题 ----------


def _make_plugin_with_theme(tmp_path: Path):
    """构造带主题存储的插件。"""
    from blockly.theme import ThemeStore

    plugin = _make_plugin(tmp_path)
    plugin.themes = ThemeStore(tmp_path / "themes")
    return plugin


def _build_theme_zip(css: str, name: str = "我的主题") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("theme_name.txt", name)
        zf.writestr("theme.css", css)
    return buf.getvalue()


def test_theme_get_default(tmp_path):
    plugin = _make_plugin_with_theme(tmp_path)
    res = asyncio.run(plugin.api_get_theme())
    assert res["ok"] is True
    assert res["active"] == "default"
    assert res["custom_themes"] == []
    assert res["active_css"] == ""


def test_theme_import_and_file_edit(tmp_path):
    """导入 zip 生成主题目录与文件树，支持读取/保存/越界拦截。"""
    plugin = _make_plugin_with_theme(tmp_path)
    zipped = _build_theme_zip(".theme-item{color:red}", "红色主题")
    REQUEST_STATE["json"] = {
        "file_b64": base64.b64encode(zipped).decode("ascii"),
    }
    res = asyncio.run(plugin.api_import_theme())
    assert res["ok"] is True
    tid = res["active"]
    assert tid not in ("default", "dark")
    assert res["name"] == "红色主题"
    assert "color:red" in res["css"]

    # 主题列表含文件树
    got = asyncio.run(plugin.api_get_theme())
    assert got["active"] == tid
    assert len(got["custom_themes"]) == 1
    theme = got["custom_themes"][0]
    assert theme["id"] == tid
    paths = {f["path"] for f in theme["files"]}
    assert "theme.css" in paths and "theme_name.txt" in paths

    # 读取文件
    REQUEST_STATE["query"] = {"path": "theme.css"}
    f = asyncio.run(plugin.api_theme_file(tid))
    assert f["ok"] is True
    assert "color:red" in f["content"]

    # 保存文件
    REQUEST_STATE["json"] = {"path": "theme.css", "content": "body{}"}
    s = asyncio.run(plugin.api_theme_file_save(tid))
    assert s["ok"] is True
    assert plugin.themes.main_css(tid) == "body{}"

    # 路径越界（../）拒绝
    REQUEST_STATE["json"] = {"path": "../evil.css", "content": "x"}
    s2 = asyncio.run(plugin.api_theme_file_save(tid))
    assert s2 is None

    REQUEST_STATE["query"] = {}
    REQUEST_STATE["json"] = None


def test_theme_switch_and_delete(tmp_path):
    """多主题导入、切换激活、删除激活主题后重置为默认。"""
    plugin = _make_plugin_with_theme(tmp_path)

    REQUEST_STATE["json"] = {
        "file_b64": base64.b64encode(_build_theme_zip(".a{}", "主题A")).decode("ascii"),
    }
    res_a = asyncio.run(plugin.api_import_theme())
    tid_a = res_a["active"]

    REQUEST_STATE["json"] = {
        "file_b64": base64.b64encode(_build_theme_zip(".b{}", "主题B")).decode("ascii"),
    }
    res_b = asyncio.run(plugin.api_import_theme())
    tid_b = res_b["active"]
    assert tid_a != tid_b

    # 切换到主题 A
    REQUEST_STATE["json"] = {"active": tid_a}
    sv = asyncio.run(plugin.api_save_theme())
    assert sv["ok"] is True
    assert sv["active"] == tid_a
    assert ".a{}" in sv["css"]

    # 删除激活的主题 A：删除后重置为默认，列表只剩 B
    del_res = asyncio.run(plugin.api_theme_delete(tid_a))
    assert del_res["ok"] is True
    assert del_res["active"] == "default"

    got = asyncio.run(plugin.api_get_theme())
    assert len(got["custom_themes"]) == 1
    assert got["custom_themes"][0]["id"] == tid_b

    REQUEST_STATE["json"] = None


def test_theme_delete_builtin_rejected(tmp_path):
    plugin = _make_plugin_with_theme(tmp_path)
    res = asyncio.run(plugin.api_theme_delete("default"))
    assert res is None  # error_response stub


def test_theme_import_missing_file(tmp_path):
    plugin = _make_plugin_with_theme(tmp_path)
    REQUEST_STATE["json"] = {}
    res = asyncio.run(plugin.api_import_theme())
    # 缺少文件时应报错（error_response stub 返回 None）
    assert res is None
    assert plugin.themes.list_custom() == []
    REQUEST_STATE["json"] = None


def test_theme_import_zip_traversal_sanitized(tmp_path):
    """zip 条目含 ../ 时应被剔除，不产生目录穿越。"""
    plugin = _make_plugin_with_theme(tmp_path)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("theme_name.txt", "安全主题")
        zf.writestr("theme.css", "body{}")
        zf.writestr("../escape.txt", "evil")
    REQUEST_STATE["json"] = {
        "file_b64": base64.b64encode(buf.getvalue()).decode("ascii"),
    }
    res = asyncio.run(plugin.api_import_theme())
    assert res["ok"] is True
    # escape.txt 不应出现在主题目录外
    assert not (tmp_path / "escape.txt").exists()
    REQUEST_STATE["json"] = None


def _export_theme_captured(plugin, query: dict):
    """调用导出 API，捕获 file_response 参数。

    成功时返回 (结果, {path, filename})，失败（error_response）时返回 (None, {})。
    通过临时替换 main 模块的 file_response 绑定，验证导出 zip 的实际内容。
    """
    import main as main_mod

    captured = {}

    def _file_response(path, filename=None, content_type=None):
        captured["path"] = path
        captured["filename"] = filename
        return {"__file__": path, "__filename__": filename}

    original = main_mod.file_response
    main_mod.file_response = _file_response
    try:
        REQUEST_STATE["query"] = dict(query)
        result = asyncio.run(plugin.api_export_theme())
    finally:
        main_mod.file_response = original
        REQUEST_STATE["query"] = {}
    return result, captured


def test_theme_export_by_tid(tmp_path):
    """指定 tid 导出自定义主题：即使当前激活的不是该主题也能导出。"""
    plugin = _make_plugin_with_theme(tmp_path)
    REQUEST_STATE["json"] = {
        "file_b64": base64.b64encode(_build_theme_zip(".a{}", "导出主题A")).decode(
            "ascii"
        ),
    }
    res = asyncio.run(plugin.api_import_theme())
    tid = res["active"]
    REQUEST_STATE["json"] = None

    # 切换到内置主题，验证 tid 指定导出不受激活状态影响
    REQUEST_STATE["json"] = {"active": "default"}
    asyncio.run(plugin.api_save_theme())
    REQUEST_STATE["json"] = None

    result, captured = _export_theme_captured(plugin, {"tid": tid})
    assert result is not None
    assert captured["path"]
    assert "导出主题A" in captured["filename"]
    # 生成的 zip 含主题文件
    with zipfile.ZipFile(captured["path"]) as zf:
        names = set(zf.namelist())
    assert "theme.css" in names and "theme_name.txt" in names


def test_theme_export_fallback_to_active(tmp_path):
    """未指定 tid 时导出当前激活的自定义主题。"""
    plugin = _make_plugin_with_theme(tmp_path)
    REQUEST_STATE["json"] = {
        "file_b64": base64.b64encode(_build_theme_zip(".b{}", "激活主题")).decode(
            "ascii"
        ),
    }
    asyncio.run(plugin.api_import_theme())  # 导入后自动激活
    REQUEST_STATE["json"] = None

    result, captured = _export_theme_captured(plugin, {})
    assert result is not None
    assert "激活主题" in captured["filename"]


def test_theme_export_builtin_available(tmp_path):
    """内置主题可导出：内容为默认样式（theme.css + theme_name.txt）。"""
    plugin = _make_plugin_with_theme(tmp_path)
    for tid, expect_name in (("default", "默认主题"), ("dark", "深色主题")):
        result, captured = _export_theme_captured(plugin, {"tid": tid})
        assert result is not None
        assert captured["path"]
        assert expect_name in captured["filename"]
        with zipfile.ZipFile(captured["path"]) as zf:
            names = set(zf.namelist())
            name_content = zf.read("theme_name.txt").decode("utf-8").strip()
        assert "theme.css" in names and "theme_name.txt" in names
        assert name_content == expect_name


def test_theme_export_missing_rejected(tmp_path):
    """导出不存在的主题应被拒绝。"""
    plugin = _make_plugin_with_theme(tmp_path)
    result, captured = _export_theme_captured(plugin, {"tid": "not-exist"})
    assert result is None
    assert not captured


def test_theme_create(tmp_path):
    """新增主题：内容为默认主题样式、自动激活、重名自动追加序号。"""
    plugin = _make_plugin_with_theme(tmp_path)
    REQUEST_STATE["json"] = {}
    res = asyncio.run(plugin.api_create_theme())
    assert res["ok"] is True
    tid = res["id"]
    assert tid not in ("default", "dark")
    assert res["name"] == "新主题"
    assert res["active"] == tid
    # 内容为默认主题样式
    assert plugin.themes.read_file(tid, "theme_name.txt").strip() == "新主题"
    assert plugin.themes.read_file(tid, "theme.css") != ""
    # 再次创建同名自动追加序号
    res2 = asyncio.run(plugin.api_create_theme())
    assert res2["name"] == "新主题 (2)"
    assert res2["id"] != tid
    REQUEST_STATE["json"] = None


def test_theme_create_includes_icons(tmp_path):
    """新增主题包含默认 UI 图标（img/ 单独文件夹）。"""
    plugin = _make_plugin_with_theme(tmp_path)
    REQUEST_STATE["json"] = {}
    res = asyncio.run(plugin.api_create_theme())
    tid = res["id"]
    REQUEST_STATE["json"] = None
    paths = {f["path"] for f in res["files"]}
    assert any(p.startswith("img/") for p in paths)
    # 图标为可读的二进制文件
    assert plugin.themes.read_file_bytes(tid, "img/icon.png") is not None


def test_theme_export_builtin_includes_icons(tmp_path):
    """内置主题导出含默认 UI 图标（img/ 文件夹）。"""
    plugin = _make_plugin_with_theme(tmp_path)
    result, captured = _export_theme_captured(plugin, {"tid": "default"})
    assert result is not None
    with zipfile.ZipFile(captured["path"]) as zf:
        names = set(zf.namelist())
    assert any(n.startswith("img/") for n in names)


def test_theme_file_binary_roundtrip(tmp_path):
    """二进制文件（图片图标）：base64 保存与读取，文本文件仍返回 content。"""
    plugin = _make_plugin_with_theme(tmp_path)
    REQUEST_STATE["json"] = {
        "file_b64": base64.b64encode(_build_theme_zip(".a{}")).decode("ascii"),
    }
    res = asyncio.run(plugin.api_import_theme())
    tid = res["active"]
    REQUEST_STATE["json"] = None

    # base64 保存 PNG 图标到 img/icon.png
    png = b"\x89PNG\r\n\x1a\nfake-png-content"
    REQUEST_STATE["json"] = {
        "path": "img/icon.png",
        "base64": base64.b64encode(png).decode("ascii"),
    }
    s = asyncio.run(plugin.api_theme_file_save(tid))
    assert s["ok"] is True
    REQUEST_STATE["json"] = None

    # 读取：二进制返回 base64 + mime，不含 content
    REQUEST_STATE["query"] = {"path": "img/icon.png"}
    f = asyncio.run(plugin.api_theme_file(tid))
    assert f["ok"] is True
    assert f["base64"] == base64.b64encode(png).decode("ascii")
    assert f["mime"] == "image/png"
    assert "content" not in f
    REQUEST_STATE["query"] = {}

    # 文本文件仍返回 content
    REQUEST_STATE["query"] = {"path": "theme.css"}
    f2 = asyncio.run(plugin.api_theme_file(tid))
    assert f2["ok"] is True
    assert "content" in f2
    assert "base64" not in f2
    REQUEST_STATE["query"] = {}
