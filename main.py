"""Blockly 可视化编程插件主入口。

本插件为 AstrBot 提供可视化编程能力：
- 使用 Blockly 积木（或直接编写 Python）创建"程序"；
- 监听全部消息事件，命中触发条件的程序会被执行（可回复/劫持消息，也可放行给 AstrBot）；
- 通过插件 Pages 提供独立的 WebUI 编辑器；
- 通过 /blockly 聊天指令提供轻量的程序管理能力。
"""

from __future__ import annotations

import asyncio
import json
import tempfile
import time
from pathlib import Path
from typing import Any

from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star
from astrbot.api.web import error_response, file_response, json_response, request
from astrbot.core.star.filter.command import GreedyStr
from astrbot.core.utils.astrbot_path import get_astrbot_plugin_data_path

try:  # AstrBot 以 data.plugins.<name>.main 的包形式加载插件
    from .blockly.manager import BlocklyManager
    from .blockly.program import (
        CONTENT_BLOCKLY,
        BlocklyProgram,
        new_id,
    )
    from .blockly.runtime import resolve_event_kind, run_program, simulate_program
except ImportError:  # 直接以脚本/独立目录方式加载插件时回退
    from blockly.manager import BlocklyManager
    from blockly.program import (
        CONTENT_BLOCKLY,
        BlocklyProgram,
        new_id,
    )
    from blockly.runtime import resolve_event_kind, run_program, simulate_program

PLUGIN_NAME = "astrbot_plugin_blockly"
# 监听优先级：远高于第三方插件默认值（0），仅次于 AstrBot 内置插件（maxsize）。
# 保证本插件最先处理消息，这样「返回消息/停止事件传播」劫持事件后其他插件不会再收到该消息。
DEFAULT_PRIORITY = 1000

# Web API 更新时允许写入的字段（白名单，避免覆盖内部字段）
UPDATABLE_FIELDS = (
    "name",
    "description",
    "enabled",
    "content_type",
    "workspace",
    "code",
    "trigger",
    "event_type",
    "event_attr",
    "models",
    "priority",
    "timeout",
)

# 事件类型到程序 event_type 的映射（部分支持事件，保留旧版全部消息行为）
# 事件类型判定见 blockly.runtime.resolve_event_kind

# 消息段类型到程序 event_attr 的映射（用于消息属性过滤）
EVENT_ATTR_SEGMENT_KINDS = {
    "plain": "text",
    "image": "image",
    "face": "face",
    "at": "at",
    "atall": "at",
    "record": "voice",
    "reply": "reply",
}


