"""Blockly 程序数据模型。"""

from __future__ import annotations

import json
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
EVENT_TYPES = ("message", "recall", "member_increase", "member_decrease", "poke")

# 消息事件的属性过滤（仅对 message 事件生效）
EVENT_ATTRS = ("any", "text", "image", "face", "at", "voice", "reply")

# Blockly 事件入口积木类型 -> 事件类型
EVENT_BLOCK_TYPES = {
    "blockly_event": "message",
    "blockly_event_recall": "recall",
    "blockly_event_member_increase": "member_increase",
    "blockly_event_member_decrease": "member_decrease",
    "blockly_event_poke": "poke",
}


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def _now() -> float:
    return time.time()


def normalize_event_types(value) -> list[str]:
    """规范化事件类型为去重、有序、合法的列表。

    支持字符串（逗号分隔，如 ``"message,recall"``）或列表；非法项被剔除，
    结果为空时回退为 ``["message"]``。
    """
    if isinstance(value, (list, tuple, set)):
        parts = [str(x).strip() for x in value]
    else:
        parts = [p.strip() for p in str(value or "").split(",")]
    valid: list[str] = []
    for part in parts:
        if part in EVENT_TYPES and part not in valid:
            valid.append(part)
    return valid or ["message"]


def workspace_event_types(workspace_json: str) -> list[str]:
    """从积木工作区 JSON 中提取所有事件入口积木对应的事件类型。"""
    if not workspace_json:
        return []
    try:
        data = json.loads(workspace_json)
    except (TypeError, ValueError):
        return []
    blocks = (data.get("blocks") or {}).get("blocks") or []
    found: list[str] = []

    def walk(block: dict) -> None:
        if not isinstance(block, dict):
            return
        event_type = EVENT_BLOCK_TYPES.get(block.get("type"))
        if event_type and event_type not in found:
            found.append(event_type)
        node = block.get("inputs") or {}
        for sub in node.values():
            if isinstance(sub, dict):
                walk(sub.get("block"))
        nxt = block.get("next")
        if isinstance(nxt, dict):
            walk(nxt.get("block"))

    for block in blocks:
        walk(block)
    return found


@dataclass
class BlocklyProgram:
    """一个 Blockly 程序（对应磁盘上的一个文件）。"""

    id: str = field(default_factory=new_id)
    name: str = "未命名程序"
    description: str = ""
    enabled: bool = False
    content_type: str = CONTENT_BLOCKLY
    workspace: str = ""  # Blockly 序列化 JSON（content_type 为 blockly 时使用）
    code: str = ""  # 生成的或手写的 Python 代码
    trigger: dict = field(default_factory=lambda: {"type": "all", "value": ""})
    event_type: str = "message"  # 监听的事件类型；多个用逗号分隔（如 "message,recall"）
    event_attr: str = "any"  # message 属性过滤：any/text/image/face/at/voice/reply
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

    @property
    def event_types(self) -> list[str]:
        """按事件块顺序返回监听的事件类型列表（逗号分隔的 ``event_type`` 解析结果）。"""
        return normalize_event_types(self.event_type)

    def sync_event_type_from_workspace(self) -> None:
        """以积木工作区中的事件入口块为权威，回填 ``event_type``。

        向后兼容：旧版本仅保存画布上第一个事件块、且更换事件类型后通知类事件
        无法触发，这里保证加载/导入后多个事件块都能被正确识别。
        """
        if self.content_type != CONTENT_BLOCKLY:
            return
        ws_types = workspace_event_types(self.workspace)
        if ws_types:
            self.event_type = ",".join(ws_types)

    def to_dict(self) -> dict:
        data = asdict(self)
        return data

    @classmethod
    def from_dict(cls, data: dict) -> BlocklyProgram:
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
        data["event_type"] = ",".join(normalize_event_types(data.get("event_type")))
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
        program = cls(**data)
        program.sync_event_type_from_workspace()
        return program

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
