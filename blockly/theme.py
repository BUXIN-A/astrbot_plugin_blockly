"""主题管理器。

每个自定义主题对应 ``themes/<id>/`` 目录，主题 zip 解压出的全部文件即该主题的
文件树（其中 ``theme.css`` 为主样式、``theme_name.txt`` 为主题名）。内置主题
``default`` / ``dark`` 不占用目录，其内容（默认样式）由 ``default_theme_css``
提供，支持导出为 zip 便于复制修改。
"""

from __future__ import annotations

import io
import shutil
import zipfile
from pathlib import Path
from typing import Any

from .program import new_id

# 内置主题（不占用磁盘目录）
BUILTIN_THEMES = ("default", "dark")
# 内置主题的显示名
BUILTIN_THEME_NAMES = {"default": "默认主题", "dark": "深色主题"}
# 激活状态文件名
ACTIVE_FILE = "active.txt"
# 主题名文件名
NAME_FILE = "theme_name.txt"
# 主样式文件名
MAIN_CSS = "theme.css"
# 新建主题的默认名称（重名时自动追加序号）
DEFAULT_THEME_NAME = "新主题"


def _safe_zip_path(name: str) -> str:
    """把 zip 条目名规范化为安全相对路径（剔除 .. 与绝对路径段）。"""
    name = str(name or "").replace("\\", "/")
    parts = [p for p in name.split("/") if p and p not in (".", "..")]
    return "/".join(parts)


def _safe_join(base: Path, rel: str) -> Path | None:
    """把相对路径解析到 base 下，越界（如 ../）时返回 None。"""
    rel = str(rel or "").replace("\\", "/")
    target = (base / rel).resolve()
    if not target.is_relative_to(base.resolve()):
        return None
    return target


def default_theme_css() -> str:
    """返回默认主题样式内容（Blockly 编辑器的 ``pages/blockly/style.css``）。"""
    try:
        return _default_theme_files().get(MAIN_CSS, "").decode("utf-8")
    except UnicodeDecodeError:
        return ""


def _default_theme_files() -> dict[str, bytes]:
    """收集默认主题资源：theme.css（编辑器样式）+ img/ 目录全部图标。

    内置主题（default/dark）导出与「新增主题」都使用这一份内容，保证新建
    主题与内置主题是完整可编辑的起点（样式 + UI 图标）。
    """
    files: dict[str, bytes] = {}
    root = Path(__file__).resolve().parent.parent / "pages" / "blockly"
    css_path = root / "style.css"
    try:
        if css_path.is_file():
            files[MAIN_CSS] = css_path.read_bytes()
    except OSError:
        pass
    img_dir = root / "img"
    try:
        if img_dir.is_dir():
            for f in sorted(img_dir.iterdir()):
                if f.is_file():
                    files[f"img/{f.name}"] = f.read_bytes()
    except OSError:
        pass
    return files


