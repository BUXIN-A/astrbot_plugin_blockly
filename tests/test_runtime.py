"""Blockly 受限执行引擎的单元测试。"""

import asyncio
from pathlib import Path

from blockly.program import BlocklyProgram
from blockly.runtime import _assert_safe_source, wrap_code
from blockly.runtime import simulate_program as run_sim


def test_wrap_code_builds_async_function():
    source = wrap_code("await _blk.reply('hi')")
    assert "async def _blk_run(event, ctx, _blk):" in source
    assert "await _blk.reply('hi')" in source


def test_wrap_code_accepts_nested_blocks():
    """顶层代码无缩进、内部带 Blockly 缩进的代码包装后必须可编译。

    回归：事件块生成器若给顶层代码整体加缩进，包装成函数体会触发
    unexpected indent / unindent 语法错误。
    """
    code = (
        "if _blk.get_message() == '你好':\n"
        "  await _blk.return_msg('hello')\n"
        "else:\n"
        "  await _blk.return_msg('other')\n"
    )
    source = wrap_code(code)
    _assert_safe_source(source)
    compile(source, "<test>", "exec")


def test_wrap_code_accepts_multiple_statements():
    code = "await _blk.reply('a')\nawait _blk.reply('b')\n"
    source = wrap_code(code)
    _assert_safe_source(source)
    compile(source, "<test>", "exec")


def test_reply_continues():
    program = BlocklyProgram(code="await _blk.reply('你好')")
    result = asyncio.run(run_sim(program, message="hi"))
    assert "你好" in result["replies"]
    assert result["stopped"] is False


def test_return_msg_stops():
    program = BlocklyProgram(code="await _blk.return_msg('再见')")
    result = asyncio.run(run_sim(program, message="hi"))
    assert "再见" in result["replies"]
    assert result["stopped"] is True


def test_no_stop_block_by_default():
    """未使用返回/停止积木时，事件不停止（交由 AstrBot 继续处理）。"""
    program = BlocklyProgram(code="await _blk.reply('hi')")
    result = asyncio.run(run_sim(program, message="x"))
    assert result["replies"] == ["hi"]
    assert result["stopped"] is False


def test_empty_program_does_not_stop():
    program = BlocklyProgram(code="")
    result = asyncio.run(run_sim(program, message="hi"))
    assert result["stopped"] is False
    assert result["error"] == ""


def test_blockly_with_blocks_but_no_code_reports_error():
    """积木程序有积木内容但缺少生成的 code 时，应给出明确错误而非静默跳过。"""
    workspace = (
        '{"blocks": {"languageVersion": 0, "blocks": [{"type": "blockly_event"}]}}'
    )
    program = BlocklyProgram(content_type="blockly", workspace=workspace, code="")
    result = asyncio.run(run_sim(program, message="hi"))
    assert result["error"] != ""


def test_forward_block_keeps_running():
    program = BlocklyProgram(code="_blk.forward()")
    result = asyncio.run(run_sim(program, message="hi"))
    assert result["stopped"] is False


def test_stop_block():
    program = BlocklyProgram(code="_blk.stop()")
    result = asyncio.run(run_sim(program, message="hi"))
    assert result["stopped"] is True


def test_chat_block():
    program = BlocklyProgram(code="await _blk.reply(await _blk.chat('天气'))")
    result = asyncio.run(
        run_sim(program, message="hi", chat_responses={"天气": "晴天"})
    )
    assert "晴天" in result["replies"]


