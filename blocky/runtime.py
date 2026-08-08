"""Blocky 受限执行引擎。

积木（或手写）生成的 Python 代码会被包装成异步函数，在受限的命名空间内执行：
- 仅暴露白名单内置函数（不含 __import__/open/eval/exec 等）；
- 提供 math / random 模块（Blockly 数学与随机积木需要）；
- 提供 event / ctx / _blk 三个对象供代码操控 AstrBot；
- 每个程序有独立的执行超时。
"""

from __future__ import annotations

import ast
import asyncio
import inspect
import json
import logging
import math
import random
import textwrap
import time
from functools import lru_cache
from typing import Any, ClassVar

from .program import CONTENT_BLOCKLY, BlockyProgram

try:
    # AstrBot 只对「astrbot」命名空间的 logger 配置了 handler/界面输出，
    # 独立 logger 的 INFO 会被丢弃，因此优先复用 AstrBot 的主 logger。
    from astrbot.core import logger
except ImportError:  # 测试环境（未安装 AstrBot）
    logger = logging.getLogger("astrbot_plugin_blocky")

try:
    # 「AI 工具」积木使用 AstrBot 的 FunctionTool/ToolSet 接入函数调用。
    from astrbot.core.agent.tool import FunctionTool as _AstrFunctionTool
    from astrbot.core.agent.tool import ToolSet as _AstrToolSet
except ImportError:  # 测试环境（未安装 AstrBot）
    _AstrFunctionTool = None
    _AstrToolSet = None

# OneBot notice 事件类型映射到本插件的事件类型
NOTICE_KINDS = {
    "group_recall": "recall",
    "group_increase": "member_increase",
}


def resolve_event_kind(event) -> str:
    """返回事件的真实类型（message / recall / member_increase / poke / other_notice）。

    AstrBot 把 OneBot 的通知（撤回/成员加入/戳一戳等）统一包装为消息事件，
    原始事件保存在 ``message_obj.raw_message`` 中，据此区分。
    """
    raw = getattr(getattr(event, "message_obj", None), "raw_message", None)
    if isinstance(raw, dict) and raw.get("post_type") == "notice":
        notice_type = raw.get("notice_type")
        if notice_type in NOTICE_KINDS:
            return NOTICE_KINDS[notice_type]
        if notice_type == "friend_poke" or (
            notice_type == "notify" and raw.get("sub_type") == "poke"
        ):
            return "poke"
        return "other_notice"
    return "message"


def _safe_print(*args, **kwargs):
    try:
        logger.info(" ".join(str(a) for a in args))
    except Exception:  # noqa: S110, BLE001 - 打印仅是辅助手段，失败时静默忽略
        pass


# 白名单内置函数/常量。刻意不包含：__import__ / open / eval / exec / compile /
# getattr / setattr / delattr / globals / locals / vars / type.__... 等。
SAFE_BUILTINS: dict[str, Any] = {
    "True": True,
    "False": False,
    "None": None,
    "abs": abs,
    "all": all,
    "any": any,
    "bool": bool,
    "dict": dict,
    "enumerate": enumerate,
    "float": float,
    "hash": hash,
    "id": id,
    "int": int,
    "isinstance": isinstance,
    "len": len,
    "list": list,
    "max": max,
    "min": min,
    "print": _safe_print,
    "range": range,
    "reversed": reversed,
    "round": round,
    "set": set,
    "sorted": sorted,
    "str": str,
    "sum": sum,
    "tuple": tuple,
    "type": type,
    "zip": zip,
    "Exception": Exception,
    "BaseException": BaseException,
    "ArithmeticError": ArithmeticError,
    "AssertionError": AssertionError,
    "AttributeError": AttributeError,
    "IndexError": IndexError,
    "KeyError": KeyError,
    "LookupError": LookupError,
    "RuntimeError": RuntimeError,
    "TypeError": TypeError,
    "ValueError": ValueError,
}


