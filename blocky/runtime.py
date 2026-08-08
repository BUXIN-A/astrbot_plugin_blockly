"""Blocky 受限执行引擎。

积木（或手写）生成的 Python 代码会被包装成异步函数，在受限的命名空间内执行：
- 仅暴露白名单内置函数（不含 __import__/open/eval/exec 等）；
- 提供 math / random 模块（Blockly 数学与随机积木需要）；
- 提供 event / ctx / _blk 三个对象供代码操控 AstrBot；
- 每个程序有独立的执行超时。
"""

from __future__ import annotations

import asyncio
import logging
import math
import random
import textwrap
from typing import Any

from .program import MODE_RETURN, BlockyProgram

logger = logging.getLogger("astrbot_plugin_blocky")


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

    def __init__(self, context, event, program: BlockyProgram) -> None:
        self._ctx = context
        self._event = event
        self._program = program

    # ---------- 消息读取 ----------
    def get_message(self) -> str:
        return self._event.message_str

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

    async def chat(self, prompt: Any) -> str:
        """调用当前会话的 LLM，返回回答文本。"""
        umo = self._event.unified_msg_origin
        provider_id = await self._ctx.get_current_chat_provider_id(umo=umo)
        resp = await self._ctx.llm_generate(
            chat_provider_id=provider_id, prompt=str(prompt)
        )
        return resp.completion_text

    def log(self, text: Any) -> None:
        logger.info("[blocky:%s] %s", self._program.name, text)

    async def sleep(self, ms: Any) -> None:
        await asyncio.sleep(max(0.0, float(ms) / 1000.0))

    # ---------- HTTP ----------
    async def http_get(self, url: Any, headers: Any = None) -> dict:
        return await _http_request("GET", url, headers=headers)

    async def http_get_json(self, url: Any, headers: Any = None) -> Any:
        resp = await _http_request("GET", url, headers=headers)
        import json as _json

        try:
            return _json.loads(resp["body"])
        except Exception:  # noqa: BLE001 - JSON 解析失败时返回空结果
            return {}

    async def http_post(self, url: Any, data: Any = None, headers: Any = None) -> dict:
        return await _http_request("POST", url, json_data=data, headers=headers)

    async def http_post_json(
        self, url: Any, data: Any = None, headers: Any = None
    ) -> Any:
        resp = await _http_request("POST", url, json_data=data, headers=headers)
        import json as _json

        try:
            return _json.loads(resp["body"])
        except Exception:  # noqa: BLE001 - JSON 解析失败时返回空结果
            return {}

    def dict_get(self, d: Any, key: Any, default: Any = "") -> Any:
        if isinstance(d, dict):
            return d.get(key, default)
        return default


def wrap_code(code: str, func_name: str = "_blk_run") -> str:
    """将积木生成的代码包装为异步函数体。"""
    body = textwrap.indent(code or "", "    ", predicate=lambda line: line.strip())
    return f"async def {func_name}(event, ctx, _blk):\n{body}\n"


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
        return
    source = wrap_code(code)
    ns = _build_namespace(context, event, program)
    try:
        compiled = compile(source, f"<blocky:{program.id}>", "exec")
    except SyntaxError as exc:
        raise RuntimeError(f"程序代码存在语法错误：{exc}") from exc
    exec(compiled, ns)  # noqa: S102 - 受限命名空间内执行
    coro = ns["_blk_run"](event, context, ns["_blk"])
    await asyncio.wait_for(coro, timeout=timeout)
    # 模式默认行为
    if program.mode == MODE_RETURN and not event.is_stopped():
        event.stop_event()


async def simulate_program(
    program: BlockyProgram,
    message: str = "",
    timeout: float = 30.0,
    chat_responses: dict | None = None,
    is_admin: bool = False,
    is_private: bool = False,
) -> dict:
    """使用模拟事件运行程序（WebUI 测试运行）。

    Args:
        program: 待运行的程序。
        message: 模拟的输入消息文本。
        timeout: 执行超时（秒）。
        chat_responses: prompt 到回答的映射，用于模拟 AI 回答。
        is_admin: 模拟事件中发送者是否为管理员。
        is_private: 模拟事件是否为私聊。

    Returns:
        包含 replies / sends / stopped / error / cost 的字典。
    """
    from .mock_event import MockContext, MockEvent

    event = MockEvent(
        message_str=message,
        is_admin=is_admin,
        is_private=is_private,
    )
    ctx = MockContext()
    if chat_responses:
        ctx.chat_responses.update(chat_responses)

    error = ""
    start = asyncio.get_event_loop().time()
    try:
        await run_program(program, ctx, event, timeout=timeout)
    except asyncio.TimeoutError:
        error = "执行超时"
    except Exception as exc:  # noqa: BLE001
        error = str(exc)
    finally:
        cost = round(asyncio.get_event_loop().time() - start, 3)

    return {
        "replies": list(event.sent_messages),
        "sends": list(ctx.sent),
        "stopped": event.is_stopped(),
        "error": error,
        "cost": cost,
    }
