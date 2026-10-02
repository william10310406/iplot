"""唯一碰 macOS 的地方。全部用 subprocess.run 傳清單，不拼字串；換作業系統只換這個檔。"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def open(path: Path) -> None:
    """用 macOS 的 open 打開：資料夾進 Finder，檔案用預設程式。"""
    subprocess.run(["open", str(path)], check=False)


def edit(path: Path, editor: tuple[str, ...] | None, line: int | None = None) -> None:
    """用編輯器打開檔案；editor 是 None 時用系統預設文字編輯器。資料夾一律交給 open。"""
    if path.is_dir():
        return open(path)
    argv = ["open", "-t", str(path)] if editor is None else [
        p.format(file=str(path), line=line or 1) for p in editor]
    subprocess.run(argv, check=False)


def reveal(path: Path) -> None:
    """在 Finder 裡顯示並選取。"""
    subprocess.run(["open", "-R", str(path)], check=False)


def terminal(path: Path) -> None:
    """在 Terminal 打開這個資料夾。"""
    subprocess.run(["open", "-a", "Terminal", str(path)], check=False)


def trash(path: Path, trash_dir: Path | None = None) -> Path:
    """搬到垃圾桶（同名就加「 2」「 3」…），回傳搬到哪裡。永遠不刪除。"""
    folder = trash_dir or Path.home() / ".Trash"
    dest, n = folder / path.name, 1
    while dest.exists():
        n += 1
        dest = folder / f"{path.name} {n}"
    shutil.move(str(path), str(dest))
    return dest
