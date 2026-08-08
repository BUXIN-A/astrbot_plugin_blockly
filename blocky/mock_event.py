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
    ) -> None:
        self.message_str = message_str
        self._sender_name = sender_name
        self._sender_id = sender_id
        self._group_id = group_id
        self._platform = platform
        self._is_admin = is_admin
        self._is_private = is_private
        self.unified_msg_origin = f"{platform}:frien_m_message:mock_session"
        self._result = None
        self._force_stopped = False
        self.sent_messages: list[str] = []

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
        self.current_model = current_model
        self.current_provider = current_provider

    async def get_current_model(self) -> str:
        return self.current_model

    async def get_current_chat_provider_id(self, umo=None) -> str:
        return self.current_provider

    async def llm_generate(self, chat_provider_id=None, prompt="", **kwargs):
        class _Resp:
            completion_text = ""

        if prompt in self.chat_responses:
            _Resp.completion_text = self.chat_responses[prompt]
        else:
            _Resp.completion_text = f"(模拟) AI 响应：{prompt}"
        return _Resp()

    async def send_message(self, umo, chain) -> None:
        self.sent.append((umo, _chain_to_text(chain)))


def _chain_to_text(chain) -> str:
    chain_list = getattr(chain, "chain", None)
    if chain_list is None:
        chain_list = [chain]
    parts = []
    for comp in chain_list:
        text = getattr(comp, "text", None)
        if text is not None:
            parts.append(str(text))
        else:
            parts.append(str(comp))
    return "".join(parts)
