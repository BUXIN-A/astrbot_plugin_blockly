"""Blocky 受限执行引擎的单元测试。"""

import asyncio

from blocky.program import BlockyProgram
from blocky.runtime import simulate_program as run_sim
from blocky.runtime import wrap_code


def test_wrap_code_builds_async_function():
    source = wrap_code("await _blk.reply('hi')")
    assert "async def _blk_run(event, ctx, _blk):" in source
    assert "await _blk.reply('hi')" in source


def test_reply_continues():
    program = BlockyProgram(code="await _blk.reply('你好')")
    result = asyncio.run(run_sim(program, message="hi"))
    assert "你好" in result["replies"]
    assert result["stopped"] is False


def test_return_msg_stops():
    program = BlockyProgram(code="await _blk.return_msg('再见')")
    result = asyncio.run(run_sim(program, message="hi"))
    assert "再见" in result["replies"]
    assert result["stopped"] is True


def test_no_stop_block_by_default():
    """未使用返回/停止积木时，事件不停止（交由 AstrBot 继续处理）。"""
    program = BlockyProgram(code="await _blk.reply('hi')")
    result = asyncio.run(run_sim(program, message="x"))
    assert result["replies"] == ["hi"]
    assert result["stopped"] is False


def test_empty_program_does_not_stop():
    program = BlockyProgram(code="")
    result = asyncio.run(run_sim(program, message="hi"))
    assert result["stopped"] is False
    assert result["error"] == ""


def test_forward_block_keeps_running():
    program = BlockyProgram(code="_blk.forward()")
    result = asyncio.run(run_sim(program, message="hi"))
    assert result["stopped"] is False


def test_stop_block():
    program = BlockyProgram(code="_blk.stop()")
    result = asyncio.run(run_sim(program, message="hi"))
    assert result["stopped"] is True


def test_chat_block():
    program = BlockyProgram(code="await _blk.reply(await _blk.chat('天气'))")
    result = asyncio.run(
        run_sim(program, message="hi", chat_responses={"天气": "晴天"})
    )
    assert "晴天" in result["replies"]


def test_chat_uses_authorized_model_when_current_not_allowed():
    program = BlockyProgram(
        models=["qwen-max"],
        code="await _blk.reply(await _blk.chat('天气'))",
    )
    result = asyncio.run(
        run_sim(
            program,
            message="hi",
            chat_responses={"天气": "晴天"},
            current_model="gpt-4o",
        )
    )
    assert "晴天" in result["replies"]


def test_message_info_blocks():
    program = BlockyProgram(
        code="""
name = _blk.get_sender_name()
msg = _blk.get_message()
await _blk.reply(name + ': ' + msg)
""",
    )
    result = asyncio.run(run_sim(program, message="你好"))
    assert "测试用户: 你好" in result["replies"]


def test_admin_and_private_flags():
    program = BlockyProgram(
        code="""
await _blk.reply('admin=' + str(_blk.is_admin()) + ' private=' + str(_blk.is_private()))
""",
    )
    result = asyncio.run(run_sim(program, message="x", is_admin=True, is_private=True))
    assert "admin=True private=True" in result["replies"]


def test_send_block():
    program = BlockyProgram(code="await _blk.send('mock:group:g1', '群消息')")
    result = asyncio.run(run_sim(program, message="x"))
    assert ("mock:group:g1", "群消息") in result["sends"]


def test_timeout():
    program = BlockyProgram(code="await _blk.sleep(999999)")
    result = asyncio.run(run_sim(program, message="hi", timeout=0.05))
    assert result["error"] == "执行超时"


def test_syntax_error_reported():
    program = BlockyProgram(code="def broken(")
    result = asyncio.run(run_sim(program, message="hi"))
    assert "语法错误" in result["error"]


def test_safe_builtins_block_import():
    program = BlockyProgram(
        code="""
try:
    _ = __import__('os')
    result = 'unsafe'
except Exception:
    result = 'blocked'
await _blk.reply(result)
""",
    )
    result = asyncio.run(run_sim(program, message="x"))
    assert "blocked" in result["replies"]


def test_safe_builtins_block_open():
    program = BlockyProgram(
        code="""
try:
    _ = open('/etc/hostname')
    result = 'unsafe'
except Exception:
    result = 'blocked'
await _blk.reply(result)
""",
    )
    result = asyncio.run(run_sim(program, message="x"))
    assert "blocked" in result["replies"]


def test_math_and_random_available():
    program = BlockyProgram(
        code="""
await _blk.reply(str(math.floor(3.7)) + ' ' + str(int(random.random() >= 0 or 1)))
""",
    )
    result = asyncio.run(run_sim(program, message="x"))
    assert "3 1" in result["replies"]
