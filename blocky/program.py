"""Blocky 程序数据模型。"""

from __future__ import annotations

import re
import time
import uuid
from dataclasses import asdict, dataclass, field

# 触发条件类型
TRIGGER_TYPES = ("all", "contains", "prefix", "regex", "admin_only")

# 内容类型
CONTENT_BLOCKLY = "blockly"
CONTENT_PYTHON = "python"

# 程序监听的事件类型
EVENT_TYPES = ("message", "recall", "member_increase", "poke")

# 消息事件的属性过滤（仅对 event_type=message 生效）
EVENT_ATTRS = ("any", "text", "image", "face", "at", "voice", "reply")


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def _now() -> float:
    return time.time()


@dataclass
class BlockyProgram:
    """一个 Blocky 程序（对应磁盘上的一个文件）。"""

    id: str = field(default_factory=new_id)
    name: str = "未命名程序"
    description: str = ""
    enabled: bool = False
    content_type: str = CONTENT_BLOCKLY
    workspace: str = ""  # Blockly 序列化 JSON（content_type 为 blockly 时使用）
    code: str = ""  # 生成的或手写的 Python 代码
    trigger: dict = field(default_factory=lambda: {"type": "all", "value": ""})
    event_type: str = "message"  # 监听的 AstrBot 事件类型（消息/撤回/新成员/戳一戳）
    event_attr: str = "any"  # 消息属性过滤：any/text/image/face/at/voice/reply
    models: list[str] = field(
        default_factory=list
    )  # AI 积木可用模型白名单，空表示不限制
    priority: int = 0
    timeout: int = 30
    last_error: str = ""
    last_run_at: float = 0
    run_count: int = 0
    created_at: float = field(default_factory=_now)
    updated_at: float = field(default_factory=_now)

    def to_dict(self) -> dict:
        data = asdict(self)
        return data

    @classmethod
    def from_dict(cls, data: dict) -> BlockyProgram:
        known = {f for f in cls.__dataclass_fields__}
        data = {k: v for k, v in (data or {}).items() if k in known}
        if "content_type" in data and data["content_type"] not in (
            CONTENT_BLOCKLY,
            CONTENT_PYTHON,
        ):
            data["content_type"] = CONTENT_BLOCKLY
        models = data.get("models")
        if not isinstance(models, list):
            models = []
        data["models"] = [str(m) for m in models if str(m).strip()]
        trig = data.get("trigger")
        if not isinstance(trig, dict):
            trig = {"type": "all", "value": ""}
        if trig.get("type") not in TRIGGER_TYPES:
            trig["type"] = "all"
        data["trigger"] = trig
        if data.get("event_type") not in EVENT_TYPES:
            data["event_type"] = "message"
        if data.get("event_attr") not in EVENT_ATTRS:
            data["event_attr"] = "any"
        try:
            data["priority"] = int(data.get("priority") or 0)
        except (TypeError, ValueError):
            data["priority"] = 0
        try:
            data["timeout"] = max(1, int(data.get("timeout") or 30))
        except (TypeError, ValueError):
            data["timeout"] = 30
        return cls(**data)

    def matches(self, event) -> bool:
        """根据触发条件判断该程序是否应处理当前消息事件。"""
        trig = self.trigger or {}
        t = trig.get("type", "all")
        value = str(trig.get("value") or "")
        message = getattr(event, "message_str", "") or ""
        try:
            if t == "contains":
                return bool(value) and value in message
            if t == "prefix":
                return bool(value) and message.strip().startswith(value)
            if t == "regex":
                if not value:
                    return False
                try:
                    return re.search(value, message) is not None
                except re.error:
                    return False
            if t == "admin_only":
                return bool(event.is_admin())
        except Exception:  # noqa: BLE001 - 触发判断出错时视为不匹配
            return False
        return True

    def mark_run(self, error: str = "", success: bool = True) -> None:
        self.run_count += 1
        self.last_run_at = _now()
        self.last_error = error if not success else ""
