"""Blockly 程序数据模型的单元测试。"""

from blockly.mock_event import MockEvent
from blockly.program import (
    CONTENT_BLOCKLY,
    CONTENT_PYTHON,
    BlocklyProgram,
)


def test_from_dict_keeps_known_fields():
    data = {
        "id": "abc123",
        "name": "测试程序",
        "models": ["gpt-4o", "qwen-max"],
        "priority": "5",
        "timeout": "10",
        "unknown": {"x": 1},
    }
    p = BlocklyProgram.from_dict(data)
    assert p.id == "abc123"
    assert p.name == "测试程序"
    assert p.models == ["gpt-4o", "qwen-max"]
    assert p.priority == 5
    assert p.timeout == 10


def test_from_dict_normalizes_invalid_values():
    p = BlocklyProgram.from_dict(
        {
            "mode": "bad",
            "content_type": "bad",
            "trigger": {"type": "bad", "value": "x"},
            "priority": "not-a-number",
            "timeout": "not-a-number",
            "models": "not-a-list",
        }
    )
    assert p.content_type == CONTENT_BLOCKLY
    assert p.trigger["type"] == "all"
    assert p.priority == 0
    assert p.timeout == 30
    assert p.models == []


def test_from_dict_accepts_python_content_type():
    p = BlocklyProgram.from_dict({"content_type": CONTENT_PYTHON})
    assert p.content_type == CONTENT_PYTHON


def test_from_dict_repairs_bad_trigger():
    p = BlocklyProgram.from_dict({"trigger": None})
    assert p.trigger == {"type": "all", "value": ""}
    p2 = BlocklyProgram.from_dict({"trigger": "not-a-dict"})
    assert p2.trigger == {"type": "all", "value": ""}


def test_matches_all():
    p = BlocklyProgram(trigger={"type": "all"})
    assert p.matches(MockEvent(message_str="随便什么消息"))


def test_matches_contains():
    p = BlocklyProgram(trigger={"type": "contains", "value": "你好"})
    assert p.matches(MockEvent(message_str="朋友你好呀"))
    assert not p.matches(MockEvent(message_str="再见"))


def test_matches_prefix():
    p = BlocklyProgram(trigger={"type": "prefix", "value": "/test"})
    assert p.matches(MockEvent(message_str="  /test 开始执行"))
    assert not p.matches(MockEvent(message_str="xx/test 不匹配"))


def test_matches_regex():
    p = BlocklyProgram(trigger={"type": "regex", "value": r"温度\s*\d+"})
    assert p.matches(MockEvent(message_str="今天温度 28 度"))
    assert not p.matches(MockEvent(message_str="今天没有温度信息"))


def test_matches_regex_invalid():
    p = BlocklyProgram(trigger={"type": "regex", "value": "("})
    assert p.matches(MockEvent(message_str="任意消息")) is False


def test_matches_admin_only():
    p = BlocklyProgram(trigger={"type": "admin_only"})
    assert p.matches(MockEvent(message_str="x", is_admin=True))
    assert not p.matches(MockEvent(message_str="x", is_admin=False))


def test_mark_run():
    p = BlocklyProgram()
    assert p.run_count == 0
    p.mark_run()
    assert p.run_count == 1
    assert p.last_error == ""
    p.mark_run(error="boom", success=False)
    assert p.run_count == 2
    assert p.last_error == "boom"


def test_to_dict_roundtrip():
    p = BlocklyProgram(
        name="往返",
        models=["qwen-max"],
        trigger={"type": "contains", "value": "你好"},
    )
    restored = BlocklyProgram.from_dict(p.to_dict())
    assert restored.to_dict() == p.to_dict()
