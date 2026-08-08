"""Blocky 程序文件管理器的单元测试。"""

import asyncio

from blocky.manager import BlockyManager


def test_create_and_get(tmp_path):
    manager = BlockyManager(tmp_path)
    program = asyncio.run(manager.create(name="测试程序"))
    assert manager.get(program.id) is not None
    assert program.enabled is False
    assert program.name == "测试程序"


def test_update_persists(tmp_path):
    manager = BlockyManager(tmp_path)
    program = asyncio.run(manager.create(name="旧名字"))
    program.name = "新名字"
    program.enabled = True
    asyncio.run(manager.update(program))
    assert manager.get(program.id).name == "新名字"
    assert manager.get(program.id).enabled is True


def test_delete(tmp_path):
    manager = BlockyManager(tmp_path)
    program = asyncio.run(manager.create(name="待删除"))
    assert asyncio.run(manager.delete(program.id)) is True
    assert manager.get(program.id) is None
    assert asyncio.run(manager.delete(program.id)) is False


def test_duplicate(tmp_path):
    manager = BlockyManager(tmp_path)
    program = asyncio.run(manager.create(name="原始", content_type="python"))
    clone = asyncio.run(manager.duplicate(program.id))
    assert clone is not None
    assert clone.id != program.id
    assert clone.name == "原始 (副本)"
    assert clone.enabled is False
    assert clone.content_type == "python"


def test_create_avoids_duplicate_names(tmp_path):
    manager = BlockyManager(tmp_path)
    first = asyncio.run(manager.create(name="同名"))
    second = asyncio.run(manager.create(name="同名"))
    third = asyncio.run(manager.create(name="同名"))
    assert first.name == "同名"
    assert second.name == "同名 (2)"
    assert third.name == "同名 (3)"


def test_unique_name_appends_suffix(tmp_path):
    manager = BlockyManager(tmp_path)
    asyncio.run(manager.create(name="去重"))
    assert manager.unique_name("去重") == "去重 (2)"
    assert manager.unique_name("去重") == "去重 (2)"
    assert manager.unique_name("全新名称") == "全新名称"
    assert manager.unique_name("  ") == "未命名程序"


def test_duplicate_missing(tmp_path):
    manager = BlockyManager(tmp_path)
    assert asyncio.run(manager.duplicate("no-such-id")) is None


def test_persistence_across_instances(tmp_path):
    manager = BlockyManager(tmp_path)
    program = asyncio.run(
        manager.create(name="持久化测试", code="await _blk.reply('hi')")
    )
    assert manager.get(program.id) is not None

    manager2 = BlockyManager(tmp_path)
    loaded = manager2.get(program.id)
    assert loaded is not None
    assert loaded.name == "持久化测试"
    assert loaded.code == "await _blk.reply('hi')"


def test_ignores_corrupt_files(tmp_path):
    (tmp_path / "programs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "programs" / "corrupt.json").write_text(
        "{ not valid json", encoding="utf-8"
    )
    manager = BlockyManager(tmp_path)
    assert manager.get("corrupt") is None
    assert manager.list_programs() == []


def test_list_sorted_by_priority(tmp_path):
    manager = BlockyManager(tmp_path)
    low = asyncio.run(manager.create(name="低优先级"))
    high = asyncio.run(manager.create(name="高优先级"))
    low.priority = 1
    high.priority = 99
    asyncio.run(manager.update(low))
    asyncio.run(manager.update(high))
    programs = manager.list_programs()
    assert programs[0].name == "高优先级"
    assert programs[1].name == "低优先级"