def _make_chain(text: str):
    """构造消息链。优先使用 AstrBot 的 MessageChain，测试环境下回退为鸭子类型。"""
    try:
        from astrbot.api.message_components import Plain
        from astrbot.core.message.message_event_result import MessageChain

        return MessageChain([Plain(str(text))])
    except ImportError:  # pragma: no cover - 仅在脱离 AstrBot 的测试环境中触发

        class _Plain:
            def __init__(self, t: str):
                self.text = t

        class _Chain:
            def __init__(self, t: str):
                self.chain = [_Plain(t)]

        return _Chain(str(text))


def _parse_allowlist(allowed: list[str]) -> list[tuple[str | None, str]]:
    """解析「可用模型」白名单条目为 ``(provider_id, model)`` 列表。

    条目格式为 ``provider_id:model``；旧格式（不含冒号）视为任意提供商的 model。
    """
    parsed: list[tuple[str | None, str]] = []
    for entry in allowed or []:
        entry = str(entry).strip()
        if not entry:
            continue
        if ":" in entry:
            provider, _, model = entry.rpartition(":")
            parsed.append((provider or None, model))
        else:
            parsed.append((None, entry))
    return parsed


def _assert_safe_source(source: str) -> None:
    """通过 AST 静态检查阻断常见的沙箱逃逸途径。

    原生 ``exec`` 即使在受限命名空间内仍可通过 ``().__class__.__bases__[0].__subclasses__()``
    等方式逃逸，因此额外禁止魔术属性/名称、import、global/nonlocal 与类定义。

    Raises:
        SyntaxError: 代码存在语法错误。
        RuntimeError: 代码包含被禁止的构造。
    """
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            if node.attr.startswith("__"):
                raise RuntimeError(f"禁止访问以双下划线开头的属性：{node.attr!r}")
        elif isinstance(node, ast.Name):
            if node.id.startswith("__"):
                raise RuntimeError(f"禁止使用以双下划线开头的名称：{node.id!r}")
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            raise RuntimeError("禁止使用 import 语句")  # noqa: TRY004 - 安全违规
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            raise RuntimeError(  # noqa: TRY004 - 安全违规
                "禁止使用 global/nonlocal 语句"
            )
        elif isinstance(node, ast.ClassDef):
            raise RuntimeError("禁止定义类")  # noqa: TRY004 - 安全违规


