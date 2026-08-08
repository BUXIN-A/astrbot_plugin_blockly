"""Blocky 程序文件管理器。

程序以 JSON 文件形式持久化在 ``data/plugin_data/astrbot_plugin_blocky/programs/<id>.json``。
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from .program import BlockyProgram, new_id

logger = logging.getLogger("astrbot_plugin_blocky")


class BlockyManager:
    def __init__(self, data_dir: str | Path) -> None:
        self.programs_dir = Path(data_dir) / "programs"
        self.programs_dir.mkdir(parents=True, exist_ok=True)
        self._programs: dict[str, BlockyProgram] = {}
        self._lock = asyncio.Lock()
        self.load()

    # ---------- 生命周期 ----------
    def load(self) -> None:
        """从磁盘加载全部程序。"""
        self._programs.clear()
        for path in sorted(self.programs_dir.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                program = BlockyProgram.from_dict(data)
                self._programs[program.id] = program
            except Exception as exc:  # noqa: BLE001
                logger.warning("跳过损坏的程序文件 %s: %s", path, exc)

    def _path(self, pid: str) -> Path:
        return self.programs_dir / f"{pid}.json"

    async def _save(self, program: BlockyProgram) -> None:
        path = self._path(program.id)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(program.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.replace(path)

    # ---------- 查询 ----------
    def get(self, pid: str) -> BlockyProgram | None:
        return self._programs.get(pid)

    def list_programs(self) -> list[BlockyProgram]:
        programs = list(self._programs.values())
        programs.sort(key=lambda p: (-p.priority, p.created_at))
        return programs

    def enabled_programs(self) -> list[BlockyProgram]:
        programs = [p for p in self._programs.values() if p.enabled]
        programs.sort(key=lambda p: (-p.priority, p.created_at))
        return programs

    # ---------- 增删改 ----------
    def _unique_name(self, name: str) -> str:
        """若名称已存在，则追加序号（如「xx (2)」）以避免重名。"""
        name = (name or "").strip() or "未命名程序"
        used = {p.name for p in self._programs.values()}
        if name not in used:
            return name
        i = 2
        while f"{name} ({i})" in used:
            i += 1
        return f"{name} ({i})"

    async def create(
        self,
        name: str,
        content_type: str = "blockly",
        workspace: str = "",
        code: str = "",
    ) -> BlockyProgram:
        async with self._lock:
            program = BlockyProgram(
                name=self._unique_name(name),
                content_type=content_type,
                workspace=workspace,
                code=code,
            )
            self._programs[program.id] = program
            await self._save(program)
            return program

    async def update(self, program: BlockyProgram) -> None:
        async with self._lock:
            self._programs[program.id] = program
            await self._save(program)

    async def delete(self, pid: str) -> bool:
        async with self._lock:
            program = self._programs.pop(pid, None)
            if program is None:
                return False
            path = self._path(pid)
            if path.exists():
                path.unlink()
            return True

    async def duplicate(self, pid: str) -> BlockyProgram | None:
        async with self._lock:
            src = self._programs.get(pid)
            if src is None:
                return None
            clone = BlockyProgram.from_dict(src.to_dict())
            clone.id = new_id()
            clone.name = f"{src.name} (副本)"
            clone.enabled = False
            clone.created_at = clone.updated_at = _now()
            self._programs[clone.id] = clone
            await self._save(clone)
            return clone


def _now() -> float:
    import time

    return time.time()