class BlocklyPlugin(Star):
    def __init__(self, context: Context, config: dict | None = None) -> None:
        super().__init__(context)
        self.config = config or {}
        plugin_name = getattr(self, "name", None) or PLUGIN_NAME
        data_dir = Path(get_astrbot_plugin_data_path()) / plugin_name
        self.manager = BlocklyManager(data_dir)
        self._register_web_apis()

    # ---------- 生命周期 ----------

    async def initialize(self) -> None:
        """插件激活时调用：应用配置的监听优先级并记录加载状态。"""
        self._apply_config_priority()
        self.logger.info(
            "Blockly 插件初始化完成，已加载 %d 个程序",
            len(self.manager.list_programs()),
        )

    async def terminate(self) -> None:
        """插件禁用/重载时调用。"""

    def _apply_config_priority(self) -> None:
        """将配置中的监听优先级写入本插件的事件监听器。

        装饰器在类定义时求值，此时还无法读取配置，因此在插件激活后手动覆盖。
        """
        try:
            from astrbot.core.star.star_handler import star_handlers_registry

            priority = int(self.config.get("priority") or DEFAULT_PRIORITY)
            module_path = self.__class__.__module__
            for handler in star_handlers_registry.get_handlers_by_module_name(
                module_path
            ):
                handler.extras_configs["priority"] = priority
            star_handlers_registry._handlers.sort(
                key=lambda h: -h.extras_configs.get("priority", 0),
            )
        except Exception as exc:  # noqa: BLE001 - 不因优先级调整失败而阻塞插件启动
            self.logger.warning("应用消息监听优先级失败：%s", exc)

    # ---------- 消息监听 ----------

    @filter.event_message_type(filter.EventMessageType.ALL, priority=DEFAULT_PRIORITY)
    async def on_message(self, event: AstrMessageEvent) -> None:
        """监听全部事件，执行所有命中触发条件的已启用程序。

        普通消息事件会做文本/属性过滤；撤回、新成员加入、戳一戳等通知事件
        按程序设置的 ``event_type`` 分派（见 :func:`_event_kind`）。
        """
        if not self._plugin_enabled():
            return
        kind = resolve_event_kind(event)
        if kind == "message":
            message = (event.message_str or "").strip()
            # 图片/表情/@/语音等消息 message_str 为空文本，不能因此跳过：
            # 是否处理交给触发条件与消息属性过滤（event_attr）。
            if message and self._is_skipped(message):
                return
            if self.config.get("admin_only_programs") and not event.is_admin():
                return
            programs = [
                p
                for p in self.manager.enabled_programs()
                if "message" in p.event_types
                and p.matches(event)
                and self._attr_matches(p, event)
            ]
        else:
            self.logger.info(
                "Blockly 收到通知事件 kind=%s, sender=%s，开始分派程序",
                kind,
                event.get_sender_id(),
            )
            if self.config.get("admin_only_programs") and not event.is_admin():
                return
            programs = [
                p for p in self.manager.enabled_programs() if kind in p.event_types
            ]
            # 旧版本生成的积木代码不含事件分支判断（只有 message 逻辑），
            # 通知事件执行它会造成误行为，跳过并提示用户重新保存一次。
            programs = self._filter_stale_code(kind, programs)
        if not programs:
            if kind == "message":
                for p in self.manager.enabled_programs():
                    self.logger.debug(
                        "Blockly 事件 message 未命中程序 %s：event_types=%s attr=%s",
                        p.name,
                        p.event_types,
                        p.event_attr,
                    )
            else:
                self.logger.info(
                    "Blockly 事件 %s 未命中任何程序（当前启用程序事件：%s）",
                    kind,
                    [p.event_types for p in self.manager.enabled_programs()],
                )
            return
        self.logger.debug(
            "Blockly 事件 %s 命中 %d 个程序：%s",
            kind,
            len(programs),
            [p.name for p in programs],
        )
        await self._run_programs(event, programs)

    def _filter_stale_code(
        self, kind: str, programs: list[BlocklyProgram]
    ) -> list[BlocklyProgram]:
        """过滤掉旧版本生成的、不含事件分支判断的积木程序。

        这类程序最初只保存了画布上第一个事件块的逻辑，在新版本的分派机制下
        会造成通知事件误执行消息分支，这里跳过并提示用户重新保存。
        """
        filtered: list[BlocklyProgram] = []
        for program in programs:
            if (
                program.content_type == CONTENT_BLOCKLY
                and "_blk.event_type" not in (program.code or "")
            ):
                self.logger.info(
                    "Blockly 程序 %s 的代码为旧版本生成（不含事件分支判断），"
                    "已跳过 %s 事件；请在弹出的 WebUI 编辑器中打开并保存一次程序",
                    program.name,
                    kind,
                )
                continue
            filtered.append(program)
        return filtered

    async def _run_programs(
        self,
        event: AstrMessageEvent,
        programs: list[BlocklyProgram],
    ) -> None:
        """按优先级依次执行程序；事件被停止（返回消息/停止积木）后不再执行后续程序。"""
        for program in programs:
            timeout = program.timeout or self._default_timeout()
            try:
                await run_program(program, self.context, event, timeout=timeout)
                program.mark_run()
            except asyncio.TimeoutError:
                program.mark_run(error="执行超时", success=False)
                self.logger.warning(
                    "Blockly 程序 %s(%s) 执行超时", program.name, program.id
                )
            except Exception as exc:  # noqa: BLE001 - 单个程序出错不影响其他程序
                program.mark_run(error=str(exc), success=False)
                self.logger.error(
                    "Blockly 程序 %s(%s) 执行出错：%s", program.name, program.id, exc
                )
            try:
                await self.manager.update(program)
            except Exception as exc:  # noqa: BLE001
                self.logger.warning("保存程序运行状态失败：%s", exc)
            if event.is_stopped():
                break

    # ---------- /blockly 聊天指令（仅管理员） ----------

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("blockly", alias={"blk"})
    async def blockly(self, event: AstrMessageEvent, args: GreedyStr = "") -> None:
        """Blockly 程序管理指令。"""
        parts = (args or "").strip().split()
        if not parts:
            yield event.plain_result(self._command_help())
            return
        action, *rest = parts
        try:
            if action == "list":
                yield event.plain_result(self._format_program_list())
            elif action == "on":
                yield event.plain_result(
                    await self._set_enabled(rest[0] if rest else "", True)
                )
            elif action == "off":
                yield event.plain_result(
                    await self._set_enabled(rest[0] if rest else "", False)
                )
            elif action == "new":
                yield event.plain_result(await self._command_new(" ".join(rest)))
            elif action == "delete":
                yield event.plain_result(
                    await self._command_delete(rest[0] if rest else "")
                )
            elif action == "reload":
                self.manager.load()
                yield event.plain_result("已从磁盘重新加载全部程序。")
            else:
                yield event.plain_result(self._command_help())
        except Exception as exc:
            self.logger.exception("执行 /blockly 指令失败")
            yield event.plain_result(f"执行出错：{exc}")

    def _command_help(self) -> str:
        """返回 /blockly 指令帮助文本。"""
        return (
            "Blockly 可视化编程指令：\n"
            "/blockly list - 列出所有程序\n"
            "/blockly new <名称> - 新建程序\n"
            "/blockly on <id> - 开启程序\n"
            "/blockly off <id> - 关闭程序\n"
            "/blockly delete <id> - 删除程序\n"
            "/blockly reload - 从磁盘重新加载\n\n"
            "更完整的功能请使用 WebUI（插件详情页打开 Blockly 页面）。"
        )

    def _format_program_list(self) -> str:
        """格式化程序列表文本。"""
        programs = self.manager.list_programs()
        if not programs:
            return "暂无程序。使用 /blockly new <名称> 创建，或到 WebUI 编辑。"
        lines = ["Blockly 程序列表："]
        for program in programs:
            state = "开" if program.enabled else "关"
            ctype = "代码" if program.content_type == "python" else "积木"
            lines.append(
                f"[{state}] {program.id} | {ctype} | {program.name}"
                + (f"（{program.last_error}）" if program.last_error else "")
            )
        return "\n".join(lines)

    async def _set_enabled(self, pid: str, enabled: bool) -> str:
        """开启或关闭指定程序。"""
        program = self.manager.get(pid)
        if not program:
            return f"未找到程序：{pid}。可使用 /blockly list 查看。"
        program.enabled = enabled
        await self.manager.update(program)
        return f"程序 {program.name} 已{'开启' if enabled else '关闭'}。"

    async def _command_new(self, name: str) -> str:
        """新建一个积木模式的程序。"""
        name = (name or "").strip() or "未命名程序"
        program = await self.manager.create(name=name)
        return f"已创建程序：{program.name}（id: {program.id}）。请到 WebUI 编辑逻辑。"

    async def _command_delete(self, pid: str) -> str:
        """删除指定程序。"""
        if not await self.manager.delete(pid):
            return f"未找到程序：{pid}。"
        return f"已删除程序：{pid}。"

    # ---------- Web API ----------

    def _register_web_apis(self) -> None:
        """注册插件 Web API 路由（供 Dashboard 转发调用）。"""
        prefix = f"/{PLUGIN_NAME}"
        ctx = self.context
        ctx.register_web_api(
            f"{prefix}/programs",
            self.api_list_programs,
            ["GET"],
            "获取 Blockly 程序列表",
        )
        ctx.register_web_api(
            f"{prefix}/programs", self.api_create_program, ["POST"], "新建 Blockly 程序"
        )
        ctx.register_web_api(
            f"{prefix}/programs/<pid>",
            self.api_get_program,
            ["GET"],
            "获取单个 Blockly 程序",
        )
        ctx.register_web_api(
            f"{prefix}/programs/<pid>",
            self.api_update_program,
            ["POST"],
            "更新 Blockly 程序",
        )
        ctx.register_web_api(
            f"{prefix}/programs/<pid>/delete",
            self.api_delete_program,
            ["POST"],
            "删除 Blockly 程序",
        )
        ctx.register_web_api(
            f"{prefix}/programs/<pid>/duplicate",
            self.api_duplicate_program,
            ["POST"],
            "复制 Blockly 程序",
        )
        ctx.register_web_api(
            f"{prefix}/programs/<pid>/toggle",
            self.api_toggle_program,
            ["POST"],
            "开关 Blockly 程序",
        )
        ctx.register_web_api(
            f"{prefix}/programs/<pid>/test",
            self.api_test_program,
            ["POST"],
            "测试运行 Blockly 程序",
        )
        ctx.register_web_api(
            f"{prefix}/models",
            self.api_list_models,
            ["GET"],
            "获取可用 AI 模型列表",
        )
        ctx.register_web_api(
            f"{prefix}/export", self.api_export, ["GET"], "导出全部 Blockly 程序"
        )
        ctx.register_web_api(
            f"{prefix}/export/<pid>",
            self.api_export_program,
            ["GET"],
            "导出单个 Blockly 程序",
        )
        ctx.register_web_api(
            f"{prefix}/import", self.api_import, ["POST"], "导入 Blockly 程序（JSON）"
        )
        ctx.register_web_api(
            f"{prefix}/import/file",
            self.api_import_file,
            ["POST"],
            "导入 Blockly 程序（文件）",
        )

    async def api_list_programs(self) -> Any:
        """返回全部程序（含运行统计，不含大字段），供前端列表渲染。"""
        return json_response(
            {
                "ok": True,
                "programs": [
                    self._program_summary(p) for p in self.manager.list_programs()
                ],
            }
        )

    def _program_summary(self, program: BlocklyProgram) -> dict:
        """轻量化的程序数据（列表用，剔除 workspace/code 大字段）。"""
        data = program.to_dict()
        data.pop("workspace", None)
        data.pop("code", None)
        return data

    async def api_create_program(self) -> Any:
        """新建程序（名称重复时后端自动追加序号）。"""
        body = await request.json(default={})
        program = await self.manager.create(
            name=str(body.get("name") or "未命名程序"),
            content_type=str(body.get("content_type") or CONTENT_BLOCKLY),
            workspace=body.get("workspace") or "",
            code=body.get("code") or "",
        )
        return json_response({"ok": True, "program": program.to_dict()})

    async def api_get_program(self, pid: str) -> Any:
        """获取单个程序。"""
        program = self.manager.get(pid)
        if not program:
            return error_response("程序不存在", status_code=404)
        return json_response({"ok": True, "program": program.to_dict()})

    async def api_update_program(self, pid: str) -> Any:
        """更新程序（仅接受白名单字段）。"""
        program = self.manager.get(pid)
        if not program:
            return error_response("程序不存在", status_code=404)
        body = await request.json(default={})
        data = program.to_dict()
        for key in body:
            if key in UPDATABLE_FIELDS:
                data[key] = body[key]
        data["updated_at"] = time.time()
        updated = BlocklyProgram.from_dict(data)
        await self.manager.update(updated)
        return json_response({"ok": True, "program": updated.to_dict()})

    async def api_delete_program(self, pid: str) -> Any:
        """删除程序。"""
        if not await self.manager.delete(pid):
            return error_response("程序不存在", status_code=404)
        return json_response({"ok": True})

    async def api_duplicate_program(self, pid: str) -> Any:
        """复制程序。"""
        clone = await self.manager.duplicate(pid)
        if not clone:
            return error_response("程序不存在", status_code=404)
        return json_response({"ok": True, "program": clone.to_dict()})

    async def api_toggle_program(self, pid: str) -> Any:
        """开关程序；不带 enabled 时切换当前状态。"""
        program = self.manager.get(pid)
        if not program:
            return error_response("程序不存在", status_code=404)
        body = await request.json(default={})
        if "enabled" in body:
            program.enabled = bool(body["enabled"])
        else:
            program.enabled = not program.enabled
        await self.manager.update(program)
        return json_response({"ok": True, "enabled": program.enabled})

    async def api_test_program(self, pid: str) -> Any:
        """在模拟事件上运行程序，返回测试结果。"""
        program = self.manager.get(pid)
        if not program:
            return error_response("程序不存在", status_code=404)
        body = await request.json(default={})
        result = await simulate_program(
            program,
            message=str(body.get("message") or ""),
            timeout=program.timeout or self._default_timeout(),
            chat_responses=body.get("chat_responses") or None,
            is_admin=bool(body.get("is_admin")),
            is_private=bool(body.get("is_private")),
            message_type=str(body.get("message_type") or "text"),
        )
        return json_response({"ok": True, **result})

    async def api_list_models(self) -> Any:
        """返回当前已配置的 AI 模型列表（提供商 ID + 模型 ID），供「可用模型」白名单选择。

        返回格式：[{"provider": 提供商ID, "model": 模型ID, "id": "provider:model"}]
        """
        models: list[dict[str, str]] = []
        seen: set[tuple[str, str]] = set()
        try:
            insts = getattr(self.context, "provider_manager", None)
            for inst in getattr(insts, "provider_insts", None) or []:
                try:
                    meta = inst.meta()
                    provider = str(meta.id or "")
                    model = str(meta.model or "")
                except Exception:  # noqa: BLE001 - meta 不可用时回退
                    provider = ""
                    model = str(getattr(inst, "get_model", lambda: "")() or "")
                if provider and model and (provider, model) not in seen:
                    seen.add((provider, model))
                    models.append(
                        {
                            "provider": provider,
                            "model": model,
                            "id": f"{provider}:{model}",
                        }
                    )
        except Exception:  # noqa: BLE001 - 模型列表不可用时返回空
            self.logger.warning("获取可用模型列表失败")
        return json_response({"ok": True, "models": models})

    async def api_export(self) -> Any:
        """导出全部程序为 JSON 文件。"""
        data = self._export_data(self.manager.list_programs())
        return self._json_file_response(data, "blockly_programs.json")

    async def api_export_program(self, pid: str) -> Any:
        """导出单个程序为 JSON 文件。"""
        program = self.manager.get(pid)
        if not program:
            return error_response("程序不存在", status_code=404)
        data = self._export_data([program])
        return self._json_file_response(
            data, f"blockly_{program.name}_{program.id}.json"
        )

    async def api_import(self) -> Any:
        """从 JSON 导入程序（body 为导出格式或程序对象列表）。

        ``body.on_conflict``（可选）为同名冲突处理策略映射：
        ``{程序名(不区分大小写): "overwrite" | "rename"}``。
        未提供该参数且检测到同名冲突时，返回 ``{"ok": false, "code":
        "NAME_CONFLICT", "conflicts": [{"name", "id"}]}`` 供前端二次确认。
        """
        body = await request.json(default={})
        return await self._import_data(body)

    async def api_import_file(self) -> Any:
        """从上传的文件导入程序（multipart 字段名：file）。"""
        files = await request.files()
        upload = files.get("file")
        if not upload:
            return error_response("缺少上传文件（字段名：file）", status_code=400)
        try:
            raw = await upload.read()
            body = json.loads(raw.decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            return error_response(f"文件解析失败：{exc}", status_code=400)
        return await self._import_data(body)

    def _export_data(self, programs: list[BlocklyProgram]) -> dict:
        """构造导出的 JSON 结构。"""
        return {
            "format": "astrbot_plugin_blockly",
            "version": 1,
            "exported_at": time.time(),
            "programs": [p.to_dict() for p in programs],
        }

    def _json_file_response(self, data: dict, filename: str) -> Any:
        """将 JSON 数据写为临时文件并返回下载响应。"""
        with tempfile.NamedTemporaryFile(
            "w", suffix=".json", delete=False, encoding="utf-8"
        ) as fp:
            json.dump(data, fp, ensure_ascii=False, indent=2)
            tmp_path = fp.name
        return file_response(
            tmp_path,
            filename=filename,
            content_type="application/json",
        )

    async def _import_data(self, body: Any) -> Any:
        """解析并导入导出数据。

        与现有程序名称相同（不区分大小写）的导入条目一律视为"同名冲突"：
        - 未提供 ``on_conflict`` 策略时，返回冲突列表由前端二次确认；
        - 提供策略 ``overwrite`` 时，用导入内容覆盖已有同名程序；
        - 策略 ``rename`` 时，为导入条目更换 id、追加序号命名并新建。
        """
        programs_data = body.get("programs") if isinstance(body, dict) else body
        if not isinstance(programs_data, list) or not programs_data:
            return error_response("导入数据格式不正确", status_code=400)
        on_conflict: dict[str, str] = {}
        if isinstance(body, dict) and isinstance(body.get("on_conflict"), dict):
            on_conflict = {
                str(k).strip().lower(): str(v)
                for k, v in body["on_conflict"].items()
            }
        items = [i for i in programs_data if isinstance(i, dict)]
        if not items:
            return error_response("导入数据格式不正确", status_code=400)

        existing_by_name: dict[str, BlocklyProgram] = {}
        for p in self.manager.list_programs():
            existing_by_name.setdefault(p.name.strip().lower(), p)

        conflicts = [
            {
                "name": existing_by_name[str(item.get("name") or "").strip().lower()].name,
                "id": str(item.get("id") or ""),
            }
            for item in items
            if str(item.get("name") or "").strip().lower() in existing_by_name
        ]
        if conflicts and not on_conflict:
            return json_response(
                {
                    "ok": False,
                    "code": "NAME_CONFLICT",
                    "conflicts": conflicts,
                }
            )

        count = 0
        name_map: dict[str, BlocklyProgram] = dict(existing_by_name)
        for item in items:
            program = BlocklyProgram.from_dict(item)
            if not str(program.name or "").strip():
                program.name = "未命名程序"
            name_key = program.name.strip().lower()
            existing = name_map.get(name_key)
            if existing is not None:
                strategy = on_conflict.get(name_key, "rename") or "rename"
                if strategy == "overwrite":
                    program.id = existing.id
                    program.name = existing.name
                else:
                    program.id = new_id()
                    program.name = self.manager.unique_name(
                        program.name,
                        {p.name for p in name_map.values()},
                    )
            program.updated_at = time.time()
            name_map[program.name.strip().lower()] = program
            await self.manager.update(program)
            count += 1
        return json_response({"ok": True, "imported": count})

    # ---------- 内部工具 ----------

    @staticmethod
    def _attr_matches(program: BlocklyProgram, event: AstrMessageEvent) -> bool:
        """按程序的 ``event_attr`` 过滤消息内容类型；any 表示不限制。"""
        attr = getattr(program, "event_attr", "any") or "any"
        if attr == "any":
            return True
        getter = getattr(event, "get_messages", None)
        segments = list(getter()) if callable(getter) else []
        if not segments:
            return attr == "text"
        kinds = set()
        for seg in segments:
            seg_type = getattr(seg, "type", None)
            name = str(getattr(seg_type, "name", None) or seg_type or "").lower()
            kinds.add(EVENT_ATTR_SEGMENT_KINDS.get(name, name))
        return attr in kinds

    def _plugin_enabled(self) -> bool:
        """是否启用插件总开关。"""
        return bool(self.config.get("enabled", True))

    def _is_skipped(self, message: str) -> bool:
        """是否命中不触发程序的消息前缀。"""
        for line in str(self.config.get("skip_prefixes", "")).splitlines():
            prefix = line.strip()
            if prefix and message.startswith(prefix):
                return True
        return False

    def _default_timeout(self) -> float:
        """程序默认执行超时（秒）。"""
        try:
            return max(1, int(self.config.get("default_timeout") or 30))
        except (TypeError, ValueError):
            return 30.0
