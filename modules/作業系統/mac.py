"""macOS：全部用 open 指令；垃圾桶是 ~/.Trash。"""
import shutil
import subprocess
from pathlib import Path

NAME = "macOS"


def _launch(argv, **kw):
    """啟動後不等。"""
    subprocess.Popen(argv, **kw)


def open(app, path):
    """資料夾進 Finder，檔案用預設程式。"""
    _launch(["open", str(path)])


def edit(app, path, editor, line):
    """editor 是 None 時用系統預設文字編輯器，否則照 config.py 的 EDITOR；資料夾一律交給 open。"""
    if Path(path).is_dir():
        return open(app, path)
    _launch(["open", "-t", str(path)] if editor is None
            else [p.format(file=str(path), line=line or 1) for p in editor])


def reveal(app, path):
    """在 Finder 裡顯示並選取。"""
    _launch(["open", "-R", str(path)])


def terminal(app, path):
    """在 Terminal 打開這個資料夾。想換成別的終端機程式，改 "Terminal" 這個名字。"""
    _launch(["open", "-a", "Terminal", str(path)])


def trash(app, path):
    """搬到 ~/.Trash（同名就加「 2」「 3」…），回傳搬到哪裡。永遠不刪除。"""
    folder, name = Path.home() / ".Trash", Path(path).name
    folder.mkdir(exist_ok=True)
    dest, n = folder / name, 1
    while dest.exists():
        n += 1
        dest = folder / f"{name} {n}"
    shutil.move(str(path), str(dest))
    return dest
