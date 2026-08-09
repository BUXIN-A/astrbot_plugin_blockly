"""导入导出逻辑的单元测试。

覆盖 export 剔除内部字段、import 随机 id / 默认不启用 / 不会覆盖已有程序等行为。
"""

import asyncio
import sys
import types
import tempfile
import time
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
    web_mod.request = types.SimpleNamespace(json=staticmethod(lambda default=None: default), files=staticmethod(lambda: {}))
    path_mod.get_astrbot_plugin_data_path = lambda: str(Path(tempfile.gettempdir()) / "blockly_test_data")
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
    sys.modules["astrbot.core.star.filter"] = types.ModuleType("astrbot.core.star.filter")
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
    # 缺少 name 应被拒绝（error_response stub 返回 None），不导入任何条目
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
        "name": "导入程序",
        "programs": [
            {
                "id": "some-old-id",
                "name": "原导入名",
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
    new_program = [p for p in imported if p.id != existing_id][0]
    assert res["ok"] is True
    assert res["imported"] == 1
    # 新 id，且不等于原 id
    assert new_program.id != "some-old-id"
    # 使用统一命名，而非导出文件中的原名
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
        "name": "同名",
        "programs": [{"content_type": "blockly"}],
    }
    res = asyncio.run(plugin._import_data(body))
    # 与已有程序同名应拒绝（error_response stub 返回 None），不导入任何条目
    assert res is None
    assert len(plugin.manager.list_programs()) == 1