class ThemeStore:
    """多主题存储与文件树管理。"""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    # ---------- 激活状态 ----------
    def get_active(self) -> str:
        """返回当前激活主题（default / dark / 自定义主题 id）。"""
        try:
            active = (self.root / ACTIVE_FILE).read_text(encoding="utf-8").strip()
        except OSError:
            active = ""
        if active in BUILTIN_THEMES or (active and (self.root / active).is_dir()):
            return active
        return "default"

    def set_active(self, tid: str) -> None:
        tid = str(tid or "").strip()
        if tid in BUILTIN_THEMES or (tid and (self.root / tid).is_dir()):
            (self.root / ACTIVE_FILE).write_text(tid, encoding="utf-8")

    def active_is_custom(self) -> bool:
        active = self.get_active()
        return bool(active) and active not in BUILTIN_THEMES

    # ---------- 主题列表 ----------
    def list_custom(self) -> list[dict[str, Any]]:
        """返回全部自定义主题：{id, name, files: [{path, size}]}。"""
        themes: list[dict[str, Any]] = []
        for d in sorted(self.root.iterdir()):
            if not d.is_dir() or d.name.startswith("."):
                continue
            name = d.name
            name_file = d / NAME_FILE
            try:
                if name_file.exists():
                    name = name_file.read_text(encoding="utf-8").strip() or name
            except OSError:
                pass
            themes.append({"id": d.name, "name": name, "files": self._list_files(d)})
        return themes

    @staticmethod
    def _list_files(d: Path) -> list[dict[str, Any]]:
        """列出目录下全部文件的相对路径与大小。"""
        files: list[dict[str, Any]] = []
        for p in sorted(d.rglob("*")):
            if not p.is_file():
                continue
            try:
                rel = p.relative_to(d).as_posix()
            except ValueError:
                continue
            try:
                size = p.stat().st_size
            except OSError:
                size = 0
            files.append({"path": rel, "size": size})
        return files

    def main_css(self, tid: str) -> str:
        """读取主题的主样式（theme.css）内容；缺失时返回空字符串。"""
        content = self.read_file(tid, MAIN_CSS)
        return content or ""

    # ---------- 导入 / 删除 ----------
    def import_zip(self, raw: bytes) -> dict[str, Any]:
        """把主题 zip 解压为新的自定义主题目录，返回 {id, name, files}。"""
        tid = new_id()
        target = self.root / tid
        target.mkdir(parents=True, exist_ok=True)
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as zf:
                for info in zf.infolist():
                    if info.is_dir():
                        continue
                    rel = _safe_zip_path(info.filename)
                    if not rel:
                        continue
                    dest = _safe_join(target, rel)
                    if dest is None:
                        continue
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(zf.read(info))
            # 主题名：优先 theme_name.txt，否则默认
            name = ""
            name_file = target / NAME_FILE
            try:
                if name_file.exists():
                    name = name_file.read_text(encoding="utf-8").strip()
            except OSError:
                pass
            if not name:
                name = "自定义主题"
                name_file.write_text(name, encoding="utf-8")
            # 确保存在主样式 theme.css：没有时用包内任一 css 充当
            if not (target / MAIN_CSS).exists():
                css_file = next(
                    (
                        f["path"]
                        for f in self._list_files(target)
                        if f["path"].lower().endswith(".css")
                    ),
                    None,
                )
                if css_file:
                    shutil.copyfile(target / css_file, target / MAIN_CSS)
        except Exception:
            shutil.rmtree(target, ignore_errors=True)
            raise
        return {"id": tid, "name": name, "files": self._list_files(target)}

    def delete(self, tid: str) -> bool:
        """删除自定义主题目录；删除的是激活主题时重置为默认。"""
        tid = str(tid or "").strip()
        if not tid or tid in BUILTIN_THEMES:
            return False
        target = self.root / tid
        if not target.is_dir() or target.parent.resolve() != self.root.resolve():
            return False
        shutil.rmtree(target)
        if self.get_active() == tid:
            self.set_active("default")
        return True

    def create(self, name: str = "") -> dict[str, Any]:
        """新建自定义主题：内容为默认主题样式与 UI 图标，返回 {id, name, files}。

        名称缺省或为空时使用「新主题」，与已有主题重名时自动追加序号。
        """
        tid = new_id()
        target = self.root / tid
        target.mkdir(parents=True, exist_ok=True)
        name = self._unique_theme_name(str(name or "").strip() or DEFAULT_THEME_NAME)
        try:
            (target / NAME_FILE).write_text(name, encoding="utf-8")
            for rel, data in _default_theme_files().items():
                dest = _safe_join(target, rel)
                if dest is None:
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(data)
        except Exception:
            shutil.rmtree(target, ignore_errors=True)
            raise
        return {"id": tid, "name": name, "files": self._list_files(target)}

    def _unique_theme_name(self, base: str) -> str:
        """在已有自定义主题名中去重：base、base (2)、base (3)…"""
        existing = {t["name"] for t in self.list_custom()}
        if base not in existing:
            return base
        index = 2
        while f"{base} ({index})" in existing:
            index += 1
        return f"{base} ({index})"

    def export_zip(self, tid: str) -> bytes | None:
        """把主题（内置或自定义）打包为 zip 字节。

        内置主题内容为默认样式（theme.css + theme_name.txt）；自定义主题为
        目录全部文件；主题不存在或路径非法时返回 None。
        """
        tid = str(tid or "").strip()
        if not tid:
            return None
        if tid in BUILTIN_THEMES:
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.writestr(NAME_FILE, BUILTIN_THEME_NAMES.get(tid, tid))
                for rel, data in _default_theme_files().items():
                    zf.writestr(rel, data)
            return buf.getvalue()
        theme_dir = self._theme_dir(tid)
        if theme_dir is None:
            return None
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in theme_dir.rglob("*"):
                if f.is_file():
                    zf.write(f, f.relative_to(theme_dir).as_posix())
        return buf.getvalue()

    # ---------- 文件树读写 ----------
    def _theme_dir(self, tid: str) -> Path | None:
        tid = str(tid or "").strip()
        if not tid or tid in BUILTIN_THEMES:
            return None
        target = self.root / tid
        if target.parent.resolve() != self.root.resolve() or not target.is_dir():
            return None
        return target

    def read_file(self, tid: str, rel_path: str) -> str | None:
        """读取主题内文件文本；路径越界或文件不存在时返回 None。

        二进制文件（无法按 UTF-8 解码）也返回 None，调用方可用
        :meth:`read_file_bytes` 读取原始字节。
        """
        target = self._theme_dir(tid)
        if target is None:
            return None
        path = _safe_join(target, rel_path)
        if path is None or not path.is_file():
            return None
        try:
            return path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None

    def read_file_bytes(self, tid: str, rel_path: str) -> bytes | None:
        """读取主题内文件原始字节；路径越界或文件不存在时返回 None。"""
        target = self._theme_dir(tid)
        if target is None:
            return None
        path = _safe_join(target, rel_path)
        if path is None or not path.is_file():
            return None
        try:
            return path.read_bytes()
        except OSError:
            return None

    def write_file(self, tid: str, rel_path: str, content: str) -> bool:
        """写主题内文件文本；路径越界时拒绝并返回 False。"""
        target = self._theme_dir(tid)
        if target is None:
            return False
        path = _safe_join(target, rel_path)
        if path is None:
            return False
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(str(content or ""), encoding="utf-8")
            return True
        except OSError:
            return False

    def write_file_bytes(self, tid: str, rel_path: str, data: bytes) -> bool:
        """写主题内文件原始字节；路径越界时拒绝并返回 False。"""
        target = self._theme_dir(tid)
        if target is None:
            return False
        path = _safe_join(target, rel_path)
        if path is None:
            return False
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            return True
        except OSError:
            return False