async def _http_request(
    method: str,
    url: str,
    json_data: Any = None,
    headers: dict | None = None,
    timeout: float = 15.0,
) -> dict:
    """发起 HTTP 请求，返回 {status, body}。优先 aiohttp，回退 httpx。"""
    url = str(url)
    try:
        import aiohttp

        async with (
            aiohttp.ClientSession() as session,
            session.request(
                method,
                url,
                json=json_data,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as resp,
        ):
            body = await resp.text()
            return {"status": resp.status, "body": body}
    except ImportError:  # pragma: no cover
        import httpx

        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.request(method, url, json=json_data, headers=headers)
            return {"status": resp.status_code, "body": resp.text}


class BlockyRuntime:
    """积木生成代码通过 ``_blk`` 调用本对象，屏蔽底层 AstrBot 细节。"""

    # 段类型（ComponentType.name 小写）到事件属性（EVENT_ATTRS）的映射
    ATTR_SEGMENT_KINDS: ClassVar[dict[str, str]] = {
        "plain": "text",
        "image": "image",
        "face": "face",
        "at": "at",
        "atall": "at",
        "record": "voice",
    }

    def __init__(self, context, event, program: BlockyProgram) -> None:
        self._ctx = context
        self._event = event
        self._program = program
        self.event_type = resolve_event_kind(event)
        self._tools: dict[str, Any] = {}  # 「AI 工具」积木注册的工具（名称 -> FunctionTool）
        self._tool_result: Any = None  # 当前工具调用通过「设置工具返回值」写入的值
        self._tool_return_set = False  # 本次工具调用是否设置了返回值

    # ---------- 事件读取 ----------
    def _messages(self) -> list:
        getter = getattr(self._event, "get_messages", None)
        if callable(getter):
            try:
                return list(getter() or [])
            except Exception:  # noqa: BLE001 - 段读取失败按空处理
                return []
        return list(getattr(getattr(self._event, "message_obj", None), "message", []))

    def _raw(self) -> Any:
        obj = getattr(self._event, "message_obj", None)
        return getattr(obj, "raw_message", None)

    def _raw_get(self, key: str, default: str = "") -> str:
        """从原始事件（如 OneBot 通知）中安全读取字段。"""
        raw = self._raw()
        if isinstance(raw, dict):
            value = raw.get(key)
            if value is not None and value != "":
                return str(value)
        return default

    @staticmethod
    def _segment_kind(seg: Any) -> str:
        """返回消息段的小写类型名（如 image/face/atall/record/plain）。"""
        seg_type = getattr(seg, "type", None)
        name = getattr(seg_type, "name", None)
        return str(name or seg_type or "").lower()

    def get_event_type(self) -> str:
        """本次执行对应的事件类型（message/recall/member_increase/poke）。"""
        return str(self.event_type or "message")

    def get_message(self) -> str:
        return self._event.message_str

    def get_message_type(self) -> str:
        """返回第一条非文本段的消息类型（image/face/at/voice/reply/poke…），全文本返回 text。"""
        for seg in self._messages():
            kind = self._segment_kind(seg)
            if kind not in ("plain", "", "unknown"):
                return kind
        return "text"

    def has_type(self, kind: Any) -> bool:
        """判断消息是否包含指定类型的内容（如 image/fae/at/voice/reply/poke）。"""
        target = str(kind or "").strip().lower()
        if not target:
            return False
        for seg in self._messages():
            if self._segment_kind(seg) == target:
                return True
        return False

    def get_target_id(self) -> str:
        """被戳一戳等交互事件中目标的 ID。"""
        return self._raw_get("target_id")

    def get_operator_id(self) -> str:
        """事件操作者的 ID（如撤回者、邀请者）。"""
        return self._raw_get("operator_id")

    def get_message_id(self) -> str:
        """本条消息/被撤回消息的 ID。"""
        message_id = getattr(getattr(self._event, "message_obj", None), "message_id", None)
        if message_id:
            return str(message_id)
        return self._raw_get("message_id")

    def get_sender_name(self) -> str:
        return self._event.get_sender_name()

    def get_sender_id(self) -> str:
        return self._event.get_sender_id()

    def get_group_id(self) -> str:
        return self._event.get_group_id()

    def get_session(self) -> str:
        return self._event.unified_msg_origin

    def get_platform(self) -> str:
        return self._event.get_platform_name()

    def is_admin(self) -> bool:
        return self._event.is_admin()

    def is_private(self) -> bool:
        return self._event.is_private_chat()

    # ---------- 动作 ----------
    async def reply(self, text: Any) -> None:
        """回复一条消息，并继续事件传播。"""
        await self._event.send(_make_chain(text))

    async def return_msg(self, text: Any) -> None:
        """返回消息：设置回复结果并劫持事件（阻止 AstrBot 继续处理）。

        不调用 ``send`` 主动发送，而是设置结果由 AstrBot 的响应阶段统一发送，
        避免在同一会话中出现重复回复。
        """
        result = self._event.plain_result(str(text)).stop_event()
        self._event.set_result(result)

    def forward(self) -> None:
        """传出消息：放行事件，交给 AstrBot 继续处理。"""
        self._event.continue_event()

    def stop(self) -> None:
        """停止事件传播。"""
        self._event.stop_event()

    async def send(self, umo: Any, text: Any) -> None:
        """主动发送消息到指定会话（unified_msg_origin）。"""
        await self._ctx.send_message(str(umo), _make_chain(text))

    def _parse_models(self, raw: Any) -> list[tuple[str | None, str]]:
        """解析 AI 积木上「指定模型」字段。

        支持逗号分隔的 ``provider:model``（或仅 ``model`` 的旧格式）列表，
        顺序即优先级。
        """
        if raw is None or raw == "":
            return []
        if isinstance(raw, (list, tuple)):
            return _parse_allowlist(raw)
        parts = [p.strip() for p in str(raw).split(",")]
        return _parse_allowlist([p for p in parts if p])

    def _ordered_entries(
        self,
        entries: list[tuple[str | None, str]],
        provider_id: str,
        current_model: str,
    ) -> list[tuple[str | None, str]]:
        """把「当前会话正在使用的模型」放到列表首位，其余保持原顺序。

        当前模型已就绪时直接复用它，避免不必要的重新请求；仍以用户指定顺序为后备。
        """
        ordered: list[tuple[str | None, str]] = []
        for prov, model in entries:
            if (prov is None or prov == provider_id) and model == current_model:
                ordered.insert(0, (prov, model))
            else:
                ordered.append((prov, model))
        return ordered

    # ---------- AI 工具（「AI 工具」积木） ----------
    def tool(self, name: Any, description: Any, handler: Any, return_content: Any = True) -> None:
        """注册一个「AI 工具」：AI 可根据描述决定何时调用 handler。

        ``handler`` 为积木生成的 ``async def`` 函数，无参数；调用期间可通过
        ``_blk.tool_return(...)`` 设置返回值。``return_content`` 为真时该返回值
        会作为工具结果返回给 AI；否则不向 AI 返回内容（可自行回复/发消息）。
        """
        name = str(name or "").strip()
        if not name:
            raise RuntimeError("AI 工具名称不能为空，请在积木上填写")
        if not callable(handler):
            raise RuntimeError(f"AI 工具 {name} 缺少可执行的函数体")

        async def _handler(event, *args, **kwargs):  # noqa: ARG001 - AstrBot 以 (event, **kwargs) 调用
            # 每次调用重置返回值状态，避免上一次调用的结果串到本次。
            self._tool_return_set = False
            self._tool_result = None
            result = handler()
            if asyncio.iscoroutine(result):
                await result
            elif inspect.isasyncgen(result):
                async for _ in result:
                    pass
            if self._tool_return_set:
                return str(self._tool_result) if self._tool_result is not None else ""
            return None

        parameters = {"type": "object", "properties": {}}
        if _AstrFunctionTool is not None:
            tool = _AstrFunctionTool(
                name=name,
                description=str(description or ""),
                parameters=parameters,
                handler=_handler,
            )
        else:  # 测试环境（未安装 AstrBot）：构造行为兼容的鸭子类型
            tool = type(
                "_FakeTool",
                (),
                {
                    "name": name,
                    "description": str(description or ""),
                    "parameters": parameters,
                    "handler": _handler,
                    "active": True,
                },
            )()
        self._tools[name] = tool

    def tool_return(self, value: Any) -> None:
        """「设置工具返回值」积木：把值作为本次工具调用的结果返回给 AI。"""
        self._tool_result = value
        self._tool_return_set = True

    async def _chat_with_tools(self, prompt: Any) -> str:
        """程序注册了「AI 工具」时，通过工具循环调用 LLM，让 AI 可调用工具。"""
        provider_id = await self._get_current_provider_id()
        if _AstrToolSet is not None:
            tools: Any = _AstrToolSet(list(self._tools.values()))
        else:
            tools = list(self._tools.values())
        resp = await self._ctx.tool_loop_agent(
            event=self._event,
            chat_provider_id=provider_id,
            prompt=str(prompt),
            tools=tools,
            max_steps=10,
        )
        return resp.completion_text

    async def chat(self, prompt: Any, models: Any = None) -> str:
        """调用当前会话的 LLM，返回回答文本。

        若程序注册了「AI 工具」，走工具循环（AI 可调用工具）；否则按
        ``models``（AI 积木「指定模型」字段）显式指定一个有序的
        ``provider:model`` 列表（逗号分隔）。提供时按顺序尝试：当前会话正在
        使用的模型优先，其余模型请求失败时自动切换到下一个；全部失败则抛出错误。
        未指定时沿用程序级「可用模型」白名单的原有逻辑。
        """
        if self._tools:
            return await self._chat_with_tools(prompt)
        provider_id = await self._get_current_provider_id()
        current_model = await self._get_current_model()
        entries = self._parse_models(models) or _parse_allowlist(self._program.models)
        if not entries:
            resp = await self._ctx.llm_generate(
                chat_provider_id=provider_id, prompt=str(prompt)
            )
            return resp.completion_text
        ordered = self._ordered_entries(entries, provider_id, current_model)
        errors: list[str] = []
        for prov, model in ordered:
            try:
                kwargs: dict[str, Any] = {}
                pid = prov or provider_id
                if model and (model != current_model or pid != provider_id):
                    kwargs["model"] = model
                resp = await self._ctx.llm_generate(
                    chat_provider_id=pid, prompt=str(prompt), **kwargs
                )
                return resp.completion_text
            except Exception as exc:  # noqa: BLE001 - 单模型失败切换到下一个
                errors.append(f"{model}: {exc}")
        raise RuntimeError(
            f"指定模型全部请求失败：{'；'.join(errors)}"
        )

    async def _get_current_provider_id(self) -> str:
        """获取当前会话使用的提供商 ID；无法获取时返回空字符串。"""
        try:
            return str(
                await self._ctx.get_current_chat_provider_id(
                    umo=self._event.unified_msg_origin
                )
                or ""
            )
        except Exception:  # noqa: BLE001 - 获取失败按空处理
            return ""

    async def _get_current_model(self) -> str:
        """获取当前会话使用的模型名称；无法获取时返回空字符串。"""
        ctx = self._ctx
        getter = getattr(ctx, "get_current_model", None)
        if callable(getter):
            try:
                return str(await getter() or "")
            except Exception:  # noqa: BLE001 - 获取失败按空处理
                return ""
        try:
            provider_id = await self._get_current_provider_id()
            if not provider_id:
                return ""
            prov = await ctx.provider_manager.get_provider_by_id(provider_id)
            return str(getattr(prov, "get_model", lambda: "")() or "")
        except Exception:  # noqa: BLE001 - 获取失败按空处理
            return ""

    def log(self, text: Any) -> None:
        logger.info("[blocky:%s] %s", self._program.name, text)

    async def sleep(self, ms: Any) -> None:
        await asyncio.sleep(max(0.0, float(ms) / 1000.0))

    # ---------- HTTP ----------
    async def http_get(self, url: Any, headers: Any = None) -> dict:
        return await _http_request("GET", url, headers=headers)

    async def http_get_json(self, url: Any, headers: Any = None) -> Any:
        resp = await _http_request("GET", url, headers=headers)

        try:
            return json.loads(resp["body"])
        except Exception:  # noqa: BLE001 - JSON 解析失败时返回空结果
            return {}

    async def http_post(self, url: Any, data: Any = None, headers: Any = None) -> dict:
        return await _http_request("POST", url, json_data=data, headers=headers)

    async def http_post_json(
        self, url: Any, data: Any = None, headers: Any = None
    ) -> Any:
        resp = await _http_request("POST", url, json_data=data, headers=headers)

        try:
            return json.loads(resp["body"])
        except Exception:  # noqa: BLE001 - JSON 解析失败时返回空结果
            return {}

    def dict_get(self, d: Any, key: Any, default: Any = "") -> Any:
        if isinstance(d, dict):
            return d.get(key, default)
        return default


def _has_blocks(workspace_json: str) -> bool:
    """判断积木工作区 JSON 中是否含有实际积木。"""
    if not workspace_json:
        return False
    try:
        data = json.loads(workspace_json)
    except (TypeError, ValueError):
        return False
    blocks = (data.get("blocks") or {}).get("blocks") or []
    return bool(blocks)


def wrap_code(code: str, func_name: str = "_blk_run") -> str:
    """将积木生成的代码包装为异步函数体。"""
    body = textwrap.indent(code or "", "    ", predicate=lambda line: line.strip())
    return f"async def {func_name}(event, ctx, _blk):\n{body}\n"


@lru_cache(maxsize=256)
def _compile_safe(source: str) -> Any:
    """AST 静态检查 + 编译。代码相同的结果会被缓存，避免每条消息重复编译。"""
    _assert_safe_source(source)
    return compile(source, "<blocky>", "exec")


def _build_namespace(context, event, program: BlockyProgram) -> dict:
    return {
        "__builtins__": dict(SAFE_BUILTINS),
        "math": math,
        "random": random,
        "event": event,
        "ctx": context,
        "_blk": BlockyRuntime(context, event, program),
    }


async def run_program(
    program: BlockyProgram,
    context,
    event,
    timeout: float = 30.0,
) -> None:
    """执行一个程序。

    Args:
        program: 程序对象。
        context: AstrBot Context（或测试 MockContext）。
        event: AstrMessageEvent（或测试 MockEvent）。
        timeout: 执行超时（秒）。

    Raises:
        asyncio.TimeoutError: 执行超时。
        SyntaxError / RuntimeError: 代码编译或执行错误。
    """
    code = (program.code or "").strip()
    if not code:
        if (
            program.content_type == CONTENT_BLOCKLY
            and _has_blocks(program.workspace)
        ):
            raise RuntimeError(
                "积木程序缺少已生成的代码（code 为空）：请在 WebUI 打开该程序并保存一次，"
                "或重新导入包含 code 的数据"
            )
        return
    source = wrap_code(code)
    ns = _build_namespace(context, event, program)
    try:
        compiled = _compile_safe(source)
    except SyntaxError as exc:
        raise RuntimeError(f"程序代码存在语法错误：{exc}") from exc
    exec(compiled, ns)  # noqa: S102 - 受限命名空间 + AST 检查后执行
    coro = ns["_blk_run"](event, context, ns["_blk"])
    await asyncio.wait_for(coro, timeout=timeout)


async def simulate_program(
    program: BlockyProgram,
    message: str = "",
    timeout: float = 30.0,
    chat_responses: dict | None = None,
    is_admin: bool = False,
    is_private: bool = False,
    current_model: str = "mock-model",
    current_provider: str = "mock_provider",
    message_type: str = "text",
) -> dict:
    """使用模拟事件运行程序（WebUI 测试运行）。

    Args:
        program: 待运行的程序。
        message: 模拟的输入消息文本。
        timeout: 执行超时（秒）。
        chat_responses: prompt 到回答的映射，用于模拟 AI 回答。
        is_admin: 模拟事件中发送者是否为管理员。
        is_private: 模拟事件是否为私聊。
        current_model: 模拟会话当前使用的模型名称。
        current_provider: 模拟会话当前使用的提供商 ID。
        message_type: 模拟消息的类型（text/image/face/at/…）。

    Returns:
        包含 replies / sends / stopped / error / cost 的字典。
    """
    from .mock_event import MockContext, MockEvent

    event = MockEvent(
        message_str=message,
        is_admin=is_admin,
        is_private=is_private,
        message_type=message_type,
    )
    ctx = MockContext(
        current_model=current_model,
        current_provider=current_provider,
    )
    if chat_responses:
        ctx.chat_responses.update(chat_responses)

    error = ""
    start = time.monotonic()
    try:
        await run_program(program, ctx, event, timeout=timeout)
    except asyncio.TimeoutError:
        error = "执行超时"
    except Exception as exc:  # noqa: BLE001
        error = str(exc)
    finally:
        cost = round(time.monotonic() - start, 3)

    return {
        "replies": list(event.sent_messages),
        "sends": list(ctx.sent),
        "stopped": event.is_stopped(),
        "error": error,
        "cost": cost,
    }