def test_chat_uses_authorized_model_when_current_not_allowed():
    program = BlocklyProgram(
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


def test_chat_allowlist_compound_provider_model():
    """白名单条目为 提供商ID:模型ID，当前模型不在名单时改用白名单模型。"""
    program = BlocklyProgram(
        models=["mock_provider:qwen-max"],
        code="await _blk.reply(await _blk.chat('天气'))",
    )
    result = asyncio.run(
        run_sim(
            program,
            message="hi",
            chat_responses={"天气": "晴天"},
            current_model="gpt-4o",
            current_provider="mock_provider",
        )
    )
    assert "晴天" in result["replies"]


def test_chat_allowlist_current_provider_model_allowed():
    """当前 提供商+模型 已在白名单中时不切换模型。"""
    program = BlocklyProgram(
        models=["mock_provider:mock-model"],
        code="await _blk.reply(await _blk.chat('天气'))",
    )
    result = asyncio.run(
        run_sim(
            program,
            message="hi",
            chat_responses={"天气": "晴天"},
            current_model="mock-model",
            current_provider="mock_provider",
        )
    )
    assert "晴天" in result["replies"]


def test_message_info_blocks():
    program = BlocklyProgram(
        code="""
name = _blk.get_sender_name()
msg = _blk.get_message()
await _blk.reply(name + ': ' + msg)
""",
    )
    result = asyncio.run(run_sim(program, message="你好"))
    assert "测试用户: 你好" in result["replies"]


def test_admin_and_private_flags():
    program = BlocklyProgram(
        code="""
await _blk.reply('admin=' + str(_blk.is_admin()) + ' private=' + str(_blk.is_private()))
""",
    )
    result = asyncio.run(run_sim(program, message="x", is_admin=True, is_private=True))
    assert "admin=True private=True" in result["replies"]


def test_send_block():
    program = BlocklyProgram(code="await _blk.send('mock:group:g1', '群消息')")
    result = asyncio.run(run_sim(program, message="x"))
    assert ("mock:group:g1", "群消息") in result["sends"]


def test_timeout():
    program = BlocklyProgram(code="await _blk.sleep(999999)")
    result = asyncio.run(run_sim(program, message="hi", timeout=0.05))
    assert result["error"] == "执行超时"


def test_syntax_error_reported():
    program = BlocklyProgram(code="def broken(")
    result = asyncio.run(run_sim(program, message="hi"))
    assert "语法错误" in result["error"]


def test_safe_builtins_block_open():
    program = BlocklyProgram(
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


def test_magic_attribute_blocked():
    """AST 静态检查阻断 ``().__class__`` 等沙箱逃逸。"""
    program = BlocklyProgram(code="await _blk.reply(str(().__class__))")
    result = asyncio.run(run_sim(program, message="x"))
    assert "禁止" in result["error"]


def test_double_underscore_name_blocked():
    """AST 静态检查阻断 ``__import__`` 等魔术名称。"""
    program = BlocklyProgram(code="await _blk.reply(str(__import__))")
    result = asyncio.run(run_sim(program, message="x"))
    assert "禁止" in result["error"]


def test_import_blocked():
    """AST 静态检查阻断 import 语句。"""
    program = BlocklyProgram(code="import os\nawait _blk.reply('x')")
    result = asyncio.run(run_sim(program, message="x"))
    assert "禁止" in result["error"]


def test_math_and_random_available():
    program = BlocklyProgram(
        code="""
await _blk.reply(str(math.floor(3.7)) + ' ' + str(int(random.random() >= 0 or 1)))
""",
    )
    result = asyncio.run(run_sim(program, message="x"))
    assert "3 1" in result["replies"]


def test_message_type_text_and_not():
    program = BlocklyProgram(
        code="await _blk.reply(_blk.get_message_type())",
    )
    result = asyncio.run(run_sim(program, message="hi", message_type="text"))
    assert result["replies"] == ["text"]
    result2 = asyncio.run(run_sim(program, message="hi", message_type="image"))
    assert result2["replies"] == ["image"]


def test_has_type_blocks():
    program = BlocklyProgram(
        code="""
await _blk.reply(str(_blk.has_type('image')) + ',' + str(_blk.has_type('face')))
""",
    )
    result = asyncio.run(run_sim(program, message="x", message_type="face"))
    assert "False,True" in result["replies"]


def test_resolve_notice_event_kinds():
    """通知类事件（撤回/戳一戳）应被识别为对应的事件类型。"""
    from blockly.mock_event import MockEvent
    from blockly.runtime import resolve_event_kind

    recall = MockEvent(
        message_str="",
        raw_message={
            "post_type": "notice",
            "notice_type": "group_recall",
            "group_id": "255918033",
            "user_id": "1451173433",
            "operator_id": "1451173433",
            "message_id": 999,
        },
    )
    assert resolve_event_kind(recall) == "recall"

    poke = MockEvent(
        raw_message={
            "post_type": "notice",
            "notice_type": "notify",
            "group_id": "255918033",
            "user_id": "1451173433",
            "target_id": "2222",
            "sub_type": "poke",
        },
    )
    assert resolve_event_kind(poke) == "poke"

    joined = MockEvent(
        raw_message={
            "post_type": "notice",
            "notice_type": "group_increase",
            "group_id": "255918033",
            "sender_id": "1451173433",
        },
    )
    assert resolve_event_kind(joined) == "member_increase"

    plain = MockEvent(message_str="你好")
    assert resolve_event_kind(plain) == "message"


def test_event_type_and_ids():
    """事件类型块返回本次执行对应的真实事件类型，而非程序配置。"""
    from blockly.mock_event import MockContext, MockEvent
    from blockly.runtime import run_program

    program = BlocklyProgram(
        code="""
await _blk.reply(_blk.get_event_type() + '|' + _blk.get_sender_id())
""",
    )
    event = MockEvent(
        message_str="",
        raw_message={
            "post_type": "notice",
            "notice_type": "group_recall",
            "group_id": "255918033",
            "user_id": "1451173433",
            "operator_id": "1451173433",
            "message_id": 1024,
        },
    )

    async def run():
        await run_program(program, MockContext(), event)

    asyncio.run(run())
    assert event.sent_messages == ["recall|123456789"]


def test_program_event_types_multi():
    """event_type 支持逗号分隔的多事件；from_dict 会规范化并去重。"""
    from blockly.program import BlocklyProgram

    program = BlocklyProgram.from_dict(
        {
            "name": "multi",
            "event_type": "message,recall,message,poke",
            "enabled": True,
        }
    )
    assert program.event_types == ["message", "recall", "poke"]

    program2 = BlocklyProgram.from_dict({"event_type": "unknown_event"})
    assert program2.event_types == ["message"]


def test_workspace_event_types_sync():
    """from_dict 会从积木工作区中的多个事件入口块推断 event_type（兼容旧数据）。"""
    from blockly.program import BlocklyProgram

    workspace = """{"blocks":{"languageVersion":0,"blocks":[
        {"type":"blockly_event","id":"1","inputs":{"DO":{"block":{"type":"text","id":"t1"}}}},
        {"type":"blockly_event_recall","id":"2"},
        {"type":"blockly_event_poke","id":"3","next":{"block":{"type":"blockly_log","id":"4"}}}
    ]}}"""
    program = BlocklyProgram.from_dict(
        {
            "workspace": workspace,
            "event_type": "message",  # 旧版本保存的可能是 message
        }
    )
    assert program.event_types == ["message", "recall", "poke"]


def test_chat_block_models_ordered():
    """AI 积木「指定模型」按顺序尝试；成功即返回。"""
    program = BlocklyProgram(
        models=[],
        code="""
await _blk.reply(await _blk.chat('天气', 'mock_provider:qwen-max,mock_provider:mock-model'))
""",
    )
    result = asyncio.run(
        run_sim(program, message="hi", chat_responses={"天气": "晴天"})
    )
    assert "晴天" in result["replies"]


def test_chat_models_all_failed_raises():
    """全部指定模型失败时报错并给出各模型原因。"""

    async def failing_run():
        from blockly.mock_event import MockContext, MockEvent
        from blockly.runtime import run_program

        program = BlocklyProgram(
            models=[],
            code="""
await _blk.reply(await _blk.chat('天气', 'bad_provider:bad-model'))
""",
        )
        ctx = MockContext()
        ctx.chat_failure_models = {"bad_provider:bad-model"}
        try:
            await run_program(program, ctx, MockEvent(message_str="hi"))
        except RuntimeError as exc:
            return str(exc)
        return ""

    error = asyncio.run(failing_run())
    assert "全部请求失败" in error


def test_tool_generated_code_compiles():
    """前端「AI 工具」生成器输出的代码可被沙箱编译并正常执行。"""
    code = (
        "async def blk_tool_abc():\n"
        "    _blk.tool_return(_blk.get_message())\n"
        "_blk.tool('my_tool', 'desc', blk_tool_abc, True)\n"
        "if _blk.event_type == 'message':\n"
        "    await _blk.reply(await _blk.chat('hi'))\n"
    )
    source = wrap_code(code)
    _assert_safe_source(source)
    compile(source, "<test>", "exec")
    program = BlocklyProgram(code=code)
    result = asyncio.run(run_sim(program, message="hi"))
    assert result["error"] == ""
    assert result["replies"] and "hi" in result["replies"][0]


def test_ai_tool_registered_and_called():
    """「AI 工具」注册后由工具循环调用，返回值作为结果返回给 AI。"""
    program = BlocklyProgram(
        code="""
async def blk_tool_abc():
    await _blk.reply('工具被调用')
    _blk.tool_return('42')
_blk.tool('my_tool', '查询数字', blk_tool_abc, True)
await _blk.reply(await _blk.chat('给我一个数字'))
""",
    )
    result = asyncio.run(run_sim(program, message="hi"))
    assert result["error"] == ""
    assert "工具被调用" in result["replies"]
    assert any("[工具 my_tool] 42" in r for r in result["replies"])


def test_ai_tool_no_return_content():
    """RETURN 未勾选时不向 AI 返回内容。"""
    program = BlocklyProgram(
        code="""
async def blk_tool_abc():
    _blk.log('done')
_blk.tool('my_tool', '描述', blk_tool_abc, False)
await _blk.reply(await _blk.chat('hi'))
""",
    )
    result = asyncio.run(run_sim(program, message="x"))
    assert result["error"] == ""
    assert result["replies"] and "无返回内容" in result["replies"][0]


def test_ai_tool_empty_name_raises():
    """工具名称为空时报错。"""
    program = BlocklyProgram(code="_blk.tool('', 'x', lambda: None, True)")
    result = asyncio.run(run_sim(program, message="x"))
    assert "不能为空" in result["error"]


def test_reply_image_and_voice():
    """回复积木支持图片/语音类型（模拟环境显示为 [图片/语音: 地址]）。"""
    program = BlocklyProgram(
        code="await _blk.reply('https://example.com/a.png', 'image')"
    )
    result = asyncio.run(run_sim(program, message="x"))
    assert any("[图片:" in r for r in result["replies"])

    program2 = BlocklyProgram(
        code="await _blk.reply('https://example.com/a.mp3', 'voice')"
    )
    result2 = asyncio.run(run_sim(program2, message="x"))
    assert any("[语音:" in r for r in result2["replies"])


def test_return_msg_image_stops():
    """返回消息积木选择图片类型时同样劫持事件。"""
    program = BlocklyProgram(
        code="await _blk.return_msg('https://example.com/a.png', 'image')"
    )
    result = asyncio.run(run_sim(program, message="x"))
    assert result["stopped"] is True
    assert any("[图片:" in r for r in result["replies"])


def test_send_image_and_voice():
    """主动发送积木支持图片/语音类型。"""
    program = BlocklyProgram(
        code="await _blk.send('mock:group:g1', 'https://example.com/a.png', 'image')"
    )
    result = asyncio.run(run_sim(program, message="x"))
    assert result["sends"] and any(
        "mock:group:g1" == umo and "[图片:" in text for umo, text in result["sends"]
    )


def test_global_store_set_get_delete():
    """持久化变量设置/读取/删除（JSON 落盘）。"""
    import tempfile

    from blockly.runtime import init_global_store

    with tempfile.TemporaryDirectory() as tmp:
        store_path = str(Path(tmp) / "global_store.json")
        init_global_store(store_path)

        program = BlocklyProgram(
            code="""
_blk.store_set('count', 3)
_blk.store_set('name', 'Alice')
await _blk.reply(str(_blk.store_get('count')) + ',' + str(_blk.store_get('name')) + ',' + str(_blk.store_get('missing', 'none')))
_blk.store_del('name')
await _blk.reply(str(_blk.store_get('name', 'gone')))
""",
        )
        result = asyncio.run(run_sim(program, message="x"))
        assert result["error"] == ""
        assert "3,Alice,none" in result["replies"]
        assert "gone" in result["replies"]


def test_global_store_persists_across_reload():
    """重新初始化（模拟重启）后持久化变量仍然存在。"""
    import tempfile

    from blockly.runtime import init_global_store

    with tempfile.TemporaryDirectory() as tmp:
        store_path = str(Path(tmp) / "global_store.json")
        init_global_store(store_path)

        writer = BlocklyProgram(code="_blk.store_set('count', 7)")
        asyncio.run(run_sim(writer, message="x"))

        # 模拟重启：重新初始化同一路径
        init_global_store(store_path)
        reader = BlocklyProgram(code="await _blk.reply(str(_blk.store_get('count')))")
        result = asyncio.run(run_sim(reader, message="x"))
        assert "7" in result["replies"]


def test_global_func_define_and_call():
    """全局函数定义后可被另一个程序调用并返回结果。"""
    from blockly.runtime import _clear_global_funcs

    _clear_global_funcs()
    define = BlocklyProgram(
        code="""
async def blk_gf_test(a, b):
    return a + b
_blk.define_global_func('add', blk_gf_test)
await _blk.reply('defined')
""",
    )
    result = asyncio.run(run_sim(define, message="x"))
    assert result["error"] == ""

    call = BlocklyProgram(
        code="await _blk.reply(str(await _blk.global_call('add', 1, 2)))",
    )
    result2 = asyncio.run(run_sim(call, message="x"))
    assert "3" in result2["replies"]


def test_global_func_missing_raises():
    """调用未注册的全局函数时给出明确错误。"""
    from blockly.runtime import _clear_global_funcs

    _clear_global_funcs()
    program = BlocklyProgram(code="await _blk.global_call('nope')")
    result = asyncio.run(run_sim(program, message="x"))
    assert "未找到全局函数" in result["error"]


def test_global_func_generated_code_compiles():
    """前端「全局函数定义/调用」生成器输出的代码可被沙箱编译并执行。"""
    from blockly.runtime import _clear_global_funcs

    _clear_global_funcs()
    code = (
        "async def blk_gf_abc(a, b):\n"
        "    return a + b\n"
        "_blk.define_global_func('add', blk_gf_abc)\n"
        "if _blk.event_type == 'message':\n"
        "    await _blk.reply(str(await _blk.global_call('add', 2, 3)))\n"
    )
    source = wrap_code(code)
    _assert_safe_source(source)
    compile(source, "<test>", "exec")
    program = BlocklyProgram(code=code)
    result = asyncio.run(run_sim(program, message="hi"))
    assert result["error"] == ""
    assert any("5" in r for r in result["replies"])


def test_store_generated_code_compiles():
    """前端「持久化变量」生成器输出的代码可被沙箱编译并执行。"""
    import tempfile

    from blockly.runtime import init_global_store

    with tempfile.TemporaryDirectory() as tmp:
        init_global_store(str(Path(tmp) / "global_store.json"))
        code = (
            "_blk.store_set('count', 3)\n"
            "if _blk.event_type == 'message':\n"
            "    await _blk.reply(str(_blk.store_get('count', 0)))\n"
            "_blk.store_del('count')\n"
        )
        source = wrap_code(code)
        _assert_safe_source(source)
        compile(source, "<test>", "exec")
        program = BlocklyProgram(code=code)
        result = asyncio.run(run_sim(program, message="hi"))
        assert result["error"] == ""
        assert any("3" in r for r in result["replies"])


def test_resolve_member_decrease_event():
    """群成员退群（group_decrease）应被识别为 member_decrease 事件。"""
    from blockly.mock_event import MockEvent
    from blockly.runtime import resolve_event_kind

    left = MockEvent(
        message_str="",
        raw_message={
            "post_type": "notice",
            "notice_type": "group_decrease",
            "group_id": "255918033",
            "user_id": "1451173433",
            "operator_id": "1451173433",
        },
    )
    assert resolve_event_kind(left) == "member_decrease"


def test_type_name_and_cast():
    """类型判断与类型转换块。"""
    program = BlocklyProgram(
        code="""
await _blk.reply(_blk.type_name(3) + ',' + _blk.type_name('x') + ',' + _blk.type_name(None))
await _blk.reply(str(int('42') + 1) + ',' + str(float(2)) + ',' + str(bool(0)) + ',' + str(list('ab')))
""",
    )
    result = asyncio.run(run_sim(program, message="x"))
    assert "int,str,NoneType" in result["replies"]
    assert "43,2.0,False,['a', 'b']" in result["replies"]


def test_json_blocks():
    """JSON 解析/序列化/取值块。"""
    program = BlocklyProgram(
        code="""
data = _blk.json_parse('{"name":"小明","age":18}')
await _blk.reply(str(_blk.json_get(data, 'name')) + ',' + str(_blk.json_get(data, 'age')))
await _blk.reply(_blk.json_stringify({'a': 1, 'b': '中文'}))
await _blk.reply(str(_blk.json_get('{"k":7}', 'k')))
await _blk.reply(str(_blk.json_get(data, 'missing', 'none')))
""",
    )
    result = asyncio.run(run_sim(program, message="x"))
    assert "小明,18" in result["replies"]
    assert '{"a": 1, "b": "中文"}' in result["replies"]
    assert "7" in result["replies"]
    assert "none" in result["replies"]


def test_text_split_generated_code():
    """文本分割块（前端生成器输出）可编译执行。"""
    code = (
        "if _blk.event_type == 'message':\n"
        "    await _blk.reply(str(str(_blk.get_message()).split(',')))\n"
    )
    source = wrap_code(code)
    _assert_safe_source(source)
    compile(source, "<test>", "exec")
    program = BlocklyProgram(code=code)
    result = asyncio.run(run_sim(program, message="a,b,c"))
    assert "['a', 'b', 'c']" in result["replies"]


def test_has_type_text_pure_text():
    """消息属性判断：纯文本消息 has_type('text') 为 True，含图片时为 False。"""
    program = BlocklyProgram(
        code="await _blk.reply(str(_blk.has_type('text')) + ',' + str(_blk.has_type('image')))",
    )
    result = asyncio.run(run_sim(program, message="hi", message_type="text"))
    assert "True,False" in result["replies"]

    program2 = BlocklyProgram(
        code="await _blk.reply(str(_blk.has_type('text')) + ',' + str(_blk.has_type('image')))",
    )
    result2 = asyncio.run(run_sim(program2, message="hi", message_type="image"))
    assert "False,True" in result2["replies"]


def test_json_keys():
    """JSON 所有键块：返回字典键列表（支持直接传 JSON 字符串）。"""
    program = BlocklyProgram(
        code="""
await _blk.reply(str(_blk.json_keys('{"a":1,"b":2,"c":3}')))
await _blk.reply(str(_blk.json_keys({'x': 1})))
await _blk.reply(str(_blk.json_keys('[1,2]')))
""",
    )
    result = asyncio.run(run_sim(program, message="x"))
    assert "['a', 'b', 'c']" in result["replies"]
    assert "['x']" in result["replies"]
    assert "[]" in result["replies"]


def test_to_list_smart_conversion():
    """类型转换为列表：字符串按 JSON 数组/换行/逗号智能解析，而非逐字符拆散。"""
    program = BlocklyProgram(
        code="""
await _blk.reply(str(_blk.to_list('["a", "b", "c"]')))
await _blk.reply(str(_blk.to_list('第一行\\n第二行')))
await _blk.reply(str(_blk.to_list('x, y, z')))
await _blk.reply(str(_blk.to_list({'k1': 1, 'k2': 2})))
await _blk.reply(str(_blk.to_list((1, 2))))
await _blk.reply(str(_blk.to_list(42)))
""",
    )
    result = asyncio.run(run_sim(program, message="x"))
    assert result["error"] == ""
    assert "['a', 'b', 'c']" in result["replies"]
    assert "['第一行', '第二行']" in result["replies"]
    assert "['x', 'y', 'z']" in result["replies"]
    assert "['k1', 'k2']" in result["replies"]
    assert "[1, 2]" in result["replies"]
    assert "[42]" in result["replies"]


def test_to_list_json_like_python_repr():
    """回归：字符串为 Python 列表字面量格式时解析为真实列表（test.txt 场景）。"""
    text = (
        '[\n    "20260820 223600\\n我受不了了，为什么要冤枉我，我凭什么受罪\\n😢\\n我只是想要放松一会，就那么一会！",\n'
        '    "20260820 224935\\n好烦，睡了，哈哈"\n]'
    )
    program = BlocklyProgram(
        code=f"await _blk.reply(str(_blk.to_list({text!r})))",
    )
    result = asyncio.run(run_sim(program, message="x"))
    assert result["error"] == ""
    assert result["replies"][0].startswith("[")
    assert "我受不了了" in result["replies"][0]
    assert "好烦，睡了" in result["replies"][0]


def test_type_cast_list_generated_code():
    """类型转换积木「列表」生成器输出 _blk.to_list，可编译执行。"""
    code = (
        "if _blk.event_type == 'message':\n"
        "    await _blk.reply(str(_blk.to_list(_blk.get_message())))\n"
    )
    source = wrap_code(code)
    _assert_safe_source(source)
    compile(source, "<test>", "exec")
    program = BlocklyProgram(code=code)
    result = asyncio.run(run_sim(program, message='["甲", "乙"]'))
    assert "['甲', '乙']" in result["replies"]


def test_up_range_down_range_fallback():
    """后端命名空间兜底：旧程序调用 upRange/downRange 不再报 NameError。"""
    program = BlocklyProgram(
        code="""
if _blk.event_type == 'message':
    for i in upRange(1, 3, 1):
        await _blk.reply(str(i))
""",
    )
    result = asyncio.run(run_sim(program, message="x"))
    assert result["error"] == ""
    assert result["replies"] == ["1", "2", "3"]

    program2 = BlocklyProgram(
        code="""
if _blk.event_type == 'message':
    for i in downRange(3, 1, 1):
        await _blk.reply(str(i))
""",
    )
    result2 = asyncio.run(run_sim(program2, message="x"))
    assert result2["error"] == ""
    assert result2["replies"] == ["3", "2", "1"]


def test_blockly_for_loop_shortcircuit_expression():
    """Blockly for 循环生成器输出的短路表达式可执行（回归：blockly_program.json）。"""
    program = BlocklyProgram(
        code="""
if _blk.event_type == 'message':
    n = 3
    for i in (1 <= n) and upRange(1, n, 1) or downRange(1, n, 1):
        await _blk.reply(str(i))
""",
    )
    result = asyncio.run(run_sim(program, message="x"))
    assert result["error"] == ""
    assert result["replies"] == ["1", "2", "3"]


def test_generated_code_with_blockly_definitions():
    """前端修复后生成的 code 含 upRange/downRange 定义，可编译执行。"""
    code = (
        "def upRange(start, stop, step):\n"
        "  while start <= stop:\n"
        "    yield start\n"
        "    start += abs(step)\n"
        "\n"
        "def downRange(start, stop, step):\n"
        "  while start >= stop:\n"
        "    yield start\n"
        "    start -= abs(step)\n"
        "\n"
        "if _blk.event_type == 'message':\n"
        "    for i in (1 <= 3) and upRange(1, 3, 1) or downRange(1, 3, 1):\n"
        "        await _blk.reply(str(i))\n"
    )
    source = wrap_code(code)
    _assert_safe_source(source)
    compile(source, "<test>", "exec")
    program = BlocklyProgram(code=code)
    result = asyncio.run(run_sim(program, message="x"))
    assert result["error"] == ""
    assert result["replies"] == ["1", "2", "3"]
