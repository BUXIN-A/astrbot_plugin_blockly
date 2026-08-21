"""用于 WebUI"测试运行"的模拟消息事件与模拟上下文。

这些类实现了与 AstrBot ``AstrMessageEvent`` / ``Context`` 兼容的最小接口，
让积木生成的代码可以在不依赖真实消息平台的情况下运行。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class _MockResult:
    chain: list = field(default_factory=list)
    _stopped: bool = False

    def stop_event(self):
        self._stopped = True
        return self

    def continue_event(self):
        self._stopped = False
        return self

    def is_stopped(self) -> bool:
        return self._stopped


@dataclass
class _MockSegmentType:
    name: str


@dataclass
class _MockSegment:
    type: _MockSegmentType


def _build_segments(message_type: str) -> list:
    """根据模拟的消息类型构造消息段列表。

    ``text`` 生成纯文本段；其余类型生成一个对应类型的段（如 image/face/voice）。
    """
    name = str(message_type or "text").strip().lower() or "text"
    if name == "text":
        return [_MockSegment(_MockSegmentType("plain"))]
    return [_MockSegment(_MockSegmentType(name))]


def _make_message_obj(raw_message):
    """构造带 ``raw_message`` 的模拟 ``message_obj``（用于模拟通知事件）。"""
    if raw_message is None:
        return None

    class _RawObj:
        def __init__(self, raw):
            self.raw_message = raw

    return _RawObj(raw_message)


class MockEvent:
    """模拟的 AstrMessageEvent。"""

    def __init__(
        self,
        message_str: str = "",
        sender_name: str = "测试用户",
        sender_id: str = "123456789",
        group_id: str = "",
        platform: str = "mock",
        is_admin: bool = False,
        is_private: bool = False,
        message_type: str = "text",
        raw_message: dict | None = None,
    ) -> None:
        self.message_str = message_str
        self._sender_name = sender_name
        self._sender_id = sender_id
        self._group_id = group_id
        self._platform = platform
        self._is_admin = is_admin
        self._is_private = is_private
        self._segments = _build_segments(message_type)
        self.unified_msg_origin = f"{platform}:frien_m_message:mock_session"
        self._result = None
        self._force_stopped = False
        self.sent_messages: list[str] = []
        self.message_obj = _make_message_obj(raw_message)

    def get_messages(self) -> list:
        return self._segments

    async def send(self, chain) -> None:
        text = _chain_to_text(chain)
        if text:
            self.sent_messages.append(text)

    def set_result(self, result) -> None:
        self._result = result
        text = _chain_to_text(result)
        if text:
            self.sent_messages.append(text)

    def get_result(self):
        return self._result

    def stop_event(self) -> None:
        self._force_stopped = True

    def continue_event(self) -> None:
        self._force_stopped = False

    def is_stopped(self) -> bool:
        if self._force_stopped:
            return True
        if self._result is None:
            return False
        return bool(self._result.is_stopped())

    def plain_result(self, text: str) -> _MockResult:
        return _MockResult(chain=[text]).stop_event()

    def image_result(self, url_or_path: str) -> _MockResult:
        """模拟仅包含图片的消息结果。"""
        return _MockResult(chain=[f"[图片: {url_or_path}]"])

    def chain_result(self, chain) -> _MockResult:
        """模拟包含指定消息链的结果。"""
        return _MockResult(chain=list(chain))

    def get_sender_name(self) -> str:
        return self._sender_name

    def get_sender_id(self) -> str:
        return self._sender_id

    def get_group_id(self) -> str:
        return self._group_id

    def get_platform_name(self) -> str:
        return self._platform

    def is_admin(self) -> bool:
        return self._is_admin

    def is_private_chat(self) -> bool:
        return self._is_private


class MockContext:
    """模拟的 Context，用于测试。"""

    def __init__(
        self,
        current_model: str = "mock-model",
        current_provider: str = "mock_provider",
    ) -> None:
        self.sent: list[tuple[str, str]] = []
        self.chat_responses: dict[str, str] = {}
        self.chat_failure_models: set[str] = set()  # 模拟指定模型调用失败的 key
        self.current_model = current_model
        self.current_provider = current_provider

    async def get_current_model(self) -> str:
        return self.current_model

    async def get_current_chat_provider_id(self, umo=None) -> str:
        return self.current_provider

    async def llm_generate(
        self, chat_provider_id=None, prompt="", model=None, **kwargs
    ):
        class _Resp:
            completion_text = ""

        key = f"{chat_provider_id}:{model}" if model else str(chat_provider_id or "")
        if key in self.chat_failure_models:
            raise RuntimeError(f"模型 {model or chat_provider_id} 调用失败")

        if prompt in self.chat_responses:
            _Resp.completion_text = self.chat_responses[prompt]
        else:
            _Resp.completion_text = f"(模拟) AI 响应：{prompt}"
        return _Resp()

    async def tool_loop_agent(
        self,
        *,
        event=None,
        chat_provider_id="",
        prompt="",
        tools=None,
        system_prompt=None,
        contexts=None,
        max_steps=30,
        tool_call_timeout=120,
        **kwargs,
    ):
        """模拟工具循环：不真正调用 LLM，而是依次执行每个工具并汇总结果。"""
        tool_list = list(getattr(tools, "tools", None) or tools or [])
        lines = []
        for tool in tool_list:
            try:
                ret = (
                    await tool.handler(event)
                    if getattr(tool, "handler", None)
                    else None
                )
                lines.append(f"[工具 {tool.name}] {_tool_result_to_text(ret)}")
            except Exception as exc:  # noqa: BLE001 - 单工具失败不影响其他工具
                lines.append(f"[工具 {tool.name}] 错误：{exc}")

        class _Resp:
            completion_text = ""

        if prompt in self.chat_responses:
            _Resp.completion_text = self.chat_responses[prompt]
        else:
            _Resp.completion_text = f"(模拟) AI 响应：{prompt}"
        if lines:
            _Resp.completion_text += "\n" + "\n".join(lines)
        return _Resp()

    async def send_message(self, umo, chain) -> None:
        self.sent.append((umo, _chain_to_text(chain)))


def _tool_result_to_text(ret) -> str:
    """把工具 handler 的返回值转为可读文本（str 或 mcp CallToolResult 均可）。"""
    if ret is None:
        return "(无返回内容)"
    if isinstance(ret, str):
        return ret
    content = getattr(ret, "content", None)
    if isinstance(content, list):
        return "\n".join((getattr(c, "text", None) or str(c)) for c in content)
    return str(ret)


def _chain_to_text(chain) -> str:
    chain_list = getattr(chain, "chain", None)
    if chain_list is None:
        chain_list = [chain]
    parts = []
    for comp in chain_list:
        seg_type = str(getattr(getattr(comp, "type", None), "name", None) or "").lower()
        if seg_type in ("image", "record"):
            label = "图片" if seg_type == "image" else "语音"
            src = getattr(comp, "file", None)
            if src is None:
                src = getattr(comp, "text", None)
            parts.append(f"[{label}: {src}]")
            continue
        text = getattr(comp, "text", None)
        if text is not None:
            parts.append(str(text))
        else:
            parts.append(str(comp))
    return "".join(parts)
